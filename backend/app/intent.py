"""
Intent parser: prompt -> Plan.
LLM path with Pydantic validation; regex/heuristic fallback.
"""
from __future__ import annotations

import json
import re

from app.config import get_settings
from app.llm import LLMError, call_llm
from app.models import Plan
from app.validators import ValidationError, clamp_max_depth, clamp_max_links, clamp_max_pages

_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_LINK_CHECK_RE = re.compile(
    r"\b(broken\s+links?|dead\s+links?|links?\s+check\w*|check\s+links?|404|links?\s+status)\b",
    re.IGNORECASE,
)
_SUMMARY_RE = re.compile(r"\b(summar|overview|brief|tldr|digest)\b", re.IGNORECASE)
_JSON_RE = re.compile(r"\b(json|data|extract|structured)\b", re.IGNORECASE)
_PAGES_RE = re.compile(r"\b(\d+)\s+page", re.IGNORECASE)
_DEPTH_RE = re.compile(r"\bdepth\s+(\d+)\b", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b(email|contact\s+info|contact\s+detail)\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"\bphone\b", re.IGNORECASE)

_SYSTEM_PROMPT = """
You are an intent parser for a web research tool. Given a natural language task,
extract a JSON plan with these exact fields:
{
  "task_type": "crawl" | "link_check" | "extract" | "summarize",
  "tool": "site_crawler" | "link_checker",
  "tool_reason": "<one line why>",
  "url": "<the target URL>",
  "max_pages": <1-25, default 10>,
  "max_depth": <1-3, default 2>,
  "wants_summary": <true|false>,
  "wants_json": <true|false>,
  "extract_focus": "<e.g. 'only emails', '' if none>",
  "max_links": <1-50, default 25>
}

Rules:
- Use link_checker for "broken links", "dead links", "link check", "404" tasks
- Use site_crawler for crawl, extract, summarize, general research tasks
- Extract URL from the prompt exactly
- max_pages/max_depth: clamp to stated limits
- Return ONLY the JSON object, no markdown, no explanation
""".strip()


def parse_intent(prompt: str) -> Plan:
    """
    Parse a natural language prompt into a Plan.
    Tries LLM first; falls back to heuristic regex parser.
    Raises ValidationError if no URL can be found.
    """
    settings = get_settings()

    if settings.llm_mode == "llm":
        try:
            raw = call_llm(_SYSTEM_PROMPT, prompt, max_tokens=400, temperature=0.1)
            plan = _parse_llm_response(raw)
            if plan is not None:
                return plan
        except (LLMError, Exception):
            pass  # Fall through to heuristic

    return _heuristic_parse(prompt)


def _parse_llm_response(raw: str) -> Plan | None:
    """Parse and validate LLM JSON response."""
    # Strip markdown code fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON object from text
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None

    try:
        plan = Plan(**data)
        # Clamp limits
        plan.max_pages = clamp_max_pages(plan.max_pages)
        plan.max_depth = clamp_max_depth(plan.max_depth)
        plan.max_links = clamp_max_links(plan.max_links)
        return plan
    except Exception:
        return None


def _heuristic_parse(prompt: str) -> Plan:
    """Pure regex intent parser — no LLM calls."""
    # Extract URL
    urls = _URL_RE.findall(prompt)
    if not urls:
        raise ValidationError("No URL found in prompt", "missing_url")
    url = urls[0].rstrip(".,;)")

    # Determine tool
    is_link_check = bool(_LINK_CHECK_RE.search(prompt))
    tool = "link_checker" if is_link_check else "site_crawler"
    task_type = "link_check" if is_link_check else "crawl"

    # Detect modifiers
    wants_summary = bool(_SUMMARY_RE.search(prompt)) or not is_link_check
    wants_json = bool(_JSON_RE.search(prompt))

    # Extract focus
    extract_focus = ""
    if re.search(r"\bonly\s+emails?\b", prompt, re.IGNORECASE):
        extract_focus = "only emails"
    elif re.search(r"\bonly\s+phones?\b", prompt, re.IGNORECASE):
        extract_focus = "only phones"
    elif re.search(r"\bcontact\b", prompt, re.IGNORECASE):
        extract_focus = "contact info"

    # max_pages
    max_pages = 10
    m = _PAGES_RE.search(prompt)
    if m:
        max_pages = clamp_max_pages(int(m.group(1)))

    # max_depth
    max_depth = 2
    m = _DEPTH_RE.search(prompt)
    if m:
        max_depth = clamp_max_depth(int(m.group(1)))

    tool_reason = (
        "Task mentions broken/dead links → link_checker"
        if is_link_check
        else "Task requires crawling and content extraction → site_crawler"
    )

    return Plan(
        task_type=task_type,
        tool=tool,
        tool_reason=tool_reason,
        url=url,
        max_pages=max_pages,
        max_depth=max_depth,
        wants_summary=wants_summary,
        wants_json=wants_json,
        extract_focus=extract_focus,
        max_links=25,
    )
