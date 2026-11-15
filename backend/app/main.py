"""
FastAPI application: thin routes, all business logic delegated to modules.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.extractor import build_extracted
from app.injection import scan_crawl_result
from app.intent import parse_intent
from app.models import (
    AskRequest,
    AskResponse,
    ChatRequest,
    ChatResult,
    HealthResponse,
    RunState,
    RunStatus,
)
from app.postprocess import postprocess
from app.ratelimit import RateLimiter, get_client_ip
from app.report import generate_report
from app.runner import TOOL_REGISTRY, get_slot_manager, run_tool_async
from app.runstore import RunRecord, get_store
from app.security import configure_logging, get_logger, redact_dict
from app.summarizer import answer_from_data, summarize, summarize_link_check
from app.validators import ValidationError, validate_url

configure_logging()
logger = get_logger(__name__)

settings = get_settings()
app = FastAPI(title="BuildSprint Backend", version=settings.version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_rate_limiter = RateLimiter(
    limit=settings.rate_limit_requests,
    window_s=settings.rate_limit_window_s,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sse_event(event: str, data: Any, run_id: str = "") -> dict[str, str]:
    payload = {"run_id": run_id, "event": event, "data": data}
    return {"event": event, "data": json.dumps(payload)}


def _json_error(status_code: int, error: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": error, **extra})


# ---------------------------------------------------------------------------
# /api/chat  — main SSE endpoint
# ---------------------------------------------------------------------------


@app.post("/api/chat")
async def chat(request: Request, body: ChatRequest) -> EventSourceResponse:
    # Rate limiting
    client_ip = get_client_ip(dict(request.scope), settings.trusted_proxy_list)
    allowed, retry_after = _rate_limiter.check(client_ip)
    if not allowed:
        raise _json_error(429, "rate_limit_exceeded", retry_after_s=retry_after)

    prompt = body.prompt.strip()
    if not prompt:
        raise _json_error(400, "prompt is required")
    if len(prompt) > settings.max_prompt_chars:
        raise _json_error(400, f"prompt exceeds {settings.max_prompt_chars} chars")

    run_id = str(uuid.uuid4())

    async def _stream() -> AsyncIterator[dict[str, str]]:
        store = get_store()

        yield _make_sse_event("received", {"prompt": prompt[:200]}, run_id)

        # Parse intent
        try:
            plan = parse_intent(prompt)
        except ValidationError as e:
            yield _make_sse_event("error", {"error": str(e), "reason": e.reason}, run_id)
            return

        yield _make_sse_event("plan", plan.model_dump(), run_id)

        # Validate URL
        try:
            validate_url(plan.url, allow_localhost=settings.is_test)
        except ValidationError as e:
            yield _make_sse_event("error", {"error": str(e), "reason": e.reason}, run_id)
            return

        yield _make_sse_event("validated", {"url": plan.url, "tool": plan.tool}, run_id)

        # Acquire slot
        slots = get_slot_manager()
        if not slots.acquire(timeout=settings.run_queue_timeout_s):
            yield _make_sse_event("error", {"error": "server busy, retry later", "reason": "no_slots"}, run_id)
            return

        record = RunRecord(run_id, plan.model_dump(), [])
        store.add(record)

        raw_result: str | None = None
        exit_code: int | None = None
        client_disconnected = False

        try:
            async for evt in run_tool_async(record, plan):
                event_name = evt.get("event", "progress")
                data = evt.get("data", {})

                if event_name == "_raw_result":
                    raw_result = data.get("stdout")
                    exit_code = data.get("exit_code")
                    continue

                yield _make_sse_event(event_name, data, run_id)

                # Check for SSE disconnect
                if await request.is_disconnected():
                    client_disconnected = True
                    # Cancel if still running
                    from app.runner import _transition
                    _transition(record, RunState.CANCELLED)
                    break

        except asyncio.CancelledError:
            client_disconnected = True
            from app.runner import _transition
            _transition(record, RunState.CANCELLED)
        finally:
            slots.release()

        if client_disconnected:
            store.finalize(record)
            return

        # Post-process
        yield _make_sse_event("parsing", {"exit_code": exit_code}, run_id)

        pp = postprocess(
            raw_result or "",
            exit_code,
            record.state,
            plan.model_dump(),
        )

        crawl_data: dict[str, Any] | None = pp.get("data")

        # Inject scan
        security_findings = []
        if crawl_data and "pages" in crawl_data:
            security_findings = scan_crawl_result(crawl_data)
            if security_findings:
                logger.warning(
                    "Injection patterns detected",
                    extra={"run_id": run_id, "count": len(security_findings)},
                )

        # Summarize
        summary = ""
        key_takeaways: list[str] = []
        if plan.wants_summary and crawl_data:
            yield _make_sse_event("summarizing", {}, run_id)
            if "pages" in crawl_data:
                summary, key_takeaways = summarize(crawl_data)
            elif "links" in crawl_data:
                summary, key_takeaways = summarize_link_check(crawl_data)

        # Build extracted evidence
        evidence = None
        if crawl_data and "pages" in crawl_data:
            evidence = build_extracted(crawl_data, plan.extract_focus)

        # Finalize record
        record.result = crawl_data
        record.end_time = time.monotonic()
        audit_hash = store.finalize(record)

        result = ChatResult(
            run_id=run_id,
            status=pp["status"],
            status_reason=pp["status_reason"],
            exit_code=exit_code,
            duration_s=round(record.duration_s(), 3),
            pages_crawled=len(crawl_data.get("pages", [])) if crawl_data else 0,
            summary=summary,
            key_takeaways=key_takeaways,
            json=crawl_data,
            json_valid=pp["json_valid"],
            coverage=pp.get("coverage"),
            security_findings=security_findings,
            errors=[str(e) for e in (crawl_data.get("errors", []) if crawl_data else [])],
            evidence=evidence,
            audit_hash=audit_hash,
        )

        record.result = result.model_dump(by_alias=True)

        yield _make_sse_event("result", result.model_dump(by_alias=True), run_id)

    return EventSourceResponse(_stream())


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> Response:
    store = get_store()
    record = store.get(run_id)
    if record is None:
        raise _json_error(404, "run not found")

    with record._lock:
        if record.state.is_terminal:
            return JSONResponse(
                status_code=409,
                content={"error": "already_terminal", "state": record.state.value, "run_id": run_id},
            )
        record.state = RunState.CANCELLED

    return JSONResponse(status_code=200, content={"run_id": run_id, "state": RunState.CANCELLED.value})


# ---------------------------------------------------------------------------
# Run history
# ---------------------------------------------------------------------------


@app.get("/api/runs")
async def list_runs() -> list[dict[str, Any]]:
    store = get_store()
    return [redact_dict(r.to_dict()) for r in store.all_runs()]


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    store = get_store()
    record = store.get(run_id)
    if record is None:
        raise _json_error(404, "run not found")
    return redact_dict(record.to_dict())


@app.get("/api/runs/{run_id}/logs")
async def get_logs(run_id: str) -> dict[str, Any]:
    store = get_store()
    record = store.get(run_id)
    if record is None:
        raise _json_error(404, "run not found")
    return {
        "run_id": run_id,
        "stdout": redact_dict(record.stdout),
        "stderr": redact_dict(record.stderr),
        "events": record.events,
    }


@app.get("/api/runs/{run_id}/report.md")
async def get_report(run_id: str) -> Response:
    store = get_store()
    record = store.get(run_id)
    if record is None:
        raise _json_error(404, "run not found")

    if record.result is None:
        raise _json_error(409, "run not completed")

    # Reconstruct result
    result_data = record.result if isinstance(record.result, dict) else {}
    # Build a minimal ChatResult for the report
    result = ChatResult(
        run_id=run_id,
        status=RunStatus(result_data.get("status", "FAILED")),
        status_reason=result_data.get("status_reason", ""),
        exit_code=record.exit_code,
        duration_s=record.duration_s(),
        pages_crawled=result_data.get("pages_crawled", 0),
        summary=result_data.get("summary", ""),
        key_takeaways=result_data.get("key_takeaways", []),
        json_valid=result_data.get("json_valid", False),
        audit_hash=result_data.get("audit_hash", ""),
    )

    md = generate_report(result, record.to_dict())
    return Response(content=md, media_type="text/markdown")


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


@app.post("/api/runs/{run_id}/replay")
async def replay_run(run_id: str) -> EventSourceResponse:
    store = get_store()
    record = store.get(run_id)
    if record is None:
        raise _json_error(404, "run not found")

    async def _replay() -> AsyncIterator[dict[str, str]]:
        for evt in record.events:
            yield _make_sse_event(evt["event"], evt["data"], run_id)
            await asyncio.sleep(0.05)
        if record.result:
            yield _make_sse_event("result", record.result, run_id)

    return EventSourceResponse(_replay())


# ---------------------------------------------------------------------------
# Ask
# ---------------------------------------------------------------------------


@app.post("/api/runs/{run_id}/ask")
async def ask_run(run_id: str, body: AskRequest) -> AskResponse:
    store = get_store()
    record = store.get(run_id)
    if record is None:
        raise _json_error(404, "run not found")

    crawl_data = record.result
    if not crawl_data or not isinstance(crawl_data, dict):
        raise _json_error(409, "no crawl data available for this run")

    # If result is the ChatResult dict, extract the json field
    if "json" in crawl_data and isinstance(crawl_data["json"], dict):
        crawl_data = crawl_data["json"]
    elif "pages" not in crawl_data and "links" not in crawl_data:
        raise _json_error(409, "no crawl data available for this run")

    answer, citations = answer_from_data(body.question, crawl_data)
    return AskResponse(answer=answer, citations=citations)


# ---------------------------------------------------------------------------
# Tools, audit, health
# ---------------------------------------------------------------------------


@app.get("/api/tools")
async def get_tools() -> dict[str, Any]:
    return {"tools": list(TOOL_REGISTRY.values())}


@app.get("/api/audit")
async def get_audit() -> dict[str, Any]:
    store = get_store()
    chain = store.audit.get_chain()
    return chain.model_dump()


@app.get("/api/health")
async def health() -> HealthResponse:
    return HealthResponse(
        llm_mode=settings.llm_mode,
        version=settings.version,
    )
