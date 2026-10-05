import logging
import time
from dataclasses import dataclass
from functools import lru_cache

import groq
from groq import Groq

from app.config import get_settings
from app.schemas.analysis import FailureCategory
from app.services.prompts import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger("deploydoctor.ai")

REASONING_EFFORT = "low"  # low | medium | high (gpt-oss models only)
MAX_OUTPUT_TOKENS = 4096  # includes reasoning tokens for gpt-oss


# ---------- Errors ----------
class AIServiceError(Exception):
    """Base class. `user_message` is safe to show to end users."""

    http_status = 502
    user_message = "The AI service failed to analyze this log. Please try again."

    def __init__(self, detail: str = ""):
        super().__init__(detail or self.user_message)


class AIConfigError(AIServiceError):
    http_status = 503
    user_message = "The AI service is not configured correctly. Contact the administrator."


class AITimeoutError(AIServiceError):
    http_status = 504
    user_message = "The AI service took too long to respond. Please try again."


class AIRateLimitError(AIServiceError):
    http_status = 429
    user_message = "The AI service is busy right now. Please wait a moment and retry."


class AIUnavailableError(AIServiceError):
    http_status = 502
    user_message = "The AI service is temporarily unavailable. Please try again."


class AIInvalidResponseError(AIServiceError):
    http_status = 502
    user_message = "The AI returned an unreadable answer. Please try again."


# ---------- Client ----------
@lru_cache
def get_client() -> Groq:
    settings = get_settings()
    if not settings.groq_configured:
        raise AIConfigError("GROQ_API_KEY is not set")
    return Groq(
        api_key=settings.groq_api_key,
        timeout=float(settings.ai_timeout_seconds),
        max_retries=1,  # one automatic retry for transient network errors
    )


@dataclass
class RawCompletion:
    content: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    duration_ms: float


def build_messages(log_text: str, category: FailureCategory) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(log_text, category)},
    ]


def request_completion(
    messages: list[dict[str, str]], temperature: float = 0.1
) -> RawCompletion:
    """One call to Groq in JSON mode. Raises an AIServiceError subclass on failure."""
    settings = get_settings()
    client = get_client()

    extra_body: dict[str, str] = {}
    if settings.groq_model.startswith("openai/gpt-oss"):
        extra_body["reasoning_effort"] = REASONING_EFFORT

    start = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            temperature=temperature,
            max_tokens=MAX_OUTPUT_TOKENS,
            response_format={"type": "json_object"},
            extra_body=extra_body or None,
        )
    except groq.APITimeoutError as exc:  # must come before APIConnectionError
        logger.error("Groq timeout after %ss", settings.ai_timeout_seconds)
        raise AITimeoutError() from exc
    except groq.APIConnectionError as exc:
        logger.error("Groq connection error: %s", type(exc).__name__)
        raise AIUnavailableError() from exc
    except groq.RateLimitError as exc:
        logger.warning("Groq rate limit hit")
        raise AIRateLimitError() from exc
    except (groq.AuthenticationError, groq.PermissionDeniedError) as exc:
        logger.error("Groq rejected the API key (status %s)", exc.status_code)
        raise AIConfigError("Groq rejected the API key") from exc
    except groq.NotFoundError as exc:
        logger.error("Groq model not found: %s", settings.groq_model)
        raise AIConfigError(f"Model not found: {settings.groq_model}") from exc
    except groq.BadRequestError as exc:
        text = str(exc).lower()
        if "model_decommissioned" in text or "model_not_found" in text:
            logger.error("Groq model unavailable: %s", settings.groq_model)
            raise AIConfigError(f"Model unavailable: {settings.groq_model}") from exc
        if "json_validate_failed" in text:
            logger.warning("Groq could not produce valid JSON")
            raise AIInvalidResponseError() from exc
        logger.error("Groq rejected the request (400)")
        raise AIServiceError("Groq rejected the request") from exc
    except groq.APIStatusError as exc:
        logger.error("Groq API error: status %s", exc.status_code)
        raise AIUnavailableError(f"Groq status {exc.status_code}") from exc

    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    content = (response.choices[0].message.content or "").strip()
    usage = response.usage

    logger.info(
        "Groq completion ok | model=%s | %sms | prompt_tokens=%s | completion_tokens=%s",
        settings.groq_model,
        duration_ms,
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
    )

    if not content:
        raise AIInvalidResponseError("Empty response from model")

    return RawCompletion(
        content=content,
        model=settings.groq_model,
        prompt_tokens=getattr(usage, "prompt_tokens", None),
        completion_tokens=getattr(usage, "completion_tokens", None),
        duration_ms=duration_ms,
    )


def request_analysis(log_text: str, category: FailureCategory) -> RawCompletion:
    """Build the prompts and ask the model. Parsing and validation come in Phase 8."""
    return request_completion(build_messages(log_text, category))
