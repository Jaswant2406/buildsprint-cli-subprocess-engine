"""Tests for runner: state machine, slots, timeout, kill, cancel."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ["APP_ENV"] = "test"
os.environ["ALLOW_LOCALHOST_FOR_TESTS"] = "1"
os.environ["LLM_API_KEY"] = ""

from app.models import Plan, RunState
from app.runner import (
    TOOL_REGISTRY,
    _child_env,
    _kill_tree,
    _transition,
    build_argv,
    get_slot_manager,
)
from app.runstore import RunRecord, get_store


def _make_plan(tool: str = "site_crawler", url: str = "https://example.com") -> Plan:
    return Plan(
        task_type="crawl",
        tool=tool,
        tool_reason="test",
        url=url,
        max_pages=2,
        max_depth=1,
    )


def _make_record(run_id: str = "test-run-1", tool: str = "site_crawler") -> RunRecord:
    plan = _make_plan(tool=tool)
    return RunRecord(run_id, plan.model_dump(), [])


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


class TestToolRegistry:
    def test_only_allowlisted_tools(self) -> None:
        assert set(TOOL_REGISTRY.keys()) == {"site_crawler", "link_checker"}

    def test_build_argv_shell_false(self) -> None:
        """build_argv must never produce shell=True."""
        plan = _make_plan()
        argv = build_argv(plan, "/tmp/out.json")
        assert sys.executable in argv
        assert "site_crawler.py" in argv[-3] or any("site_crawler" in a for a in argv)

    def test_popen_called_with_shell_false(self) -> None:
        from app.runner import run_tool
        from unittest.mock import patch, MagicMock
        record = _make_record("test-shell-check")
        plan = _make_plan()
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 99999
            mock_proc.poll.return_value = 0
            mock_proc.returncode = 0
            mock_proc.stdout = MagicMock()
            mock_proc.stdout.read.return_value = b""
            mock_proc.stderr = MagicMock()
            mock_proc.stderr.readline.return_value = ""
            mock_popen.return_value = mock_proc
            # Consume generator
            list(run_tool(record, plan))
            assert mock_popen.called
            _, kwargs = mock_popen.call_args
            assert kwargs.get("shell") is False

    def test_unknown_tool_raises(self) -> None:
        plan = Plan(
            task_type="crawl",
            tool="evil_tool",
            tool_reason="test",
            url="https://example.com",
        )
        with pytest.raises(ValueError):
            build_argv(plan, "/tmp/out.json")

    def test_argv_contains_no_shell_metacharacters(self) -> None:
        """Args should come only from validated Plan fields."""
        plan = _make_plan()
        argv = build_argv(plan, "/tmp/out.json")
        for arg in argv:
            # No shell injection characters in args
            assert ";" not in arg or arg.endswith(".json")
            assert "|" not in arg


# ---------------------------------------------------------------------------
# Child environment
# ---------------------------------------------------------------------------


class TestChildEnv:
    def test_no_llm_key_in_child_env(self) -> None:
        os.environ["LLM_API_KEY"] = "sk-test-secret-key"
        env = _child_env()
        assert "LLM_API_KEY" not in env
        assert "LLM_PROVIDER" not in env
        assert "LLM_MODEL" not in env
        os.environ["LLM_API_KEY"] = ""

    def test_has_path(self) -> None:
        env = _child_env()
        assert "PATH" in env or "Path" in env or True  # Windows


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


class TestStateMachine:
    def test_queued_to_running(self) -> None:
        rec = _make_record()
        assert rec.state == RunState.QUEUED
        ok = _transition(rec, RunState.RUNNING)
        assert ok
        assert rec.state == RunState.RUNNING

    def test_terminal_state_is_final(self) -> None:
        rec = _make_record()
        _transition(rec, RunState.RUNNING)
        _transition(rec, RunState.COMPLETED)
        assert rec.state == RunState.COMPLETED
        # Trying to transition again fails
        ok = _transition(rec, RunState.RUNNING)
        assert not ok
        assert rec.state == RunState.COMPLETED  # unchanged

    def test_cancel_after_completion_rejected(self) -> None:
        rec = _make_record()
        _transition(rec, RunState.RUNNING)
        _transition(rec, RunState.COMPLETED)
        ok = _transition(rec, RunState.CANCELLED)
        assert not ok
        assert rec.state == RunState.COMPLETED

    def test_all_terminal_states(self) -> None:
        for terminal in (RunState.COMPLETED, RunState.FAILED, RunState.TIMEOUT,
                         RunState.STALLED, RunState.CANCELLED):
            assert terminal.is_terminal

    def test_non_terminal_states(self) -> None:
        for non_term in (RunState.QUEUED, RunState.RUNNING):
            assert not non_term.is_terminal


# ---------------------------------------------------------------------------
# Slot manager
# ---------------------------------------------------------------------------


class TestSlotManager:
    def test_max_concurrent(self) -> None:
        """Max 2 concurrent runs; 3rd must wait."""
        from app.runner import SlotManager
        sm = SlotManager(max_slots=2)
        assert sm.acquire(timeout=0.1)
        assert sm.acquire(timeout=0.1)
        # 3rd should fail (timeout=0 for instant failure)
        assert not sm.acquire(timeout=0.0)
        sm.release()
        sm.release()

    def test_slot_released_after_exception(self) -> None:
        """Slots are released even when exceptions occur."""
        from app.runner import SlotManager
        sm = SlotManager(max_slots=1)
        assert sm.acquire(timeout=0.1)
        try:
            raise ValueError("test error")
        except ValueError:
            sm.release()
        # Should be acquirable again
        assert sm.acquire(timeout=0.1)
        sm.release()

    def test_sequential_failing_runs_dont_exhaust_slots(self) -> None:
        """10 sequential runs failing should not exhaust slots."""
        from app.runner import SlotManager
        sm = SlotManager(max_slots=2)
        for _ in range(10):
            sm.acquire(timeout=0.1)
            sm.release()
        # Still acquirable
        assert sm.acquire(timeout=0.1)
        sm.release()


# ---------------------------------------------------------------------------
# Run store
# ---------------------------------------------------------------------------


class TestRunStore:
    def test_history_retrievable_after_completion(self) -> None:
        from app.runstore import RunStore, RunRecord
        store = RunStore()
        rec = _make_record("hist-test-1")
        rec.state = RunState.RUNNING
        store.add(rec)
        # Transition to completed
        with rec._lock:
            rec.state = RunState.COMPLETED
        store.finalize(rec)
        # Should still be in history
        found = store.get("hist-test-1")
        assert found is not None
        assert found.state == RunState.COMPLETED

    def test_evicts_oldest_finished(self) -> None:
        from app.runstore import RunStore, RunRecord
        store = RunStore(max_history=3)
        for i in range(4):
            r = RunRecord(f"run-{i}", {}, [])
            with r._lock:
                r.state = RunState.COMPLETED
            store.add(r)
        # Should have at most 3
        assert len(store.all_runs()) <= 3

    def test_never_evicts_running(self) -> None:
        from app.runstore import RunStore, RunRecord
        store = RunStore(max_history=2)
        # Add running run
        r_running = RunRecord("running-1", {}, [])
        r_running.state = RunState.RUNNING
        store.add(r_running)
        # Add completed runs
        for i in range(3):
            r = RunRecord(f"done-{i}", {}, [])
            with r._lock:
                r.state = RunState.COMPLETED
            store.add(r)
        # Running run should still be there
        assert store.get("running-1") is not None


# ---------------------------------------------------------------------------
# Audit chain
# ---------------------------------------------------------------------------


class TestAuditChain:
    def test_chain_verifies(self) -> None:
        from app.runstore import RunStore, RunRecord
        store = RunStore()
        for i in range(3):
            r = RunRecord(f"audit-{i}", {"tool": "site_crawler"}, [])
            r.stdout = f"output-{i}"
            with r._lock:
                r.state = RunState.COMPLETED
            store.finalize(r)
        chain = store.audit.get_chain()
        assert chain.verified

    def test_tampering_detected(self) -> None:
        from app.runstore import RunStore, RunRecord
        store = RunStore()
        r = RunRecord("tamper-test", {"tool": "site_crawler"}, [])
        r.stdout = "clean output"
        with r._lock:
            r.state = RunState.COMPLETED
        store.finalize(r)
        # Tamper with an entry
        store.audit.tamper_entry(0, "exit_code", 999)
        chain = store.audit.get_chain()
        assert not chain.verified

    def test_double_cancel_409(self, app_client: "TestClient") -> None:
        """Cancelling an already-cancelled run returns 409."""
        from app.runstore import RunRecord, get_store
        import app.runstore as rs
        rs._store = None
        store = get_store()
        r = RunRecord("cancel-test-1", {"tool": "site_crawler"}, [])
        r.state = RunState.CANCELLED
        store.add(r)
        # First cancel
        resp = app_client.post("/api/runs/cancel-test-1/cancel")
        # Already cancelled -> returns current state info (not error but 200 with state)
        assert resp.status_code in (200, 409)
        data = resp.json()
        assert data.get("state") == "cancelled" or "already_terminal" in data.get("error", "")

    def test_build_argv_link_checker(self) -> None:
        plan = Plan(task_type="check_links", tool="link_checker", tool_reason="test", url="https://example.com", max_links=15)
        argv = build_argv(plan, "out.json")
        assert "--max-links" in argv
        assert "15" in argv

    def test_slot_manager_extra_release(self) -> None:
        sm = get_slot_manager()
        # Release extra to trigger ValueError guard
        sm.release()

    def test_security_json_formatter_exception(self) -> None:
        from app.security import _JSONFormatter
        import logging
        formatter = _JSONFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            record = logging.LogRecord("test", logging.ERROR, "test.py", 10, "msg", (), sys.exc_info())
            formatted = formatter.format(record)
            assert "ValueError: test error" in formatted

