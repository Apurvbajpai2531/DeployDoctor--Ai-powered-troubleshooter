import json
import re

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json_object(text: str) -> dict:
    """Parse a JSON object from model output, tolerating fences and surrounding prose."""
    cleaned = _FENCE.sub("", text.strip()).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        data = _first_object(cleaned)
    if not isinstance(data, dict):
        raise ValueError("Model output is not a JSON object")
    return data


def _first_object(text: str) -> dict:
    """Find the first balanced {...} block, respecting braces inside strings."""
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model output")

    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON in model output: {exc.msg}") from exc
    raise ValueError("Unterminated JSON object in model output")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def verify_evidence(items: list[str], log_text: str) -> tuple[list[str], int]:
    """Keep only evidence that really appears in the log (whitespace-insensitive).

    Returns (verified_items, number_dropped).
    """
    haystack = _normalize(log_text)
    kept = [item for item in items if _normalize(item) and _normalize(item) in haystack]
    return kept, len(items) - len(kept)
