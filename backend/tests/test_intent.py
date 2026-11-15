"""Tests for intent parsing and tool selection."""
from __future__ import annotations

import pytest
from app.intent import parse_intent
from app.validators import ValidationError


class TestIntentParser:
    def test_crawl_intent_selects_site_crawler(self) -> None:
        plan = parse_intent("Crawl https://example.com and summarize it")
        assert plan.tool == "site_crawler"
        assert plan.task_type == "crawl"
        assert plan.url == "https://example.com"
        assert plan.wants_summary is True
        assert len(plan.tool_reason) > 0

    def test_broken_links_intent_selects_link_checker(self) -> None:
        plan = parse_intent("Check for broken links on https://example.com/blog")
        assert plan.tool == "link_checker"
        assert plan.task_type == "link_check"
        assert plan.url == "https://example.com/blog"
        assert "link" in plan.tool_reason.lower()

    def test_dead_links_intent_selects_link_checker(self) -> None:
        plan = parse_intent("Find all dead links at https://test.org")
        assert plan.tool == "link_checker"
        assert plan.url == "https://test.org"

    def test_email_focus_intent(self) -> None:
        plan = parse_intent("Crawl https://mycorp.io and extract only emails in json")
        assert plan.tool == "site_crawler"
        assert plan.extract_focus == "only emails"
        assert plan.wants_json is True

    def test_limits_extracted_and_clamped(self) -> None:
        plan = parse_intent("Crawl 50 pages at depth 10 on https://example.com")
        assert plan.max_pages <= 25  # Clamped to hard cap 25
        assert plan.max_depth <= 3   # Clamped to hard cap 3

    def test_missing_url_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError) as exc:
            parse_intent("Please crawl the website and find all contacts")
        assert exc.value.reason == "missing_url"
