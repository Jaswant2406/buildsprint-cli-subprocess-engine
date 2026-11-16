"""Tests for the two approved CLIs: site_crawler.py and link_checker.py."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_CLI_DIR = Path(__file__).parent.parent.parent / "cli"
_SITE_CRAWLER = str(_CLI_DIR / "site_crawler.py")
_LINK_CHECKER = str(_CLI_DIR / "link_checker.py")


def _run_cli(script: str, args: list[str]) -> tuple[int, str, str]:
    cmd = [sys.executable, script] + args
    env = os.environ.copy()
    env["APP_ENV"] = "test"
    env["ALLOW_LOCALHOST_FOR_TESTS"] = "1"
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


class TestSiteCrawlerCLI:
    def test_version_and_help(self) -> None:
        rc, out, _ = _run_cli(_SITE_CRAWLER, ["--version"])
        assert rc == 0
        assert "site_crawler" in out

        rc, out, _ = _run_cli(_SITE_CRAWLER, ["--help"])
        assert rc == 0
        assert "Exit codes:" in out
        assert "--max-pages" in out

    def test_crawl_local_site_success(self, local_site: str) -> None:
        rc, out, err = _run_cli(_SITE_CRAWLER, ["--url", f"{local_site}/index.html", "--max-pages", "2", "--max-depth", "1"])
        assert rc == 0
        data = json.loads(out)
        assert data["site"] == f"{local_site}/index.html"
        assert len(data["pages"]) >= 1
        page = data["pages"][0]
        assert "url" in page
        assert "title" in page
        assert "main_text" in page
        assert "status_code" in page
        assert page["status_code"] == 200

    def test_unreachable_target_returns_code_4(self) -> None:
        rc, out, err = _run_cli(_SITE_CRAWLER, ["--url", "http://invalid-nonexistent-domain-12345.com"])
        assert rc == 4

    def test_respects_max_pages(self, local_site: str) -> None:
        rc, out, _ = _run_cli(_SITE_CRAWLER, ["--url", f"{local_site}/index.html", "--max-pages", "1"])
        assert rc == 0
        data = json.loads(out)
        assert len(data["pages"]) == 1

    def test_exit_code_3_robots_blocked(self, local_site: str) -> None:
        rc, out, err = _run_cli(_SITE_CRAWLER, ["--url", f"{local_site}/private/index.html"])
        assert rc == 3
        data = json.loads(out)
        assert data.get("reason") == "robots_blocked" or any(s.get("reason") == "robots_disallowed" for s in data.get("skipped", []))

    def test_exit_code_2_partial_crawl(self, local_site: str) -> None:
        rc, out, err = _run_cli(_SITE_CRAWLER, ["--url", f"{local_site}/index.html", "--max-pages", "5", "--max-depth", "1"])
        # index.html has a broken link (/broken.html) which results in partial exit code 2
        assert rc == 2
        data = json.loads(out)
        assert len(data["pages"]) >= 1
        assert len(data.get("errors", [])) > 0 or len(data.get("skipped", [])) > 0

    def test_respects_max_depth(self, local_site: str) -> None:
        # Max depth 0 should only crawl the starting page, no linked pages
        rc, out, _ = _run_cli(_SITE_CRAWLER, ["--url", f"{local_site}/index.html", "--max-depth", "0", "--max-pages", "5"])
        assert rc == 0
        data = json.loads(out)
        assert len(data["pages"]) == 1
        assert data["pages"][0]["url"] == f"{local_site}/index.html"

    def test_canonical_url_duplicate_detection(self) -> None:
        """Verify duplicate canonical URLs are normalized and distinct categories preserved."""
        import sys
        sys.path.insert(0, str(_CLI_DIR))
        from site_crawler import _canonical_url

        # Root page, /index.html and books_1 category page map to identical root canonical
        root = "https://books.toscrape.com/"
        index = "https://books.toscrape.com/index.html"
        books_cat = "https://books.toscrape.com/catalogue/category/books_1/index.html"

        assert _canonical_url(root) == "https://books.toscrape.com/"
        assert _canonical_url(index) == "https://books.toscrape.com/"
        assert _canonical_url(books_cat) == "https://books.toscrape.com/"

        # Valid distinct category pages are preserved
        travel = "https://books.toscrape.com/catalogue/category/books/travel_2/index.html"
        mystery = "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html"

        assert _canonical_url(travel) == "https://books.toscrape.com/catalogue/category/books/travel_2/"
        assert _canonical_url(mystery) == "https://books.toscrape.com/catalogue/category/books/mystery_3/"
        assert _canonical_url(travel) != _canonical_url(root)
        assert _canonical_url(travel) != _canonical_url(mystery)


class TestLinkCheckerCLI:
    def test_version_and_help(self) -> None:
        rc, out, _ = _run_cli(_LINK_CHECKER, ["--version"])
        assert rc == 0
        assert "link_checker" in out

        rc, out, _ = _run_cli(_LINK_CHECKER, ["--help"])
        assert rc == 0
        assert "Exit codes:" in out

    def test_link_checker_exact_schema_and_invariants(self, local_site: str) -> None:
        rc, out, err = _run_cli(_LINK_CHECKER, ["--url", f"{local_site}/index.html", "--max-links", "10"])
        # Should exit 2 because index.html contains /broken.html (404)
        assert rc in (0, 2)
        data = json.loads(out)
        assert "site" in data
        assert "links" in data
        assert "stats" in data

        # Invariant: stats.checked == len(links)
        assert data["stats"]["checked"] == len(data["links"])
        assert data["stats"]["working"] + data["stats"]["broken"] <= data["stats"]["checked"]

        # Check fields of each link
        for lnk in data["links"]:
            assert "url" in lnk
            assert "status" in lnk
            assert lnk["status"] in ("working", "broken", "error")
            if lnk["status"] == "error":
                assert lnk["status_code"] is None
                assert "reason" in lnk

    def test_detects_broken_link(self, local_site: str) -> None:
        rc, out, _ = _run_cli(_LINK_CHECKER, ["--url", f"{local_site}/index.html"])
        data = json.loads(out)
        # Check that broken link was caught
        broken = [lnk for lnk in data["links"] if lnk["status"] == "broken"]
        assert len(broken) > 0 or data["stats"]["broken"] > 0
        assert rc == 2

    def test_ssrf_and_robots_links_never_fetched(self, local_site: str, server_requests: list[str]) -> None:
        """Assert SSRF links are marked error and NEVER fetched; robots links NEVER requested on socket."""
        rc, out, err = _run_cli(_LINK_CHECKER, ["--url", f"{local_site}/links.html"])
        assert rc == 2
        data = json.loads(out)

        # Check SSRF metadata link
        ssrf_links = [lnk for lnk in data["links"] if "169.254.169.254" in lnk["url"]]
        assert len(ssrf_links) == 1
        assert ssrf_links[0]["status"] == "error"
        assert "ssrf_blocked" in ssrf_links[0]["reason"]
        assert ssrf_links[0]["status_code"] is None

        # Check robots-disallowed link
        robots_links = [lnk for lnk in data["links"] if "/private/index.html" in lnk["url"]]
        assert len(robots_links) == 1
        assert robots_links[0]["status"] == "error"
        assert robots_links[0]["reason"] == "robots_disallowed"
        assert robots_links[0]["status_code"] is None

        # Assert via server_requests fixture that /private/index.html was NEVER requested
        assert "/private/index.html" not in server_requests
