"""
Prompt injection pattern detector.
Scans crawled content for injection attempts.
Detection is reporting-only; it never changes control flow.
"""
from __future__ import annotations

import base64
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import SecurityFinding

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ignore_instructions", re.compile(
        r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.IGNORECASE
    )),
    ("system_prompt", re.compile(
        r"(system\s+prompt|you\s+are\s+an?\s+ai|your\s+instructions?)", re.IGNORECASE
    )),
    ("run_command", re.compile(
        r"(run\s+command|execute\s+|shell\s+command|subprocess|os\.system|eval\(|exec\()",
        re.IGNORECASE
    )),
    ("rm_rf", re.compile(r"rm\s+-rf|del\s+/[qsf]|format\s+c:", re.IGNORECASE)),
    ("exfiltrate", re.compile(
        r"(send\s+(all\s+)?(your\s+)?(data|context|conversation)|exfiltrat|leak\s+)",
        re.IGNORECASE
    )),
    ("hidden_text", re.compile(
        r"(color\s*:\s*#?fff(fff)?|font-size\s*:\s*0|display\s*:\s*none|visibility\s*:\s*hidden)",
        re.IGNORECASE
    )),
    ("override_role", re.compile(
        r"(act\s+as\s+(a\s+)?(different|new|another)|pretend\s+you\s+are|you\s+are\s+now)",
        re.IGNORECASE
    )),
]

_MAX_SNIPPET_LEN = 120


def _check_base64_blobs(text: str) -> list[tuple[str, str]]:
    """Find base64 blobs that decode to instruction-like strings."""
    findings: list[tuple[str, str]] = []
    # Look for long base64-looking strings
    for m in re.finditer(r"[A-Za-z0-9+/]{40,}={0,2}", text):
        blob = m.group(0)
        try:
            decoded = base64.b64decode(blob + "==").decode("utf-8", errors="replace")
            for name, pat in _PATTERNS:
                if pat.search(decoded):
                    snippet = decoded[:_MAX_SNIPPET_LEN]
                    findings.append((f"base64_{name}", snippet))
                    break
        except Exception:
            pass
    return findings


def scan_page(page_url: str, text: str) -> "list[SecurityFinding]":
    """
    Scan a page's text content for injection patterns.
    Returns a list of SecurityFinding objects.
    """
    from app.models import SecurityFinding

    results: list[SecurityFinding] = []

    for name, pat in _PATTERNS:
        m = pat.search(text)
        if m:
            start = max(0, m.start() - 20)
            end = min(len(text), m.end() + 20)
            snippet = text[start:end].strip()[:_MAX_SNIPPET_LEN]
            results.append(SecurityFinding(
                page_url=page_url,
                pattern=name,
                snippet=snippet,
            ))

    # Base64 blobs
    for name, snippet in _check_base64_blobs(text):
        results.append(SecurityFinding(
            page_url=page_url,
            pattern=name,
            snippet=snippet,
        ))

    return results


def scan_crawl_result(crawl_data: dict) -> "list[SecurityFinding]":
    """Scan all pages in a crawl result."""
    findings: list[SecurityFinding] = []
    for page in crawl_data.get("pages", []):
        url = page.get("url", "")
        text = " ".join([
            page.get("title", ""),
            page.get("meta_description", ""),
            " ".join(page.get("h1_headings", [])),
            " ".join(page.get("h2_headings", [])),
            page.get("main_text", ""),
        ])
        findings.extend(scan_page(url, text))
    return findings
