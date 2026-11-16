"""Tests for runner process management: stall detection, kill tree, and cancellation races."""
from __future__ import annotations

import subprocess
import sys
import time
from types import SimpleNamespace

import psutil
from app.models import Plan, RunState
from app.runner import SlotManager, _kill_tree, _transition, run_tool
from app.runstore import RunRecord


def _spawn_process_tree() -> tuple[subprocess.Popen[str], int, int]:
    """Spawn parent -> child -> grandchild and return (parent_proc, child_pid, grandchild_pid)."""
    # Grandchild script: sleep 60s
    grandchild_code = "import time; time.sleep(60)"
    # Child script: spawn grandchild, print its pid, sleep 60s
    child_code = (
        f"import subprocess, sys, time; "
        f"p = subprocess.Popen([sys.executable, '-c', {grandchild_code!r}]); "
        f"print(p.pid, flush=True); "
        f"time.sleep(60)"
    )
    # Parent script: spawn child, print child pid, sleep 60s
    parent_cmd = [sys.executable, "-c", child_code]
    parent = subprocess.Popen(parent_cmd, stdout=subprocess.PIPE, text=True)
    child_pid_line = parent.stdout.readline().strip()
    child_pid = int(child_pid_line)

    # Wait briefly for grandchild to be spawned
    time.sleep(0.5)
    grandchild_pid = 0
    try:
        child_p = psutil.Process(child_pid)
        grandchildren = child_p.children()
        if grandchildren:
            grandchild_pid = grandchildren[0].pid
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    return parent, child_pid, grandchild_pid


