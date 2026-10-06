import json
from types import SimpleNamespace

import httpx

from app.services.ai_service import RawCompletion

SESSION_A = "test-session-aaaa-0001"
SESSION_B = "test-session-bbbb-0002"

FENCE = "\x60" * 3  # a markdown code fence, written without literal backticks

SAMPLE_LOG = (
    "Warning  BackOff  40s  kubelet  Back-off restarting failed container api\n"
    "Traceback (most recent call last):\n"
    '  File "/app/main.py", line 12, in <module>\n'
    "KeyError: 'DATABASE_URL'\n"
    "Exit Code: 1"
)


def ai_payload(**overrides) -> dict:
    """A valid model answer. Its evidence lines really appear in SAMPLE_LOG."""
    data = {
        "summary": "The api pod keeps crashing on startup.",
        "severity": "HIGH",
        "root_cause": "The DATABASE_URL environment variable is not set.",
        "affected_component": "api pod (Kubernetes)",
        "evidence": ["KeyError: 'DATABASE_URL'", "Exit Code: 1"],
        "recommended_fix": ["Add DATABASE_URL to the Deployment."],
        "commands": ["kubectl describe pod api"],
        "prevention": ["Validate required environment variables at startup."],
        "devops_insight": "CrashLoopBackOff is a symptom, not a cause.",
        "confidence": 0.93,
    }
    data.update(overrides)
    return data


def ai_json(**overrides) -> str:
    return json.dumps(ai_payload(**overrides))


class FakeAI:
    """Replaces ai_service.request_completion.

    push() queues replies: a str is returned as the model's text, an Exception is raised.
    With an empty queue it answers with a valid default diagnosis.
    """

    def __init__(self):
        self.queue = []
        self.calls = []

    def push(self, *items):
        self.queue.extend(items)
        return self

    def __call__(self, messages, temperature=0.1):
        self.calls.append(messages)
        item = self.queue.pop(0) if self.queue else ai_json()
        if isinstance(item, Exception):
            raise item
        return RawCompletion(
            content=item,
            model="fake-model",
            prompt_tokens=10,
            completion_tokens=20,
            duration_ms=1.0,
        )


# ---------- stand-ins for the Groq SDK ----------
REQUEST = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def http_response(status: int) -> httpx.Response:
    return httpx.Response(status, request=REQUEST)


def groq_completion(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=22),
    )


class StubGroqClient:
    """Mimics client.chat.completions.create(); returns or raises `outcome`."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome
