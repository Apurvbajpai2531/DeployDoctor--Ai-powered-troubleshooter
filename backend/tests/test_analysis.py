import uuid

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Analysis
from app.services.ai_service import (
    AIConfigError,
    AIRateLimitError,
    AITimeoutError,
    AIUnavailableError,
)
from tests.helpers import SAMPLE_LOG, SESSION_A, ai_json


def stored_rows():
    with SessionLocal() as db:
        return db.scalars(select(Analysis)).all()


# ---------------------------------------------------------------- analyze: happy path
def test_analyze_saves_and_returns_a_diagnosis(analyze, fake_ai):
    r = analyze()
    assert r.status_code == 201
    body = r.json()
    assert body["severity"] == "HIGH"
    assert body["category"] == "Kubernetes"
    assert body["confidence"] == pytest.approx(0.93)
    assert body["evidence"] == ["KeyError: 'DATABASE_URL'", "Exit Code: 1"]
    assert body["degraded"] is False
    assert body["redactions"] == 0
    assert body["ai_model"] == "fake-model"

    assert len(fake_ai.calls) == 1
    user_prompt = fake_ai.calls[0][1]["content"]
    assert "Kubernetes" in user_prompt and "KeyError" in user_prompt

    rows = stored_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row.id == body["id"]
    assert row.session_id == SESSION_A
    assert row.category == "Kubernetes"
    assert row.log_input == SAMPLE_LOG
    assert row.recommended_fix == ["Add DATABASE_URL to the Deployment."]


def test_category_defaults_to_unknown(analyze):
    r = analyze(category=None)
    assert r.status_code == 201
    assert r.json()["category"] == "Unknown"


def test_a_uuid_session_id_is_accepted(client, fake_ai):
    r = client.post(
        "/api/analyze",
        json={"log_text": SAMPLE_LOG},
        headers={"X-Session-ID": str(uuid.uuid4())},
    )
    assert r.status_code == 201


# ---------------------------------------------------------------- analyze: validation
def test_missing_session_header_is_rejected(client, fake_ai):
    r = client.post("/api/analyze", json={"log_text": SAMPLE_LOG})
    assert r.status_code == 400
    assert fake_ai.calls == []


@pytest.mark.parametrize(
    "value",
    ["bad", "x" * 65, "contains spaces here 123456", "under_score_1234567890", "../../etc/passwd-0000"],
)
def test_invalid_session_header_is_rejected(client, fake_ai, value):
    r = client.post("/api/analyze", json={"log_text": SAMPLE_LOG}, headers={"X-Session-ID": value})
    assert r.status_code == 400


@pytest.mark.parametrize("log", ["", "   ", "\n\n\t", "\x00\x00 \x1b[31m "])
def test_empty_logs_are_rejected(client, headers_a, fake_ai, log):
    r = client.post("/api/analyze", json={"log_text": log}, headers=headers_a)
    assert r.status_code == 422
    assert fake_ai.calls == []


def test_missing_or_null_log_is_rejected(client, headers_a, fake_ai):
    assert client.post("/api/analyze", json={}, headers=headers_a).status_code == 422
    assert client.post("/api/analyze", json={"log_text": None}, headers=headers_a).status_code == 422


def test_unknown_category_is_rejected(client, headers_a, fake_ai):
    r = client.post("/api/analyze", json={"log_text": "x", "category": "Banana"}, headers=headers_a)
    assert r.status_code == 422


def test_log_at_the_limit_is_accepted(analyze, fake_ai):
    fake_ai.push(ai_json(evidence=[]))
    assert analyze(log="x" * 50000).status_code == 201


def test_log_over_the_limit_is_rejected_without_echoing_it(client, headers_a, fake_ai):
    marker = "UNIQUE-MARKER-12345"
    r = client.post(
        "/api/analyze", json={"log_text": marker + "x" * 50001}, headers=headers_a
    )
    assert r.status_code == 422
    assert marker not in r.text
    assert len(r.text) < 1000
    assert fake_ai.calls == []


def test_oversized_request_body_is_rejected_early(client, headers_a, fake_ai):
    r = client.post(
        "/api/analyze",
        content=b"x" * 3_000_000,
        headers={**headers_a, "Content-Type": "application/json"},
    )
    assert r.status_code == 413
    assert fake_ai.calls == []


# ---------------------------------------------------------------- analyze: secrets
def test_secrets_are_masked_before_the_ai_and_the_database(analyze, fake_ai):
    password = "Hunter2-Secret"
    aws_secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    log = (
        "FATAL: password authentication failed for user deploy\n"
        f"DATABASE_URL=postgresql://deploy:{password}@db.example.com:5432/app\n"
        f"AWS_SECRET_ACCESS_KEY={aws_secret}\n"
    )
    fake_ai.push(ai_json(evidence=[]))
    r = analyze(log=log, category="Database")
    assert r.status_code == 201
    assert r.json()["redactions"] >= 2

    sent_to_ai = " ".join(m["content"] for m in fake_ai.calls[0])
    assert password not in sent_to_ai and aws_secret not in sent_to_ai
    assert "[REDACTED" in sent_to_ai

    assert password not in r.text and aws_secret not in r.text

    stored = stored_rows()[0].log_input
    assert password not in stored and aws_secret not in stored
    assert "[REDACTED" in stored


def test_control_characters_do_not_break_the_save(analyze, fake_ai):
    fake_ai.push(ai_json(evidence=[]))
    r = analyze(log="before\x00after \x1b[31mred\x1b[0m error")
    assert r.status_code == 201
    assert "\x00" not in stored_rows()[0].log_input


