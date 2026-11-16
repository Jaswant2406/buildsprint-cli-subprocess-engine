"""Tests for intent parsing and tool selection."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from app.config import Settings
from app.intent import parse_intent
from app.llm import LLMError
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

    def test_llm_mode_success_parses_plan(self) -> None:
        """When LLM is configured and succeeds, intent is parsed from LLM JSON response."""
        mock_settings = Settings(LLM_PROVIDER="openai", LLM_API_KEY="sk-valid-key")
        llm_json = (
            '{"task_type": "crawl", "tool": "site_crawler", '
            '"tool_reason": "LLM selected site_crawler for comprehensive coverage", '
            '"url": "https://example.com", "max_pages": 5, "max_depth": 2, '
            '"wants_summary": true, "wants_json": true, "extract_focus": "", "max_links": 25}'
        )
        with patch("app.intent.get_settings", return_value=mock_settings):
            with patch("app.intent.call_llm", return_value=llm_json):
                plan = parse_intent("Crawl https://example.com and summarize")
                assert plan.tool == "site_crawler"
                assert plan.url == "https://example.com"
                assert "LLM selected site_crawler" in plan.tool_reason

    def test_bad_or_expired_key_falls_back_to_heuristic_with_honest_note(self) -> None:
        """When LLM provider fails (e.g. 401 expired key), falls back to heuristic with honest note."""
        mock_settings = Settings(LLM_PROVIDER="openai", LLM_API_KEY="sk-expired-key")
        with patch("app.intent.get_settings", return_value=mock_settings):
            with patch("app.intent.call_llm", side_effect=LLMError("OpenAI error 401: Invalid API key")):
                plan = parse_intent("Crawl https://example.com and summarize")
                assert plan.tool == "site_crawler"
                assert plan.url == "https://example.com"
                assert "Note: LLM provider unavailable" in plan.tool_reason
                assert "401" in plan.tool_reason
