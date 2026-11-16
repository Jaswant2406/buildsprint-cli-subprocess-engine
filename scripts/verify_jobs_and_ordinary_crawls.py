#!/usr/bin/env python3
"""
scripts/verify_jobs_and_ordinary_crawls.py

Runs the full suite of verification crawls requested by the user:
1. Mandatory example.com crawl (ordinary crawling verified)
2. Books to Scrape crawl (ordinary crawling verified)
3. Fake Jobs structured extraction crawl (structured job listings extracted)
4. Ordinary crawl preservation check (same site crawled without job prompt -> ordinary mode)
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath("backend"))
sys.path.insert(0, os.path.abspath("."))

from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def parse_sse(response) -> list[dict]:
    events = []
    current_event = None
    for line in response.iter_lines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("event:"):
            current_event = line[6:].strip()
        elif line.startswith("data:"):
            try:
                payload = json.loads(line[5:].strip())
                events.append({"event": current_event or payload.get("event"), "data": payload.get("data", payload)})
            except json.JSONDecodeError:
                pass
    return events


def print_sep(title: str) -> None:
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def main() -> None:
    os.environ["RATE_LIMIT_REQUESTS"] = "100"
    client = TestClient(app)

    # -----------------------------------------------------------------------
    # 1. Mandatory example.com Crawl
    # -----------------------------------------------------------------------
    print_sep("1. Mandatory example.com Crawl (Ordinary Crawl Test)")
    t0 = time.time()
    with client.stream("POST", "/api/chat", json={"prompt": "Crawl https://example.com, extract important information and return JSON"}) as r:
        assert r.status_code == 200
        events = parse_sse(r)

    res_evt = next((e for e in events if e.get("event") == "result"), None)
    assert res_evt is not None
    data1 = res_evt["data"]
    print(f"Run ID: {data1.get('run_id')}")
    print(f"Status: {data1.get('status')} ({data1.get('status_reason')})")
    print(f"Pages crawled: {data1.get('pages_crawled')}")
    print(f"Coverage score: {data1.get('coverage_score')}% ({data1.get('coverage_breakdown')})")
    print(f"Jobs result present: {data1.get('jobs') is not None} (expected: False/None)")
    print(f"Summary excerpt: {data1.get('summary', '')[:120]}...")
    assert data1.get("status") == "SUCCESS"
    assert data1.get("pages_crawled") == 1
    assert data1.get("jobs") is None, "Ordinary crawl must not generate jobs result"
    print("[PASS] Mandatory example.com crawl succeeded with ordinary extraction.")

    # -----------------------------------------------------------------------
    # 2. Books to Scrape Crawl
    # -----------------------------------------------------------------------
    print_sep("2. Books to Scrape Crawl (Ordinary Crawl Test)")
    t0 = time.time()
    with client.stream("POST", "/api/chat", json={"prompt": "Crawl https://books.toscrape.com/index.html max 3 pages and summarize content"}) as r:
        assert r.status_code == 200
        events = parse_sse(r)

    res_evt = next((e for e in events if e.get("event") == "result"), None)
    assert res_evt is not None
    data2 = res_evt["data"]
    print(f"Run ID: {data2.get('run_id')}")
    print(f"Status: {data2.get('status')}")
    print(f"Pages crawled: {data2.get('pages_crawled')}")
    print(f"Coverage score: {data2.get('coverage_score')}%")
    print(f"Jobs result present: {data2.get('jobs') is not None} (expected: False/None)")
    assert data2.get("status") == "SUCCESS"
    assert data2.get("pages_crawled") >= 1
    assert data2.get("jobs") is None
    print("[PASS] Books to Scrape crawl succeeded with ordinary extraction.")

    # -----------------------------------------------------------------------
    # 3. Fake Jobs Structured Extraction Crawl
    # -----------------------------------------------------------------------
    print_sep("3. Fake Jobs Structured Job Extraction Test")
    t0 = time.time()
    prompt = "Extract job listings and vacancies from https://realpython.github.io/fake-jobs/ max 3 pages"
    print(f"Prompt: '{prompt}'")
    with client.stream("POST", "/api/chat", json={"prompt": prompt}) as r:
        assert r.status_code == 200
        events = parse_sse(r)
    elapsed = time.time() - t0
    print(f"Elapsed time: {elapsed:.2f}s")

    plan_evt = next((e for e in events if e.get("event") == "plan"), None)
    assert plan_evt is not None
    print(f"Plan extract_focus: {plan_evt['data'].get('extract_focus')}")
    assert plan_evt["data"].get("extract_focus") == "jobs"

    res_evt = next((e for e in events if e.get("event") == "result"), None)
    assert res_evt is not None
    data3 = res_evt["data"]
    jobs = data3.get("jobs")
    print(f"Run ID: {data3.get('run_id')}")
    print(f"Status: {data3.get('status')}")
    print(f"Pages crawled: {data3.get('pages_crawled')}")
    print(f"Jobs result present: {jobs is not None}")
    assert jobs is not None, "Jobs result must be populated when user requests job listings"

    records = jobs.get("records", [])
    stats = jobs.get("stats", {})
    print(f"Total jobs extracted: {stats.get('total_jobs')}")
    print(f"Distinct companies:   {stats.get('companies')}")
    print(f"Distinct locations:   {stats.get('locations')}")
    print(f"With job URL:         {stats.get('with_job_url')}")
    print(f"With apply URL:       {stats.get('with_apply_url')}")
    print(f"With publication date:{stats.get('with_date')}")
    print(f"With description:     {stats.get('with_description')}")
    print(f"Crawled detail pages: {stats.get('crawled_detail_pages')}")
    print(f"Coverage note:        {stats.get('coverage_note')}")
    assert len(records) > 0, "Expected at least 1 extracted job record"
    assert stats.get("total_jobs") == len(records)
    assert stats.get("companies") > 0
    assert stats.get("locations") > 0
    assert stats.get("with_job_url") > 0
    assert stats.get("with_apply_url") == 0

    print("\nSample Extracted Job Records:")
    for idx, job in enumerate(records[:3], 1):
        print(f"  [{idx}] Title:       {job.get('title')}")
        print(f"      Company:     {job.get('company')}")
        print(f"      Location:    {job.get('location')}")
        print(f"      Date Posted: {job.get('date_posted')}")
        print(f"      Job URL:     {job.get('job_url')}")
        print(f"      Apply URL:   {job.get('apply_url')}")
        print(f"      Source URL:  {job.get('source_url')}")
        print(f"      Description: {str(job.get('description'))[:80]}...")
        assert job.get("source_url") is not None
        assert "title" in job and "company" in job and "location" in job

    print("\nFull Research Summary:")
    print(data3.get("summary"))
    print("\nKey Takeaways:")
    for t in data3.get("key_takeaways", []):
        print(f"  - {t}")

    print("[PASS] Fake Jobs structured extraction test succeeded with accurate records and statistics!")

    # -----------------------------------------------------------------------
    # 4. Ordinary Crawl of Fake Jobs (Preservation of General Behavior)
    # -----------------------------------------------------------------------
    print_sep("4. Ordinary Crawl of Fake Jobs (Preserve General Behavior)")
    with client.stream("POST", "/api/chat", json={"prompt": "Crawl https://realpython.github.io/fake-jobs/ max 1 page"}) as r:
        assert r.status_code == 200
        events = parse_sse(r)

    plan_evt = next((e for e in events if e.get("event") == "plan"), None)
    assert plan_evt is not None
    print(f"Plan extract_focus: '{plan_evt['data'].get('extract_focus')}' (expected empty)")
    assert plan_evt["data"].get("extract_focus") == ""

    res_evt = next((e for e in events if e.get("event") == "result"), None)
    assert res_evt is not None
    data4 = res_evt["data"]
    print(f"Status: {data4.get('status')}")
    print(f"Pages crawled: {data4.get('pages_crawled')}")
    print(f"Jobs result: {data4.get('jobs')} (expected None)")
    assert data4.get("jobs") is None, "General crawl must not trigger jobs extraction"
    print("[PASS] Ordinary crawl of the same site preserved general behavior without job extraction.")

    print_sep("ALL VERIFICATION SUITES COMPLETED WITH ZERO FAILURES")


if __name__ == "__main__":
    main()
