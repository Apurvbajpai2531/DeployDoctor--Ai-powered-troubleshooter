from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Analysis(Base):
    """One AI diagnosis of a deployment/application log."""

    __tablename__ = "analyses"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_analyses_severity",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_analyses_confidence",
        ),
        # History query: "this session's analyses, newest first"
        Index("ix_analyses_session_created", "session_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Anonymous per-browser identifier (sent in the X-Session-ID header)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # Input (secrets are redacted before this is saved, see Phase 13)
    log_input: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)

    # AI output
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    affected_component: Mapped[str] = mapped_column(String(255), nullable=False)
    evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    recommended_fix: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    commands: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    prevention: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    devops_insight: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Metadata
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Analysis id={self.id} category={self.category} severity={self.severity}>"
