"""
Test configuration, fixtures, and helpers.
"""
from __future__ import annotations

import http.server
import os
import threading
import time
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

# Set test environment BEFORE any app imports
os.environ["APP_ENV"] = "test"
os.environ["ALLOW_LOCALHOST_FOR_TESTS"] = "1"
os.environ["LLM_API_KEY"] = ""  # Ensure heuristic mode
os.environ["LLM_PROVIDER"] = ""

# ---------------------------------------------------------------------------
# Demo site HTTP server fixture
# ---------------------------------------------------------------------------

_DEMO_SITE_DIR = Path(__file__).parent.parent.parent / "demo_site"


class _SilentHTTPHandler(http.server.SimpleHTTPRequestHandler):
    requested_paths: list[str] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(_DEMO_SITE_DIR), **kwargs)  # type: ignore[call-arg]

    def do_GET(self) -> None:
        _SilentHTTPHandler.requested_paths.append(self.path)
        if self.path == "/redirect-loop":
            self.send_response(302)
            self.send_header("Location", "/redirect-loop")
            self.end_headers()
            return
        elif self.path == "/redirect-to-private":
            self.send_response(302)
            self.send_header("Location", "http://192.168.1.1/test")
            self.end_headers()
            return
        elif self.path == "/redirect-to-robots-disallowed":
            self.send_response(302)
            self.send_header("Location", "/private/index.html")
            self.end_headers()
            return
        elif self.path == "/non-html":
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(b"\x89PNG\r\n\x1a\n")
            return
        elif self.path == "/slow":
            time.sleep(5)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>Slow page</body></html>")
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        _SilentHTTPHandler.requested_paths.append(self.path)
        super().do_HEAD()

    def log_message(self, format: str, *args: object) -> None:
        pass  # Suppress output


@pytest.fixture(scope="session")
def local_site() -> Generator[str, None, None]:
    """Start a local HTTP server serving demo_site/ and yield its base URL."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SilentHTTPHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()


# ---------------------------------------------------------------------------
# App client fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def server_requests() -> Generator[list[str], None, None]:
    _SilentHTTPHandler.requested_paths.clear()
    yield _SilentHTTPHandler.requested_paths


@pytest.fixture
def app_client() -> Generator[TestClient, None, None]:
    """FastAPI test client with test environment."""
    # Reset global state
    import app.runstore as rs
    rs._store = None
    # Reset config
    import app.config as cfg
    cfg._settings = None

    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


# ---------------------------------------------------------------------------
# Injectable clock
# ---------------------------------------------------------------------------


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self._t = start

    def __call__(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


# ---------------------------------------------------------------------------
# CLI test helper
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_python() -> str:
    """Return the path to the venv Python interpreter."""
    import sys
    return sys.executable
