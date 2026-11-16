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
    (
        "ignore_instructions",
        re.compile(
            r"\b(?:ignore|disregard|forget|skip|clear)\s+(?:all\s+)?(?:previous|prior|above|former|preceding|initial|system)\s+(?:instructions?|directives?|prompts?|rules?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "system_prompt",
        re.compile(
            r"\b(?:system\s+prompt\s*(?:override|injection|bypass|leak|reveal|ignore|reset)|reveal\s+(?:the\s+|your\s+)?(?:system\s+prompt|developer\s+instructions?|initial\s+prompt)|new\s+system\s+prompt\s*[:=]|repeat\s+(?:the\s+|your\s+)?(?:system\s+prompt|developer\s+instructions?))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "run_command",
        re.compile(
            r"(?:\b(?:run|execute|spawn)\s+(?:the\s+)?(?:following\s+)?(?:shell\s+|bash\s+|system\s+|cmd\s+|terminal\s+)?(?:command|binary|script|executable)\s*[:=]|\b(?:run|execute)\s+command\s*[:=]?|\b(?:shell|bash|powershell|cmd|terminal)\s+command\s*[:=]|\b(?:run|execute)\s+(?:the\s+)?(?:command\s+)?[\"']?(?:rm\s+-rf|del\s+/[qsf]|curl\s+|wget\s+|chmod\s+|bash\s+-c|sh\s+-c|powershell\s+)|\b(?:os\.system|subprocess\.(?:run|Popen|call|check_output))\s*\(|\b(?:eval|exec)\s*\(\s*[\"'])",
            re.IGNORECASE,
        ),
    ),
    (
        "rm_rf",
        re.compile(
            r"\b(?:rm\s+-rf|del\s+/[qsf]|format\s+[a-z]:)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "exfiltrate",
        re.compile(
            r"\b(?:send|exfiltrate|transmit|post|upload)\s+(?:all\s+)?(?:the\s+|your\s+)?(?:data|context|conversation|secrets?|passwords?|credentials?|api[_\s]?keys?)\s+(?:to\s+|towards\s+https?://|via\s+webhook)|\b(?:exfiltrat(?:e|ion)\s+(?:data|secrets?|credentials?|keys?))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "hidden_text",
        re.compile(
            r"(?:color\s*:\s*(?:#?fff(?:fff)?|white)\s*;\s*font-size\s*:\s*0|font-size\s*:\s*0(?:px)?\s*;\s*color\s*:\s*(?:#?fff(?:fff)?|white)|font-size\s*:\s*0px?\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "override_role",
        re.compile(
            r"\b(?:you\s+are\s+now\s+(?:an?\s+)?(?:different|new|another|unrestricted|jailbroken|evil|rogue|DAN|assistant|bot|agent)\b|act\s+as\s+(?:a\s+)?(?:different|new|another|unrestricted|jailbroken|evil|rogue|DAN)\b|pretend\s+you\s+are\s+(?:a\s+)?(?:different|new|another|unrestricted|jailbroken|evil|DAN)\b)",
            re.IGNORECASE,
        ),
    ),
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
