"""SQLAlchemy ORM models for the SecQA Hub.

Domain overview:

    Project ─┬─ Run ─┬─ Finding ──(promoted to)──┐
             │       ├─ TestResult ── TestCase   │
             │       └─ PerfMetric               │
             ├─ TestCase                         │
             └─ Defect ◄─────────────────────────┘
                 ├─ DefectComment
                 └─ DefectEvent (history)

`Finding` is raw tool output awaiting triage; `Defect` is the tracked work item
(bug, vulnerability, incident or performance regression) with a lifecycle and SLA.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    # Naive UTC everywhere: SQLite drops tzinfo, and mixing aware/naive breaks comparisons.
    # The API layer re-attaches "Z" on serialization.
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


def str_enum(enum_cls: type[Enum]) -> SAEnum:
    # Store enum *values* as VARCHAR + CHECK, portable across SQLite and Postgres.
    return SAEnum(
        enum_cls,
        native_enum=False,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
        length=32,
    )


class Severity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class RunKind(str, Enum):
    security = "security"
    performance = "performance"
    functional = "functional"
    manual = "manual"


class RunStatus(str, Enum):
    running = "running"
    passed = "passed"
    failed = "failed"
    completed = "completed"
    aborted = "aborted"


class TriageStatus(str, Enum):
    new = "new"
    confirmed = "confirmed"
    false_positive = "false_positive"
    accepted_risk = "accepted_risk"
    duplicate = "duplicate"


class DefectKind(str, Enum):
    bug = "bug"
    vulnerability = "vulnerability"
    incident = "incident"
    performance = "performance"


class DefectStatus(str, Enum):
    new = "new"
    triaged = "triaged"
    in_progress = "in_progress"
    fixed = "fixed"
    verified = "verified"
    closed = "closed"
    wont_fix = "wont_fix"
    duplicate = "duplicate"


OPEN_DEFECT_STATUSES = (DefectStatus.new, DefectStatus.triaged, DefectStatus.in_progress, DefectStatus.fixed)


class Priority(str, Enum):
    p1 = "P1"
    p2 = "P2"
    p3 = "P3"
    p4 = "P4"


class TestType(str, Enum):
    security = "security"
    performance = "performance"
    functional = "functional"
    api = "api"


class TestCaseStatus(str, Enum):
    draft = "draft"
    active = "active"
    deprecated = "deprecated"


class ResultStatus(str, Enum):
    passed = "passed"
    failed = "failed"
    skipped = "skipped"
    blocked = "blocked"
    error = "error"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    repo_url: Mapped[str | None] = mapped_column(String(500))
    defect_seq: Mapped[int] = mapped_column(Integer, default=0)
    testcase_seq: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    runs: Mapped[list[Run]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[RunKind] = mapped_column(str_enum(RunKind))
    status: Mapped[RunStatus] = mapped_column(str_enum(RunStatus), default=RunStatus.running)
    name: Mapped[str | None] = mapped_column(String(200))
    target: Mapped[str | None] = mapped_column(String(500))
    environment: Mapped[str | None] = mapped_column(String(100))
    branch: Mapped[str | None] = mapped_column(String(200))
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    triggered_by: Mapped[str | None] = mapped_column(String(100))
    scope_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    stack_detected: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    finished_at: Mapped[datetime | None]

    project: Mapped[Project] = relationship(back_populates="runs")
    findings: Mapped[list[Finding]] = relationship(back_populates="run", cascade="all, delete-orphan")
    results: Mapped[list[TestResult]] = relationship(back_populates="run", cascade="all, delete-orphan")
    perf_metrics: Mapped[list[PerfMetric]] = relationship(back_populates="run", cascade="all, delete-orphan")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(32))  # recon|sast|sca|secrets|api|dast|perf|manual
    tool: Mapped[str | None] = mapped_column(String(64))
    rule_id: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[Severity] = mapped_column(str_enum(Severity), index=True)
    cvss_score: Mapped[float | None] = mapped_column(Float)
    cvss_vector: Mapped[str | None] = mapped_column(String(200))
    cwe_id: Mapped[str | None] = mapped_column(String(32))
    owasp_id: Mapped[str | None] = mapped_column(String(32))
    iso_control: Mapped[str | None] = mapped_column(String(32))
    file_path: Mapped[str | None] = mapped_column(String(1000))
    line_start: Mapped[int | None]
    line_end: Mapped[int | None]
    endpoint: Mapped[str | None] = mapped_column(String(1000))
    evidence: Mapped[str | None] = mapped_column(Text)
    remediation: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    triage_status: Mapped[TriageStatus] = mapped_column(str_enum(TriageStatus), default=TriageStatus.new)
    defect_id: Mapped[int | None] = mapped_column(ForeignKey("defects.id", ondelete="SET NULL"), index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(100))
    reviewed_at: Mapped[datetime | None]
    review_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    run: Mapped[Run] = relationship(back_populates="findings")
    defect: Mapped[Defect | None] = relationship(back_populates="findings")


class Defect(Base):
    __tablename__ = "defects"
    __table_args__ = (UniqueConstraint("project_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(32))  # e.g. SHOP-12
    kind: Mapped[DefectKind] = mapped_column(str_enum(DefectKind), default=DefectKind.bug)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[Severity] = mapped_column(str_enum(Severity))
    priority: Mapped[Priority] = mapped_column(str_enum(Priority), default=Priority.p3)
    status: Mapped[DefectStatus] = mapped_column(str_enum(DefectStatus), default=DefectStatus.new, index=True)
    assignee: Mapped[str | None] = mapped_column(String(100))
    reporter: Mapped[str | None] = mapped_column(String(100))
    environment: Mapped[str | None] = mapped_column(String(100))
    steps_to_reproduce: Mapped[str | None] = mapped_column(Text)
    expected_result: Mapped[str | None] = mapped_column(Text)
    actual_result: Mapped[str | None] = mapped_column(Text)
    cwe_id: Mapped[str | None] = mapped_column(String(32))
    owasp_id: Mapped[str | None] = mapped_column(String(32))
    iso_control: Mapped[str | None] = mapped_column(String(32))
    tags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    found_in_run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("defects.id", ondelete="SET NULL"))
    due_at: Mapped[datetime | None]
    resolved_at: Mapped[datetime | None]
    closed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    findings: Mapped[list[Finding]] = relationship(back_populates="defect")
    comments: Mapped[list[DefectComment]] = relationship(
        cascade="all, delete-orphan", order_by="DefectComment.created_at"
    )
    events: Mapped[list[DefectEvent]] = relationship(
        cascade="all, delete-orphan", order_by="DefectEvent.at"
    )


class DefectComment(Base):
    __tablename__ = "defect_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    defect_id: Mapped[int] = mapped_column(ForeignKey("defects.id", ondelete="CASCADE"), index=True)
    author: Mapped[str] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class DefectEvent(Base):
    __tablename__ = "defect_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    defect_id: Mapped[int] = mapped_column(ForeignKey("defects.id", ondelete="CASCADE"), index=True)
    actor: Mapped[str] = mapped_column(String(100))
    field: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(default=utcnow)


class TestCase(Base):
    __tablename__ = "test_cases"
    __table_args__ = (UniqueConstraint("project_id", "key"),)
    __test__ = False  # keep pytest from collecting this class

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(32))  # e.g. SHOP-TC-7
    title: Mapped[str] = mapped_column(String(500))
    type: Mapped[TestType] = mapped_column(str_enum(TestType), default=TestType.security)
    suite: Mapped[str | None] = mapped_column(String(200))
    priority: Mapped[Priority] = mapped_column(str_enum(Priority), default=Priority.p3)
    status: Mapped[TestCaseStatus] = mapped_column(str_enum(TestCaseStatus), default=TestCaseStatus.active)
    description: Mapped[str | None] = mapped_column(Text)
    preconditions: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[list[Any]] = mapped_column(JSON, default=list)
    expected_result: Mapped[str | None] = mapped_column(Text)
    automated: Mapped[bool] = mapped_column(Boolean, default=False)
    automation_ref: Mapped[str | None] = mapped_column(String(500))  # e.g. k6 script path, semgrep rule id
    cwe_id: Mapped[str | None] = mapped_column(String(32))
    owasp_id: Mapped[str | None] = mapped_column(String(32))
    iso_control: Mapped[str | None] = mapped_column(String(32))
    tags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class TestResult(Base):
    __tablename__ = "test_results"
    __test__ = False

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    test_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_cases.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(500))
    status: Mapped[ResultStatus] = mapped_column(str_enum(ResultStatus))
    duration_ms: Mapped[float | None] = mapped_column(Float)
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    run: Mapped[Run] = relationship(back_populates="results")


class PerfMetric(Base):
    """Aggregated latency/throughput for one request group in a performance run.

    `name == "__total__"` holds the run-wide aggregate.
    """

    __tablename__ = "perf_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    scenario: Mapped[str] = mapped_column(String(200), default="default")
    name: Mapped[str] = mapped_column(String(500))
    tool: Mapped[str] = mapped_column(String(32))  # k6 | jmeter
    requests: Mapped[int] = mapped_column(Integer, default=0)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    error_rate: Mapped[float] = mapped_column(Float, default=0.0)
    rps: Mapped[float | None] = mapped_column(Float)
    avg_ms: Mapped[float | None] = mapped_column(Float)
    min_ms: Mapped[float | None] = mapped_column(Float)
    med_ms: Mapped[float | None] = mapped_column(Float)
    p90_ms: Mapped[float | None] = mapped_column(Float)
    p95_ms: Mapped[float | None] = mapped_column(Float)
    p99_ms: Mapped[float | None] = mapped_column(Float)
    max_ms: Mapped[float | None] = mapped_column(Float)
    vus_max: Mapped[int | None]
    duration_s: Mapped[float | None] = mapped_column(Float)
    thresholds: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    run: Mapped[Run] = relationship(back_populates="perf_metrics")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    finding_id: Mapped[int | None] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"))
    defect_id: Mapped[int | None] = mapped_column(ForeignKey("defects.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int]
    storage_path: Mapped[str] = mapped_column(String(500))
    # screenshot | http (request/response capture) | file
    kind: Mapped[str] = mapped_column(String(16), default="file", server_default="file")
    caption: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    actor: Mapped[str] = mapped_column(String(100))  # agent | human:<name> | system
    action: Mapped[str] = mapped_column(Text)
    target: Mapped[str | None] = mapped_column(String(1000))
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
