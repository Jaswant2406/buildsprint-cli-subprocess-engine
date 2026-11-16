"""
Post-process raw CLI output: parse, schema-validate, compute status + coverage.
"""
from __future__ import annotations

import json
from typing import Any

from app.models import CoverageBreakdown, RunState, RunStatus
from app.security import get_logger

logger = get_logger(__name__)


def compute_coverage(data: dict[str, Any], plan_dict: dict[str, Any]) -> CoverageBreakdown:
    """Compute coverage score 0-100 with breakdown."""
    pages_limit = plan_dict.get("max_pages", 10)

    if "pages" in data:
        # Site crawler result
        pages_crawled = len(data.get("pages", []))
        errors = data.get("errors", [])
        skipped = data.get("skipped", [])
        robots_skips = sum(1 for s in skipped if "robots" in s.get("reason", "").lower())
        redirect_blocked = sum(1 for s in skipped if "redirect" in s.get("reason", "").lower())
        total = pages_crawled + len(errors) + len(skipped)

        stats = data.get("stats", {})
        if isinstance(stats.get("pages_discovered"), int) and stats["pages_discovered"] > 0:
            pages_discovered = stats["pages_discovered"]
        else:
            pages_discovered = max(total, pages_crawled, 1 if pages_crawled > 0 else 0)

        # Separate page-limit utilization from discovered-page crawl ratio
        limit_utilization = round((pages_crawled / max(pages_limit, 1)) * 100, 2)
        discovered_ratio = round((pages_crawled / max(pages_discovered, 1)) * 100, 2)

        # Full website coverage is ONLY established if:
        # - multiple pages were crawled (pages_crawled > 1)
        # - all discovered pages were crawled (pages_crawled >= pages_discovered)
        # - 0 errors and 0 skipped
        coverage_established = (
            pages_crawled > 1
            and pages_crawled >= pages_discovered
            and len(errors) == 0
            and len(skipped) == 0
        )

        if pages_crawled == 0:
            score = 0
            error_ratio = 1.0 if total > 0 else 0.0
            coverage_established = False
        else:
            error_ratio = len(errors) / max(total, 1)
            # Complete crawl with zero errors or skips
            if len(errors) == 0 and len(skipped) == 0:
                if pages_crawled >= pages_discovered:
                    score = 100
                else:
                    # Partial crawl of discovered pages: score represents the percentage of discovered pages crawled
                    score = max(0, min(100, int(round(discovered_ratio))))
            else:
                penalty = (len(errors) / total) * 35
                base = discovered_ratio if pages_discovered > pages_crawled else (pages_crawled / total) * 100
                score = max(0, min(100, int(base - penalty)))

        util_fmt = f"{limit_utilization:.0f}%" if limit_utilization.is_integer() else f"{limit_utilization:.2f}%"
        ratio_fmt = (
            f"{discovered_ratio:.0f}%"
            if (discovered_ratio.is_integer() and pages_crawled == pages_discovered)
            else f"{discovered_ratio:.2f}%"
        )

        disc_str = f"{pages_crawled} of {pages_discovered} discovered page{'s' if pages_discovered != 1 else ''} crawled (limit: {pages_limit})"
        metrics_str = f"Page limit utilization: {pages_crawled}/{pages_limit} = {util_fmt}, Discovered-page crawl ratio: {pages_crawled}/{pages_discovered} = {ratio_fmt}"
        skip_str = f"{len(errors)} errors, {robots_skips} robots-skipped, {redirect_blocked} redirects-blocked"

        if not coverage_established:
            notes = f"{disc_str}, {metrics_str}, {skip_str}, coverage not fully established"
        else:
            notes = f"{disc_str}, {metrics_str}, {skip_str}"

        return CoverageBreakdown(
            score=score,
            pages_crawled=pages_crawled,
            pages_discovered=pages_discovered,
            pages_limit=pages_limit,
            page_limit_utilization=limit_utilization,
            discovered_ratio=discovered_ratio,
            coverage_established=coverage_established,
            error_ratio=round(error_ratio, 3),
            robots_skips=robots_skips,
            redirects_blocked=redirect_blocked,
            notes=notes,
        )

    elif "links" in data:
        # Link checker result
        stats = data.get("stats", {})
        checked = stats.get("checked", 0)
        working = stats.get("working", 0)
        broken = stats.get("broken", 0)
        total = stats.get("total_links", checked)
        ratio = working / max(checked, 1)
        score = int(ratio * 90 + 10)
        score = max(0, min(100, score))
        notes = f"{working}/{checked} links working, {broken} broken"
        limit_utilization = round((checked / max(pages_limit, 1)) * 100, 2)
        discovered_ratio = round((checked / max(total, 1)) * 100, 2)
        return CoverageBreakdown(
            score=score,
            pages_crawled=checked,
            pages_discovered=total,
            pages_limit=pages_limit,
            page_limit_utilization=limit_utilization,
            discovered_ratio=discovered_ratio,
            coverage_established=checked > 0 and broken == 0,
            error_ratio=round(1 - ratio, 3),
            notes=notes,
        )

    return CoverageBreakdown(score=50, coverage_established=False, notes="unknown output format")


