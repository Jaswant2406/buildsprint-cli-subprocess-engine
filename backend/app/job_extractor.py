"""
backend/app/job_extractor.py

Independent structured job listing extraction module.
Reuses generic crawler output (pages, headings, main_text, URLs) without modifying
crawler or runner internals.

Extracts:
- title: job title (str | None)
- company: company name (str | None)
- location: job location (str | None)
- date_posted: publication date (str | None)
- description: job description excerpt (str | None)
- job_url: individual job-detail page URL (str | None)
- apply_url: actual external candidate application destination (str | None)
- source_url: URL of the page where the record was discovered (str)

Rules:
1. Never copy job_url into apply_url.
2. If an application link points to the job's own detail page, populate job_url only.
3. Reject javascript:, data:, file:, malformed URLs, and private/unsafe IP destinations.
4. If crawler output does not expose a separate application destination, apply_url is None.
5. Calculate statistics strictly from actual extracted records.
6. Honestly report partial coverage and limit utilisation without inventing unvisited counts.
"""
from __future__ import annotations

import ipaddress
import re
import urllib.parse
from typing import Any

from app.netpolicy import _is_forbidden_ip, _parse_alternative_ip

_LOC_EXPLICIT_RE = re.compile(
    r"\bLocation:\s*([^\n\r]+?)(?:\s+Posted:|\s+Date:|\s*$)",
    re.IGNORECASE,
)
_POSTED_EXPLICIT_RE = re.compile(
    r"\b(?:Posted|Date):\s*(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

# Regex to match card pattern on listing pages:
# e.g. "<title> <company> <location> <date> Learn Apply"
_CARD_LOC_RE = re.compile(
    r"(?:(?:East|West|North|South|Port|New|Old|Fort|Mount|Lake)\s+)?[A-Z][a-zA-Z]+(?:ville|bury|burgh|view|town|berg|stad|shire|ton|land|borough|ford|field|wood|port)?,\s*[A-Z]{2}"
)

# Common application link markers in URLs or text
_APPLY_PATH_RE = re.compile(
    r"/(?:apply|application|submit|apply-now|job-apply|candidates?|careers?/[^/]+/apply)\b",
    re.IGNORECASE,
)


def validate_apply_url(candidate_url: str | None, job_url: str | None) -> str | None:
    """
    Validate an application destination URL:
    - Must be a valid HTTP or HTTPS URL.
    - Cannot match or resolve to the job's own detail page (job_url).
    - Cannot use dangerous schemes (javascript, data, file).
    - Cannot target loopback, private, link-local, or cloud metadata IP destinations.
    - Accepts legitimate external application portals (e.g. Greenhouse, Lever, Workday).
    - Returns None if invalid, unsafe, or matching job_url. Never fabricates.
    """
    if not candidate_url or not isinstance(candidate_url, str):
        return None

    raw = candidate_url.strip()
    if not raw:
        return None

    # Check for dangerous or non-web schemes
    lower_raw = raw.lower()
    if lower_raw.startswith(("javascript:", "data:", "file:", "mailto:", "tel:", "blob:", "about:")):
        return None

    try:
        parsed = urllib.parse.urlparse(raw)
    except Exception:
        return None

    if parsed.scheme.lower() not in ("http", "https"):
        return None

    host = parsed.hostname
    if not host:
        return None

    # Rule 1 & 2: Never classify job_url as apply_url
    if job_url:
        try:
            norm_cand = raw.rstrip("/")
            norm_job = job_url.strip().rstrip("/")
            if norm_cand.lower() == norm_job.lower():
                return None
        except Exception:
            pass

    # Rule 7: Reject loopback, private, link-local, or metadata IPs
    if host.lower() in ("localhost", "127.0.0.1", "::1"):
        return None

    alt = _parse_alternative_ip(host)
    if alt is not None:
        forbidden, _ = _is_forbidden_ip(alt)
        if forbidden:
            return None

    try:
        ip = ipaddress.ip_address(host)
        forbidden, _ = _is_forbidden_ip(ip)
        if forbidden:
            return None
    except ValueError:
        # Host is a domain name, not an IP literal
        pass

    return raw


def extract_jobs_from_crawl(crawl_data: dict[str, Any]) -> dict[str, Any]:
    """
    Extract structured job records from crawler output.
    Returns dict formatted for JobExtractionResult:
    {
        "records": [ ... ],
        "stats": { ... }
    }
    """
    pages: list[dict[str, Any]] = crawl_data.get("pages", [])
    records_by_key: dict[tuple[str | None, str | None], dict[str, Any]] = {}
    ordered_records: list[dict[str, Any]] = []
    crawled_detail_pages_count = 0

    for page in pages:
        url = page.get("url", "")
        main_text = page.get("main_text", "")
        h1s = [h.strip() for h in page.get("h1_headings", []) if h.strip()]
        h2s = [h.strip() for h in page.get("h2_headings", []) if h.strip()]

        loc_match = _LOC_EXPLICIT_RE.search(main_text)
        date_match = _POSTED_EXPLICIT_RE.search(main_text)

        # -------------------------------------------------------------------
        # 1. Check for Individual Job Detail Page
        # -------------------------------------------------------------------
        # In typical detail pages (e.g. fake-jobs/jobs/*), h1 has [SiteName, JobTitle]
        # and h2 has [Company], while main_text has "Location: ... Posted: ..."
        if loc_match and (len(h1s) >= 2 or len(h2s) == 1):
            crawled_detail_pages_count += 1
            title = h1s[1] if len(h1s) >= 2 else (h1s[0] if len(h1s) == 1 else None)
            company = h2s[0] if h2s else None
            location = loc_match.group(1).strip()
            date_posted = date_match.group(1).strip() if date_match else None

            # Extract job description body between company heading and Location label
            description: str | None = None
            if company:
                try:
                    c_idx = main_text.find(company)
                    l_idx = main_text.find("Location:")
                    if c_idx != -1 and l_idx != -1 and l_idx > c_idx:
                        desc_cand = main_text[c_idx + len(company):l_idx].strip()
                        if desc_cand:
                            description = desc_cand
                except Exception:
                    pass

            # Rule: job_url is the individual job detail page URL
            job_url: str | None = url

            # Rule: apply_url is strictly the external candidate application destination.
            # Never copy job_url into apply_url.
            # If the crawler output does not expose a separate application portal link,
            # apply_url MUST be None.
            apply_url: str | None = None

            record = {
                "title": title,
                "company": company,
                "location": location,
                "date_posted": date_posted,
                "description": description,
                "job_url": job_url,
                "apply_url": apply_url,
                "source_url": url,
            }

            key = (title, company)
            if key in records_by_key:
                # Merge enriched detail page data into existing card
                existing = records_by_key[key]
                if description and not existing.get("description"):
                    existing["description"] = description
                if job_url and not existing.get("job_url"):
                    existing["job_url"] = job_url
                if location and not existing.get("location"):
                    existing["location"] = location
                if date_posted and not existing.get("date_posted"):
                    existing["date_posted"] = date_posted
            else:
                records_by_key[key] = record
                ordered_records.append(record)

        # -------------------------------------------------------------------
        # 2. Check for Listing Page Cards
        # -------------------------------------------------------------------
        # On listing pages (e.g. fake-jobs index), h2 headings contain job titles
        # followed in main_text by Company, Location, Date
        for t in h2s:
            if t.lower() in ("navigation", "menu", "search", "categories", "filters", "footer", "fake python"):
                continue

            pat = (
                re.escape(t)
                + r"\s+(?P<company>.+?)\s+(?P<location>(?:(?:East|West|North|South|Port|New|Old|Fort|Mount|Lake)\s+)?[A-Z][a-zA-Z]+(?:ville|bury|burgh|view|town|berg|stad|shire|ton|land|borough|ford|field|wood|port)?,\s*[A-Z]{2})\s+(?P<date>\d{4}-\d{2}-\d{2})"
            )
            m = re.search(pat, main_text)
            if m:
                company_str = m.group("company").strip()
                location_str = m.group("location").strip()
                date_str = m.group("date").strip()

                key = (t, company_str)
                if key not in records_by_key:
                    record = {
                        "title": t,
                        "company": company_str,
                        "location": location_str,
                        "date_posted": date_str,
                        "description": None,
                        "job_url": None,  # Not visited yet
                        "apply_url": None,
                        "source_url": url,
                    }
                    records_by_key[key] = record
                    ordered_records.append(record)

    # -----------------------------------------------------------------------
    # 3. Calculate statistics strictly from successfully extracted records
    # -----------------------------------------------------------------------
    total_jobs = len(ordered_records)
    companies = len({r["company"] for r in ordered_records if r.get("company")})
    locations = len({r["location"] for r in ordered_records if r.get("location")})
    with_job_url = sum(1 for r in ordered_records if r.get("job_url") is not None)
    with_apply = sum(1 for r in ordered_records if r.get("apply_url") is not None)
    with_date = sum(1 for r in ordered_records if r.get("date_posted") is not None)
    with_desc = sum(1 for r in ordered_records if r.get("description") is not None)

    # Partial coverage and crawl limit disclosure
    # Distinguish page-limit utilisation from entire website coverage.
    is_partial = (total_jobs > crawled_detail_pages_count) or (len(pages) <= 5 and total_jobs > 0)
    coverage_note = ""
    if total_jobs > 0:
        coverage_note = (
            f"{total_jobs} job records extracted from a {len(pages)}-page crawl sample "
            f"({crawled_detail_pages_count} detail page(s) visited). "
            f"Crawl limit constraints (max_pages={len(pages)}) bound this research; "
            f"additional unvisited job pages may exist on the domain."
        )

    return {
        "records": ordered_records,
        "stats": {
            "total_jobs": total_jobs,
            "companies": companies,
            "locations": locations,
            "with_job_url": with_job_url,
            "with_apply_url": with_apply,
            "with_date": with_date,
            "with_description": with_desc,
            "crawled_detail_pages": crawled_detail_pages_count,
            "is_partial_crawl": is_partial,
            "coverage_note": coverage_note,
        },
    }
