import os

import pytest

# ---------------------------------------------------------------------------
# Environment: must be set BEFORE the app is imported, so a developer's .env
# file can never change how the tests behave.
# ---------------------------------------------------------------------------
_test_db = os.environ.get("TEST_DATABASE_URL", "sqlite://")
if not _test_db.startswith("sqlite"):
    _db_name = _test_db.rsplit("/", 1)[-1].split("?")[0]
    if not _db_name.endswith("_test"):
        raise pytest.UsageError(
            "TEST_DATABASE_URL must point at a database whose name ends with '_test' "
            "(the test run creates and DROPS all tables)."
        )

for _var in ("RDS_HOSTNAME", "RDS_PORT", "RDS_DB_NAME", "RDS_USERNAME", "RDS_PASSWORD"):
    os.environ.pop(_var, None)

os.environ.update(
    {
        "ENVIRONMENT": "test",
        "LOG_LEVEL": "WARNING",
        "DATABASE_URL": _test_db,
        "GROQ_API_KEY": "test-key-not-real",
        "GROQ_MODEL": "openai/gpt-oss-120b",
        "AI_TIMEOUT_SECONDS": "5",
        "MAX_LOG_CHARS": "50000",
        "MAX_UPLOAD_BYTES": "1048576",
        "MAX_REQUEST_BYTES": "2097152",
        "RATE_LIMIT": "1000/minute",
        "UPLOAD_RATE_LIMIT": "3/minute",
        "CORS_ORIGINS": "http://localhost:8000",
        "TRUSTED_PROXY_HOPS": "0",
    }
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Analysis  # noqa: E402
from app.services import ai_service  # noqa: E402
from app.utils.ratelimit import limiter  # noqa: E402
from tests.helpers import SAMPLE_LOG, SESSION_A, SESSION_B, FakeAI  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database_schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """Fresh rate-limit counters, no real Groq client, empty tables after every test."""
    limiter.reset()

    def _blocked():
        raise AssertionError("A test tried to create a real Groq client")

    monkeypatch.setattr(ai_service, "get_client", _blocked)
    yield
    with SessionLocal() as db:
        db.execute(delete(Analysis))
        db.commit()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def headers_a():
    return {"X-Session-ID": SESSION_A}


@pytest.fixture()
def headers_b():
    return {"X-Session-ID": SESSION_B}


@pytest.fixture()
def fake_ai(monkeypatch):
    fake = FakeAI()
    monkeypatch.setattr(ai_service, "request_completion", fake)
    return fake


@pytest.fixture()
def analyze(client, headers_a, fake_ai):
    """POST /api/analyze with the fake AI installed. Returns the response."""

    def _analyze(log=SAMPLE_LOG, category="Kubernetes", headers=None):
        payload = {"log_text": log}
        if category:
            payload["category"] = category
        return client.post("/api/analyze", json=payload, headers=headers or headers_a)

    return _analyze
