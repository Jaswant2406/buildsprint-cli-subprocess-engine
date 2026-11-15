"""Tests for FastAPI endpoints: SSE, history, cancel, replay, ask, health, tools, audit."""
from __future__ import annotations

import json
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.models import Plan, RunState, RunStatus
from app.runstore import RunRecord, get_store


class TestAPIEndpoints:
    def test_health_endpoint(self, app_client: TestClient) -> None:
        resp = app_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["llm_mode"] in ("heuristic", "llm")
        assert "version" in data

    def test_tools_endpoint(self, app_client: TestClient) -> None:
        resp = app_client.get("/api/tools")
        assert resp.status_code == 200
        tools = resp.json().get("tools", [])
        tool_names = [t["name"] for t in tools]
        assert "site_crawler" in tool_names
        assert "link_checker" in tool_names
        for t in tools:
            assert "description" in t
            assert "why_chosen" in t
            assert "allowed_args" in t

    def test_audit_endpoint(self, app_client: TestClient) -> None:
        resp = app_client.get("/api/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "verified" in data
        assert data["verified"] is True

    def test_invalid_chat_requests(self, app_client: TestClient) -> None:
        # Empty prompt
        resp = app_client.post("/api/chat", json={"prompt": "   "})
        assert resp.status_code == 400

        # Oversized prompt (> 1000 chars)
        resp = app_client.post("/api/chat", json={"prompt": "a" * 1001})
        assert resp.status_code in (400, 422)

    def test_run_lifecycle_and_history(self, app_client: TestClient) -> None:
        store = get_store()
        run_id = "test-history-run"
        rec = RunRecord(
            run_id,
            {"task_type": "crawl", "tool": "site_crawler", "url": "https://example.com"},
            ["python", "cli/site_crawler.py"],
        )
        rec.state = RunState.COMPLETED
        rec.stdout = "{\"site\": \"https://example.com\", \"pages\": []}"
        rec.exit_code = 0
        rec.result = {
            "run_id": run_id,
            "status": "SUCCESS",
            "pages_crawled": 1,
            "summary": "Example domain crawled.",
            "json": {
                "site": "https://example.com",
                "pages": [{"url": "https://example.com", "title": "Example", "main_text": "Sample text"}],
            },
        }
        rec.add_event("received")
        rec.add_event("plan")
        rec.add_event("result", rec.result)
        store.add(rec)
        store.finalize(rec)

        # GET /api/runs
        resp = app_client.get("/api/runs")
        assert resp.status_code == 200
        runs = resp.json()
        assert any(r["run_id"] == run_id for r in runs)

        # GET /api/runs/{id}
        resp = app_client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == run_id
        assert data["state"] == "completed"

        # GET /api/runs/{id}/logs
        resp = app_client.get(f"/api/runs/{run_id}/logs")
        assert resp.status_code == 200
        logs = resp.json()
        assert "stdout" in logs
        assert "events" in logs

        # GET /api/runs/{id}/report.md
        resp = app_client.get(f"/api/runs/{run_id}/report.md")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")
        assert "BuildSprint Run Report" in resp.text
        assert run_id in resp.text

        # POST /api/runs/{id}/ask
        resp = app_client.post(f"/api/runs/{run_id}/ask", json={"question": "What is the sample text?"})
        assert resp.status_code == 200
        ans = resp.json()
        assert "answer" in ans
        assert "citations" in ans
        assert len(ans["citations"]) > 0

        # POST /api/runs/{id}/replay
        resp = app_client.post(f"/api/runs/{run_id}/replay")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    def test_secret_redaction_in_logs_and_responses(self, app_client: TestClient) -> None:
        store = get_store()
        run_id = "test-redact-run"
        rec = RunRecord(run_id, {"tool": "site_crawler"}, [])
        secret = "sk-123456789012345678901234"
        rec.stdout = f"Debug log with key: {secret} and password: mysecretpassword123"
        rec.state = RunState.COMPLETED
        store.add(rec)

        resp = app_client.get(f"/api/runs/{run_id}/logs")
        assert resp.status_code == 200
        text = resp.text
        assert secret not in text
        assert "mysecretpassword123" not in text
        assert "[REDACTED]" in text

    def test_cancel_finished_run_returns_409(self, app_client: TestClient) -> None:
        store = get_store()
        run_id = "test-finished-cancel"
        rec = RunRecord(run_id, {"tool": "site_crawler"}, [])
        rec.state = RunState.COMPLETED
        store.add(rec)

        resp = app_client.post(f"/api/runs/{run_id}/cancel")
        assert resp.status_code == 409
        assert "already_terminal" in resp.text

        # Run history and logs remain retrievable
        resp = app_client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["state"] == "completed"

        resp = app_client.get(f"/api/runs/{run_id}/logs")
        assert resp.status_code == 200

    def test_sse_event_order_and_end_to_end_crawl(self, app_client: TestClient, local_site: str) -> None:
        """Verify exact SSE event sequence: received -> plan -> validated -> spawned -> progress -> parsing -> summarizing -> result."""
        resp = app_client.post(
            "/api/chat",
            json={"prompt": f"Crawl {local_site}/index.html and summarize the important info"},
        )
        assert resp.status_code == 200
        text = resp.text

        # Extract event types in order from SSE lines
        event_types = []
        for line in text.splitlines():
            if line.startswith("event: "):
                event_types.append(line.split("event: ")[1].strip())

        # Assert key lifecycle events appeared
        assert "received" in event_types
        assert "plan" in event_types
        assert "validated" in event_types
        assert "spawned" in event_types
        assert "progress" in event_types
        assert "parsing" in event_types
        assert "summarizing" in event_types
        assert "result" in event_types

        # Assert relative ordering
        idx_received = event_types.index("received")
        idx_plan = event_types.index("plan")
        idx_validated = event_types.index("validated")
        idx_spawned = event_types.index("spawned")
        idx_parsing = event_types.index("parsing")
        idx_summarizing = event_types.index("summarizing")
        idx_result = event_types.index("result")

        assert idx_received < idx_plan < idx_validated < idx_spawned < idx_parsing < idx_summarizing < idx_result

    def test_injection_html_crawled_end_to_end_safe(self, app_client: TestClient, local_site: str) -> None:
        """demo_site/injection.html crawled end-to-end: security_findings populated, text treated as data, summarizer wrapped in delimiters."""
        resp = app_client.post(
            "/api/chat",
            json={"prompt": f"Crawl {local_site}/injection.html and summarize the contents"},
        )
        assert resp.status_code == 200
        text = resp.text

        # Parse the 'result' event payload
        result_payload = None
        for block in text.split("\r\n\r\n" if "\r\n\r\n" in text else "\n\n"):
            if "event: result" in block:
                for line in block.splitlines():
                    if line.startswith("data: "):
                        outer = json.loads(line[6:])
                        result_payload = outer.get("data")
                        break

        assert result_payload is not None
        # Assert security_findings populated
        findings = result_payload.get("security_findings", [])
        assert len(findings) > 0
        patterns = [f.get("pattern") for f in findings]
        assert any("ignore" in p.lower() or "instruction" in p.lower() for p in patterns)

        # Assert injection text treated as data only
        assert result_payload["status"] in ("SUCCESS", "PARTIAL")

    def test_ask_answers_from_data_with_source_urls(self, app_client: TestClient) -> None:
        store = get_store()
        run_id = "test-ask-sources"
        rec = RunRecord(run_id, {"tool": "site_crawler"}, [])
        rec.state = RunState.COMPLETED
        rec.result = {
            "run_id": run_id,
            "status": "SUCCESS",
            "json": {
                "site": "https://company.example",
                "pages": [
                    {
                        "url": "https://company.example/about",
                        "title": "About Us",
                        "main_text": "We were founded in 2018 in Seattle. Contact us at contact@company.example.",
                    }
                ],
            },
        }
        store.add(rec)
        store.finalize(rec)

        resp = app_client.post(f"/api/runs/{run_id}/ask", json={"question": "When was the company founded?"})
        assert resp.status_code == 200
        data = resp.json()
        assert "2018" in data["answer"]
        assert len(data["citations"]) > 0
        assert "https://company.example/about" in data["citations"]

    def test_replay_restreams_identical_events(self, app_client: TestClient) -> None:
        store = get_store()
        run_id = "test-replay-run"
        rec = RunRecord(run_id, {"tool": "site_crawler"}, [])
        rec.add_event("received", {"step": 1})
        rec.add_event("plan", {"step": 2})
        rec.add_event("progress", {"step": 3})
        rec.state = RunState.COMPLETED
        rec.result = {"run_id": run_id, "status": "SUCCESS"}
        store.add(rec)
        store.finalize(rec)

        resp = app_client.post(f"/api/runs/{run_id}/replay")
        assert resp.status_code == 200
        text = resp.text

        events = []
        for line in text.splitlines():
            if line.startswith("event: "):
                events.append(line.split("event: ")[1].strip())

        assert events == ["received", "plan", "progress", "result"]

    def test_report_md_contains_all_required_sections(self, app_client: TestClient) -> None:
        store = get_store()
        run_id = "test-report-full"
        rec = RunRecord(run_id, {"tool": "site_crawler", "url": "https://example.com"}, [])
        rec.state = RunState.COMPLETED
        rec.result = {
            "run_id": run_id,
            "status": "SUCCESS",
            "status_reason": "ok",
            "summary": "This is a detailed summary of the example domain.",
            "pages_crawled": 1,
            "json_valid": True,
            "audit_hash": "a1b2c3d4e5f67890abcdef1234567890",
        }
        store.add(rec)
        store.finalize(rec)

        resp = app_client.get(f"/api/runs/{run_id}/report.md")
        assert resp.status_code == 200
        text = resp.text

        assert "## Status" in text
        assert "SUCCESS" in text
        assert "## Summary" in text
        assert "This is a detailed summary" in text
        assert "## Audit" in text
        assert "a1b2c3d4e5f67890abcdef1234567890" in text

    def test_no_secret_appears_in_response_log_or_report(self, app_client: TestClient) -> None:
        secret_key = "sk-live-super-secret-api-key-999888"
        import os
        old_val = os.environ.get("LLM_API_KEY")
        os.environ["LLM_API_KEY"] = secret_key

        try:
            store = get_store()
            run_id = "test-no-leak"
            rec = RunRecord(run_id, {"tool": "site_crawler"}, [])
            rec.stdout = f"Called upstream with authorization: Bearer {secret_key}"
            rec.state = RunState.COMPLETED
            rec.result = {
                "run_id": run_id,
                "status": "SUCCESS",
                "summary": f"Summary with safe output",
                "audit_hash": "hash123",
            }
            store.add(rec)
            store.finalize(rec)

            # Check logs
            resp = app_client.get(f"/api/runs/{run_id}/logs")
            assert resp.status_code == 200
            assert secret_key not in resp.text

            # Check run detail
            resp = app_client.get(f"/api/runs/{run_id}")
            assert resp.status_code == 200
            assert secret_key not in resp.text

            # Check report.md
            resp = app_client.get(f"/api/runs/{run_id}/report.md")
            assert resp.status_code == 200
            assert secret_key not in resp.text

        finally:
            if old_val is not None:
                os.environ["LLM_API_KEY"] = old_val
            else:
                os.environ.pop("LLM_API_KEY", None)

    def test_cors_headers(self, app_client: TestClient) -> None:
        resp = app_client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code in (200, 204)
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
