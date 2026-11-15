"""
Tool registry, subprocess execution, state machine, slot manager.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, AsyncIterator, Iterator

import psutil

from app.config import get_settings
from app.models import Plan, RunState
from app.runstore import RunRecord
from app.security import get_logger, redact

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

_CLI_DIR = Path(__file__).parent.parent.parent / "cli"


def _cli_path(name: str) -> str:
    return str(_CLI_DIR / f"{name}.py")


TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "site_crawler": {
        "name": "site_crawler",
        "script": "site_crawler.py",
        "description": "BFS web crawler: extracts titles, headings, text, links, emails, phones.",
        "why_chosen": "Use for crawl, extract, summarize tasks requiring full page content.",
        "allowed_args": {
            "--url": {"type": "str", "required": True},
            "--max-pages": {"type": "int", "min": 1, "max": 25, "default": 10},
            "--max-depth": {"type": "int", "min": 1, "max": 3, "default": 2},
            "--out-file": {"type": "str"},
            "--timeout": {"type": "int", "min": 5, "max": 120, "default": 60},
        },
        "exit_codes": {
            0: "success",
            1: "generic error",
            2: "partial success (some pages failed)",
            3: "robots-blocked",
            4: "unreachable",
        },
    },
    "link_checker": {
        "name": "link_checker",
        "script": "link_checker.py",
        "description": "Checks all links on a page for broken/working status via HEAD/GET.",
        "why_chosen": "Use for broken link detection, 404 checks, link status tasks.",
        "allowed_args": {
            "--url": {"type": "str", "required": True},
            "--max-links": {"type": "int", "min": 1, "max": 50, "default": 25},
            "--out-file": {"type": "str"},
            "--timeout": {"type": "int", "min": 5, "max": 120, "default": 60},
        },
        "exit_codes": {
            0: "all links working",
            1: "other error",
            2: "some broken or error links",
            3: "robots-blocked",
            4: "unreachable",
        },
    },
}


def build_argv(plan: Plan, out_file: str) -> list[str]:
    """Build argv list from a validated Plan. Never interpolates prompt text."""
    tool = plan.tool
    if tool not in TOOL_REGISTRY:
        raise ValueError(f"Unknown tool: {tool!r}")

    cli_script = str(_CLI_DIR / TOOL_REGISTRY[tool]["script"])
    argv = [sys.executable, cli_script, "--url", plan.url, "--out-file", out_file]

    if tool == "site_crawler":
        argv += ["--max-pages", str(plan.max_pages)]
        argv += ["--max-depth", str(plan.max_depth)]
        argv += ["--timeout", "60"]
    elif tool == "link_checker":
        argv += ["--max-links", str(plan.max_links)]
        argv += ["--timeout", "60"]

    return argv


# ---------------------------------------------------------------------------
# Slot manager (semaphore for max concurrent runs)
# ---------------------------------------------------------------------------


class SlotManager:
    def __init__(self, max_slots: int = 2) -> None:
        self._sem = threading.BoundedSemaphore(max_slots)
        self._max = max_slots

    def acquire(self, timeout: float = 30.0) -> bool:
        return self._sem.acquire(timeout=timeout)

    def release(self) -> None:
        try:
            self._sem.release()
        except ValueError:
            pass  # Already at max; ignore


_slot_manager: SlotManager | None = None


def get_slot_manager() -> SlotManager:
    global _slot_manager
    if _slot_manager is None:
        settings = get_settings()
        _slot_manager = SlotManager(settings.max_concurrent_runs)
    return _slot_manager


# ---------------------------------------------------------------------------
# Child process helpers
# ---------------------------------------------------------------------------

_MIN_ENV_KEYS = {"PATH", "SYSTEMROOT", "TEMP", "TMP", "HOMEDRIVE", "HOMEPATH",
                 "WINDIR", "COMSPEC", "PROGRAMFILES"}  # Windows essentials


def _child_env() -> dict[str, str]:
    """Minimal environment for child — explicitly NO LLM key."""
    env: dict[str, str] = {}
    for key in _MIN_ENV_KEYS:
        val = os.environ.get(key)
        if val:
            env[key] = val
    # APP_ENV for test mode
    app_env = os.environ.get("APP_ENV", "production")
    env["APP_ENV"] = app_env
    if app_env == "test":
        allow = os.environ.get("ALLOW_LOCALHOST_FOR_TESTS", "")
        if allow:
            env["ALLOW_LOCALHOST_FOR_TESTS"] = allow
    # Explicitly excluded: LLM_API_KEY, LLM_PROVIDER, LLM_MODEL
    return env


def _kill_tree(pid: int) -> None:
    """SIGTERM process group, then SIGKILL, verify all dead."""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        procs = [parent] + children

        if sys.platform != "win32":
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        else:
            for p in procs:
                try:
                    p.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        _, alive = psutil.wait_procs(procs, timeout=3)
        for p in alive:
            try:
                if sys.platform != "win32":
                    p.kill()
                else:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(p.pid)],
                        capture_output=True, timeout=5
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied, FileNotFoundError):
                pass

        # Verify
        _, still_alive = psutil.wait_procs(procs, timeout=2)
        if still_alive:
            logger.warning("Orphan processes remain", extra={"pids": [p.pid for p in still_alive]})
        else:
            logger.info("All child processes killed", extra={"pid": pid})
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass


# ---------------------------------------------------------------------------
# State machine transitions
# ---------------------------------------------------------------------------


def _transition(record: RunRecord, new_state: RunState) -> bool:
    """
    Atomically transition to new_state.
    Returns True if successful; False if the run is already in a terminal state.
    """
    with record._lock:
        if record.state.is_terminal:
            logger.debug(
                f"Rejected transition {record.state} -> {new_state} (already terminal)",
                extra={"run_id": record.run_id},
            )
            return False
        record.state = new_state
        return True


# ---------------------------------------------------------------------------
# Main run executor
# ---------------------------------------------------------------------------


def run_tool(
    record: RunRecord,
    plan: Plan,
    settings_override: Any = None,
) -> Iterator[dict[str, Any]]:
    """
    Execute a tool as a subprocess. Yields progress event dicts.
    Uses record._lock for state transitions.
    This is a blocking generator — wrap in a thread for async use.
    """
    settings = settings_override or get_settings()
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        out_file = tf.name

    argv = build_argv(plan, out_file)
    record.argv = argv

    logger.info("Spawning tool", extra={"run_id": record.run_id, "argv": argv})

    env = _child_env()
    cwd = str(_CLI_DIR)

    # Apply resource limits (Linux only)
    def _preexec() -> None:  # type: ignore[return]
        if sys.platform != "win32":
            try:
                import resource
                resource.setrlimit(resource.RLIMIT_CPU, (30, 60))
                resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
                resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
                os.setsid()  # New process group
            except Exception:
                pass

    popen_kwargs: dict[str, Any] = {
        "args": argv,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "env": env,
        "cwd": cwd,
        "shell": False,  # NEVER True
    }
    if sys.platform != "win32":
        popen_kwargs["preexec_fn"] = _preexec
        popen_kwargs["start_new_session"] = False
    else:
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    if not _transition(record, RunState.RUNNING):
        yield {"event": "cancelled", "data": {"reason": "pre-spawn cancel"}}
        return

    record.start_time = time.monotonic()
    proc: subprocess.Popen[bytes] | None = None

    try:
        proc = subprocess.Popen(**popen_kwargs)
        record.pid = proc.pid
        yield {"event": "spawned", "data": {"tool": plan.tool, "argv": argv, "pid": proc.pid}}

        stderr_lines: list[str] = []
        stdout_chunks: list[bytes] = []

        # Read stderr line by line in a thread
        last_heartbeat = time.monotonic()
        heartbeat_timeout = settings.heartbeat_timeout_s
        overall_timeout = settings.default_run_timeout_s

        def _read_stderr() -> None:
            nonlocal last_heartbeat
            assert proc is not None
            for raw in proc.stderr:  # type: ignore[union-attr]
                line = raw.decode(errors="replace").rstrip()
                stderr_lines.append(line)
                last_heartbeat = time.monotonic()
                try:
                    evt = json.loads(line)
                    record.add_event("progress", evt)
                except json.JSONDecodeError:
                    pass

        def _read_stdout() -> None:
            assert proc is not None
            if proc.stdout:
                while True:
                    chunk = proc.stdout.read(4096)
                    if not chunk:
                        break
                    stdout_chunks.append(chunk)

        stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
        stderr_thread.start()

        stdout_thread = threading.Thread(target=_read_stdout, daemon=True)
        stdout_thread.start()

        emitted_stderr_idx = 0

        # Poll loop
        while True:
            # Check overall timeout
            elapsed = time.monotonic() - record.start_time
            if elapsed > overall_timeout:
                if _transition(record, RunState.TIMEOUT):
                    logger.warning("Run timed out", extra={"run_id": record.run_id})
                    _kill_tree(proc.pid)
                    yield {"event": "timeout", "data": {"elapsed_s": round(elapsed, 1)}}
                return

            # Check heartbeat
            now = time.monotonic()
            if (now - last_heartbeat) > heartbeat_timeout:
                if _transition(record, RunState.STALLED):
                    logger.warning("Run stalled (no heartbeat)", extra={"run_id": record.run_id})
                    _kill_tree(proc.pid)
                    yield {"event": "stalled", "data": {"elapsed_s": round(elapsed, 1)}}
                return

            # Check if cancelled
            if record.state == RunState.CANCELLED:
                _kill_tree(proc.pid)
                yield {"event": "cancelled", "data": {}}
                return

            # Emit any new progress events
            while emitted_stderr_idx < len(stderr_lines):
                line = stderr_lines[emitted_stderr_idx]
                emitted_stderr_idx += 1
                try:
                    evt = json.loads(line)
                    yield {"event": "progress", "data": evt}
                except json.JSONDecodeError:
                    pass

            ret = proc.poll()
            if ret is not None:
                break

            time.sleep(0.1)

        stderr_thread.join(timeout=5)
        stdout_thread.join(timeout=5)

        # Emit any trailing progress events
        while emitted_stderr_idx < len(stderr_lines):
            line = stderr_lines[emitted_stderr_idx]
            emitted_stderr_idx += 1
            try:
                evt = json.loads(line)
                yield {"event": "progress", "data": evt}
            except json.JSONDecodeError:
                pass

        record.stderr = redact("\n".join(stderr_lines))
        record.exit_code = proc.returncode

        # Read stdout
        raw_stdout = b"".join(stdout_chunks)
        record.stdout = redact(raw_stdout.decode(errors="replace"))

        # Prefer out_file result
        result_json: str | None = None
        try:
            with open(out_file, encoding="utf-8") as f:
                result_json = f.read()
        except (FileNotFoundError, OSError):
            result_json = record.stdout

        # Only transition to COMPLETED if not already terminal (e.g. cancelled)
        if not record.state.is_terminal:
            _transition(record, RunState.COMPLETED)

        record.end_time = time.monotonic()
        yield {
            "event": "_raw_result",
            "data": {"stdout": result_json, "exit_code": proc.returncode},
        }

    except Exception as e:
        logger.exception("Runner error", extra={"run_id": record.run_id})
        if proc is not None:
            try:
                _kill_tree(proc.pid)
            except Exception:
                pass
        if not record.state.is_terminal:
            _transition(record, RunState.FAILED)
        record.end_time = time.monotonic()
        yield {"event": "error", "data": {"error": str(e)}}
    finally:
        try:
            os.unlink(out_file)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Async wrapper
# ---------------------------------------------------------------------------


async def run_tool_async(
    record: RunRecord,
    plan: Plan,
) -> AsyncIterator[dict[str, Any]]:
    """Async generator wrapping the blocking run_tool generator."""
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    def _worker() -> None:
        try:
            for evt in run_tool(record, plan):
                loop.call_soon_threadsafe(queue.put_nowait, evt)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    while True:
        item = await queue.get()
        if item is None:
            break
        yield item

    thread.join(timeout=5)
