"""Abstract integration ports (Protocols) for source reading, model calls, and backend writes."""

from __future__ import annotations

from typing import Any, Protocol

from backend.agent.schemas import (
    AuthLevel,
    CandidatePlan,
    ExecutionRecord,
    ExtractedRequirement,
    RequirementEvaluation,
    RunContext,
    SourceDocument,
    WrittenTask,
)


class SourceReaderPort(Protocol):
    """Port for public official source reading (owned by 蔡信坡)."""

    def fetch_sources(
        self,
        urls: list[str],
        goal: str,
        *,
        scope_year: int | None = None,
    ) -> list[SourceDocument]:
        """Fetch official source documents with publisher, version, and attachment metadata."""
        ...


class ModelAdapterPort(Protocol):
    """Port for structured LLM extraction and candidate planning (owned by 庄凯堃)."""

    def extract_requirements(
        self,
        goal: str,
        sources: list[SourceDocument],
    ) -> list[ExtractedRequirement]:
        """Extract structured requirements with source citations from official documents."""
        ...

    def generate_candidate_plan(
        self,
        context: RunContext,
        sources: list[SourceDocument],
        evaluations: list[RequirementEvaluation],
    ) -> CandidatePlan:
        """Generate a structured candidate plan without persisting any formal tasks."""
        ...


class CandidatePersistencePort(Protocol):
    """Port for persisting, reading, and deciding candidate plans (PR #41)."""

    def persist_requirements(
        self, matter_id: str, payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Persist extracted requirements + evidence and return created records."""
        ...

    def persist_candidate_plan(
        self, matter_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Persist pending candidate plan + items + item sources and return plan detail."""
        ...

    def get_candidate_plan(self, plan_id: str) -> dict[str, Any]:
        """Fetch a persisted candidate plan detail by plan_id."""
        ...

    def confirm_candidate_plan(
        self, plan_id: str, *, operation_id: str
    ) -> dict[str, Any]:
        """Confirm a persisted candidate plan idempotently on the backend."""
        ...

    def reject_candidate_plan(
        self, plan_id: str, *, operation_id: str
    ) -> dict[str, Any]:
        """Reject a persisted candidate plan idempotently on the backend."""
        ...

    def reject_requirements(self, matter_id: str, requirement_ids: list[str]) -> None:
        """Invalidate requirements whose candidate plan was not persisted."""
        ...


class WorkspaceBackendPort(Protocol):
    """Port for business service ownership, version, consent, and write checks (owned by 李义东)."""

    def check_permission(
        self, user_id: str, matter_id: str, auth_level: AuthLevel
    ) -> bool:
        """Verify user ownership of the matter and authorization for the requested tier."""
        ...

    def has_valid_transfer_consent(
        self,
        user_id: str,
        *,
        purpose: str,
        field_categories: tuple[str, ...],
    ) -> bool:
        """Verify an active global consent covering the requested purpose and fields."""
        ...

    def get_workspace_version(self, matter_id: str) -> int:
        """Return the current workspace version for optimistic concurrency checks."""
        ...

    def consume_candidate_and_write_tasks(
        self,
        user_id: str,
        matter_id: str,
        candidate_plan: CandidatePlan,
        expected_workspace_version: int,
        operation_id: str,
    ) -> list[WrittenTask]:
        """Atomically verify version, consume candidate, and persist formal tasks idempotently."""
        ...

    def record_execution(self, matter_id: str, record: ExecutionRecord) -> None:
        """Persist gateway execution record for traceability."""
        ...
