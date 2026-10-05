from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Analysis


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
