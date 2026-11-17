"""Structured schemas, enums, and error models for Agent orchestration."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EvaluationStatus(StrEnum):
    """Four-state self-check conclusion (DYH-R06, D-13)."""

    MATCHED = "按现有信息符合"
    NOT_MATCHED = "按现有信息不符合"
    MISSING_INFO = "待补充信息"
    NEEDS_USER_REVIEW = "待用户核对"


class ObligationType(StrEnum):
    """Independent obligation classification for tasks/materials (DYH-R10, D-14)."""

    OFFICIAL_REQUIRED = "官方必需"
    OFFICIAL_RECOMMENDED = "官方建议"
    OPTIONAL = "自主可选"
    PENDING_VERIFICATION = "待核实"


class MentorContactStatus(StrEnum):
    """Mentor contact requirement classification (DYH-R09)."""

    EXPLICITLY_REQUIRED = "明确要求"
    OFFICIALLY_RECOMMENDED = "官方建议"
    NOT_MENTIONED = "通知未提及"
    NEEDS_USER_REVIEW = "待用户核对"


class RunStatus(StrEnum):
    """Agent run lifecycle states."""

    RUNNING = "运行中"
    WAITING_USER = "等待用户"
    WAITING_CONFIRMATION = "等待确认"
    COMPLETED = "已完成"
    FAILED = "失败"
    CANCELLED = "已取消"


class AuthLevel(StrEnum):
    """In-product authorization tiers (DYH-R32)."""

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class AgentErrorCode(StrEnum):
    """Explicit failure/pause codes; never mask errors as success."""

    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    MISSING_PERSONAL_FACT = "MISSING_PERSONAL_FACT"
    RULE_CONFLICT_OR_AMBIGUOUS = "RULE_CONFLICT_OR_AMBIGUOUS"
    CONSENT_REQUIRED_OR_REVOKED = "CONSENT_REQUIRED_OR_REVOKED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    MODEL_ERROR = "MODEL_ERROR"
    TOOL_NOT_ALLOWED = "TOOL_NOT_ALLOWED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"


class AgentError(BaseModel):
    """Structured error or pause reason surfaced to business services and UI."""

    code: AgentErrorCode
    message: str
    missing_fields: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class SourceCitation(BaseModel):
    """Traceable reference back to a specific source version and clause locator."""

    source_version_id: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    excerpt: str | None = None


class SourceDocument(BaseModel):
    """Official source document fetched by the public source reader."""

    source_version_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    url: str | None = None
    year: int | None = None
    content: str = Field(min_length=1)
    is_repost: bool = False
    is_expired: bool = False
    missing_attachments: list[str] = Field(default_factory=list)
    unread_ranges: list[str] = Field(default_factory=list)


class ExtractedRequirement(BaseModel):
    """Requirement item extracted from an official source with citation."""

    requirement_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    obligation: ObligationType
    basis: list[SourceCitation] = Field(min_length=1)
    official_deadline: datetime | None = None
    required_fact_keys: list[str] = Field(default_factory=list)
    is_ambiguous: bool = False


class RequirementEvaluation(BaseModel):
    """Four-state evaluation result for a single requirement."""

    requirement_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: EvaluationStatus
    reason: str = Field(min_length=1)
    missing_fields: list[str] = Field(default_factory=list)
    basis: list[SourceCitation] = Field(default_factory=list)


class CandidateTask(BaseModel):
    """Single candidate task generated for user review prior to persistence."""

    task_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    basis: list[SourceCitation] = Field(min_length=1)
    obligation: ObligationType
    official_deadline: datetime | None = None
    suggested_date: date | None = None
    depends_on: list[str] = Field(default_factory=list)
    evidence_required: str = Field(min_length=1)


class CandidatePlan(BaseModel):
    """Structured candidate plan awaiting explicit user confirmation."""

    candidate_id: str = Field(min_length=1)
    workspace_version: int = Field(ge=0)
    candidate_version: int = Field(ge=1)
    input_snapshot_id: str = Field(min_length=1)
    tasks: list[CandidateTask] = Field(default_factory=list)


class WrittenTask(BaseModel):
    """Formal task persisted by business service after user confirmation."""

    task_id: str
    matter_id: str
    title: str
    obligation: ObligationType
    official_deadline: datetime | None = None
    suggested_date: date | None = None
    depends_on: list[str] = Field(default_factory=list)
    evidence_required: str


class RunContext(BaseModel):
    """Scoped context passed from business service to start an Agent run."""

    user_id: str = Field(min_length=1)
    matter_id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    workspace_version: int = Field(ge=0)
    source_urls: list[str] = Field(default_factory=list)
    confirmed_facts: dict[str, Any] = Field(default_factory=dict)
    model_transfer_consent_id: str | None = None


class ExecutionRecord(BaseModel):
    """Audit record produced by ToolGateway for every tool invocation."""

    operation_id: str | None = None
    tool_name: str
    auth_level: AuthLevel
    input_version: int
    succeeded: bool
    error: AgentError | None = None
    output_summary: dict[str, Any] = Field(default_factory=dict)


class RunCheckpoint(BaseModel):
    """State persisted when a run pauses for user input or confirmation."""

    run_id: str
    user_id: str
    matter_id: str
    workspace_version: int
    status: RunStatus
    sources: list[SourceDocument] = Field(default_factory=list)
    evaluations: list[RequirementEvaluation] = Field(default_factory=list)
    candidate_plan: CandidatePlan | None = None
    written_tasks: list[WrittenTask] = Field(default_factory=list)
    error: AgentError | None = None
    execution_records: list[ExecutionRecord] = Field(default_factory=list)


class AgentRunResult(BaseModel):
    """Return payload for orchestrator lifecycle methods."""

    run_id: str
    status: RunStatus
    evaluations: list[RequirementEvaluation] = Field(default_factory=list)
    candidate_plan: CandidatePlan | None = None
    written_tasks: list[WrittenTask] = Field(default_factory=list)
    error: AgentError | None = None
    execution_records: list[ExecutionRecord] = Field(default_factory=list)
