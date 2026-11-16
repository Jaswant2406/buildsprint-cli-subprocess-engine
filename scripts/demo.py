#!/usr/bin/env python3
"""
scripts/demo.py — BuildSprint Round 2 Live Demonstration Script.
Executes the mandatory end-to-end use case:
"Crawl https://example.com, extract the important information, give me a summary,
and return the extracted data in JSON format."

Streams events in real time and renders a clean, readable terminal report.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Add backend to path
_HERE = Path(__file__).parent
_ROOT = _HERE.parent
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    import httpx
except ImportError:
    httpx = None


PROMPT = "Crawl https://example.com, extract the important information, give me a summary, and return the extracted data in JSON format."
BASE_URL = "http://127.0.0.1:8000"


def run_via_server() -> bool:
    """Connect to live FastAPI server over SSE."""
    print(f"Connecting to live API at {BASE_URL}...")
    try:
        with httpx.Client(timeout=60.0) as client:
            # Check health
            h = client.get(f"{BASE_URL}/api/health")
            health_data = h.json()
            print(f"Server Health: OK (mode={health_data.get('llm_mode')}, version={health_data.get('version')})")

            print(f"\nSending task: \"{PROMPT}\"\n")
            print("-" * 70)
            print("STREAMING SSE EVENTS:")
            print("-" * 70)

            with client.stream("POST", f"{BASE_URL}/api/chat", json={"prompt": PROMPT}) as response:
                result_payload = None
                for line in response.iter_lines():
                    if not line:
                        continue
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                        print(f"  [EVENT] {event_type:<14}", end="")
                    elif line.startswith("data:"):
                        data_str = line[5:].strip()
                        try:
                            data_obj = json.loads(data_str)
                            data = data_obj.get("data", {})
                            if data_obj.get("event") == "spawned":
                                print(f"-> spawned PID {data.get('pid')} (tool={data.get('tool')})")
                            elif data_obj.get("event") == "plan":
                                print(f"-> tool={data.get('tool')}, max_pages={data.get('max_pages')}, reason=\"{data.get('tool_reason')}\"")
                            elif data_obj.get("event") == "progress":
                                print(f"-> {data.get('event')} ({data.get('url', '')})")
                            elif data_obj.get("event") == "result":
                                print("-> Final result received!")
                                result_payload = data
                            else:
                                print(f"-> {str(data)[:60]}")
                        except Exception:
                            print(f"-> {data_str[:60]}")

            if result_payload:
                render_report(result_payload)
                return True
            return False
    except Exception as e:
        print(f"Live server connection error: {e}")
        return False


def run_in_process() -> None:
    """Execute end-to-end pipeline in-process if server is not running."""
    print("Running in-process end-to-end pipeline...")
    from app.extractor import build_extracted
    from app.injection import scan_crawl_result
    from app.intent import parse_intent
    from app.postprocess import postprocess
    from app.runner import run_tool
    from app.runstore import RunRecord, get_store
    from app.summarizer import summarize
    from app.validators import validate_url

    print(f"\nTask: \"{PROMPT}\"")
    plan = parse_intent(PROMPT)
    print(f"Plan Parsed: tool={plan.tool}, reason=\"{plan.tool_reason}\", url={plan.url}")

    validated_url = validate_url(plan.url)
    print(f"URL Validated: {validated_url} (SSRF checks passed)")

    store = get_store()
    rec = RunRecord("demo-run-local", plan.model_dump(), [])
    store.add(rec)

    print("\nExecuting Subprocess Tool...")
    raw_result = None
    exit_code = None
    for evt in run_tool(rec, plan):
        event_name = evt.get("event")
        data = evt.get("data", {})
        if event_name == "_raw_result":
            raw_result = data.get("stdout")
            exit_code = data.get("exit_code")
        elif event_name == "spawned":
            print(f"  [SPAWNED] tool={data.get('tool')}, PID={data.get('pid')}")
        elif event_name == "progress":
            print(f"  [PROGRESS] {data}")
        else:
            print(f"  [EVENT] {event_name}")

    print("\nPost-Processing & Extraction...")
    pp = postprocess(raw_result or "", exit_code, rec.state, plan.model_dump())
    crawl_data = pp.get("data", {})

    evidence = build_extracted(crawl_data, plan.extract_focus)
    findings = scan_crawl_result(crawl_data)
    summary, takeaways = summarize(crawl_data)
    audit_hash = store.finalize(rec)

    result_dict = {
        "run_id": rec.run_id,
        "status": pp["status"].value,
        "status_reason": pp["status_reason"],
        "exit_code": exit_code,
        "duration_s": round(rec.duration_s(), 2),
        "pages_crawled": len(crawl_data.get("pages", [])),
        "summary": summary,
        "key_takeaways": takeaways,
        "json": crawl_data,
        "json_valid": pp["json_valid"],
        "coverage": pp.get("coverage").model_dump() if pp.get("coverage") else None,
        "security_findings": [f.model_dump() for f in findings],
        "evidence": evidence.model_dump(),
        "audit_hash": audit_hash,
    }
    render_report(result_dict)


def render_report(result: dict) -> None:
    print("\n" + "=" * 70)
    print("                      BUILDSPRINT EXECUTION REPORT                    ")
    print("=" * 70)
    print(f"Run ID:         {result.get('run_id')}")
    print(f"Status:         {result.get('status')} ({result.get('status_reason')})")
    print(f"Exit Code:      {result.get('exit_code')}")
    print(f"Duration:       {result.get('duration_s')}s")
    print(f"Pages Crawled:  {result.get('pages_crawled')}")
    print(f"JSON Valid:     {result.get('json_valid')}")

    cov = result.get("coverage")
    if cov:
        print(f"Coverage Score: {cov.get('score')}/100 — {cov.get('notes')}")

    print("\n" + "-" * 70)
    print("SUMMARY:")
    print("-" * 70)
    print(result.get("summary", "N/A"))

    takeaways = result.get("key_takeaways", [])
    if takeaways:
        print("\nKey Takeaways:")
        for t in takeaways:
            print(f"  * {t}")

    evidence = result.get("evidence", {})
    if evidence:
        print("\n" + "-" * 70)
        print("STRUCTURED EVIDENCE (ALL FACTS WITH PROVENANCE):")
        print("-" * 70)
        print(f"Site Name:   {evidence.get('site_name')}")
        print(f"Domain:      {evidence.get('domain')}")
        print(f"Language:    {evidence.get('language')}")
        if evidence.get("main_topics"):
            print(f"Main Topics: {', '.join(evidence.get('main_topics'))}")

    sec = result.get("security_findings", [])
    print("\n" + "-" * 70)
    print(f"SECURITY FINDINGS ({len(sec)} detected):")
    print("-" * 70)
    if sec:
        for s in sec:
            print(f"  ! Page: {s.get('page_url')} — Pattern: {s.get('pattern')}")
    else:
        print("  ✓ No injection or security threats detected in crawled content.")

    print("\n" + "-" * 70)
    print(f"TAMPER-EVIDENT AUDIT HASH: {result.get('audit_hash')}")
    print("=" * 70 + "\n")


def main() -> int:
    if httpx:
        try:
            r = httpx.get(f"{BASE_URL}/api/health", timeout=1.0)
            if r.status_code == 200:
                success = run_via_server()
                return 0 if success else 1
        except Exception:
            pass

    run_in_process()
    return 0


if __name__ == "__main__":
    sys.exit(main())
