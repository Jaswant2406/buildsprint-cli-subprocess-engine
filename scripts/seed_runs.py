#!/usr/bin/env python3
"""
scripts/seed_runs.py — Seeds the backend with real runs:
1. Mandatory crawl (https://example.com) -> SUCCESS
2. Bad domain -> FAILED
3. Injection page -> SUCCESS/PARTIAL with security_findings
4. Cancelled run -> CANCELLED
"""
from __future__ import annotations

import http.server
from pathlib import Path
import threading
import time
import httpx

BASE_URL = "http://127.0.0.1:8000"
DEMO_DIR = Path(__file__).parent.parent / "demo_site"


class DemoHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DEMO_DIR), **kwargs)

    def log_message(self, format, *args):
        pass


def start_demo_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 8899), DemoHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def consume_chat(prompt: str) -> dict:
    with httpx.Client(timeout=30.0) as client:
        res = client.post(f"{BASE_URL}/api/chat", json={"prompt": prompt})
        text = res.text
        events = []
        result_payload = None
        error_payload = None
        run_id = None
        for block in text.split("\n\n"):
            if not block.strip():
                continue
            for line in block.splitlines():
                if line.startswith("data: "):
                    import json
                    try:
                        parsed = json.loads(line[6:])
                        if "run_id" in parsed and not run_id:
                            run_id = parsed["run_id"]
                        if parsed.get("event") == "result":
                            result_payload = parsed.get("data")
                        elif parsed.get("event") == "error":
                            error_payload = parsed.get("data")
                    except Exception:
                        pass
        return {"run_id": run_id, "result": result_payload, "error": error_payload}


def main():
    print("Seeding backend with real runs...")

    # 1. Mandatory crawl
    print("1. Running mandatory crawl (https://example.com)...")
    r1 = consume_chat("Crawl https://example.com, extract the important information, give me a summary, and return the extracted data in JSON format.")
    print(f"   -> Run ID: {r1.get('run_id')} (Status: {(r1.get('result') or {}).get('status')})")

    # 2. Bad domain
    print("2. Running bad domain crawl...")
    r2 = consume_chat("Crawl https://this-domain-does-not-exist-123454321.com and extract information.")
    status_or_err = (r2.get('result') or {}).get('status') or (r2.get('error') or {}).get('error')
    print(f"   -> Run ID: {r2.get('run_id')} (Status/Error: {status_or_err})")

    # 3. Injection page
    print("3. Starting demo server for injection page...")
    start_demo_server()
    time.sleep(0.5)
    print("   Running injection page crawl...")
    r3 = consume_chat("Crawl http://127.0.0.1:8899/injection.html and summarize the contents")
    findings = (r3.get('result') or {}).get('security_findings', [])
    print(f"   -> Run ID: {r3.get('run_id')} (Findings: {len(findings)}, Status: {(r3.get('result') or {}).get('status')})")

    # 4. Cancelled run
    print("4. Starting run to cancel...")
    with httpx.Client(timeout=10.0) as client:
        # Start a stream in a thread, then call cancel
        import json
        with client.stream("POST", f"{BASE_URL}/api/chat", json={"prompt": "Crawl https://example.com and check links"}) as resp:
            cancel_id = None
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    cancel_id = data.get("run_id")
                    if cancel_id:
                        break
            if cancel_id:
                time.sleep(0.1)
                c_res = client.post(f"{BASE_URL}/api/runs/{cancel_id}/cancel")
                print(f"   -> Run ID: {cancel_id} cancelled with status {c_res.status_code}")

    print("Seeding complete.")


if __name__ == "__main__":
    main()
