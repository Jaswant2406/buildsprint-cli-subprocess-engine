#!/usr/bin/env python3
"""
backend/scripts/verify_mocked_llm_fallback.py

MOCKED-PROVIDER TEST ONLY:
This script uses simulated/mocked LLM responses to test intent parsing and
fallback behavior offline. It is strictly an automated test harness and is
NOT evidence of a real live external LLM API call.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

# Setup paths
_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent
_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.config import Settings
from app.llm import LLMError
from app.main import _rate_limiter, app
from fastapi.testclient import TestClient

PROMPT = "Crawl https://example.com, extract the important information, give me a summary, and return the extracted data in JSON format."


def run_llm_success_demo() -> None:
    print("=" * 70)
    print("[MOCK HARNESS] TEST 1: MOCKED LLM PATH (LLM_PROVIDER=openai, LLM_MODEL=gpt-4o-mini)")
    print("NOTE: Using simulated mock provider; NOT a live external API call.")
    print("=" * 70)

    mock_settings = Settings(
        APP_ENV="test",
        LLM_PROVIDER="openai",
        LLM_API_KEY="sk-active-valid-key-live",
        LLM_MODEL="gpt-4o-mini",
        ALLOW_LOCALHOST_FOR_TESTS=True,
    )

    llm_plan_json = json.dumps({
        "task_type": "crawl",
        "tool": "site_crawler",
        "tool_reason": "GPT-4o-mini parsed natural language request: Crawl operation requiring structured content extraction and synthesis.",
        "url": "https://example.com",
        "max_pages": 10,
        "max_depth": 2,
        "wants_summary": True,
        "wants_json": True,
        "extract_focus": "",
        "max_links": 25,
    })

    llm_summary_text = (
        "SUMMARY: Example Domain is an illustrative website maintained by the Internet Assigned "
        "Numbers Authority (IANA). It is designated as a reserved domain for documentation and "
        "informational literature, requiring no prior coordination or authorization for use.\n"
        "TAKEAWAYS:\n"
        "- Official documentation domain operated by IANA\n"
        "- Reserved under RFC 2606 and RFC 6761\n"
        "- Clean single-page structure without external scripts or trackers"
    )

    def mock_call_llm(system_prompt: str, user_prompt: str, **kwargs) -> str:
        if "intent parser" in system_prompt:
            return llm_plan_json
        return llm_summary_text

    _rate_limiter._windows.clear()
    with patch("app.main.get_settings", return_value=mock_settings):
        with patch("app.intent.get_settings", return_value=mock_settings):
            with patch("app.config.get_settings", return_value=mock_settings):
                with patch("app.intent.call_llm", side_effect=mock_call_llm):
                    with patch("app.summarizer.call_llm", side_effect=mock_call_llm):
                        client = TestClient(app)
                        with client.stream("POST", "/api/chat", json={"prompt": PROMPT}) as resp:
                            assert resp.status_code == 200
                            result = None
                            plan_data = None
                            for line in resp.iter_lines():
                                if not line:
                                    continue
                                if line.startswith("data:"):
                                    payload = json.loads(line[5:].strip())
                                    evt = payload.get("event")
                                    data = payload.get("data", {})
                                    if evt == "plan":
                                        plan_data = data
                                        print(f"  [EVENT] plan        -> tool={data.get('tool')}")
                                        print(f"                         reason=\"{data.get('tool_reason')}\"")
                                    elif evt == "result":
                                        result = data
                                    elif evt in ("spawned", "progress", "summarizing"):
                                        print(f"  [EVENT] {evt:<12} -> {str(data)[:50]}")

    if result:
        print("\n" + "-" * 70)
        print("LLM-PRODUCED INTENT PLAN:")
        print(f"  Task Type:   {plan_data.get('task_type')}")
        print(f"  Tool:        {plan_data.get('tool')}")
        print(f"  Tool Reason: {plan_data.get('tool_reason')}")
        print(f"  URL:         {plan_data.get('url')}")
        print("-" * 70)
        print("LLM-PRODUCED SYNTHESIZED SUMMARY:")
        print(result.get("summary"))
        print("\nLLM-PRODUCED KEY TAKEAWAYS:")
        for t in result.get("key_takeaways", []):
            print(f"  * {t}")
        print("-" * 70)
        cov = result.get("coverage", {})
        print(f"Coverage: {cov.get('score')}/100 — {cov.get('notes')}")
        print("=" * 70 + "\n")


def run_bad_expired_key_demo() -> None:
    print("=" * 70)
    print("[MOCK HARNESS] TEST 2: MOCKED 401 EXPIRED KEY FALLBACK TEST")
    print("NOTE: Simulating 401 Unauthorized; verifying graceful heuristic fallback.")
    print("=" * 70)

    mock_settings = Settings(
        APP_ENV="test",
        LLM_PROVIDER="openai",
        LLM_API_KEY="sk-EXPIRED-KEY-999999",
        LLM_MODEL="gpt-4o-mini",
        ALLOW_LOCALHOST_FOR_TESTS=True,
    )

    def failing_call_llm(system_prompt: str, user_prompt: str, **kwargs) -> str:
        raise LLMError("OpenAI error 401: Incorrect API key provided or key has expired.")

    _rate_limiter._windows.clear()
    with patch("app.main.get_settings", return_value=mock_settings):
        with patch("app.intent.get_settings", return_value=mock_settings):
            with patch("app.config.get_settings", return_value=mock_settings):
                with patch("app.intent.call_llm", side_effect=failing_call_llm):
                    with patch("app.summarizer.call_llm", side_effect=failing_call_llm):
                        client = TestClient(app)
                        with client.stream("POST", "/api/chat", json={"prompt": PROMPT}) as resp:
                            assert resp.status_code == 200
                            result = None
                            plan_data = None
                            for line in resp.iter_lines():
                                if not line:
                                    continue
                                if line.startswith("data:"):
                                    payload = json.loads(line[5:].strip())
                                    evt = payload.get("event")
                                    data = payload.get("data", {})
                                    if evt == "plan":
                                        plan_data = data
                                        print(f"  [EVENT] plan        -> tool={data.get('tool')}")
                                        print(f"                         reason=\"{data.get('tool_reason')}\"")
                                    elif evt == "result":
                                        result = data
                                    elif evt in ("spawned", "progress", "summarizing"):
                                        print(f"  [EVENT] {evt:<12} -> {str(data)[:50]}")

    if result:
        print("\n" + "-" * 70)
        print("FALLBACK INTENT PLAN (WITH HONEST NOTE):")
        print(f"  Tool:        {plan_data.get('tool')}")
        print(f"  Tool Reason: {plan_data.get('tool_reason')}")
        print("-" * 70)
        print("FALLBACK SUMMARY (WITH HONEST NOTE):")
        print(result.get("summary"))
        print("\nSTATUS REASON:")
        print(f"  {result.get('status')} ({result.get('status_reason')})")
        print("-" * 70)
        cov = result.get("coverage", {})
        print(f"Coverage: {cov.get('score')}/100 — {cov.get('notes')}")
        print("=" * 70)


if __name__ == "__main__":
    run_llm_success_demo()
    run_bad_expired_key_demo()
