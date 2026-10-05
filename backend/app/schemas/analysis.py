from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import get_settings
from app.utils.sanitize import sanitize_log_text


class FailureCategory(str, Enum):
    DOCKER = "Docker"
    KUBERNETES = "Kubernetes"
    CICD = "CI/CD"
    LINUX = "Linux"
    AWS = "AWS"
    TERRAFORM = "Terraform"
    APPLICATION = "Application"
    DATABASE = "Database"
    NETWORKING = "Networking"
    UNKNOWN = "Unknown"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AnalyzeRequest(BaseModel):
    """Body of POST /api/analyze (the route itself is added in Phase 8)."""

    log_text: str = Field(
        description="Raw deployment or application log text to analyze.",
        examples=["Back-off restarting failed container api in pod api-7d9f..."],
    )
    category: FailureCategory = Field(
        default=FailureCategory.UNKNOWN,
        description="Failure category; the AI reasons specifically about it.",
    )

    @field_validator("log_text")
    @classmethod
    def validate_log_text(cls, value: str) -> str:
        value = sanitize_log_text(value)
        if not value:
            raise ValueError("Log text must not be empty")
        limit = get_settings().max_log_chars
        if len(value) > limit:
            raise ValueError(f"Log text exceeds the {limit} character limit")
        return value


class AnalysisSummary(BaseModel):
    """Compact form used in the history list."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    category: FailureCategory
    severity: Severity
    summary: str
    confidence: float = Field(ge=0, le=1)
    created_at: datetime


class AnalysisOut(AnalysisSummary):
    """Full analysis returned by the detail endpoint."""

    log_input: str
    root_cause: str
    affected_component: str
    evidence: list[str]
    recommended_fix: list[str]
    commands: list[str]
    prevention: list[str]
    devops_insight: str | None = None
    ai_model: str | None = None


class AnalysisListResponse(BaseModel):
    items: list[AnalysisSummary]
    total: int
    limit: int
    offset: int


class UploadResponse(BaseModel):
    filename: str
    size_bytes: int
    characters: int
    text: str


class AnalyzeResponse(AnalysisOut):
    """Returned by POST /api/analyze."""

    degraded: bool = Field(
        default=False,
        description=(
            "True when the AI answer could not be validated and a low-confidence "
            "fallback result was returned instead."
        ),
    )

    redactions: int = Field(
        default=0,
        ge=0,
        description=(
            "How many sensitive values (keys, tokens, passwords) were masked in the "
            "log before it was analyzed and saved."
        ),
    )