def _build_status_reason(
    exit_code: int | None,
    data: dict[str, Any] | None,
    state: RunState,
) -> str:
    if state == RunState.TIMEOUT:
        return "run timed out"
    if state == RunState.STALLED:
        return "run stalled (no heartbeat for 15s)"
    if state == RunState.CANCELLED:
        return "run was cancelled"
    if data is None:
        return f"no valid output (exit {exit_code})"

    if "pages" in data:
        pages = data.get("pages", [])
        errors = data.get("errors", [])
        skipped = data.get("skipped", [])
        parts = []
        if errors:
            reasons = set(str(e.get("error", ""))[:40] for e in errors[:3])
            parts.append(f"{len(errors)} error(s): {', '.join(reasons)}")
        if skipped:
            parts.append(f"{len(skipped)} skipped")
        reason = "; ".join(parts) if parts else f"{len(pages)} pages crawled"
        return reason

    elif "links" in data:
        stats = data.get("stats", {})
        broken = stats.get("broken", 0)
        total = stats.get("checked", 0)
        if broken:
            return f"{broken} of {total} links broken/error"
        return f"all {total} links working"

    return "output parsed successfully"


def postprocess(
    raw_output: str,
    exit_code: int | None,
    state: RunState,
    plan_dict: dict[str, Any],
) -> dict[str, Any]:
    """
    Parse and validate CLI output.
    Returns dict with status, status_reason, json_valid, data, coverage.
    NEVER returns SUCCESS without valid, parseable output.
    """
    # State overrides everything for terminal failure states
    if state == RunState.CANCELLED:
        return {
            "status": RunStatus.CANCELLED,
            "status_reason": "run was cancelled",
            "json_valid": False,
            "data": None,
            "coverage": CoverageBreakdown(score=0, coverage_established=False, notes="cancelled"),
        }
    if state == RunState.TIMEOUT:
        return {
            "status": RunStatus.TIMEOUT,
            "status_reason": "run timed out",
            "json_valid": False,
            "data": None,
            "coverage": CoverageBreakdown(score=0, coverage_established=False, notes="timeout"),
        }
    if state == RunState.STALLED:
        return {
            "status": RunStatus.FAILED,
            "status_reason": "run stalled (no heartbeat for 15s)",
            "json_valid": False,
            "data": None,
            "coverage": CoverageBreakdown(score=0, coverage_established=False, notes="stalled"),
        }

    # Try to parse JSON
    data: dict[str, Any] | None = None
    json_valid = False

    try:
        data = json.loads(raw_output.strip())
        if not isinstance(data, dict):
            raise ValueError("Top-level JSON must be an object")
        json_valid = True
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse CLI output: {e}")

    if not json_valid or data is None:
        return {
            "status": RunStatus.FAILED,
            "status_reason": f"invalid or missing JSON output (exit {exit_code})",
            "json_valid": False,
            "data": None,
            "coverage": CoverageBreakdown(score=0, coverage_established=False, notes="invalid output"),
        }

    # Determine status from exit code + data
    if exit_code == 0:
        # Validate required fields
        if "pages" in data or "links" in data:
            status = RunStatus.SUCCESS
        else:
            status = RunStatus.FAILED
            json_valid = False
    elif exit_code == 2:
        status = RunStatus.PARTIAL
    elif exit_code == 3:
        status = RunStatus.FAILED  # robots blocked
    elif exit_code == 4:
        status = RunStatus.FAILED  # unreachable
    else:
        status = RunStatus.FAILED

    if not json_valid:
        status = RunStatus.FAILED

    coverage = compute_coverage(data, plan_dict)
    status_reason = _build_status_reason(exit_code, data, state)

    return {
        "status": status,
        "status_reason": status_reason,
        "json_valid": json_valid,
        "data": data if json_valid else None,
        "coverage": coverage,
    }
