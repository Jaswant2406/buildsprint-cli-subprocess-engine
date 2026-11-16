"""
Bounded run history with tamper-evident audit chain.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any

from app.models import AuditChain, AuditEntry, RunState
from app.security import get_logger, redact

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Run record
# ---------------------------------------------------------------------------


class RunRecord:
    """Mutable record for a single run."""

    def __init__(self, run_id: str, plan_dict: dict[str, Any], argv: list[str]) -> None:
        self.run_id = run_id
        self.plan = plan_dict
        self.argv = argv
        self.state: RunState = RunState.QUEUED
        self.stdout: str = ""
        self.stderr: str = ""
        self.exit_code: int | None = None
        self.events: list[dict[str, Any]] = []
        self.result: dict[str, Any] | None = None
        self.start_time: float | None = None
        self.end_time: float | None = None
        self.pid: int | None = None
        self._lock = threading.Lock()

    def duration_s(self) -> float:
        if self.start_time is None:
            return 0.0
        end = self.end_time or time.monotonic()
        return end - self.start_time

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "plan": self.plan,
            "argv": self.argv,
            "state": self.state.value,
            "exit_code": self.exit_code,
            "duration_s": round(self.duration_s(), 3),
            "pid": self.pid,
            "stdout": redact(self.stdout),
            "stderr": redact(self.stderr),
            "events": self.events,
            "result": self.result,
        }

    def add_event(self, event: str, data: dict[str, Any] | None = None) -> None:
        self.events.append({
            "event": event,
            "data": data or {},
            "ts": time.time(),
        })


# ---------------------------------------------------------------------------
# Audit chain
# ---------------------------------------------------------------------------


class _AuditLog:
    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._prev_hash = "0" * 64

    def append(self, record: RunRecord) -> str:
        with self._lock:
            stdout_sha = hashlib.sha256(record.stdout.encode()).hexdigest()
            entry_data = {
                "run_id": record.run_id,
                "tool": record.plan.get("tool", ""),
                "argv": record.argv,
                "exit_code": record.exit_code,
                "stdout_sha256": stdout_sha,
                "state": record.state.value,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "prev_hash": self._prev_hash,
            }
            blob = json.dumps(entry_data, sort_keys=True).encode()
            h = hashlib.sha256(blob).hexdigest()
            entry_data["hash"] = h
            self._entries.append(entry_data)
            self._prev_hash = h
            return h

    def get_chain(self) -> AuditChain:
        with self._lock:
            entries = list(self._entries)

        verified = True
        prev = "0" * 64
        for e in entries:
            check = dict(e)
            stored_hash = check.pop("hash")
            check["prev_hash"] = prev
            blob = json.dumps(check, sort_keys=True).encode()
            computed = hashlib.sha256(blob).hexdigest()
            if computed != stored_hash:
                verified = False
                break
            prev = stored_hash

        return AuditChain(
            entries=[AuditEntry(**e) for e in entries],
            records=[AuditEntry(**e) for e in entries],
            length=len(entries),
            verified=verified,
        )

    def tamper_entry(self, index: int, field: str, value: Any) -> None:
        """For testing only: corrupt an entry."""
        with self._lock:
            if 0 <= index < len(self._entries):
                self._entries[index][field] = value


# ---------------------------------------------------------------------------
# Run store
# ---------------------------------------------------------------------------


class RunStore:
    MAX_HISTORY = 100

    def __init__(self, max_history: int = 100) -> None:
        self.MAX_HISTORY = max_history
        self._runs: OrderedDict[str, RunRecord] = OrderedDict()
        self._lock = threading.Lock()
        self.audit = _AuditLog()

    def add(self, record: RunRecord) -> None:
        with self._lock:
            self._runs[record.run_id] = record
            self._evict()

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._runs.get(run_id)

    def all_runs(self) -> list[RunRecord]:
        with self._lock:
            return list(self._runs.values())

    def finalize(self, record: RunRecord) -> str:
        """Record final state in audit log. Returns audit hash."""
        return self.audit.append(record)

    def _evict(self) -> None:
        """Evict oldest FINISHED runs if over limit. Never evict running runs."""
        while len(self._runs) > self.MAX_HISTORY:
            for run_id, rec in self._runs.items():
                if rec.state.is_terminal:
                    del self._runs[run_id]
                    break
            else:
                break  # All running; can't evict


# Global singleton
_store: RunStore | None = None


def get_store() -> RunStore:
    global _store
    if _store is None:
        _store = RunStore()
    return _store
