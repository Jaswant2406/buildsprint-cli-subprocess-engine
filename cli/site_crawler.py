#!/usr/bin/env python3
"""
site_crawler.py — BuildSprint CLI tool.
BFS web crawler with SSRF protection via netpolicy.

Exit codes:
  0  success
  1  generic error
  2  partial success (some pages failed)
  3  robots-blocked (starting URL blocked)
  4  unreachable (DNS/network failure)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
from collections import deque
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup: allow running as a standalone script
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent
_BACKEND = _HERE.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

try:
    from bs4 import BeautifulSoup
except ImportError:
    print(json.dumps({"error": "beautifulsoup4 not installed"}), file=sys.stderr)
    sys.exit(1)

try:
    from app.netpolicy import (
        ContentTypeError,
        RedirectError,
        RedirectPolicy,
        RobotsError,
        SSRFError,
        policy_get,
    )
except ImportError as e:
    print(json.dumps({"error": f"Cannot import netpolicy: {e}"}), file=sys.stderr)
    sys.exit(1)

VERSION = "1.0.0"
USER_AGENT = "BuildSprintBot/1.0 (site_crawler)"
POLITE_DELAY = 0.3  # seconds between requests

_EMAIL_RE = __import__("re").compile(
    r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"
)
_PHONE_RE = __import__("re").compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
_SOCIAL_RE = {
    "twitter": __import__("re").compile(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)", __import__("re").IGNORECASE),
    "linkedin": __import__("re").compile(r"linkedin\.com/(?:in|company)/([A-Za-z0-9\-_]+)", __import__("re").IGNORECASE),
    "github": __import__("re").compile(r"github\.com/([A-Za-z0-9\-_]+)", __import__("re").IGNORECASE),
    "facebook": __import__("re").compile(r"facebook\.com/([A-Za-z0-9.\-_]+)", __import__("re").IGNORECASE),
    "instagram": __import__("re").compile(r"instagram\.com/([A-Za-z0-9.\-_]+)", __import__("re").IGNORECASE),
    "youtube": __import__("re").compile(r"youtube\.com/(?:channel|@|user)/([A-Za-z0-9.\-_]+)", __import__("re").IGNORECASE),
}


def _stderr_progress(event: str, **kwargs: Any) -> None:
    data = {"event": event, **kwargs}
    print(json.dumps(data), file=sys.stderr, flush=True)


def _same_domain(url: str, base_netloc: str) -> bool:
    """Check if URL is on the same domain as base."""
    parsed = urllib.parse.urlparse(url)
    netloc = parsed.netloc
    # Strip port for comparison
    base = base_netloc.split(":")[0].lower().lstrip("www.")
    target = netloc.split(":")[0].lower().lstrip("www.")
    return base == target


def _extract_page_data(url: str, html: str) -> dict[str, Any]:
    """Extract structured data from an HTML page."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove script/style tags for text extraction
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else ""

    meta_desc = ""
    meta_tag = soup.find("meta", attrs={"name": ["description", "Description"]})
    if meta_tag and hasattr(meta_tag, "get"):
        meta_desc = str(meta_tag.get("content", "") or "")

    # Language
    html_tag = soup.find("html")
    language = ""
    if html_tag and hasattr(html_tag, "get"):
        language = str(html_tag.get("lang", "") or "")

    # Headings
    h1s = [h.get_text(strip=True) for h in soup.find_all("h1")][:5]
    h2s = [h.get_text(strip=True) for h in soup.find_all("h2")][:8]

    # Main text
    main = soup.find("main") or soup.find("article") or soup.find("body")
    main_text = ""
    if main:
        main_text = main.get_text(separator=" ", strip=True)[:2000]

    # Links
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = str(a.get("href", ""))
        abs_url = urllib.parse.urljoin(url, href)
        parsed = urllib.parse.urlparse(abs_url)
        if parsed.scheme in ("http", "https"):
            links.append(abs_url)

    # Images
    images = soup.find_all("img", src=True)

    # Emails from mailto links and text
    emails: list[str] = []
    for a in soup.find_all("a", href=True):
        href = str(a.get("href", ""))
        if href.startswith("mailto:"):
            email = href[7:].split("?")[0].strip()
            if email and email not in emails:
                emails.append(email)
    for m in _EMAIL_RE.finditer(main_text):
        e = m.group(0)
        if e not in emails:
            emails.append(e)

    # Phones
    phones: list[str] = []
    for m in _PHONE_RE.finditer(main_text):
        p = m.group(0).strip()
        if p not in phones:
            phones.append(p)

    # Social links
    social: dict[str, str] = {}
    page_text = str(soup)
    for name, pat in _SOCIAL_RE.items():
        soc_m = pat.search(page_text)
        if soc_m:
            social[name] = soc_m.group(0)

    # Script/meta hints
    tech_hints: list[str] = []
    for script in soup.find_all("script", src=True):
        src = str(script.get("src", ""))
        if "wp-content" in src:
            tech_hints.append("WordPress")
        elif "shopify" in src.lower():
            tech_hints.append("Shopify")
        elif "react" in src.lower():
            tech_hints.append("React")
        elif "angular" in src.lower():
            tech_hints.append("Angular")
        elif "vue" in src.lower():
            tech_hints.append("Vue")

    gen = soup.find("meta", attrs={"name": "generator"})
    if gen and hasattr(gen, "get"):
        content = str(gen.get("content", ""))
        if content:
            tech_hints.append(content)

    return {
        "url": url,
        "title": title,
        "meta_description": meta_desc,
        "language": language,
        "h1_headings": h1s,
        "h2_headings": h2s,
        "main_text": main_text,
        "links_count": len(links),
        "images_count": len(images),
        "emails": emails,
        "phones": phones,
        "social_links": social,
        "tech_hints": list(set(tech_hints)),
        "_links": links,  # used for BFS, not in output
    }


