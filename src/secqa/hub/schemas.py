"""Pydantic request/response models for the Hub API."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from .models import (
    DefectKind,
    DefectStatus,
    Priority,
    ResultStatus,
    RunKind,
    RunStatus,
    Severity,
    TestCaseStatus,
    TestType,
    TriageStatus,
)


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


UTCDateTime = Annotated[datetime, PlainSerializer(_iso_utc, return_type=str)]

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# ---- projects --------------------------------------------------------------

class ProjectCreate(BaseModel):
    key: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,15}$", description="Short uppercase key, e.g. SHOP")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    repo_url: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    repo_url: str | None = None


class ProjectOut(ORM):
    id: int
    key: str
    name: str
    description: str | None
    repo_url: str | None
    created_at: UTCDateTime


class ProjectSummary(ProjectOut):
    open_defects: int = 0
    critical_open: int = 0
    last_run_at: UTCDateTime | None = None
    run_count: int = 0


# ---- runs ------------------------------------------------------------------

class RunCreate(BaseModel):
    kind: RunKind
    name: str | None = None
    target: str | None = None
    environment: str | None = None
    branch: str | None = None
    commit_sha: str | None = None
    triggered_by: str | None = None
    scope_snapshot: dict[str, Any] | None = None
    notes: str | None = None


class RunUpdate(BaseModel):
    name: str | None = None
    status: RunStatus | None = None
    stack_detected: dict[str, Any] | None = None
    notes: str | None = None
    is_baseline: bool | None = None


class RunFinish(BaseModel):
    status: RunStatus | None = None  # inferred from results when omitted
    notes: str | None = None


class RunOut(ORM):
    id: int
    project_id: int
    project_key: str | None = None
    kind: RunKind
    status: RunStatus
    name: str | None
    target: str | None
    environment: str | None
    branch: str | None
    commit_sha: str | None
    triggered_by: str | None
    scope_snapshot: dict[str, Any] | None
    stack_detected: dict[str, Any] | None
    summary: dict[str, Any] | None
    notes: str | None
    is_baseline: bool
    started_at: UTCDateTime
    finished_at: UTCDateTime | None
    duration_s: float | None = None
    findings_by_severity: dict[str, int] = {}
    results_by_status: dict[str, int] = {}


# ---- findings --------------------------------------------------------------

class FindingCreate(BaseModel):
    source: str = "manual"
    tool: str | None = None
    rule_id: str | None = None
    category: str = "uncategorized"
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    severity: Severity
    cvss_score: float | None = Field(default=None, ge=0, le=10)
    cvss_vector: str | None = None
    cwe_id: str | None = None
    owasp_id: str | None = None
    iso_control: str | None = None
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    endpoint: str | None = None
    evidence: str | None = None
    remediation: str | None = None
    fingerprint: str | None = None


class FindingTriage(BaseModel):
    triage_status: TriageStatus | None = None
    severity: Severity | None = None
    category: str | None = None
    cwe_id: str | None = None
    owasp_id: str | None = None
    iso_control: str | None = None
    remediation: str | None = None
    review_comment: str | None = None


class BulkTriage(BaseModel):
    ids: list[int] = Field(min_length=1)
    triage_status: TriageStatus
    review_comment: str | None = None


class FindingOut(ORM):
    id: int
    run_id: int
    project_id: int
    source: str
    tool: str | None
    rule_id: str | None
    category: str
    title: str
    description: str | None
    severity: Severity
    cvss_score: float | None
    cvss_vector: str | None
    cwe_id: str | None
    owasp_id: str | None
    iso_control: str | None
    file_path: str | None
    line_start: int | None
    line_end: int | None
    endpoint: str | None
    evidence: str | None
    remediation: str | None
    fingerprint: str
    triage_status: TriageStatus
    defect_id: int | None
    defect_key: str | None = None
    reviewed_by: str | None
    reviewed_at: UTCDateTime | None
    review_comment: str | None
    created_at: UTCDateTime
    first_seen_run_id: int | None = None


class IngestResult(BaseModel):
    created: int
    suppressed: int = 0
    linked_to_defects: int = 0
    skipped: int = 0
    detail: dict[str, Any] = {}


# ---- defects ---------------------------------------------------------------

class DefectCreate(BaseModel):
    kind: DefectKind = DefectKind.bug
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    severity: Severity
    priority: Priority = Priority.p3
    assignee: str | None = None
    environment: str | None = None
    steps_to_reproduce: str | None = None
    expected_result: str | None = None
    actual_result: str | None = None
    cwe_id: str | None = None
    owasp_id: str | None = None
    iso_control: str | None = None
    tags: list[str] = []
    found_in_run_id: int | None = None
    finding_ids: list[int] = []


class DefectFromFindings(BaseModel):
    finding_ids: list[int] = Field(min_length=1)
    title: str | None = None
    priority: Priority | None = None
    assignee: str | None = None


class DefectUpdate(BaseModel):
    kind: DefectKind | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    severity: Severity | None = None
    priority: Priority | None = None
    status: DefectStatus | None = None
    assignee: str | None = None
    environment: str | None = None
    steps_to_reproduce: str | None = None
    expected_result: str | None = None
    actual_result: str | None = None
    cwe_id: str | None = None
    owasp_id: str | None = None
    iso_control: str | None = None
    tags: list[str] | None = None
    duplicate_of_id: int | None = None
    due_at: datetime | None = None


class CommentCreate(BaseModel):
    body: str = Field(min_length=1)


class CommentOut(ORM):
    id: int
    author: str
    body: str
    created_at: UTCDateTime


class EventOut(ORM):
    id: int
    actor: str
    field: str
    old_value: str | None
    new_value: str | None
    at: UTCDateTime


class AttachmentOut(ORM):
    id: int
    filename: str
    content_type: str
    size: int
    created_at: UTCDateTime
    url: str = ""


class DefectOut(ORM):
    id: int
    project_id: int
    key: str
    kind: DefectKind
    title: str
    description: str | None
    severity: Severity
    priority: Priority
    status: DefectStatus
    assignee: str | None
    reporter: str | None
    environment: str | None
    steps_to_reproduce: str | None
    expected_result: str | None
    actual_result: str | None
    cwe_id: str | None
    owasp_id: str | None
    iso_control: str | None
    tags: list[str]
    found_in_run_id: int | None
    duplicate_of_id: int | None
    due_at: UTCDateTime | None
    resolved_at: UTCDateTime | None
    closed_at: UTCDateTime | None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    sla_breached: bool = False
    finding_count: int = 0


class DefectDetail(DefectOut):
    comments: list[CommentOut] = []
    events: list[EventOut] = []
    attachments: list[AttachmentOut] = []
    findings: list[FindingOut] = []


# ---- test cases ------------------------------------------------------------

class TestStep(BaseModel):
    action: str
    expected: str | None = None


class TestCaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    type: TestType = TestType.security
    suite: str | None = None
    priority: Priority = Priority.p3
    status: TestCaseStatus = TestCaseStatus.active
    description: str | None = None
    preconditions: str | None = None
    steps: list[TestStep] = []
    expected_result: str | None = None
    automated: bool = False
    automation_ref: str | None = None
    cwe_id: str | None = None
    owasp_id: str | None = None
    iso_control: str | None = None
    tags: list[str] = []


class TestCaseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    type: TestType | None = None
    suite: str | None = None
    priority: Priority | None = None
    status: TestCaseStatus | None = None
    description: str | None = None
    preconditions: str | None = None
    steps: list[TestStep] | None = None
    expected_result: str | None = None
    automated: bool | None = None
    automation_ref: str | None = None
    cwe_id: str | None = None
    owasp_id: str | None = None
    iso_control: str | None = None
    tags: list[str] | None = None


class TestCaseOut(ORM):
    id: int
    project_id: int
    key: str
    title: str
    type: TestType
    suite: str | None
    priority: Priority
    status: TestCaseStatus
    description: str | None
    preconditions: str | None
    steps: list[TestStep]
    expected_result: str | None
    automated: bool
    automation_ref: str | None
    cwe_id: str | None
    owasp_id: str | None
    iso_control: str | None
    tags: list[str]
    created_at: UTCDateTime
    updated_at: UTCDateTime
    last_status: ResultStatus | None = None
    last_run_id: int | None = None


class TestResultCreate(BaseModel):
    name: str
    status: ResultStatus
    test_case_key: str | None = None
    duration_ms: float | None = None
    message: str | None = None


class TestResultOut(ORM):
    id: int
    run_id: int
    test_case_id: int | None
    test_case_key: str | None = None
    name: str
    status: ResultStatus
    duration_ms: float | None
    message: str | None
    created_at: UTCDateTime


# ---- performance -----------------------------------------------------------

class PerfMetricOut(ORM):
    id: int
    run_id: int
    scenario: str
    name: str
    tool: str
    requests: int
    failures: int
    error_rate: float
    rps: float | None
    avg_ms: float | None
    min_ms: float | None
    med_ms: float | None
    p90_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    max_ms: float | None
    vus_max: int | None
    duration_s: float | None
    thresholds: dict[str, Any] | None


# ---- audit -----------------------------------------------------------------

class AuditCreate(BaseModel):
    action: str = Field(min_length=1)
    target: str | None = None
    run_id: int | None = None


class AuditOut(ORM):
    id: int
    project_id: int | None
    run_id: int | None
    actor: str
    action: str
    target: str | None
    at: UTCDateTime
