"""Agent run lifecycle owned by the backend business service."""

from __future__ import annotations

import threading
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from backend.agent import (
    AgentErrorCode,
    AgentOrchestrator,
    AgentRunResult,
    ModelInvocationError,
    RunContext,
)
from backend.agent.backend_bridge import (
    BackendSourceReader,
    SqlCandidatePersistence,
    SqlWorkspaceBackend,
)
from backend.agent.ports import ModelAdapterPort
from backend.agent.schemas import (
    CandidatePlan,
    ExtractedRequirement,
    RequirementEvaluation,
    RunCheckpoint,
    SourceDocument,
)
from backend.clock import Clock
from backend.config import Settings
from backend.errors import ApiError
from backend.schemas import AgentRunCreate
from backend.services.common import require_matter, transaction
from backend.services.sources import SourceReader, read_public_html


class _UnavailableModelAdapter:
    """Fail runs explicitly when the model adapter is not available."""

    def extract_requirements(
        self, goal: str, sources: list[SourceDocument]
    ) -> list[ExtractedRequirement]:
        raise ModelInvocationError(AgentErrorCode.MODEL_ERROR, "模型适配器不可用")

    def generate_candidate_plan(
        self,
        context: RunContext,
        sources: list[SourceDocument],
        evaluations: list[RequirementEvaluation],
    ) -> CandidatePlan:
        raise ModelInvocationError(AgentErrorCode.MODEL_ERROR, "模型适配器不可用")


class AgentRunService:
    """Create, read, decide, and cancel Agent runs in the backend process."""

    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        clock: Clock,
        model_adapter: ModelAdapterPort | None,
        *,
        source_reader: SourceReader = read_public_html,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._clock = clock
        self._model_adapter = model_adapter or _UnavailableModelAdapter()
        self._source_reader = source_reader
        self._runs: dict[str, AgentOrchestrator] = {}
        self._operations: dict[tuple[str, str, str], AgentRunResult] = {}
        self._lock = threading.Lock()

    def start(self, matter_id: UUID, body: AgentRunCreate) -> AgentRunResult:
        operation_key = (
            (
                str(self._settings.demo_user_id),
                str(matter_id),
                body.operation_id,
            )
            if body.operation_id is not None
            else None
        )
        if operation_key is not None:
            with self._lock:
                cached = self._operations.get(operation_key)
            if cached is not None:
                return cached

        with self._session_factory() as session, transaction(session, self._settings):
            matter_row = require_matter(session, self._settings, matter_id)
        scope_year = (
            body.scope_year if body.scope_year is not None else matter_row["scope_year"]
        )
        if scope_year != matter_row["scope_year"]:
            raise ApiError(
                422,
                "scope_year_mismatch",
                "运行的适用年度与事项年度不一致",
                next_step="核对运行与事项的适用年度",
            )

        backend = SqlWorkspaceBackend(self._settings, self._session_factory)
        source_reader = BackendSourceReader(
            self._settings,
            self._session_factory,
            self._clock,
            matter_id=matter_id,
            publisher=body.publisher,
            scope=body.scope,
            scope_year=scope_year,
            reader=self._source_reader,
        )
        orchestrator = AgentOrchestrator(
            source_reader=source_reader,
            model_adapter=self._model_adapter,
            backend=backend,
            persistence=SqlCandidatePersistence(
                self._settings, self._session_factory, self._clock
            ),
            clock=self._clock.now,
        )
        context = RunContext(
            user_id=str(self._settings.demo_user_id),
            matter_id=str(matter_id),
            goal=body.goal or str(matter_row["goal"]),
            workspace_version=backend.get_workspace_version(str(matter_id)),
            source_urls=[str(url) for url in body.source_urls],
            confirmed_facts=body.confirmed_facts,
            model_transfer_consent_id=body.model_transfer_consent_id,
            scope_year=scope_year,
            scope_attrs=dict(matter_row["scope_attrs"] or {}),
            operation_id=body.operation_id,
        )
        result = orchestrator.start_run(context)
        with self._lock:
            self._runs[result.run_id] = orchestrator
            if operation_key is not None:
                self._operations[operation_key] = result
        return result

    def get(self, run_id: str) -> AgentRunResult:
        checkpoint = self._require(run_id).get_checkpoint(
            run_id, caller_user_id=str(self._settings.demo_user_id)
        )
        if checkpoint is None:
            raise _run_not_found()
        return _result_from_checkpoint(checkpoint)

    def confirm(
        self,
        run_id: str,
        *,
        candidate_version: int,
        operation_id: str,
        plan_id: str | None = None,
    ) -> AgentRunResult:
        return self._require(run_id).confirm_plan(
            run_id,
            candidate_version=candidate_version,
            operation_id=operation_id,
            plan_id=plan_id,
            user_id=str(self._settings.demo_user_id),
        )

    def reject(
        self,
        run_id: str,
        *,
        operation_id: str,
    ) -> AgentRunResult:
        return self._require(run_id).reject_plan(
            run_id,
            operation_id=operation_id,
            user_id=str(self._settings.demo_user_id),
        )

    def cancel(self, run_id: str) -> AgentRunResult:
        return self._require(run_id).cancel_run(
            run_id, user_id=str(self._settings.demo_user_id)
        )

    def _require(self, run_id: str) -> AgentOrchestrator:
        with self._lock:
            orchestrator = self._runs.get(run_id)
        if orchestrator is None:
            raise _run_not_found()
        return orchestrator


def _result_from_checkpoint(checkpoint: RunCheckpoint) -> AgentRunResult:
    return AgentRunResult(
        run_id=checkpoint.run_id,
        status=checkpoint.status,
        extracted_requirements=checkpoint.extracted_requirements,
        evaluations=checkpoint.evaluations,
        gaps=checkpoint.gaps,
        scope_summary=checkpoint.scope_summary,
        candidate_plan=checkpoint.candidate_plan,
        persisted_requirement_ids=checkpoint.persisted_requirement_ids,
        persisted_plan_id=checkpoint.persisted_plan_id,
        written_tasks=checkpoint.written_tasks,
        error=checkpoint.error,
        execution_records=checkpoint.execution_records,
    )


def _run_not_found() -> ApiError:
    return ApiError(
        404,
        "agent_run_not_found",
        "未找到当前进程中的 Agent 运行",
        next_step="重新发起运行，或通过候选计划接口继续处理已持久化候选",
    )
