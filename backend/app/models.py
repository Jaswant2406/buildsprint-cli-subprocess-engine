"""Pydantic v2 models for all domain objects."""
from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, Field


class RunState(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    STALLED = "stalled"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (
            RunState.COMPLETED,
            RunState.FAILED,
            RunState.TIMEOUT,
            RunState.STALLED,
            RunState.CANCELLED,
        )


class RunStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"


class Plan(BaseModel):
    task_type: str = Field(description="Type: crawl, link_check, extract, summarize")
    tool: str = Field(description="Tool to use: site_crawler or link_checker")
    tool_reason: str = Field(description="One-line reason why this tool was chosen")
    url: str = Field(description="Target URL")
    max_pages: int = Field(default=10, ge=1, le=25)
    max_depth: int = Field(default=2, ge=1, le=3)
    wants_summary: bool = Field(default=True)
    wants_json: bool = Field(default=True)
    extract_focus: str = Field(default="", description="e.g. 'only emails'")
    max_links: int = Field(default=25, ge=1, le=50)


class RunEvent(BaseModel):
    event: str
    data: dict[str, Any] = Field(default_factory=dict)
    run_id: str = ""


class KeyPage(BaseModel):
    url: str
    title: str
    role: str  # home/about/contact/pricing/blog/docs/other


class ContactItem(BaseModel):
    value: str
    source_url: str


class SocialLink(BaseModel):
    value: str
    source_url: str


class Contact(BaseModel):
    emails: list[ContactItem] = Field(default_factory=list)
    phones: list[ContactItem] = Field(default_factory=list)
    addresses: list[ContactItem] = Field(default_factory=list)


class SocialLinks(BaseModel):
    twitter: SocialLink | None = None
    linkedin: SocialLink | None = None
    github: SocialLink | None = None
    facebook: SocialLink | None = None
    instagram: SocialLink | None = None
    youtube: SocialLink | None = None


class ExtractedStats(BaseModel):
    pages_crawled: int = 0
    total_links: int = 0
    total_images: int = 0


class Extracted(BaseModel):
    site_name: str = ""
    domain: str = ""
    description: str = ""
    language: str = ""
    main_topics: list[str] = Field(default_factory=list)
    key_pages: list[KeyPage] = Field(default_factory=list)
    contact: Contact = Field(default_factory=Contact)
    social_links: SocialLinks = Field(default_factory=SocialLinks)
    tech_hints: list[str] = Field(default_factory=list)
    stats: ExtractedStats = Field(default_factory=ExtractedStats)
    focus_result: dict[str, Any] | None = None


class SecurityFinding(BaseModel):
    page_url: str
    pattern: str
    snippet: str


class CoverageBreakdown(BaseModel):
    score: int | None = Field(default=None, ge=0, le=100)
    pages_crawled: int = 0
    pages_discovered: int = 0
    pages_limit: int = 0
    page_limit_utilization: float = 0.0
    discovered_ratio: float = 0.0
    coverage_established: bool = False
    error_ratio: float = 0.0
    robots_skips: int = 0
    redirects_blocked: int = 0
    notes: str = ""


class JobRecord(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    date_posted: str | None = None
    description: str | None = None
    job_url: str | None = None
    apply_url: str | None = None
    source_url: str


class JobExtractionStats(BaseModel):
    total_jobs: int = 0
    companies: int = 0
    locations: int = 0
    with_job_url: int = 0
    with_apply_url: int = 0
    with_date: int = 0
    with_description: int = 0
    crawled_detail_pages: int = 0
    is_partial_crawl: bool = False
    coverage_note: str = ""


class JobExtractionResult(BaseModel):
    records: list[JobRecord] = Field(default_factory=list)
    stats: JobExtractionStats = Field(default_factory=JobExtractionStats)


class ChatResult(BaseModel):
    run_id: str
    status: RunStatus
    status_reason: str = ""
    exit_code: int | None = None
    duration_s: float = 0.0
    pages_crawled: int = 0
    summary: str = ""
    key_takeaways: list[str] = Field(default_factory=list)
    json_output: dict[str, Any] | None = Field(default=None, alias="json")
    json_valid: bool = False
    coverage: CoverageBreakdown | None = None
    coverage_score: int | None = None
    coverage_breakdown: str | None = None
    security_findings: list[SecurityFinding] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    evidence: Extracted | None = None
    jobs: JobExtractionResult | None = None
    audit_hash: str = ""

    model_config = {"populate_by_name": True}


class AuditEntry(BaseModel):
    run_id: str
    tool: str
    argv: list[str]
    exit_code: int | None
    stdout_sha256: str
    state: str
    timestamp: str
    prev_hash: str
    hash: str


class AuditChain(BaseModel):
    entries: list[AuditEntry]
    records: list[AuditEntry] = Field(default_factory=list)
    length: int = 0
    verified: bool


# --- API request/response models ---

class ChatRequest(BaseModel):
    prompt: str = Field(max_length=1000)


class CancelRequest(BaseModel):
    pass


class AskRequest(BaseModel):
    question: str = Field(max_length=500)


class AskResponse(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    llm_mode: str
    version: str
    status: str = "ok"
