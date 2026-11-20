"""In-process adapters binding Agent ports to Alpha backend services."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.agent.contracts import PersistenceApiError
from backend.agent.ports import WorkspaceBackendPort
from backend.agent.schemas import (
    AuthLevel,
    CandidatePlan,
    ExecutionRecord,
    SourceDocument,
    WrittenTask,
)
from backend.agent.source_bridge import SourceReadUnavailableError
from backend.clock import Clock
from backend.config import Settings
from backend.db import workspace_transaction
from backend.errors import ApiError
from backend.schemas import (
    CandidatePlanCreate,
    RequirementBatchCreate,
    SourceReadRequest,
)
from backend.services import decisions as decision_service
from backend.services import plans as plan_service
from backend.services import requirements as requirement_service
from backend.services import sources as source_service
from backend.services.sources import SourceReader, read_public_html
from backend.sources import source_document_from_registration
from backend.tables import matter, workspace

logger = logging.getLogger(__name__)


class BackendSourceReader:
    """Read public HTML sources and register them for one matter."""

    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        clock: Clock,
        *,
        matter_id: UUID,
        publisher: str,
        scope: str | None,
        scope_year: int,
        reader: SourceReader = read_public_html,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._clock = clock
        self._matter_id = matter_id
        self._publisher = publisher
        self._scope = scope
        self._scope_year = scope_year
        self._reader = reader

    def fetch_sources(
        self,
        urls: list[str],
        goal: str,
        *,
        scope_year: int | None = None,
    ) -> list[SourceDocument]:
        """Fetch and register each public source, returning citation-ready documents."""
        documents: list[SourceDocument] = []
        for url in urls:
            request = SourceReadRequest(
                url=url,
                publisher=self._publisher,
                scope=self._scope,
                scope_year=scope_year or self._scope_year,
            )
            with self._session_factory() as session:
                try:
                    registration = source_service.read_and_register_source(
                        session,
                        self._settings,
                        self._matter_id,
                        request,
                        now=self._clock.now(),
                        reader=self._reader,
                    )
                except ApiError as exc:
                    code = str(exc.details.get("code") or exc.code)
                    raise SourceReadUnavailableError(code, exc.message) from exc
            documents.append(
                SourceDocument.model_validate(
                    source_document_from_registration(registration)
                )
            )
        return documents


class SqlCandidatePersistence:
    """Persist and decide candidate artifacts through the Alpha services."""

    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        clock: Clock,
        *,
        expected_fact_versions: Mapping[str, int | None] | None = None,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._clock = clock
        self._expected_fact_versions = expected_fact_versions

    def persist_requirements(
        self, matter_id: str, payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        try:
            body = RequirementBatchCreate.model_validate(payload)
        except ValueError as exc:
            raise PersistenceApiError(
                422, f"候选要求不符合接口契约: {exc}", error_code="validation_error"
            ) from exc
        try:
            with self._session_factory() as session:
                result = requirement_service.create_requirements(
                    session,
                    self._settings,
                    UUID(matter_id),
                    body,
                    now=self._clock.now(),
                )
        except ApiError as exc:
            raise _to_persistence_error(exc) from exc
        return list(result["requirements"])

    def persist_candidate_plan(
        self, matter_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            body = CandidatePlanCreate.model_validate(payload)
        except ValueError as exc:
            raise PersistenceApiError(
                422, f"候选计划不符合接口契约: {exc}", error_code="validation_error"
            ) from exc
        try:
            with self._session_factory() as session:
                result = plan_service.create_plan(
                    session,
                    self._settings,
                    UUID(matter_id),
                    body,
                    now=self._clock.now(),
                    expected_fact_versions=self._expected_fact_versions,
                )
        except ApiError as exc:
            raise _to_persistence_error(exc) from exc
        return result

    def get_candidate_plan(self, plan_id: str) -> dict[str, Any]:
        try:
            with self._session_factory() as session:
                return plan_service.get_plan(session, self._settings, UUID(plan_id))
        except ApiError as exc:
            raise _to_persistence_error(exc) from exc

    def confirm_candidate_plan(
        self, plan_id: str, *, operation_id: str
    ) -> dict[str, Any]:
        return self._decide(plan_id, decision="confirmed", operation_id=operation_id)

    def reject_candidate_plan(
        self, plan_id: str, *, operation_id: str
    ) -> dict[str, Any]:
        return self._decide(plan_id, decision="rejected", operation_id=operation_id)

    def _decide(
        self,
        plan_id: str,
        *,
        decision: Literal["confirmed", "rejected"],
        operation_id: str,
    ) -> dict[str, Any]:
        try:
            with self._session_factory() as session:
                result = decision_service.decide_plan(
                    session,
                    self._settings,
                    UUID(plan_id),
                    decision=decision,
                    operation_id=UUID(operation_id),
                    now=self._clock.now(),
                )
        except ApiError as exc:
            raise _to_persistence_error(exc) from exc
        if result.expired:
            raise PersistenceApiError(
                409,
                "候选计划依据已变化，候选已过期",
                error_code="basis_changed",
            )
        return {
            "plan_id": str(result.plan_id),
            "status": result.status,
            "decision": result.decision,
            "tasks": result.tasks,
            "replayed": result.replayed,
        }


class SqlWorkspaceBackend(WorkspaceBackendPort):
    """Provide matter ownership, workspace version, and audit hooks for Alpha."""

    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory

    def check_permission(
        self, user_id: str, matter_id: str, auth_level: AuthLevel
    ) -> bool:
        if user_id != str(self._settings.demo_user_id):
            return False
        try:
            matter_uuid = UUID(matter_id)
        except ValueError:
            return False
        with (
            self._session_factory() as session,
            workspace_transaction(session, self._settings.demo_workspace_id),
        ):
            row = session.execute(
                select(matter.c.id)
                .join(workspace, workspace.c.id == matter.c.workspace_id)
                .where(
                    matter.c.id == matter_uuid,
                    matter.c.workspace_id == self._settings.demo_workspace_id,
                    workspace.c.owner_id == self._settings.demo_user_id,
                )
            ).first()
        return row is not None

    def has_valid_transfer_consent(
        self, user_id: str, matter_id: str, consent_id: str | None
    ) -> bool:
        """Alpha 只向模型传输公开来源正文与事项适用范围，演示身份即本次传输范围。"""
        return self.check_permission(user_id, matter_id, AuthLevel.L1)

    def get_workspace_version(self, matter_id: str) -> int:
        try:
            matter_uuid = UUID(matter_id)
        except ValueError:
            return 0
        with (
            self._session_factory() as session,
            workspace_transaction(session, self._settings.demo_workspace_id),
        ):
            updated_at = session.execute(
                select(matter.c.updated_at).where(
                    matter.c.id == matter_uuid,
                    matter.c.workspace_id == self._settings.demo_workspace_id,
                )
            ).scalar_one_or_none()
        if updated_at is None:
            return 0
        return int(updated_at.timestamp() * 1_000_000)

    def consume_candidate_and_write_tasks(
        self,
        user_id: str,
        matter_id: str,
        candidate_plan: CandidatePlan,
        expected_workspace_version: int,
        operation_id: str,
    ) -> list[WrittenTask]:
        raise RuntimeError("Alpha 通过候选持久化端口完成确认写入")

    def record_execution(self, matter_id: str, record: ExecutionRecord) -> None:
        logger.info(
            "agent tool execution matter=%s tool=%s succeeded=%s",
            matter_id,
            record.tool_name,
            record.succeeded,
            extra={"agent_execution_record": record.model_dump(mode="json")},
        )


def _to_persistence_error(exc: ApiError) -> PersistenceApiError:
    return PersistenceApiError(
        exc.status_code,
        exc.message,
        error_code=exc.code,
        retryable=exc.status_code >= 500,
    )
