#!/usr/bin/env python3
"""Run the built-in sample logs through a running DeployDoctor and print each diagnosis.

Usage:
    python scripts/demo_check.py
    python scripts/demo_check.py --base-url http://localhost:8000 --only kubernetes,docker
    python scripts/demo_check.py --keep      # keep the saved analyses afterwards

Each sample is one real AI call. The exit code is 0 only if every sample returned a
normal (non-fallback) diagnosis.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES_JS = ROOT / "frontend" / "samples.js"

SAMPLE_RE = re.compile(
    r'id:\s*"(?P<id>[^"]+)",\s*label:\s*"(?P<label>[^"]+)",\s*'
    r'category:\s*"(?P<category>[^"]+)",\s*log:\s*String\.raw`(?P<log>[^`]*)`',
    re.S,
)


def load_samples() -> list[dict]:
    text = SAMPLES_JS.read_text(encoding="utf-8")
    return [m.groupdict() for m in SAMPLE_RE.finditer(text)]


def call(method, url, session_id, body=None, timeout=120):
    """Returns (status, parsed_json, lowercase_headers)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"X-Session-ID": session_id}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else None
            return response.status, parsed, {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = {"detail": raw[:200]}
        return exc.code, parsed, {k.lower(): v for k, v in exc.headers.items()}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--only", default="", help="comma-separated sample ids")
    parser.add_argument("--keep", action="store_true", help="do not delete the analyses")
    parser.add_argument("--pause", type=float, default=0.0, help="seconds between samples")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    samples = load_samples()
    if not samples:
        print("No samples found in frontend/samples.js")
        return 2
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        samples = [s for s in samples if s["id"] in wanted]
        if not samples:
            print("None of the requested sample ids exist.")
            return 2

    # A random session keeps these runs out of your browser's history
    session_id = f"demo-check-{uuid.uuid4().hex}"

    try:
        status, health, _ = call("GET", f"{base}/health", session_id, timeout=15)
    except OSError as exc:
        print(f"Cannot reach {base}: {exc}")
        return 2
    print(f"health: HTTP {status} {json.dumps(health)}")
    if status != 200:
        return 2

    print()
    print(f"{'sample':<11} {'category':<12} {'severity':<9} {'conf':>5} {'time':>7}  notes")
    problems = 0
    created: list[int] = []

    for index, sample in enumerate(samples):
        if index and args.pause:
            time.sleep(args.pause)
        body = {"log_text": sample["log"].strip(), "category": sample["category"]}
        started = time.perf_counter()
        try:
            code, data, headers = call("POST", f"{base}/api/analyze", session_id, body)
            if code == 429:
                wait = min(int(headers.get("retry-after", "10")), 65)
                print(f"{sample['id']:<11} rate limited, waiting {wait}s and retrying once")
                time.sleep(wait)
                started = time.perf_counter()
                code, data, headers = call("POST", f"{base}/api/analyze", session_id, body)
        except OSError as exc:
            problems += 1
            print(f"{sample['id']:<11} request failed: {exc}")
            continue

        elapsed = time.perf_counter() - started
        if code != 201:
            problems += 1
            detail = data.get("detail") if isinstance(data, dict) else data
            print(f"{sample['id']:<11} {sample['category']:<12} {'-':<9} {'-':>5} {elapsed:6.1f}s  HTTP {code}: {detail}")
            continue

        created.append(data["id"])
        notes = []
        if data["degraded"]:
            notes.append("FALLBACK result")
            problems += 1
        if data["confidence"] < 0.5:
            notes.append("low confidence")
        if not data["evidence"]:
            notes.append("no evidence")
        if data["redactions"]:
            notes.append(f"{data['redactions']} masked")
        print(
            f"{sample['id']:<11} {sample['category']:<12} {data['severity']:<9} "
            f"{data['confidence']:>5.2f} {elapsed:6.1f}s  {', '.join(notes) or 'ok'}"
        )
        print(f"            component: {data['affected_component'][:90]}")
        print(f"            root cause: {data['root_cause'][:140]}")

    if created and not args.keep:
        removed = 0
        for analysis_id in created:
            code, _, _ = call("DELETE", f"{base}/api/analyses/{analysis_id}", session_id, timeout=30)
            removed += code == 204
        print(f"\ncleaned up {removed}/{len(created)} saved analyses")

    print(f"\n{len(samples)} sample(s) checked, {problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
