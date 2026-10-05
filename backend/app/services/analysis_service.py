import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Analysis
from app.schemas.analysis import FailureCategory
from app.services import analyzer

logger = logging.getLogger("deploydoctor.analysis")


def list_analyses(
    db: Session, session_id: str, limit: int, offset: int
) -> tuple[list[Analysis], int]:
    """Newest first, for one session only. Returns (rows, total)."""
    total = db.scalar(
        select(func.count()).select_from(Analysis).where(Analysis.session_id == session_id)
    )
    rows = db.scalars(
        select(Analysis)
        .where(Analysis.session_id == session_id)
        .order_by(Analysis.created_at.desc(), Analysis.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total or 0


def get_analysis(db: Session, session_id: str, analysis_id: int) -> Analysis | None:
    return db.scalar(
        select(Analysis).where(
            Analysis.id == analysis_id, Analysis.session_id == session_id
        )
    )


def delete_analysis(db: Session, session_id: str, analysis_id: int) -> bool:
    row = get_analysis(db, session_id, analysis_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def create_analysis(
    db: Session, session_id: str, log_text: str, category: FailureCategory
) -> tuple[Analysis, bool]:
    """Run the AI analysis, then save it. Returns (row, degraded).

    The AI call happens BEFORE any database query, so no DB connection is held
    while waiting for Groq.
    """
    outcome = analyzer.analyze_log(log_text, category)
    r = outcome.result

    row = Analysis(
        session_id=session_id,
        log_input=log_text,
        category=category.value,
        summary=r.summary,
        severity=r.severity.value,
        root_cause=r.root_cause,
        affected_component=r.affected_component,
        evidence=r.evidence,
        recommended_fix=r.recommended_fix,
        commands=r.commands,
        prevention=r.prevention,
        devops_insight=r.devops_insight,
        confidence=r.confidence,
        ai_model=outcome.model,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    logger.info(
        "Analysis saved | id=%s | category=%s | severity=%s | confidence=%.2f "
        "| attempts=%s | degraded=%s",
        row.id,
        row.category,
        row.severity,
        row.confidence,
        outcome.attempts,
        outcome.degraded,
    )
    return row, outcome.degraded
