from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.schemas.analysis import Severity

# field name -> (max characters per item, max number of items)
LIST_LIMITS: dict[str, tuple[int, int]] = {
    "evidence": (500, 8),
    "recommended_fix": (600, 10),
    "commands": (500, 12),
    "prevention": (500, 8),
}


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _as_text(value: Any) -> str:
    if isinstance(value, Enum):  # str(Severity.HIGH) is "Severity.HIGH" on Python 3.12
        value = value.value
    return "" if value is None else str(value)


class AIAnalysisResult(BaseModel):
    """The structured diagnosis the model must return.

    Lenient about formatting (case, percent signs, strings instead of lists, over-long
    text) and strict about substance (required fields, valid severity, 0..1 confidence).
    """

    model_config = ConfigDict(extra="ignore")

    summary: str = Field(min_length=1)
    severity: Severity
    root_cause: str = Field(min_length=1)
    affected_component: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    recommended_fix: list[str] = Field(min_length=1)
    commands: list[str] = Field(default_factory=list)
    prevention: list[str] = Field(default_factory=list)
    devops_insight: str | None = None
    confidence: float = Field(ge=0, le=1)

    @field_validator("summary", mode="before")
    @classmethod
    def _clip_summary(cls, v: Any) -> str:
        return _clip(_as_text(v), 2000)

    @field_validator("root_cause", mode="before")
    @classmethod
    def _clip_root_cause(cls, v: Any) -> str:
        return _clip(_as_text(v), 4000)

    @field_validator("affected_component", mode="before")
    @classmethod
    def _clip_component(cls, v: Any) -> str:
        return _clip(_as_text(v), 255)  # matches the database column length

    @field_validator("devops_insight", mode="before")
    @classmethod
    def _clip_insight(cls, v: Any) -> str | None:
        text = _clip(_as_text(v), 2000)
        return text or None

    @field_validator("severity", mode="before")
    @classmethod
    def _normalize_severity(cls, v: Any) -> str:
        text = _as_text(v).strip().upper()
        if "|" in text:
            raise ValueError("severity must be a single value, not a list of options")
        return text

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalize_confidence(cls, v: Any) -> float:
        if isinstance(v, bool):
            raise ValueError("confidence must be a number")
        if isinstance(v, str):
            raw = v.strip()
            try:
                number = float(raw.rstrip("%"))
            except ValueError as exc:
                raise ValueError("confidence must be a number") from exc
            v = number / 100 if raw.endswith("%") else number
        if isinstance(v, (int, float)) and 1 < v <= 100:
            v = v / 100  # the model answered "92" instead of 0.92
        return v

    @field_validator(
        "evidence", "recommended_fix", "commands", "prevention", mode="before"
    )
    @classmethod
    def _normalize_list(cls, v: Any, info: ValidationInfo) -> list[str]:
        item_limit, max_items = LIST_LIMITS[info.field_name]
        if v is None:
            return []
        if not isinstance(v, (list, tuple)):
            v = [v]
        items = [_clip(_as_text(item), item_limit) for item in v]
        return [item for item in items if item][:max_items]
