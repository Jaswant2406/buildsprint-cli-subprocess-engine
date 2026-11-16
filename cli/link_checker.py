#!/usr/bin/env python3
"""
link_checker.py — BuildSprint CLI tool.
Checks all links on a page for broken/working status.

Exit codes:
  0  all links working
  1  other error
  2  some broken or error links
  3  robots-blocked (starting URL disallowed)
  4  unreachable
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

_HERE = Path(__file__).parent
_BACKEND = _HERE.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from bs4 import BeautifulSoup
except ImportError:
    print(json.dumps({"error": "beautifulsoup4 not installed"}), file=sys.stderr)
    sys.exit(1)

try:
    from app.netpolicy import (
        RobotsError,
        SSRFError,
        _build_client,
        _is_robots_allowed,
        _resolve_and_validate,
        policy_get,
    )
except ImportError as e:
    print(json.dumps({"error": f"Cannot import netpolicy: {e}"}), file=sys.stderr)
    sys.exit(1)

VERSION = "1.0.0"
USER_AGENT = "BuildSprintBot/1.0 (link_checker)"


def _stderr_progress(event: str, **kwargs: Any) -> None:
    data = {"event": event, **kwargs}
    print(json.dumps(data), file=sys.stderr, flush=True)


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


def _check_link(
    url: str,
    allow_localhost: bool = False,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """
    Check a single link.
    Returns {"url", "status_code", "status", ??"reason"}.
    status: "working" | "broken" | "error"
    """
    # First validate SSRF
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return {
            "url": url,
            "status_code": None,
            "status": "error",
            "reason": f"invalid_scheme:{parsed.scheme}",
        }

    # SSRF check without making a request
    try:
        _resolve_and_validate(parsed.hostname or "", allow_localhost=allow_localhost)
    except SSRFError as e:
        return {
            "url": url,
            "status_code": None,
            "status": "error",
            "reason": f"ssrf_blocked:{e}",
        }

    # Check robots.txt
    try:
        if not _is_robots_allowed(url, allow_localhost=allow_localhost, user_agent=USER_AGENT):
            return {
                "url": url,
                "status_code": None,
                "status": "error",
                "reason": "robots_disallowed",
            }
    except Exception:
        pass

    # Try HEAD first
    try:
        with _build_client(allow_localhost=allow_localhost, timeout=timeout, user_agent=USER_AGENT) as client:
            resp = client.request("HEAD", url)
            sc = resp.status_code

            if sc in (405, 501):
                # Fallback to GET
                resp = client.request("GET", url)
                sc = resp.status_code

            if 200 <= sc < 300:
                # Check if redirect resolves within policy
                return {"url": url, "status_code": sc, "status": "working"}
            elif sc in (301, 302, 303, 307, 308):
                # Follow redirect manually
                location = resp.headers.get("location", "")
                if location:
                    next_url = urllib.parse.urljoin(url, location)
                    try:
                        resp2 = client.request("HEAD", next_url)
                        sc2 = resp2.status_code
                        if 200 <= sc2 < 300:
                            return {"url": url, "status_code": sc, "status": "working"}
                    except Exception:
                        pass
                return {"url": url, "status_code": sc, "status": "working"}
            elif 400 <= sc < 600:
                return {"url": url, "status_code": sc, "status": "broken"}
            else:
                return {"url": url, "status_code": sc, "status": "working"}

    except SSRFError as e:
        return {"url": url, "status_code": None, "status": "error", "reason": f"ssrf_blocked:{e}"}
    except RobotsError as e:
        return {"url": url, "status_code": None, "status": "error", "reason": f"robots_disallowed:{e}"}
    except Exception as e:
        return {"url": url, "status_code": None, "status": "error", "reason": str(e)[:200]}


def check_links(
    start_url: str,
    max_links: int = 25,
    timeout: int = 60,
    allow_localhost: bool = False,
) -> dict[str, Any]:
    """Check all links found on start_url."""
    start_time = time.monotonic()

    # Fetch start page
    try:
        resp = policy_get(
            start_url,
            allow_localhost=allow_localhost,
            user_agent=USER_AGENT,
            check_robots=True,
        )
    except RobotsError:
        return {
            "site": start_url,
            "links": [],
            "stats": {"discovered": 0, "total_links": 0, "checked": 0, "working": 0, "broken": 0},
            "_robots_blocked": True,
        }
    except SSRFError:
        raise
    except Exception:
        raise

    # Extract links
    soup = BeautifulSoup(resp.text, "html.parser")
    raw_links: list[str] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = str(a.get("href", ""))
        abs_url = urllib.parse.urljoin(start_url, href)
        parsed = urllib.parse.urlparse(abs_url)
        if parsed.scheme in ("http", "https"):
            normalized = urllib.parse.urlunparse(parsed._replace(fragment=""))
            if normalized not in seen:
                seen.add(normalized)
                raw_links.append(normalized)

    links_to_check = raw_links[:max_links]
    _stderr_progress("checking", total=len(links_to_check))

    results: list[dict[str, Any]] = []
    heartbeat = _HeartbeatThread()

    try:
        for i, url in enumerate(links_to_check):
            if time.monotonic() - start_time > timeout:
                break
            _stderr_progress("checking_link", index=i, url=url)
            result = _check_link(url, allow_localhost=allow_localhost, timeout=10.0)
            results.append(result)
    finally:
        heartbeat.stop()

    # Compute stats
    working = sum(1 for r in results if r["status"] == "working")
    broken = sum(1 for r in results if r["status"] == "broken")
    checked = len(results)

    # Schema: stats.checked == len(links) INVARIANT
    assert checked == len(results), "Invariant violated: stats.checked != len(links)"

    # Clean up output: remove internal _reason where not needed
    output_links: list[dict[str, Any]] = []
    for r in results:
        entry: dict[str, Any] = {
            "url": r["url"],
            "status_code": r.get("status_code"),
            "status": r["status"],
        }
        if r["status"] == "error" and "reason" in r:
            entry["reason"] = r["reason"]
        output_links.append(entry)

    discovered = len(raw_links)
    res_dict: dict[str, Any] = {
        "site": start_url,
        "links": output_links,
        "stats": {
            "discovered": discovered,
            "total_links": discovered,
            "checked": checked,
            "working": working,
            "broken": broken,
        },
    }
    if discovered == 0:
        res_dict["status"] = "no_testable_links_found"
        res_dict["message"] = "No links found to check."

    return res_dict


def main() -> int:
    parser = argparse.ArgumentParser(
        description="BuildSprint link checker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0  all links working
  1  other error
  2  some broken or error links
  3  robots-blocked
  4  unreachable
""",
    )
    parser.add_argument("--version", action="version", version=f"link_checker {VERSION}")
    parser.add_argument("--url", required=True, help="URL to check links from")
    parser.add_argument("--max-links", type=int, default=25, help="Max links to check (default 25, max 50)")
    parser.add_argument("--out-file", default=None, help="Write JSON result to this file")
    parser.add_argument("--timeout", type=int, default=60, help="Overall timeout in seconds")

    args = parser.parse_args()
    max_links = max(1, min(args.max_links, 50))

    allow_localhost = (
        os.environ.get("APP_ENV") == "test"
        and os.environ.get("ALLOW_LOCALHOST_FOR_TESTS", "").lower() in ("1", "true", "yes")
    )

    _stderr_progress("started", url=args.url, max_links=max_links)

    try:
        result = check_links(
            start_url=args.url,
            max_links=max_links,
            timeout=args.timeout,
            allow_localhost=allow_localhost,
        )
    except SSRFError as e:
        err = {"site": args.url, "links": [], "stats": {"discovered": 0, "total_links": 0, "checked": 0, "working": 0, "broken": 0}, "error": str(e)}
        print(json.dumps(err))
        return 4
    except RobotsError:
        err = {"site": args.url, "links": [], "stats": {"discovered": 0, "total_links": 0, "checked": 0, "working": 0, "broken": 0}}
        print(json.dumps(err))
        return 3
    except Exception as e:
        err = {"site": args.url, "links": [], "stats": {"discovered": 0, "total_links": 0, "checked": 0, "working": 0, "broken": 0}, "error": str(e)}
        print(json.dumps(err))
        e_lower = str(e).lower()
        if any(w in e_lower for w in ("dns", "resolution", "nodename", "connect", "unreachable", "getaddrinfo", "refused", "name or service not known")):
            return 4
        return 1

    # Check if robots blocked
    if result.get("_robots_blocked"):
        result.pop("_robots_blocked", None)
        output = json.dumps(result)
        print(output)
        if args.out_file:
            Path(args.out_file).write_text(output, encoding="utf-8")
        return 3

    output = json.dumps(result, indent=2)
    print(output)
    if args.out_file:
        Path(args.out_file).write_text(output, encoding="utf-8")

    stats = result.get("stats", {})
    broken = stats.get("broken", 0)
    errors = sum(1 for lnk in result.get("links", []) if lnk.get("status") == "error")

    if broken > 0 or errors > 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