def crawl(
    start_url: str,
    max_pages: int = 10,
    max_depth: int = 2,
    timeout: int = 60,
    allow_localhost: bool = False,
) -> dict[str, Any]:
    """
    BFS same-domain crawler.
    Returns the full result dict.
    """
    start_time = time.monotonic()
    parsed_start = urllib.parse.urlparse(start_url)
    base_netloc = parsed_start.netloc

    pages: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    visited: set[str] = set()

    # BFS queue: (url, depth)
    queue: deque[tuple[str, int]] = deque()
    queue.append((start_url, 0))
    visited.add(start_url)

    # Check starting URL robots
    if not allow_localhost or not _is_allowed_localhost(start_url):
        try:
            from app.netpolicy import _get_robots
            rp = _get_robots(parsed_start.scheme, base_netloc, allow_localhost=allow_localhost, user_agent=USER_AGENT)
            if rp is not None and not rp.can_fetch(USER_AGENT, start_url):
                return {
                    "site": start_url,
                    "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "pages": [],
                    "skipped": [{"url": start_url, "reason": "robots_disallowed"}],
                    "errors": [],
                    "stats": {"pages_crawled": 0, "duration_s": 0},
                }
        except Exception:
            pass

    redirect_policy = RedirectPolicy(max_hops=3)
    heartbeat_thread = _start_heartbeat()

    try:
        while queue and len(pages) < max_pages:
            url, depth = queue.popleft()

            # Emit progress
            _stderr_progress("crawling", url=url, depth=depth, pages_so_far=len(pages))

            # Timeout check
            if time.monotonic() - start_time > timeout:
                skipped.append({"url": url, "reason": "timeout"})
                break

            try:
                resp = policy_get(
                    url,
                    allow_localhost=allow_localhost,
                    redirect_policy=redirect_policy,
                    user_agent=USER_AGENT,
                    check_robots=True,
                )

                ct = resp.headers.get("content-type", "")
                if not any(t in ct for t in ("text/html", "application/xhtml+xml")):
                    skipped.append({"url": url, "reason": f"non_html: {ct}"})
                    continue

                status_code = resp.status_code
                if status_code >= 400:
                    errors.append({"url": url, "error": f"HTTP {status_code}"})
                    _stderr_progress("error", url=url, error=f"HTTP {status_code}")
                    continue

                data = _extract_page_data(url, resp.text)

                page_record = {k: v for k, v in data.items() if k != "_links"}
                page_record["status_code"] = status_code
                pages.append(page_record)

                # Enqueue same-domain links
                if depth < max_depth:
                    for link in data.get("_links", []):
                        normalized = _normalize_url(link)
                        if normalized and normalized not in visited:
                            if _same_domain(normalized, base_netloc):
                                visited.add(normalized)
                                queue.append((normalized, depth + 1))

                time.sleep(POLITE_DELAY)

            except RobotsError:
                skipped.append({"url": url, "reason": "robots_disallowed"})
                _stderr_progress("skipped", url=url, reason="robots_disallowed")
            except SSRFError as e:
                skipped.append({"url": url, "reason": f"ssrf_blocked: {e}"})
                _stderr_progress("skipped", url=url, reason=str(e))
            except RedirectError as e:
                skipped.append({"url": url, "reason": str(e)})
            except ContentTypeError as e:
                skipped.append({"url": url, "reason": str(e)})
            except Exception as e:
                errors.append({"url": url, "error": str(e)[:200]})
                _stderr_progress("error", url=url, error=str(e)[:200])

    finally:
        heartbeat_thread.stop()

    duration = round(time.monotonic() - start_time, 2)

    return {
        "site": start_url,
        "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pages": pages,
        "skipped": skipped,
        "errors": errors,
        "stats": {
            "pages_crawled": len(pages),
            "duration_s": duration,
        },
    }


