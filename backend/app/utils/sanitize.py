import re
from collections.abc import Callable
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Sanitizing: make pasted text safe to process and store
# ---------------------------------------------------------------------------
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")  # terminal colors / cursor codes
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")  # keeps \t and \n


def sanitize_log_text(text: str) -> str:
    """Normalize line endings, drop ANSI codes and control characters, trim."""
    # Lone surrogates are valid in JSON but cannot be stored; replace them
    text = text.encode("utf-8", "replace").decode("utf-8")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _ANSI.sub("", text)
    text = _CONTROL.sub("", text)  # includes NUL bytes, which PostgreSQL rejects
    return text.strip()


# ---------------------------------------------------------------------------
# Secret redaction (best effort: common formats, not a guarantee)
#
# Every quantifier below is bounded or anchored on a literal prefix, so hostile
# input cannot trigger catastrophic regex backtracking.
# ---------------------------------------------------------------------------
PLACEHOLDER = "[REDACTED]"

Replacer = Callable[[re.Match[str]], str]


def _typed(label: str) -> Replacer:
    placeholder = f"[REDACTED:{label}]"
    return lambda _m: placeholder


def _redact_url_credentials(m: re.Match[str]) -> str:
    return f"{m.group('scheme')}{m.group('user')}:{PLACEHOLDER}@"


def _redact_auth_header(m: re.Match[str]) -> str:
    return f"{m.group('name')}{m.group('sep')}{PLACEHOLDER}"


def _redact_key_value(m: re.Match[str]) -> str:
    if m.group("val").startswith("[REDACTED"):  # already masked: keep it idempotent
        return m.group(0)
    return f"{m.group('key')}{m.group('sep')}{PLACEHOLDER}"


_RULES: list[tuple[str, re.Pattern[str], Replacer]] = [
    # PEM private keys: a complete block, then an unterminated (truncated) one
    (
        "private-key",
        re.compile(
            r"-----BEGIN [A-Z ]{0,30}PRIVATE KEY-----[\s\S]{0,8000}?"
            r"-----END [A-Z ]{0,30}PRIVATE KEY-----"
        ),
        _typed("private-key"),
    ),
    (
        "private-key",
        re.compile(r"-----BEGIN [A-Z ]{0,30}PRIVATE KEY-----[\s\S]*"),
        _typed("private-key"),
    ),
    # scheme://user:password@host
    (
        "url-credentials",
        re.compile(
            r"(?P<scheme>[a-z][a-z0-9+.-]{1,20}://)(?P<user>[^\s:/@]+):(?P<pw>[^\s/]+)@",
            re.IGNORECASE,
        ),
        _redact_url_credentials,
    ),
    # Authorization: Bearer xxx / Basic xxx / Token xxx
    (
        "auth-header",
        re.compile(
            r"(?P<name>\bauthorization)(?P<sep>[ \t]*[:=][ \t]*)"
            r"(?:(?:bearer|basic|token)[ \t]+)?\S+",
            re.IGNORECASE,
        ),
        _redact_auth_header,
    ),
    # Well-known token formats
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), _typed("aws-access-key")),
    ("groq-key", re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), _typed("groq-key")),
    ("api-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), _typed("api-key")),
    ("stripe-key", re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}"), _typed("stripe-key")),
    (
        "github-token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
        _typed("github-token"),
    ),
    ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}"), _typed("gitlab-token")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), _typed("slack-token")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}"), _typed("google-api-key")),
    (
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{8,1500}\.[A-Za-z0-9_-]{8,1500}\.[A-Za-z0-9_-]{8,1500}"
        ),
        _typed("jwt"),
    ),
    (
        "bearer-token",
        re.compile(r"\bbearer[ \t]+[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
        lambda _m: f"Bearer {PLACEHOLDER}",
    ),
    # password=..., "api_key": "...", AWS_SECRET_ACCESS_KEY=..., --token=...
    (
        "secret-value",
        re.compile(
            r"""(?P<key>(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key)[\w.-]{0,40})"""
            r"""(?P<sep>["']?[ \t]*[:=][ \t]*["']?)"""
            r"""(?P<val>[^\s"',;&]{4,})""",
            re.IGNORECASE,
        ),
        _redact_key_value,
    ),
]


@dataclass
class RedactionResult:
    text: str
    count: int = 0
    by_type: dict[str, int] = field(default_factory=dict)


def _apply(text: str, pattern: re.Pattern[str], repl: Replacer) -> tuple[str, int]:
    changed = 0

    def _sub(m: re.Match[str]) -> str:
        nonlocal changed
        out = repl(m)
        if out != m.group(0):
            changed += 1
        return out

    return pattern.sub(_sub, text), changed


def redact_secrets(text: str) -> RedactionResult:
    """Mask recognizable secrets. Never logs or returns the secret values."""
    by_type: dict[str, int] = {}
    for label, pattern, repl in _RULES:
        text, changed = _apply(text, pattern, repl)
        if changed:
            by_type[label] = by_type.get(label, 0) + changed
    return RedactionResult(text=text, count=sum(by_type.values()), by_type=by_type)
