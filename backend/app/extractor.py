"""
Build the consolidated `extracted` block with evidence from crawl data.
Every fact carries source_url.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any

from app.models import (
    Contact,
    ContactItem,
    Extracted,
    ExtractedStats,
    KeyPage,
    SocialLink,
    SocialLinks,
)

_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-().]{7,}\d)")
_SOCIAL_PATTERNS = {
    "twitter": re.compile(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)", re.IGNORECASE),
    "linkedin": re.compile(r"linkedin\.com/(?:in|company)/([A-Za-z0-9\-_]+)", re.IGNORECASE),
    "github": re.compile(r"github\.com/([A-Za-z0-9\-_]+)", re.IGNORECASE),
    "facebook": re.compile(r"facebook\.com/([A-Za-z0-9.\-_]+)", re.IGNORECASE),
    "instagram": re.compile(r"instagram\.com/([A-Za-z0-9.\-_]+)", re.IGNORECASE),
    "youtube": re.compile(r"youtube\.com/(?:channel|@|user)/([A-Za-z0-9.\-_]+)", re.IGNORECASE),
}

_PAGE_ROLE_PATTERNS = {
    "home": re.compile(r"^/?(?:index\.html?)?$|^/?$"),
    "about": re.compile(r"about|team|story|mission|company", re.IGNORECASE),
    "contact": re.compile(r"contact|reach|support", re.IGNORECASE),
    "pricing": re.compile(r"pricing|plans?|subscri", re.IGNORECASE),
    "blog": re.compile(r"blog|news|article|post", re.IGNORECASE),
    "docs": re.compile(r"doc|api|guide|reference|manual", re.IGNORECASE),
}


def _guess_role(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    for role, pat in _PAGE_ROLE_PATTERNS.items():
        if pat.search(path):
            return role
    return "other"


def _extract_topics(pages: list[dict]) -> list[str]:
    """Extract up to 8 main topics from headings across all pages."""
    headings: dict[str, int] = {}
    for page in pages:
        for h in page.get("h1_headings", []) + page.get("h2_headings", []):
            h = h.strip()
            if h and len(h) > 3:
                headings[h] = headings.get(h, 0) + 1
    # Sort by frequency, deduplicate similar ones
    sorted_h = sorted(headings.items(), key=lambda x: -x[1])
    seen: set[str] = set()
    topics: list[str] = []
    for h, _ in sorted_h:
        lower = h.lower()
        if lower not in seen:
            seen.add(lower)
            topics.append(h)
        if len(topics) >= 8:
            break
    return topics[:8]


def build_extracted(
    crawl_data: dict[str, Any],
    extract_focus: str = "",
) -> Extracted:
    """Build an Extracted object from site_crawler output."""
    pages: list[dict] = crawl_data.get("pages", [])
    site_url: str = crawl_data.get("site", "")
    domain = urllib.parse.urlparse(site_url).netloc

    if not pages:
        return Extracted(site_name=domain, domain=domain)

    # Site name from first page title
    first = pages[0]
    site_name = first.get("title", domain) or domain

    # Description from meta_description of first page
    description = first.get("meta_description", "")
    for p in pages:
        if p.get("meta_description"):
            description = p["meta_description"]
            break

    # Language
    language = first.get("language", "")

    # Key pages
    key_pages: list[KeyPage] = []
    seen_urls: set[str] = set()
    for page in pages:
        url = page.get("url", "")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        title = page.get("title", url)
        role = _guess_role(url)
        key_pages.append(KeyPage(url=url, title=title, role=role))
        if len(key_pages) >= 10:
            break

    # Contact info
    emails: list[ContactItem] = []
    phones: list[ContactItem] = []
    seen_emails: set[str] = set()
    seen_phones: set[str] = set()

    for page in pages:
        url = page.get("url", "")
        # From dedicated fields
        for email in page.get("emails", []):
            if email and email not in seen_emails:
                seen_emails.add(email)
                emails.append(ContactItem(value=email, source_url=url))
        for phone in page.get("phones", []):
            if phone and phone not in seen_phones:
                seen_phones.add(phone)
                phones.append(ContactItem(value=phone, source_url=url))
        # Also scan main_text
        text = page.get("main_text", "")
        for m in _EMAIL_RE.finditer(text):
            e = m.group(0)
            if e not in seen_emails:
                seen_emails.add(e)
                emails.append(ContactItem(value=e, source_url=url))

    # Social links
    social_dict: dict[str, SocialLink] = {}
    for page in pages:
        url = page.get("url", "")
        for name, pat in _SOCIAL_PATTERNS.items():
            if name in social_dict:
                continue
            # Check social_links field
            sl = page.get("social_links", {})
            link_val = None
            if isinstance(sl, dict):
                link_val = sl.get(name)
            if not link_val:
                # Scan main text
                soc_match = pat.search(page.get("main_text", ""))
                if soc_match:
                    link_val = soc_match.group(0)
            if link_val:
                social_dict[name] = SocialLink(value=link_val, source_url=url)

    social = SocialLinks(**{k: v for k, v in social_dict.items()})

    # Tech hints
    tech_hints: set[str] = set()
    for page in pages:
        for hint in page.get("tech_hints", []):
            tech_hints.add(str(hint))

    # Stats
    stats_data = crawl_data.get("stats", {})
    total_links = sum(p.get("links_count", 0) for p in pages)
    total_images = sum(p.get("images_count", 0) for p in pages)
    stats = ExtractedStats(
        pages_crawled=stats_data.get("pages_crawled", len(pages)),
        total_links=total_links,
        total_images=total_images,
    )

    # Main topics
    main_topics = _extract_topics(pages)

    # Focus result
    focus_result: dict | None = None
    if extract_focus:
        focus_lower = extract_focus.lower()
        if "email" in focus_lower:
            focus_result = {"emails": [{"value": e.value, "source_url": e.source_url} for e in emails]}
        elif "phone" in focus_lower:
            focus_result = {"phones": [{"value": p.value, "source_url": p.source_url} for p in phones]}
        elif "contact" in focus_lower:
            focus_result = {
                "emails": [{"value": e.value, "source_url": e.source_url} for e in emails],
                "phones": [{"value": p.value, "source_url": p.source_url} for p in phones],
            }

    return Extracted(
        site_name=site_name,
        domain=domain,
        description=description,
        language=language,
        main_topics=main_topics,
        key_pages=key_pages,
        contact=Contact(emails=emails, phones=phones),
        social_links=social,
        tech_hints=list(tech_hints),
        stats=stats,
        focus_result=focus_result,
    )