# ---------------------------------------------------------------- analyze: AI behaviour
def test_invalid_json_is_retried_once(analyze, fake_ai):
    fake_ai.push("oops", ai_json())
    body = analyze().json()
    assert body["degraded"] is False
    assert len(fake_ai.calls) == 2
    assert [m["role"] for m in fake_ai.calls[1]] == ["system", "user", "assistant", "user"]


def test_unusable_ai_output_returns_a_flagged_fallback(analyze, fake_ai):
    fake_ai.push("not json", "still not json")
    r = analyze()
    assert r.status_code == 201
    body = r.json()
    assert body["degraded"] is True
    assert body["ai_model"] == "fallback"
    assert body["confidence"] == 0
    assert len(fake_ai.calls) == 2


def test_invented_evidence_is_removed(analyze, fake_ai):
    fake_ai.push(ai_json(evidence=["KeyError: 'DATABASE_URL'", "this line is not in the log"]))
    assert analyze().json()["evidence"] == ["KeyError: 'DATABASE_URL'"]


@pytest.mark.parametrize(
    "error, status",
    [
        (AITimeoutError("upstream detail"), 504),
        (AIRateLimitError("upstream detail"), 429),
        (AIConfigError("GROQ_API_KEY is missing"), 503),
        (AIUnavailableError("Groq status 500"), 502),
    ],
)
def test_ai_failures_become_clean_http_errors(analyze, fake_ai, error, status):
    fake_ai.push(error)
    r = analyze()
    assert r.status_code == status
    assert r.json()["detail"]
    for leaked in ("upstream detail", "GROQ_API_KEY", "Groq status"):
        assert leaked not in r.text
    if status == 429:
        assert r.headers["retry-after"] == "10"
    assert len(fake_ai.calls) == 1  # provider errors are not retried
    assert stored_rows() == []


# ---------------------------------------------------------------- get
def test_owner_can_get_the_full_analysis(client, analyze, headers_a):
    created = analyze().json()
    r = client.get(f"/api/analyses/{created['id']}", headers=headers_a)
    assert r.status_code == 200
    body = r.json()
    assert body["root_cause"] == created["root_cause"]
    assert body["log_input"] == SAMPLE_LOG
    assert body["commands"] == ["kubectl describe pod api"]


def test_other_session_gets_404(client, analyze, headers_b):
    created = analyze().json()
    r = client.get(f"/api/analyses/{created['id']}", headers=headers_b)
    assert r.status_code == 404


def test_missing_id_is_404_and_bad_id_is_422(client, headers_a):
    assert client.get("/api/analyses/999999", headers=headers_a).status_code == 404
    assert client.get("/api/analyses/not-a-number", headers=headers_a).status_code == 422


def test_get_requires_a_session_header(client, analyze):
    created = analyze().json()
    assert client.get(f"/api/analyses/{created['id']}").status_code == 400


# ---------------------------------------------------------------- list
def test_list_is_newest_first_and_session_scoped(client, analyze, headers_a, headers_b):
    ids = [analyze(log=f"{SAMPLE_LOG}\nrun {i}").json()["id"] for i in range(3)]
    other = analyze(headers=headers_b).json()["id"]

    body = client.get("/api/analyses", headers=headers_a).json()
    assert body["total"] == 3
    assert [item["id"] for item in body["items"]] == ids[::-1]
    assert other not in [item["id"] for item in body["items"]]

    item = body["items"][0]
    assert {"id", "category", "severity", "summary", "confidence", "created_at"} <= set(item)
    assert "log_input" not in item and "root_cause" not in item


def test_list_pagination(client, analyze, headers_a):
    for i in range(5):
        analyze(log=f"{SAMPLE_LOG}\nrun {i}")
    first = client.get("/api/analyses?limit=2&offset=0", headers=headers_a).json()
    last = client.get("/api/analyses?limit=2&offset=4", headers=headers_a).json()
    beyond = client.get("/api/analyses?limit=2&offset=10", headers=headers_a).json()
    assert (len(first["items"]), first["total"]) == (2, 5)
    assert (len(last["items"]), last["total"]) == (1, 5)
    assert (len(beyond["items"]), beyond["total"]) == (0, 5)


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1"])
def test_list_rejects_out_of_range_paging(client, headers_a, query):
    assert client.get(f"/api/analyses?{query}", headers=headers_a).status_code == 422


def test_empty_history(client, headers_a):
    body = client.get("/api/analyses", headers=headers_a).json()
    assert body["items"] == [] and body["total"] == 0


# ---------------------------------------------------------------- delete
def test_delete_removes_the_analysis(client, analyze, headers_a):
    analysis_id = analyze().json()["id"]
    assert client.delete(f"/api/analyses/{analysis_id}", headers=headers_a).status_code == 204
    assert client.get(f"/api/analyses/{analysis_id}", headers=headers_a).status_code == 404
    assert client.delete(f"/api/analyses/{analysis_id}", headers=headers_a).status_code == 404
    with SessionLocal() as db:
        assert db.get(Analysis, analysis_id) is None


def test_cannot_delete_another_sessions_analysis(client, analyze, headers_a, headers_b):
    analysis_id = analyze().json()["id"]
    assert client.delete(f"/api/analyses/{analysis_id}", headers=headers_b).status_code == 404
    assert client.get(f"/api/analyses/{analysis_id}", headers=headers_a).status_code == 200
