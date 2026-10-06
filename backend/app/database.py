import logging
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings

logger = logging.getLogger("deploydoctor.database")


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def _engine_options(url: str) -> dict:
    if url.startswith("sqlite"):
        # Automated tests only: one shared in-memory connection
        return {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    return {
        "pool_pre_ping": True,  # drop dead connections instead of failing requests
        "pool_size": 5,
        "max_overflow": 5,
        "connect_args": {"connect_timeout": 5},
    }


def _build_engine():
    url = get_settings().effective_database_url
    if not url:
        raise RuntimeError(
            "No database configured. Set DATABASE_URL (development) "
            "or attach RDS on Elastic Beanstalk (RDS_* variables)."
        )
    return create_engine(url, **_engine_options(url))


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database() -> bool:
    """Return True if the database answers a trivial query."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        # Log the error type only: the message can contain connection details
        logger.error("Database check failed: %s", type(exc).__name__)
        return False
