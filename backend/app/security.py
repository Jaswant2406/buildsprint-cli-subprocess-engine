"""
Secret redaction and structured JSON logging.
"""
from __future__ import annotations

import json
import logging
import re
import sys
import time
from typing import Any

# ---------------------------------------------------------------------------
# Secret patterns to redact from all output
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"(api[_-]?key[\"':\s=]+)[A-Za-z0-9\-._~+/]{16,}", re.IGNORECASE),
    re.compile(r"(sk-[A-Za-z0-9]{20,})", re.IGNORECASE),  # OpenAI
    re.compile(r"(AIza[A-Za-z0-9\-_]{35})", re.IGNORECASE),  # Google
    re.compile(r"(ghp_[A-Za-z0-9]{36})", re.IGNORECASE),  # GitHub PAT
    re.compile(r"password[\"':\s=]+\S+", re.IGNORECASE),
    # LLM key patterns
    re.compile(r"LLM_API_KEY=\S+", re.IGNORECASE),
]

_REDACT = "[REDACTED]"


def redact(text: str) -> str:
    """Remove known secret patterns from text."""
    for pat in _SECRET_PATTERNS:
        text = pat.sub(lambda m: _REDACT, text)
    return text


def redact_dict(data: Any) -> Any:
    """Recursively redact secrets from dicts/lists/strings."""
    if isinstance(data, str):
        return redact(data)
    if isinstance(data, dict):
        return {k: redact_dict(v) for k, v in data.items()}
    if isinstance(data, list):
        return [redact_dict(item) for item in data]
    return data


# ---------------------------------------------------------------------------
# Structured JSON logging
# ---------------------------------------------------------------------------


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        run_id = getattr(record, "run_id", None)
        if run_id:
            entry["run_id"] = run_id

        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)

        extra_keys = set(record.__dict__) - {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
            "taskName",
        }
        for k in extra_keys:
            if not k.startswith("_"):
                entry[k] = redact_dict(getattr(record, k))

        return json.dumps(entry)


def configure_logging(level: str = "INFO") -> None:
    """Install JSON structured logging on the root logger."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JSONFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Suppress noisy uvicorn access logs
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
