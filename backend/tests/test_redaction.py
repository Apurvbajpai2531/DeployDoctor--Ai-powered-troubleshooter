import re
import time

import pytest

from app.config import PROJECT_ROOT
from app.utils.sanitize import redact_secrets, sanitize_log_text

# Token-shaped strings are built by concatenation so this file never contains a
# complete one (keeps secret scanners quiet).
SECRET_CASES = [
    pytest.param("key id " + "AKIA" + "IOSFODNN7EXAMPLE" + " ok", "IOSFODNN7EXAMPLE", id="aws-key-id"),
    pytest.param("aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "wJalrXUtn", id="aws-secret"),
    pytest.param("GROQ_API_KEY=" + "gsk_" + "a" * 40, "gsk_aaaa", id="groq-key"),
    pytest.param("token " + "ghp_" + "b" * 36, "ghp_bbbb", id="github-token"),
    pytest.param("jwt=" + "eyJ" + "a" * 20 + "." + "b" * 30 + "." + "c" * 30, "eyJaaaa", id="jwt"),
    pytest.param('curl -H "Authorization: Bearer ' + "x" * 30 + '"', "xxxxxxxxxx", id="auth-header"),
    pytest.param("got header bearer " + "Q" * 25, "QQQQQQQQ", id="bare-bearer"),
    pytest.param("postgresql://deploy:s3cr3tPass@db.example.com:5432/app", "s3cr3tPass", id="url-credentials"),
    pytest.param("-----BEGIN RSA PRIVATE KEY-----\nMIIEabc123\n-----END RSA PRIVATE KEY-----", "MIIEabc123", id="private-key"),
    pytest.param("x\n-----BEGIN PRIVATE KEY-----\nMIIEtruncatedKEYDATA\nmore lines", "MIIEtruncated", id="truncated-private-key"),
    pytest.param('{"password": "hunter2hunter2"}', "hunter2hunter2", id="json-password"),
    pytest.param("mysql --password=SuperSecret123 -h db", "SuperSecret123", id="cli-flag"),
    pytest.param("DB_PASSWORD=p4ssw0rd!", "p4ssw0rd", id="env-var"),
]

CLEAN_LINES = [
    'FATAL:  password authentication failed for user "deploy"',
    "KeyError: 'DATABASE_URL'",
    "secretKeyRef:\n  name: api-db",
    'secret "api-db" not found',
    "Exit Code: 1",
    "token expired at 08:12",
]


@pytest.mark.parametrize("text, fragment", SECRET_CASES)
def test_secret_is_masked(text, fragment):
    result = redact_secrets(text)
    assert fragment not in result.text
    assert result.count >= 1
    assert "[REDACTED" in result.text


@pytest.mark.parametrize("text", CLEAN_LINES)
def test_ordinary_log_lines_are_left_alone(text):
    result = redact_secrets(text)
    assert result.text == text
    assert result.count == 0


def test_redaction_is_idempotent():
    combined = "\n".join(case.values[0] for case in SECRET_CASES)
    once = redact_secrets(combined)
    twice = redact_secrets(once.text)
    assert twice.count == 0
    assert twice.text == once.text
    assert once.by_type  # the report says which kinds were found, never the values


def test_the_demo_sample_logs_are_not_touched():
    source = (PROJECT_ROOT / "frontend" / "samples.js").read_text(encoding="utf-8")
    logs = re.findall(r"log: String\.raw`([^`]*)`", source)
    assert len(logs) == 7
    for log in logs:
        clean = sanitize_log_text(log)
        result = redact_secrets(clean)
        assert result.count == 0
        assert result.text == clean


# ---------------------------------------------------------------- sanitizer
def test_sanitize_strips_control_characters_and_normalizes_newlines():
    assert sanitize_log_text("a\x00b\x1b[31mred\x1b[0m\r\nline2\x07") == "abred\nline2"


def test_sanitize_replaces_lone_surrogates():
    assert sanitize_log_text("x\ud800y") == "x?y"


def test_sanitize_keeps_tabs_and_unicode():
    assert sanitize_log_text("a\tb│c") == "a\tb│c"


# ---------------------------------------------------------------- hostile input must stay fast
HOSTILE = {
    "50k letters": "a" * 50000,
    "password repeated": "password" * 6000,
    "eyJ repeated": "eyJ" * 16000,
    "fake URLs": "ab://x:" * 7000,
    "BEGIN markers without END": "-----BEGIN PRIVATE KEY-----" * 1800,
    "token= plus 49k chars": "token=" + "x" * 49000,
    "dots": "a." * 25000,
    "Bearer repeated": "Bearer " * 7000,
    "authorization repeated": "authorization:" * 3500,
}


@pytest.mark.parametrize("text", [pytest.param(t, id=name) for name, t in HOSTILE.items()])
def test_hostile_input_is_processed_quickly(text):
    start = time.perf_counter()
    redact_secrets(sanitize_log_text(text))
    assert time.perf_counter() - start < 3.0
