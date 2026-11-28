"""Request contracts for the business API."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

from backend.config import MAX_DURATION_SECONDS

CONTENT_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
NUMBER_PATTERN = re.compile(r"^-?\d+(?:\.\d+)?$")
FIELD_KEY_PATTERN = r"^[a-z][a-z0-9_.]{1,63}$"


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AuthRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(AuthRequestModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if len(normalized) > 160:
                raise ValueError("email exceeds 160 characters")
            return normalized
        return value

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("display_name must not be blank")
        return normalized


class LoginRequest(AuthRequestModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    remember: bool = False

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if len(normalized) > 160:
                raise ValueError("email exceeds 160 characters")
            return normalized
        return value


class PasswordChangeRequest(AuthRequestModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def check_password_changed(self) -> PasswordChangeRequest:
        if self.current_password == self.new_password:
            raise ValueError("new_password must differ from current_password")
        return self


class ProfileUpdateRequest(AuthRequestModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=60)
    email: EmailStr | None = None
    current_password: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if len(normalized) > 160:
                raise ValueError("email exceeds 160 characters")
            return normalized
        return value

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("display_name must not be blank")
        return normalized

    @model_validator(mode="after")
    def check_profile_fields(self) -> ProfileUpdateRequest:
        if self.display_name is None and self.email is None:
            raise ValueError("display_name or email is required")
        return self


class AdminUserStatusUpdate(AuthRequestModel):
    status: Literal["active", "disabled"]


class AdminUserRoleUpdate(AuthRequestModel):
    account_type: Literal["applicant", "admin"]


class AdminPasswordReset(AuthRequestModel):
    new_password: str = Field(min_length=8, max_length=128)


class AdminModelSettingsUpdate(AuthRequestModel):
    provider: str | None = None
    name: str | None = None
    api_url: str | None = None
    api_key: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)


class AdminAuthSettingsUpdate(AuthRequestModel):
    session_ttl_seconds: int | None = Field(default=None, gt=0, le=MAX_DURATION_SECONDS)
    remember_session_ttl_seconds: int | None = Field(
        default=None, gt=0, le=MAX_DURATION_SECONDS
    )
    cookie_secure: bool | None = None
    login_ip_window_seconds: int | None = Field(
        default=None, gt=0, le=MAX_DURATION_SECONDS
    )
    login_ip_limit: int | None = Field(default=None, ge=0)
    login_email_window_seconds: int | None = Field(
        default=None, gt=0, le=MAX_DURATION_SECONDS
    )
    login_email_limit: int | None = Field(default=None, ge=0)
    login_lock_seconds: int | None = Field(default=None, gt=0, le=MAX_DURATION_SECONDS)


class AdminSettingsUpdate(AuthRequestModel):
    timezone: str | None = None
    model: AdminModelSettingsUpdate | None = None
    auth: AdminAuthSettingsUpdate | None = None


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


class CandidatePlanCreate(RequestModel):
    items: list[CandidatePlanItemInput] = Field(min_length=1)
    referenced_fact_types: list[str] = Field(default_factory=list)

    @field_validator("referenced_fact_types")
    @classmethod
    def check_referenced_fact_types(cls, values: list[str]) -> list[str]:
        pattern = re.compile(FIELD_KEY_PATTERN)
        invalid = [value for value in values if not pattern.fullmatch(value)]
        if invalid:
            raise ValueError(
                f"referenced_fact_types contains invalid keys: {', '.join(invalid)}"
            )
        return sorted(set(values))

    @model_validator(mode="after")
    def check_dependencies(self) -> CandidatePlanCreate:
        keys = [item.client_item_id for item in self.items]
        if len(set(keys)) != len(keys):
            raise ValueError("client_item_id must be unique within a plan")
        known = set(keys)
        for item in self.items:
            source_keys = [
                (item_source.snapshot_id, item_source.locator)
                for item_source in item.sources
            ]
            if len(set(source_keys)) != len(source_keys):
                raise ValueError(
                    "sources must be unique by snapshot_id and locator within an item"
                )
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
