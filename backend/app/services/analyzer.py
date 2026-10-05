import logging
from dataclasses import dataclass

from pydantic import ValidationError

from app.schemas.ai_output import AIAnalysisResult
from app.schemas.analysis import FailureCategory, Severity
from app.services import ai_service
from app.services.ai_service import AIInvalidResponseError
from app.utils.ai_output import extract_json_object, verify_evidence

logger = logging.getLogger("deploydoctor.analyzer")

MAX_ATTEMPTS = 2  # first try + one corrective retry
FALLBACK_MODEL = "fallback"


@dataclass
class AnalysisOutcome:
    result: AIAnalysisResult
    model: str
    degraded: bool
    attempts: int


def _fallback_result() -> AIAnalysisResult:
    return AIAnalysisResult(
        summary="Automatic analysis could not be completed for this log.",
        severity=Severity.MEDIUM,
        root_cause=(
            "The AI service returned an answer that could not be validated, so no "
            "diagnosis is available. This does not mean the deployment is healthy."
        ),
        affected_component="Unknown",
        evidence=[],
        recommended_fix=[
            "Run the analysis again.",
            "If it keeps failing, paste a shorter excerpt that includes the first "
            "error and the lines just before it.",
            "Select the most specific failure category.",
        ],
        commands=[],
        prevention=[],
        devops_insight=None,
        confidence=0.0,
    )


def _describe_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = [
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in exc.errors()[:5]
        ]
        return "; ".join(parts)
    return str(exc)[:300]


def analyze_log(log_text: str, category: FailureCategory) -> AnalysisOutcome:
    """Ask the model, validate its answer, retry once if invalid, else fall back.

    Provider failures (timeout, rate limit, auth, outage) are NOT retried or hidden:
    they propagate as AIServiceError subclasses.
    """
    messages = ai_service.build_messages(log_text, category)
    raw_content: str | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = ai_service.request_completion(
                messages, temperature=0.1 if attempt == 1 else 0.0
            )
            raw_content = raw.content
            result = AIAnalysisResult.model_validate(extract_json_object(raw.content))
        except (AIInvalidResponseError, ValueError) as exc:  # ValidationError is a ValueError
            problems = _describe_error(exc)
            logger.warning(
                "AI output invalid (attempt %s/%s): %s", attempt, MAX_ATTEMPTS, problems
            )
            if attempt < MAX_ATTEMPTS:
                messages = ai_service.build_messages(log_text, category)
                if raw_content:
                    messages.append({"role": "assistant", "content": raw_content[:6000]})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your previous reply could not be used ({problems}). "
                            "Reply again with ONE valid JSON object using exactly the "
                            "required keys. Output JSON only."
                        ),
                    }
                )
            continue

        # Enforce "never invent evidence": keep only lines that exist in the log
        kept, dropped = verify_evidence(result.evidence, log_text)
        if dropped:
            logger.warning("Dropped %s unverifiable evidence item(s)", dropped)
            result.evidence = kept
            if not kept:
                result.confidence = min(result.confidence, 0.4)

        return AnalysisOutcome(
            result=result, model=raw.model, degraded=False, attempts=attempt
        )

    logger.error("AI output invalid after %s attempts; using fallback result", MAX_ATTEMPTS)
    return AnalysisOutcome(
        result=_fallback_result(),
        model=FALLBACK_MODEL,
        degraded=True,
        attempts=MAX_ATTEMPTS,
    )