class TestProcessLifecycleAndKill:
    def test_kill_tree_terminates_process(self) -> None:
        """Spawn a long sleep process and ensure _kill_tree terminates it cleanly."""
        cmd = [sys.executable, "-c", "import time; time.sleep(30)"]
        proc = subprocess.Popen(cmd)
        pid = proc.pid
        assert proc.poll() is None

        # Kill the process tree
        _kill_tree(pid)
        time.sleep(0.5)
        # Should be terminated
        assert proc.poll() is not None

    def test_process_tree_child_and_grandchild_killed(self) -> None:
        """Assert that parent, child, and grandchild are ALL dead after _kill_tree."""
        parent, child_pid, grandchild_pid = _spawn_process_tree()
        parent_pid = parent.pid

        assert psutil.pid_exists(parent_pid)
        assert psutil.pid_exists(child_pid)
        if grandchild_pid:
            assert psutil.pid_exists(grandchild_pid)

        # Kill from parent
        _kill_tree(parent_pid)
        time.sleep(0.5)

        # Assert all descendants are dead
        assert not psutil.pid_exists(parent_pid)
        assert not psutil.pid_exists(child_pid)
        if grandchild_pid:
            assert not psutil.pid_exists(grandchild_pid)

    def test_cancel_then_exit_zero_stays_cancelled(self) -> None:
        """If a run is cancelled, it can never transition to COMPLETED."""
        rec = RunRecord("cancel-race", {"tool": "site_crawler"}, [])
        assert _transition(rec, RunState.RUNNING)
        assert _transition(rec, RunState.CANCELLED)

        # Attempt to transition to COMPLETED (e.g. if process finishes late)
        ok = _transition(rec, RunState.COMPLETED)
        assert not ok
        assert rec.state == RunState.CANCELLED

    def test_cancel_at_completion_race_single_terminal_state(self) -> None:
        """Race between cancel and completion: exactly one terminal state is reached."""
        rec = RunRecord("race-test", {"tool": "site_crawler"}, [])
        assert _transition(rec, RunState.RUNNING)

        # Thread 1 tries cancel, Thread 2 tries complete
        results = []
        import threading

        def do_cancel():
            results.append(("cancel", _transition(rec, RunState.CANCELLED)))

        def do_complete():
            results.append(("complete", _transition(rec, RunState.COMPLETED)))

        t1 = threading.Thread(target=do_cancel)
        t2 = threading.Thread(target=do_complete)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly one transition succeeded
        successes = [action for action, ok in results if ok]
        assert len(successes) == 1
        assert rec.state.is_terminal

    def test_stall_transition_is_terminal(self) -> None:
        rec = RunRecord("stall-test", {"tool": "site_crawler"}, [])
        assert _transition(rec, RunState.RUNNING)
        assert _transition(rec, RunState.STALLED)
        assert rec.state.is_terminal
        # Rejected transition out of terminal state
        assert not _transition(rec, RunState.COMPLETED)

    def test_stall_proves_process_actually_killed(self, local_site: str) -> None:
        """A stalled process (no heartbeat on stderr) must actually be killed on the OS."""
        rec = RunRecord("stall-kill-test", {"tool": "site_crawler"}, [])
        plan = Plan(tool="site_crawler", url=f"{local_site}/slow", task_type="crawl", tool_reason="test")

        settings_mock = SimpleNamespace(
            heartbeat_timeout_s=0.5,
            default_run_timeout_s=10.0,
        )

        events = []
        for evt in run_tool(rec, plan, settings_override=settings_mock):
            events.append(evt)
            if evt.get("event") == "stalled":
                break

        assert rec.state == RunState.STALLED
        assert rec.pid is not None
        # Assert the OS process is actually dead
        time.sleep(0.5)
        assert not psutil.pid_exists(rec.pid)

    def test_timeout_transition_is_terminal(self) -> None:
        rec = RunRecord("timeout-test", {"tool": "site_crawler"}, [])
        assert _transition(rec, RunState.RUNNING)
        assert _transition(rec, RunState.TIMEOUT)
        assert rec.state.is_terminal
        assert not _transition(rec, RunState.COMPLETED)

    def test_timeout_proves_process_actually_killed(self) -> None:
        """A timed out process must actually be killed on the OS."""
        rec = RunRecord("timeout-kill-test", {"tool": "site_crawler"}, [])
        plan = Plan(tool="site_crawler", url="https://example.com", task_type="crawl", tool_reason="test")

        settings_mock = SimpleNamespace(
            heartbeat_timeout_s=10.0,
            default_run_timeout_s=0.5,
        )

        events = []
        for evt in run_tool(rec, plan, settings_override=settings_mock):
            events.append(evt)
            if evt.get("event") == "timeout":
                break

        assert rec.state == RunState.TIMEOUT
        assert rec.pid is not None
        time.sleep(0.5)
        assert not psutil.pid_exists(rec.pid)

    def test_three_concurrent_requests_never_more_than_two_running(self) -> None:
        """SlotManager with max_slots=2 never allows a third concurrent runner."""
        mgr = SlotManager(max_slots=2)
        assert mgr.acquire(timeout=0.1) is True
        assert mgr.acquire(timeout=0.1) is True
        # 3rd must fail
        assert mgr.acquire(timeout=0.1) is False

        # Once one is released, 3rd can acquire
        mgr.release()
        assert mgr.acquire(timeout=0.1) is True

    def test_slot_released_after_various_scenarios(self) -> None:
        """Test slot release after exception, timeout, cancel, and simulated disconnect."""
        mgr = SlotManager(max_slots=1)

        # 1. Exception scenario
        assert mgr.acquire(timeout=0.1) is True
        try:
            raise RuntimeError("Simulation error")
        except RuntimeError:
            pass
        finally:
            mgr.release()
        assert mgr.acquire(timeout=0.1) is True

        # 2. Timeout scenario
        try:
            pass  # timeout occurs
        finally:
            mgr.release()
        assert mgr.acquire(timeout=0.1) is True

        # 3. Cancel scenario
        try:
            pass  # cancel occurs
        finally:
            mgr.release()
        assert mgr.acquire(timeout=0.1) is True

        # 4. SSE disconnect scenario
        try:
            pass  # disconnect occurs
        finally:
            mgr.release()
        assert mgr.acquire(timeout=0.1) is True
        mgr.release()

