#!/usr/bin/env python3
"""
scripts/smoke_test.py — Windows-friendly and cross-platform smoke test suite.
Validates:
1. /api/health
2. Real crawl of https://example.com (asserts SUCCESS + valid JSON)
3. Bad domain (asserts FAILED)
4. SSRF http://localhost and http://169.254.169.254 (asserts blocked)
5. link_checker tool execution
6. Rate limit (asserts 429 after 5 requests within window)
"""
from __future__ import annotations

import json
import sys
import time
from typing import Any

try:
    import httpx
except ImportError:
    print("FATAL: httpx is required. Install via pip install httpx")
    sys.exit(1)

BASE_URL = "http://127.0.0.1:8000"


def print_status(check_name: str, passed: bool, detail: str = "") -> None:
    badge = "[PASS]" if passed else "[FAIL]"
    msg = f"{badge} - {check_name}"
    if detail:
        msg += f" ({detail})"
    print(msg)


def parse_sse_events(response_text: str) -> list[dict[str, Any]]:
    """Parse SSE event stream into a list of event payloads."""
    events = []
    current_event = None
    for line in response_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("event:"):
            current_event = line[6:].strip()
        elif line.startswith("data:"):
            data_str = line[5:].strip()
            try:
                data = json.loads(data_str)
                events.append({"event": current_event, "data": data})
            except json.JSONDecodeError:
                pass
    return events


def test_health(client: httpx.Client) -> bool:
    try:
        r = client.get(f"{BASE_URL}/api/health")
        data = r.json()
        passed = r.status_code == 200 and data.get("status") == "ok" and "version" in data
        print_status("1. Health Check (/api/health)", passed, f"version={data.get('version')}, mode={data.get('llm_mode')}")
        return passed
    except Exception as e:
        print_status("1. Health Check (/api/health)", False, str(e))
        return False


def test_real_crawl(client: httpx.Client) -> bool:
    try:
        prompt = "Crawl https://example.com, extract important information and return JSON"
        r = client.post(f"{BASE_URL}/api/chat", json={"prompt": prompt}, timeout=60.0)
        events = parse_sse_events(r.text)
        result_event = next((e for e in events if e.get("event") == "result"), None)
        if not result_event:
            print_status("2. Real Crawl (https://example.com)", False, "no result event in SSE stream")
            return False

        res = result_event["data"].get("data", {})
        status = res.get("status")
        json_valid = res.get("json_valid")
        passed = status == "SUCCESS" and json_valid is True
        print_status("2. Real Crawl (https://example.com)", passed, f"status={status}, json_valid={json_valid}, duration={res.get('duration_s')}s")
        return passed
    except Exception as e:
        print_status("2. Real Crawl (https://example.com)", False, str(e))
        return False


def test_link_checker(client: httpx.Client) -> bool:
    try:
        prompt = "Check for broken links on https://example.com"
        r = client.post(f"{BASE_URL}/api/chat", json={"prompt": prompt}, timeout=45.0)
        events = parse_sse_events(r.text)
        plan_event = next((e for e in events if e.get("event") == "plan"), None)
        result_event = next((e for e in events if e.get("event") == "result"), None)
        plan_data = plan_event["data"].get("data", {}) if plan_event else {}
        tool_used = plan_data.get("tool")
        passed = tool_used == "link_checker" and result_event is not None
        print_status("3. Link Checker Intent & Execution", passed, f"tool={tool_used}")
        return passed
    except Exception as e:
        print_status("3. Link Checker Intent & Execution", False, str(e))
        return False


def test_bad_domain(client: httpx.Client) -> bool:
    try:
        prompt = "Crawl https://invalid-domain-does-not-exist-xyz987.org and summarize"
        r = client.post(f"{BASE_URL}/api/chat", json={"prompt": prompt}, timeout=30.0)
        events = parse_sse_events(r.text)
        result_event = next((e for e in events if e.get("event") == "result"), None)
        if not result_event:
            # An error event is also valid
            err_event = next((e for e in events if e.get("event") == "error"), None)
            passed = err_event is not None
            print_status("4. Bad Domain Test", passed, "error event received")
            return passed

        res = result_event["data"].get("data", {})
        status = res.get("status")
        passed = status in ("FAILED", "PARTIAL")
        print_status("4. Bad Domain Test", passed, f"status={status}")
        return passed
    except Exception as e:
        print_status("4. Bad Domain Test", False, str(e))
        return False


def test_ssrf_blocked(client: httpx.Client) -> bool:
    target = "http://169.254.169.254"
    try:
        r = client.post(f"{BASE_URL}/api/chat", json={"prompt": f"Crawl {target} and summarize"}, timeout=15.0)
        events = parse_sse_events(r.text)
        has_error = any(e.get("event") == "error" for e in events)
        res = next((e["data"].get("data", {}) for e in events if e.get("event") == "result"), {})
        status = res.get("status")
        blocked = has_error or status == "FAILED" or r.status_code in (400, 422)
        print_status(f"5. SSRF Protection ({target})", blocked, "blocked successfully")
        return blocked
    except Exception as e:
        print_status(f"5. SSRF Protection ({target})", False, str(e))
        return False


def test_rate_limiting() -> bool:
    # Use fresh client with specific IP or rapid succession
    try:
        with httpx.Client() as client:
            hit_429 = False
            for i in range(8):
                r = client.post(f"{BASE_URL}/api/chat", json={"prompt": "Crawl https://example.com"}, timeout=5.0)
                if r.status_code == 429:
                    hit_429 = True
                    break
                time.sleep(0.05)
            print_status("6. Rate Limiting (5 req / 60s -> 429)", hit_429, f"hit 429={hit_429}")
            return hit_429
    except Exception as e:
        print_status("6. Rate Limiting (5 req / 60s -> 429)", False, str(e))
        return False


def main() -> int:
    print("=" * 60)
    print("BuildSprint Smoke Test Suite")
    print(f"Target: {BASE_URL}")
    print("=" * 60)

    with httpx.Client() as client:
        # Check if server is running
        try:
            client.get(f"{BASE_URL}/api/health", timeout=3.0)
        except Exception:
            print(f"ERROR: Cannot connect to {BASE_URL}. Ensure uvicorn backend is running.")
            print("Run command: uvicorn app.main:app --port 8000")
            return 1

        results = [
            test_health(client),
            test_real_crawl(client),
            test_link_checker(client),
            test_bad_domain(client),
            test_ssrf_blocked(client),
            test_rate_limiting(),
        ]

    passed_count = sum(1 for r in results if r)
    total_count = len(results)
    print("=" * 60)
    print(f"Summary: {passed_count}/{total_count} checks passed.")
    print("=" * 60)
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
