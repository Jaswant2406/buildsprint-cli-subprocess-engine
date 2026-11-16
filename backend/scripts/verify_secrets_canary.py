"""Verification script for secrets canary leak prevention.
Sets canary key: LLM_API_KEY="sk-CANARY-1234567890"
Runs:
1. Success crawl
2. Failure crawl
3. Injection crawl
Greps all outputs for canary string. Asserts 0 hits.
"""
from __future__ import annotations

import io
import json
import logging
import os
import sys
from pathlib import Path

# Add backend to path
_BACKEND = Path(__file__).parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

CANARY = "sk-CANARY-1234567890"
os.environ["LLM_API_KEY"] = CANARY
os.environ["APP_ENV"] = "test"
os.environ["ALLOW_LOCALHOST_FOR_TESTS"] = "1"

# Capture root logging output
log_stream = io.StringIO()
handler = logging.StreamHandler(log_stream)
logging.getLogger().addHandler(handler)

from fastapi.testclient import TestClient
from app.main import app
from app.runstore import get_store

client = TestClient(app)

# Stand up local demo site server
import http.server
import threading
_DEMO_DIR = _BACKEND.parent / "demo_site"
demo_server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), lambda *args, **kw: http.server.SimpleHTTPRequestHandler(*args, directory=str(_DEMO_DIR), **kw))
demo_port = demo_server.server_address[1]
demo_thread = threading.Thread(target=demo_server.serve_forever, daemon=True)
demo_thread.start()
base_url = f"http://127.0.0.1:{demo_port}"

all_text_artifacts: list[str] = []

print("=" * 80)
print(f"CANARY SECRETS AUDIT (Canary: {CANARY})")
print("=" * 80)

def run_chat_and_collect(prompt: str, label: str) -> str:
    print(f"Executing {label} crawl: prompt='{prompt}'...")
    resp = client.post("/api/chat", json={"prompt": prompt})
    sse_text = resp.text
    all_text_artifacts.append(sse_text)

    # Extract run_id from SSE stream
    run_id = None
    for line in sse_text.splitlines():
        if line.startswith("data: "):
            try:
                evt = json.loads(line[6:])
                run_id = evt.get("run_id")
                if run_id:
                    break
            except Exception:
                pass

    if run_id:
        # Collect /api/runs/{run_id}
        r_info = client.get(f"/api/runs/{run_id}")
        all_text_artifacts.append(r_info.text)

        # Collect /api/runs/{run_id}/logs
        r_logs = client.get(f"/api/runs/{run_id}/logs")
        all_text_artifacts.append(r_logs.text)

        # Collect /api/runs/{run_id}/report.md
        r_report = client.get(f"/api/runs/{run_id}/report.md")
        all_text_artifacts.append(r_report.text)

        # Collect /api/runs/{run_id}/ask
        r_ask = client.post(f"/api/runs/{run_id}/ask", json={"question": "What is the site about?"})
        all_text_artifacts.append(r_ask.text)

        # Store internal records
        store = get_store()
        rec = store.get(run_id)
        if rec:
            all_text_artifacts.append(rec.stdout or "")
            all_text_artifacts.append(rec.stderr or "")

    return run_id or ""

# 1. Success crawl
run_success = run_chat_and_collect(f"Crawl {base_url}/index.html and summarize", "SUCCESS")

# 2. Failure crawl
run_failure = run_chat_and_collect(f"Crawl {base_url}/non-existent-page-404.html", "FAILURE")

# 3. Injection crawl
run_injection = run_chat_and_collect(f"Crawl {base_url}/injection.html and summarize", "INJECTION")

# Also include server logs
all_text_artifacts.append(log_stream.getvalue())

# Grep for Canary
total_canary_hits = 0
for idx, text in enumerate(all_text_artifacts):
    if CANARY in text:
        total_canary_hits += 1
        print(f"CANARY LEAK FOUND in artifact index {idx}: {text[:100]}...")

demo_server.shutdown()

print("-" * 80)
print(f"Total Canary Occurrences Found: {total_canary_hits}")
print("-" * 80)

if total_canary_hits == 0:
    print("CANARY VERIFICATION PASSED: ZERO LEAKS DETECTED ACROSS ALL CHANNELS")
    sys.exit(0)
else:
    print("CANARY VERIFICATION FAILED: SECRET WAS LEAKED")
    sys.exit(1)
