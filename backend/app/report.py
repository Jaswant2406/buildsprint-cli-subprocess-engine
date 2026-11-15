"""
Markdown report generator.
"""
from __future__ import annotations

from typing import Any

from app.models import ChatResult


def generate_report(result: ChatResult, record_dict: dict[str, Any]) -> str:
    """Generate a markdown report for a completed run."""
    plan = record_dict.get("plan", {})
    lines: list[str] = []

    lines.append(f"# BuildSprint Run Report: `{result.run_id}`\n")

    # Plan
    lines.append("## Plan\n")
    lines.append(f"- **Tool**: `{plan.get('tool', 'unknown')}`")
    lines.append(f"- **URL**: {plan.get('url', 'N/A')}")
    lines.append(f"- **Tool Reason**: {plan.get('tool_reason', 'N/A')}")
    lines.append(f"- **Task Type**: {plan.get('task_type', 'N/A')}\n")

    # Status
    lines.append("## Status\n")
    lines.append(f"- **Status**: `{result.status}`")
    lines.append(f"- **Status Reason**: {result.status_reason}")
    lines.append(f"- **Exit Code**: {result.exit_code}")
    lines.append(f"- **Duration**: {result.duration_s:.2f}s")
    lines.append(f"- **JSON Valid**: {result.json_valid}\n")

    # Summary
    if result.summary:
        lines.append("## Summary\n")
        lines.append(result.summary)
        lines.append("")

    # Key Takeaways
    if result.key_takeaways:
        lines.append("## Key Takeaways\n")
        for t in result.key_takeaways:
            lines.append(f"- {t}")
        lines.append("")

    # Evidence / Extracted Facts
    if result.evidence:
        ev = result.evidence
        lines.append("## Extracted Facts\n")
        if ev.site_name:
            lines.append(f"- **Site Name**: {ev.site_name}")
        if ev.domain:
            lines.append(f"- **Domain**: {ev.domain}")
        if ev.description:
            lines.append(f"- **Description**: {ev.description}")
        if ev.language:
            lines.append(f"- **Language**: {ev.language}")
        if ev.main_topics:
            lines.append(f"- **Topics**: {', '.join(ev.main_topics)}")

        if ev.contact.emails:
            lines.append("\n### Emails")
            for item in ev.contact.emails:
                lines.append(f"  - `{item.value}` (from {item.source_url})")

        if ev.contact.phones:
            lines.append("\n### Phones")
            for item in ev.contact.phones:
                lines.append(f"  - `{item.value}` (from {item.source_url})")

        if ev.key_pages:
            lines.append("\n### Key Pages")
            for kp in ev.key_pages[:5]:
                lines.append(f"  - [{kp.title}]({kp.url}) — *{kp.role}*")
        lines.append("")

    # Security Findings
    if result.security_findings:
        lines.append("## ⚠️ Security Findings\n")
        lines.append("> Potential prompt injection attempts detected in crawled content.")
        lines.append("> Content is treated as data only — no execution triggered.\n")
        for f in result.security_findings:
            lines.append(f"- **Page**: {f.page_url}")
            lines.append(f"  - Pattern: `{f.pattern}`")
            lines.append(f"  - Snippet: `{f.snippet}`")
        lines.append("")

    # Coverage
    if result.coverage:
        c = result.coverage
        lines.append("## Coverage Score\n")
        lines.append(f"**Score**: {c.score}/100\n")
        lines.append(f"{c.notes}\n")

    # Errors
    if result.errors:
        lines.append("## Errors\n")
        for err in result.errors:
            lines.append(f"- {err}")
        lines.append("")

    # Audit
    if result.audit_hash:
        lines.append("## Audit\n")
        lines.append(f"- **Audit Hash**: `{result.audit_hash}`")
        lines.append("")

    return "\n".join(lines)
