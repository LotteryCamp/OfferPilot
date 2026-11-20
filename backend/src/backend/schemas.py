"""Request contracts for the Alpha business API."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
CONTENT_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
NUMBER_PATTERN = re.compile(r"^-?\d+(?:\.\d+)?$")
FIELD_KEY_PATTERN = r"^[a-z][a-z0-9_.]{1,63}$"


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MatterCreate(RequestModel):
    goal: str = Field(min_length=1, max_length=200)
    type_code: str = Field(default="pre_recommend", min_length=2, max_length=32)
    scope_year: int = Field(ge=2020, le=2100)
    scope_attrs: dict[str, Any] = Field(default_factory=dict)


class AgentRunCreate(RequestModel):
    source_urls: list[HttpUrl] = Field(min_length=1, max_length=10)
    goal: str | None = Field(default=None, min_length=1, max_length=200)
    publisher: str = Field(default="官方公开来源", min_length=1, max_length=160)
    scope: str | None = Field(default=None, max_length=200)
    scope_year: int | None = Field(default=None, ge=2020, le=2100)
    confirmed_facts: dict[str, Any] = Field(default_factory=dict)
    operation_id: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("source_urls")
    @classmethod
    def check_source_urls(cls, value: list[HttpUrl]) -> list[HttpUrl]:
        return [_check_public_url(url) for url in value]


class AgentRunConfirm(RequestModel):
    candidate_version: int = Field(ge=1)
    plan_id: UUID | None = None


class FactSaveRequest(RequestModel):
    value: dict[str, Any]
    scope: str | None = Field(default=None, max_length=200)
    valid_from: date | None = None


class SourceFragmentInput(RequestModel):
    locator_kind: Literal["section", "page", "text_span", "table_row", "list_item"]
    locator: str = Field(min_length=1, max_length=300)
    quote: str | None = None


class SourceCreate(RequestModel):
    source_id: UUID | None = None
    snapshot_id: UUID | None = None
    version_no: int | None = Field(default=None, gt=0)
    url: HttpUrl
    publisher: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=500)
    scope: str | None = Field(default=None, max_length=200)
    scope_year: int = Field(ge=2020, le=2100)
    published_date: date | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    content: str = Field(min_length=1)
    content_hash: str | None = None
    fetched_at: AwareDatetime | None = None
    status: Literal["active", "withdrawn", "invalid"] = "active"
    auto_check_status: Literal["pending", "passed", "failed", "conflict"] = "pending"
    roi_status: Literal["original", "reposted", "expired", "ambiguous"] = "original"
    fragments: list[SourceFragmentInput] = Field(default_factory=list)

    @field_validator("url")
    @classmethod
    def check_url(cls, value: HttpUrl) -> HttpUrl:
        return _check_public_url(value)

    @field_validator("content_hash")
    @classmethod
    def check_content_hash(cls, value: str | None) -> str | None:
        if value is not None and not CONTENT_HASH_PATTERN.fullmatch(value):
            raise ValueError("content_hash must be 64 lowercase hex characters")
        return value

    @model_validator(mode="after")
    def check_valid_range(self) -> SourceCreate:
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError("valid_to must not be earlier than valid_from")
        return self


class SourceReadRequest(RequestModel):
    url: HttpUrl
    publisher: str = Field(min_length=1, max_length=160)
    scope: str | None = Field(default=None, max_length=200)
    scope_year: int = Field(ge=2020, le=2100)
    title: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("url")
    @classmethod
    def check_url(cls, value: HttpUrl) -> HttpUrl:
        return _check_public_url(value)


def _check_public_url(value: HttpUrl) -> HttpUrl:
    if value.username is not None or value.password is not None:
        raise ValueError("URL credentials are not allowed")
    if len(str(value)) > 500:
        raise ValueError("URL exceeds 500 characters")
    return value


class EvidenceInput(RequestModel):
    source_id: UUID
    snapshot_id: UUID
    locator_kind: Literal["section", "page", "text_span", "table_row"]
    locator: str = Field(min_length=1, max_length=300)
    quote: str | None = None


class SelfCheckGapInput(RequestModel):
    gap_type: Literal[
        "missing_attachment",
        "missing_basis",
        "missing_personal_fact",
        "repost_only",
        "expired_source",
        "scope_unclear",
        "ambiguous_clause",
        "read_failed",
    ]
    description: str = Field(min_length=1)
    locator: str | None = Field(default=None, max_length=300)
    source_id: UUID | None = None
    snapshot_id: UUID | None = None


class RequirementSelfCheckInput(RequestModel):
    conclusion: Literal["matched", "not_matched", "missing_info", "needs_user_review"]
    reason: str = Field(min_length=1)
    missing_fields: list[str] = Field(default_factory=list)
    computed_deadline_at: AwareDatetime | None = None
    gaps: list[SelfCheckGapInput] = Field(default_factory=list)


class RequirementInput(RequestModel):
    field_key: str = Field(pattern=FIELD_KEY_PATTERN)
    label: str = Field(min_length=1, max_length=120)
    obligation_nature: Literal["required", "advised", "optional", "to_verify"] = (
        "to_verify"
    )
    extract_status: Literal["extracted", "checked", "to_review", "rejected"] = (
        "extracted"
    )
    scope: str | None = Field(default=None, max_length=200)
    value_text: str | None = None
    value_type: Literal["text", "date", "number", "boolean", "enum"] = "text"
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    snapshot_id: UUID
    evidence: list[EvidenceInput] = Field(min_length=1)
    self_check: RequirementSelfCheckInput | None = None

    @model_validator(mode="after")
    def check_value(self) -> RequirementInput:
        if self.value_text is None:
            return self
        if self.value_type == "date":
            if len(self.value_text) != 10:
                raise ValueError("date value_text must be YYYY-MM-DD")
            date.fromisoformat(self.value_text)
        elif self.value_type == "number":
            if not NUMBER_PATTERN.fullmatch(self.value_text):
                raise ValueError(
                    "number value_text must be a decimal without separators"
                )
        elif self.value_type == "boolean" and self.value_text not in {
            "true",
            "false",
        }:
            raise ValueError("boolean value_text must be true or false")
        return self


class RequirementBatchCreate(RequestModel):
    requirements: list[RequirementInput] = Field(min_length=1)


class PlanItemSourceInput(RequestModel):
    source_id: UUID
    snapshot_id: UUID
    locator_kind: Literal["section", "page", "text_span", "table_row"]
    locator: str = Field(min_length=1, max_length=300)
    quote: str | None = None


class CandidatePlanItemInput(RequestModel):
    client_item_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    detail: str | None = None
    obligation_nature: Literal["required", "advised", "optional", "to_verify"] = (
        "to_verify"
    )
    official_deadline_date: date | None = None
    official_deadline_at: AwareDatetime | None = None
    suggested_date: date | None = None
    depends_on: list[str] = Field(default_factory=list)
    evidence_required: bool = False
    requirement_id: UUID | None = None
    sources: list[PlanItemSourceInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_deadline(self) -> CandidatePlanItemInput:
        if self.official_deadline_at is None:
            return self
        local_date = self.official_deadline_at.astimezone(SHANGHAI).date()
        if self.official_deadline_date is None:
            self.official_deadline_date = local_date
        elif self.official_deadline_date != local_date:
            raise ValueError(
                "official_deadline_date must match official_deadline_at "
                "in Asia/Shanghai"
            )
        return self


class CandidatePlanCreate(RequestModel):
    items: list[CandidatePlanItemInput] = Field(min_length=1)

    @model_validator(mode="after")
    def check_dependencies(self) -> CandidatePlanCreate:
        keys = [item.client_item_id for item in self.items]
        if len(set(keys)) != len(keys):
            raise ValueError("client_item_id must be unique within a plan")
        known = set(keys)
        for item in self.items:
            if len(set(item.depends_on)) != len(item.depends_on):
                raise ValueError("depends_on must not contain duplicates")
            if item.client_item_id in item.depends_on:
                raise ValueError("a candidate item cannot depend on itself")
            missing = [key for key in item.depends_on if key not in known]
            if missing:
                raise ValueError(f"unknown dependency keys: {', '.join(missing)}")
        _assert_acyclic(self.items)
        return self


def _assert_acyclic(items: list[CandidatePlanItemInput]) -> None:
    graph = {item.client_item_id: list(item.depends_on) for item in items}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            raise ValueError("candidate item dependencies contain a cycle")
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)
