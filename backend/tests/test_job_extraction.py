"""
Tests for structured job extraction module (app.job_extractor),
URL validation, partial coverage reporting, and research summary improvements.

Verifies:
1. Structured record extraction (title, company, location, date, description, job_url, apply_url, source_url).
2. Detail page URLs are assigned to job_url, NOT apply_url.
3. validate_apply_url rejects dangerous schemes (javascript, file, data), SSRF targets (private IPs), and self-links.
4. Missing fields remain None (null) and are never fabricated.
5. Statistics and coverage notes honestly disclose crawl limits and partial coverage without inventing unvisited counts.
6. Non-job crawl data produces 0 records without errors.
7. Job extraction validation errors in main.py are caught and reported in errors without crashing generic crawl.
8. Professional 5-section heuristic research summary pipeline.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from app.intent import parse_intent
from app.job_extractor import extract_jobs_from_crawl, validate_apply_url
from app.models import JobExtractionResult
from app.summarizer import _heuristic_summarize
from fastapi.testclient import TestClient


class TestJobExtraction:
    def test_extract_jobs_from_detail_page(self) -> None:
        crawl_data: dict[str, Any] = {
            "site": "https://realpython.github.io/fake-jobs/",
            "pages": [
                {
                    "url": "https://realpython.github.io/fake-jobs/jobs/senior-python-developer-0.html",
                    "title": "Fake Python",
                    "h1_headings": ["Fake Python", "Senior Python Developer"],
                    "h2_headings": ["Payne, Roberts and Davis"],
                    "main_text": (
                        "Fake Python Fake Jobs for Your Web Scraping Journey "
                        "Senior Python Developer Payne, Roberts and Davis "
                        "Professional asset web application environmentally friendly detail-oriented asset. "
                        "Coordinate educational dashboard agile employ growth opportunity. "
                        "Location: Stewartbury, AA Posted: 2021-04-08"
                    ),
                }
            ],
        }

        result = extract_jobs_from_crawl(crawl_data)
        assert result["stats"]["total_jobs"] == 1
        assert result["stats"]["companies"] == 1
        assert result["stats"]["locations"] == 1
        assert result["stats"]["with_job_url"] == 1
        # In Fake Jobs, detail page is NOT an external apply portal
        assert result["stats"]["with_apply_url"] == 0
        assert result["stats"]["with_date"] == 1
        assert result["stats"]["with_description"] == 1
        assert result["stats"]["crawled_detail_pages"] == 1

        job = result["records"][0]
        assert job["title"] == "Senior Python Developer"
        assert job["company"] == "Payne, Roberts and Davis"
        assert job["location"] == "Stewartbury, AA"
        assert job["date_posted"] == "2021-04-08"
        assert "Professional asset web application" in (job["description"] or "")
        # Detail URL must be job_url, NOT apply_url
        assert job["job_url"] == "https://realpython.github.io/fake-jobs/jobs/senior-python-developer-0.html"
        assert job["apply_url"] is None
        assert job["source_url"] == "https://realpython.github.io/fake-jobs/jobs/senior-python-developer-0.html"

    def test_extract_jobs_from_listing_cards_nulls_missing_fields(self) -> None:
        crawl_data: dict[str, Any] = {
            "site": "https://realpython.github.io/fake-jobs/",
            "pages": [
                {
                    "url": "https://realpython.github.io/fake-jobs/",
                    "title": "Fake Python",
                    "h1_headings": ["Fake Python"],
                    "h2_headings": [
                        "Senior Python Developer",
                        "Energy engineer",
                        "Legal executive",
                    ],
                    "main_text": (
                        "Senior Python Developer Payne, Roberts and Davis Stewartbury, AA 2021-04-08 Learn Apply "
                        "Energy engineer Vasquez-Davidson Christopherville, AA 2021-04-08 Learn Apply "
                        "Legal executive Jackson, Chambers and Levy Port Ericaburgh, AA 2021-04-08 Learn Apply "
                    ),
                }
            ],
        }

        result = extract_jobs_from_crawl(crawl_data)
        assert result["stats"]["total_jobs"] == 3
        assert result["stats"]["companies"] == 3
        assert result["stats"]["locations"] == 3
        # Listing cards do not have full descriptions or detail URLs visited yet; must be None
        assert result["stats"]["with_description"] == 0
        assert result["stats"]["with_job_url"] == 0
        assert result["stats"]["with_apply_url"] == 0
        assert result["stats"]["crawled_detail_pages"] == 0

        for r in result["records"]:
            assert r["title"] is not None
            assert r["company"] is not None
            assert r["location"] is not None
            assert r["date_posted"] == "2021-04-08"
            assert r["description"] is None, "Missing description must be None, not fabricated"
            assert r["job_url"] is None, "Unvisited job_url must be None, not fabricated"
            assert r["apply_url"] is None, "Missing apply_url must be None, not fabricated"
            assert r["source_url"] == "https://realpython.github.io/fake-jobs/"

    def test_merges_detail_enrichment_into_listing_card(self) -> None:
        crawl_data: dict[str, Any] = {
            "site": "https://realpython.github.io/fake-jobs/",
            "pages": [
                # Page 0: Index card
                {
                    "url": "https://realpython.github.io/fake-jobs/",
                    "h1_headings": ["Fake Python"],
                    "h2_headings": ["Senior Python Developer"],
                    "main_text": "Senior Python Developer Payne, Roberts and Davis Stewartbury, AA 2021-04-08 Learn Apply",
                },
                # Page 1: Detail page for the same job
                {
                    "url": "https://realpython.github.io/fake-jobs/jobs/senior-python-developer-0.html",
                    "h1_headings": ["Fake Python", "Senior Python Developer"],
                    "h2_headings": ["Payne, Roberts and Davis"],
                    "main_text": "Senior Python Developer Payne, Roberts and Davis Full description of the python role. Location: Stewartbury, AA Posted: 2021-04-08",
                },
            ],
        }

        result = extract_jobs_from_crawl(crawl_data)
        # Should merge without duplicating the job
        assert result["stats"]["total_jobs"] == 1
        assert result["stats"]["crawled_detail_pages"] == 1
        job = result["records"][0]
        assert job["title"] == "Senior Python Developer"
        assert job["company"] == "Payne, Roberts and Davis"
        assert job["description"] == "Full description of the python role."
        assert job["job_url"] == "https://realpython.github.io/fake-jobs/jobs/senior-python-developer-0.html"
        assert job["apply_url"] is None

    def test_partial_coverage_reporting_and_disclosure(self) -> None:
        crawl_data: dict[str, Any] = {
            "site": "https://realpython.github.io/fake-jobs/",
            "pages": [
                {
                    "url": "https://realpython.github.io/fake-jobs/",
                    "h1_headings": ["Fake Python"],
                    "h2_headings": ["Role A", "Role B", "Role C"],
                    "main_text": (
                        "Role A Acme Corp Austin, TX 2024-01-01 Apply "
                        "Role B Acme Corp Austin, TX 2024-01-01 Apply "
                        "Role C Acme Corp Austin, TX 2024-01-01 Apply"
                    ),
                },
                {
                    "url": "https://realpython.github.io/fake-jobs/jobs/role-a.html",
                    "h1_headings": ["Fake Python", "Role A"],
                    "h2_headings": ["Acme Corp"],
                    "main_text": "Role A Acme Corp Detailed description. Location: Austin, TX Posted: 2024-01-01",
                },
            ],
        }

        result = extract_jobs_from_crawl(crawl_data)
        stats = result["stats"]
        assert stats["total_jobs"] == 3
        assert stats["crawled_detail_pages"] == 1
        assert stats["is_partial_crawl"] is True
        assert "3 job records extracted from a 2-page crawl sample (1 detail page(s) visited)" in stats["coverage_note"]
        assert "Crawl limit constraints (max_pages=2) bound this research" in stats["coverage_note"]

    def test_validate_apply_url(self) -> None:
        detail_url = "https://example.com/jobs/dev-1"

        # Valid external portal URLs
        assert validate_apply_url("https://boards.greenhouse.io/example/jobs/123", detail_url) == "https://boards.greenhouse.io/example/jobs/123"
        assert validate_apply_url("https://jobs.lever.co/example/abc", detail_url) == "https://jobs.lever.co/example/abc"
        assert validate_apply_url("https://example.workday.com/apply", detail_url) == "https://example.workday.com/apply"

        # Self links matching job_url must be rejected
        assert validate_apply_url("https://example.com/jobs/dev-1", detail_url) is None
        assert validate_apply_url("https://example.com/jobs/dev-1/", detail_url) is None

        # Dangerous schemes
        assert validate_apply_url("javascript:alert(1)", detail_url) is None
        assert validate_apply_url("file:///etc/passwd", detail_url) is None
        assert validate_apply_url("data:text/html,payload", detail_url) is None
        assert validate_apply_url("mailto:apply@example.com", detail_url) is None

        # SSRF / Private IP addresses
        assert validate_apply_url("http://127.0.0.1/apply", detail_url) is None
        assert validate_apply_url("http://localhost/apply", detail_url) is None
        assert validate_apply_url("http://10.0.0.1/apply", detail_url) is None
        assert validate_apply_url("http://192.168.1.1/apply", detail_url) is None
        assert validate_apply_url("http://169.254.169.254/latest/meta-data", detail_url) is None

        # Empty / None / malformed
        assert validate_apply_url("", detail_url) is None
        assert validate_apply_url(None, detail_url) is None
        assert validate_apply_url("not a url", detail_url) is None

    def test_non_job_site_produces_zero_records_and_no_errors(self) -> None:
        crawl_data: dict[str, Any] = {
            "site": "https://example.com",
            "pages": [
                {
                    "url": "https://example.com",
                    "title": "Example Domain",
                    "h1_headings": ["Example Domain"],
                    "h2_headings": [],
                    "main_text": "This domain is for use in illustrative examples in documents.",
                }
            ],
        }

        result = extract_jobs_from_crawl(crawl_data)
        assert result["stats"]["total_jobs"] == 0
        assert result["stats"]["companies"] == 0
        assert result["stats"]["locations"] == 0
        assert len(result["records"]) == 0

    def test_intent_detection_for_jobs_vs_ordinary(self) -> None:
        plan_job = parse_intent("Scrape job listings from https://example.com/careers")
        assert plan_job.extract_focus == "jobs"

        plan_vacancies = parse_intent("Find vacancies at https://company.com")
        assert plan_vacancies.extract_focus == "jobs"

        # Prompt with fake-jobs in the URL but not requesting job extraction
        plan_url_only = parse_intent("Crawl https://realpython.github.io/fake-jobs/ max 1 page")
        assert plan_url_only.extract_focus == ""

        plan_ordinary = parse_intent("Crawl https://example.com and summarize content")
        assert plan_ordinary.extract_focus == ""

    def test_model_validation(self) -> None:
        res = JobExtractionResult(
            records=[
                {
                    "title": "Software Engineer",
                    "company": "Acme Corp",
                    "location": None,
                    "date_posted": None,
                    "description": None,
                    "job_url": "https://example.com/job/1",
                    "apply_url": None,
                    "source_url": "https://example.com/job/1",
                }
            ],
            stats={
                "total_jobs": 1,
                "companies": 1,
                "locations": 0,
                "with_job_url": 1,
                "with_apply_url": 0,
                "with_date": 0,
                "with_description": 0,
                "crawled_detail_pages": 1,
                "is_partial_crawl": False,
                "coverage_note": "1 job record",
            },
        )
        assert res.records[0].title == "Software Engineer"
        assert res.records[0].job_url == "https://example.com/job/1"
        assert res.records[0].apply_url is None
        assert res.stats.total_jobs == 1
        assert res.stats.with_job_url == 1

    def test_heuristic_research_summary_structure(self) -> None:
        crawl_data: dict[str, Any] = {
            "site": "https://example.com",
            "stats": {"pages_crawled": 1},
            "pages": [
                {
                    "url": "https://example.com",
                    "title": "Example Domain",
                    "meta_description": "Example domain for documentation.",
                    "h1_headings": ["Example Domain"],
                    "h2_headings": [],
                    "main_text": "This domain is for use in illustrative examples in documents. You may use this domain in literature.",
                    "links_count": 1,
                }
            ],
        }

        summary, takeaways = _heuristic_summarize(crawl_data)
        assert "### Executive Overview" in summary
        assert "### Key Findings" in summary
        assert "### Important Information" in summary
        assert "### Page-Level Findings" in summary
        assert "### Research Limitations" in summary
        assert "[Example Domain](https://example.com)" in summary
        assert len(takeaways) >= 2

    def test_api_chat_job_extraction_e2e(self, app_client: TestClient) -> None:
        from app.main import _rate_limiter
        _rate_limiter._windows.clear()

        mock_crawl_data = {
            "site": "https://realpython.github.io/fake-jobs/",
            "pages": [
                {
                    "url": "https://realpython.github.io/fake-jobs/",
                    "title": "Fake Python",
                    "h1_headings": ["Fake Python"],
                    "h2_headings": ["Senior Python Developer"],
                    "main_text": "Senior Python Developer Payne, Roberts and Davis Stewartbury, AA 2021-04-08 Learn Apply",
                    "links_count": 2,
                },
                {
                    "url": "https://realpython.github.io/fake-jobs/jobs/senior-python-developer-0.html",
                    "title": "Fake Python",
                    "h1_headings": ["Fake Python", "Senior Python Developer"],
                    "h2_headings": ["Payne, Roberts and Davis"],
                    "main_text": "Senior Python Developer Payne, Roberts and Davis Full description here. Location: Stewartbury, AA Posted: 2021-04-08",
                    "links_count": 1,
                },
            ],
            "stats": {"pages_crawled": 2},
            "errors": [],
        }

        async def _mock_run_tool_async(record: Any, plan: Any) -> Any:
            yield {"event": "progress", "data": {"step": "crawling"}}
            yield {"event": "_raw_result", "data": {"stdout": json.dumps(mock_crawl_data), "exit_code": 0}}

        with patch("app.main.run_tool_async", side_effect=_mock_run_tool_async):
            resp = app_client.post(
                "/api/chat",
                json={"prompt": "Scrape job listings from https://realpython.github.io/fake-jobs/ max 2 pages"},
            )
            assert resp.status_code == 200

            result_payload = None
            for block in resp.text.split("\r\n\r\n" if "\r\n\r\n" in resp.text else "\n\n"):
                if "event: result" in block:
                    for line in block.splitlines():
                        if line.startswith("data: "):
                            outer = json.loads(line[6:])
                            result_payload = outer.get("data")
                            break

            assert result_payload is not None
            assert result_payload["jobs"] is not None
            jobs = result_payload["jobs"]
            assert jobs["stats"]["total_jobs"] == 1
            assert jobs["stats"]["crawled_detail_pages"] == 1
            rec = jobs["records"][0]
            assert rec["title"] == "Senior Python Developer"
            assert rec["job_url"] == "https://realpython.github.io/fake-jobs/jobs/senior-python-developer-0.html"
            assert rec["apply_url"] is None
            assert "Crawl limit constraints" in jobs["stats"]["coverage_note"]

    def test_api_chat_job_extraction_validation_failure_handling(self, app_client: TestClient) -> None:
        """Verify that validation errors in job extraction are logged to errors without crashing generic crawl."""
        from app.main import _rate_limiter
        _rate_limiter._windows.clear()

        mock_crawl_data = {
            "site": "https://realpython.github.io/fake-jobs/",
            "pages": [
                {
                    "url": "https://realpython.github.io/fake-jobs/",
                    "title": "Fake Python",
                    "h1_headings": ["Fake Python"],
                    "h2_headings": ["Senior Python Developer"],
                    "main_text": "Senior Python Developer Payne, Roberts and Davis Stewartbury, AA 2021-04-08 Learn Apply",
                }
            ],
            "stats": {"pages_crawled": 1},
            "errors": [],
        }

        async def _mock_run_tool_async(record: Any, plan: Any) -> Any:
            yield {"event": "_raw_result", "data": {"stdout": json.dumps(mock_crawl_data), "exit_code": 0}}

        # Force build_extracted to produce invalid records structure that triggers ValidationError
        from app.models import Extracted
        mock_extracted = Extracted(
            site_name="Fake Python",
            focus_result={"records": [{"title": "Dev", "source_url": None}]},  # source_url must be str, None will fail
        )

        with patch("app.main.run_tool_async", side_effect=_mock_run_tool_async), \
             patch("app.main.build_extracted", return_value=mock_extracted):
            resp = app_client.post(
                "/api/chat",
                json={"prompt": "Extract jobs from https://realpython.github.io/fake-jobs/"},
            )
            assert resp.status_code == 200

            result_payload = None
            for block in resp.text.split("\r\n\r\n" if "\r\n\r\n" in resp.text else "\n\n"):
                if "event: result" in block:
                    for line in block.splitlines():
                        if line.startswith("data: "):
                            outer = json.loads(line[6:])
                            result_payload = outer.get("data")
                            break

            assert result_payload is not None
            # Crawl itself succeeded
            assert result_payload["status"] == "SUCCESS"
            # jobs is None because extraction validation failed
            assert result_payload["jobs"] is None
            # errors contains the explicit warning
            assert any("Job extraction validation warning: ValidationError" in err for err in result_payload["errors"])