def _normalize_url(url: str) -> str | None:
    """Normalize URL, strip fragments, return None if invalid."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return None
        # Strip fragment
        clean = urllib.parse.urlunparse(parsed._replace(fragment=""))
        return clean
    except Exception:
        return None


def _is_allowed_localhost(url: str) -> bool:
    return False  # Always run through robots check


class _HeartbeatThread:
    def __init__(self) -> None:
        import threading
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(2.0):
            print(json.dumps({"event": "heartbeat"}), file=sys.stderr, flush=True)

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)


def _start_heartbeat() -> _HeartbeatThread:
    return _HeartbeatThread()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="BuildSprint site crawler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0  success (all pages crawled)
  1  generic error
  2  partial success (some pages failed)
  3  robots-blocked (start URL disallowed)
  4  unreachable (DNS/network failure)
""",
    )
    parser.add_argument("--version", action="version", version=f"site_crawler {VERSION}")
    parser.add_argument("--url", required=True, help="Starting URL to crawl")
    parser.add_argument("--max-pages", type=int, default=10, help="Max pages to crawl (default 10, max 25)")
    parser.add_argument("--max-depth", type=int, default=2, help="Max BFS depth (default 2, max 3)")
    parser.add_argument("--out-file", default=None, help="Write JSON result to this file")
    parser.add_argument("--timeout", type=int, default=60, help="Overall timeout in seconds")

    args = parser.parse_args()

    # Clamp limits
    max_pages = max(1, min(args.max_pages, 25))
    max_depth = max(0, min(args.max_depth, 3))

    allow_localhost = (
        os.environ.get("APP_ENV") == "test"
        and os.environ.get("ALLOW_LOCALHOST_FOR_TESTS", "").lower() in ("1", "true", "yes")
    )

    _stderr_progress("started", url=args.url, max_pages=max_pages, max_depth=max_depth)

    try:
        result = crawl(
            start_url=args.url,
            max_pages=max_pages,
            max_depth=max_depth,
            timeout=args.timeout,
            allow_localhost=allow_localhost,
        )
    except SSRFError as e:
        err = {"error": str(e), "reason": "ssrf_blocked", "site": args.url}
        print(json.dumps(err))
        _stderr_progress("failed", reason="ssrf_blocked")
        return 4
    except RobotsError as e:
        err = {"error": str(e), "reason": "robots_blocked", "site": args.url}
        print(json.dumps(err))
        _stderr_progress("failed", reason="robots_blocked")
        return 3
    except Exception as e:
        err = {"error": str(e), "reason": "generic", "site": args.url}
        print(json.dumps(err))
        _stderr_progress("failed", reason=str(e))
        return 1

    # Determine exit code
    pages_count = len(result.get("pages", []))
    errors_list = result.get("errors", [])
    errors_count = len(errors_list)
    skipped = result.get("skipped", [])

    # Check if start URL was robots-blocked
    start_blocked = any(
        s.get("reason") == "robots_disallowed" and s.get("url") == args.url
        for s in skipped
    )
    if pages_count == 0 and start_blocked:
        output = json.dumps(result)
        print(output)
        if args.out_file:
            Path(args.out_file).write_text(output, encoding="utf-8")
        return 3

    exit_code = 0
    if pages_count == 0:
        # If no pages crawled due to network/DNS/connect errors -> 4 (unreachable)
        all_reasons = [e.get("error", "") for e in errors_list] + [s.get("reason", "") for s in skipped]
        combined = " ".join(all_reasons).lower()
        if any(w in combined for w in ("dns", "resolution", "nodename", "connect", "unreachable", "getaddrinfo", "refused", "name or service not known")):
            exit_code = 4
        else:
            exit_code = 1
    elif errors_count > 0 or len(skipped) > 0:
        exit_code = 2

    output = json.dumps(result, indent=2)
    print(output)
    if args.out_file:
        Path(args.out_file).write_text(output, encoding="utf-8")

    _stderr_progress("done", pages=pages_count, errors=errors_count, exit_code=exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
