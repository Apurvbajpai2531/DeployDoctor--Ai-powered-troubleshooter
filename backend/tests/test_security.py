import logging

import pytest
from starlette.requests import Request

from app.config import get_settings
from app.services import analysis_service
from app.utils.ratelimit import client_ip
from tests.helpers import SAMPLE_LOG, ai_json


def test_security_headers_on_the_app_page(client):
    r = client.get("/")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    csp = r.headers["content-security-policy"]
    for directive in (
        "default-src 'self'",
        "script-src 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
    ):
        assert directive in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp


def test_swagger_docs_are_exempt_from_the_strict_csp(client):
    r = client.get("/docs")
    assert r.status_code == 200
    assert "content-security-policy" not in r.headers
    assert r.headers["x-content-type-options"] == "nosniff"


def test_api_responses_are_not_cacheable(client, headers_a):
    assert client.get("/api/analyses", headers=headers_a).headers["cache-control"] == "no-store"


def test_cors_allows_only_the_configured_origin(client):
    path = "/api/analyze"
    ok = client.options(
        path, headers={"Origin": "http://localhost:8000", "Access-Control-Request-Method": "POST"}
    )
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == "http://localhost:8000"

    bad = client.options(
        path, headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"}
    )
    assert "access-control-allow-origin" not in bad.headers


def test_unhandled_errors_return_a_generic_500(client, headers_a, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("internal detail that must not leak")

    monkeypatch.setattr(analysis_service, "create_analysis", boom)
    r = client.post("/api/analyze", json={"log_text": SAMPLE_LOG}, headers=headers_a)
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "Internal server error"
    assert body["request_id"] == r.headers["x-request-id"]
    assert "internal detail" not in r.text


def test_logs_never_contain_log_text_or_secrets(analyze, fake_ai, caplog):
    caplog.set_level(logging.DEBUG)
    password = "Hunter2-Secret"
    fake_ai.push(ai_json(evidence=[]))
    analyze(
        log=f"boom happened\nDATABASE_URL=postgresql://deploy:{password}@db:5432/app",
        category="Database",
    )
    assert password not in caplog.text
    assert "test-key-not-real" not in caplog.text
    assert "boom happened" not in caplog.text


# ---------------------------------------------------------------- client IP / proxies
def make_request(forwarded=None):
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": headers,
        "client": ("203.0.113.9", 4321),
    }
    return Request(scope)


@pytest.mark.parametrize(
    "hops, forwarded, expected",
    [
        (0, "1.1.1.1", "203.0.113.9"),  # no trusted proxy: header is ignored
        (1, "6.6.6.6, 198.51.100.7", "198.51.100.7"),  # spoofed first entry is ignored
        (2, "6.6.6.6, 198.51.100.7, 10.0.0.5", "198.51.100.7"),
        (2, "198.51.100.7", "203.0.113.9"),  # fewer entries than proxies: fall back to the socket
    ],
)
def test_client_ip_trusts_only_our_proxies(monkeypatch, hops, forwarded, expected):
    monkeypatch.setattr(get_settings(), "trusted_proxy_hops", hops)
    assert client_ip(make_request(forwarded)) == expected
