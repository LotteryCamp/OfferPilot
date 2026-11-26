"""Agent run lifecycle owned by the backend business service."""

from __future__ import annotations

import threading
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import insert, select, text, update
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
    AgentError,
    CandidatePlan,
    ExtractedRequirement,
    RequirementEvaluation,
    RunCheckpoint,
    RunStatus,
    SourceDocument,
)
from backend.clock import Clock
from backend.errors import ApiError
from backend.fact_types import supported_fact_types
from backend.identity import CurrentUser
from backend.runtime_config import RuntimeConfig
from backend.schemas import AgentRunCreate
from backend.services import facts as fact_service
from backend.services.common import require_matter, transaction
from backend.services.sources import SourceReader, read_public_html
from backend.tables import agent_run
from backend.transfer import REQUIRED_TRANSFER_SCOPES

_RUN_STATUS_KEYS: dict[RunStatus, str] = {
    RunStatus.RUNNING: "running",
    RunStatus.WAITING_USER: "waiting_user",
    RunStatus.WAITING_CONFIRMATION: "waiting_confirmation",
    RunStatus.COMPLETED: "completed",
    RunStatus.FAILED: "failed",
    RunStatus.CANCELLED: "cancelled",
    RunStatus.INTERRUPTED: "interrupted",
}
_RUN_STATUS_BY_KEY = {value: key for key, value in _RUN_STATUS_KEYS.items()}
_REPLAYABLE_STATUSES = ("waiting_user", "waiting_confirmation", "completed")
_PERSISTED_DETAIL_FIELDS = (
    "extracted_requirements",
    "evaluations",
    "gaps",
    "scope_summary",
    "candidate_plan",
    "persisted_requirement_ids",
    "persisted_plan_id",
)


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


class _UnavailableSourceReader:
    """Recovery-only source reader; decisions never fetch new sources."""

    def fetch_sources(
        self,
        urls: list[str],
        goal: str,
        *,
        scope_year: int | None = None,
    ) -> list[SourceDocument]:
        raise RuntimeError("恢复运行不重新读取来源")


class AgentRunService:
    """Create, read, decide, and cancel Agent runs with persisted checkpoints."""

    def __init__(
        self,
        config: RuntimeConfig,
        session_factory: sessionmaker[Session],
        clock: Clock,
        model_adapter: ModelAdapterPort | None,
        *,
        source_reader: SourceReader = read_public_html,
    ) -> None:
        self._config = config
        self._session_factory = session_factory
        self._clock = clock
        self._model_adapter = model_adapter or _UnavailableModelAdapter()
        self._source_reader = source_reader
        self._runs: dict[str, AgentOrchestrator] = {}
        self._operations: dict[tuple[str, str, str], AgentRunResult] = {}
        self._lock = threading.Lock()

    def mark_interrupted_runs(self) -> None:
        """Mark runs left executing by a previous process as interrupted."""
        with self._session_factory() as session, session.begin():
            session.execute(text("SELECT core.mark_interrupted_agent_runs()"))

    def start(
        self,
        matter_id: UUID,
        body: AgentRunCreate,
        current_user: CurrentUser,
    ) -> AgentRunResult:
        operation_key = (
            (
                str(current_user.user_id),
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

        with (
            self._session_factory() as session,
            transaction(session, current_user),
        ):
            matter_row = require_matter(session, current_user, matter_id)
            replay_row = (
                session.execute(
                    select(agent_run)
                    .where(
                        agent_run.c.matter_id == matter_id,
                        agent_run.c.operation_id == body.operation_id,
                        agent_run.c.status.in_(_REPLAYABLE_STATUSES),
                    )
                    .order_by(agent_run.c.created_at.desc())
                    .limit(1)
                )
                .mappings()
                .first()
                if body.operation_id is not None
                else None
            )
        if replay_row is not None:
            result = self._result_from_row(replay_row)
            if operation_key is not None:
                with self._lock:
                    self._operations[operation_key] = result
            return result

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

        managed_fact_types = sorted(
            set(body.confirmed_facts) & set(supported_fact_types())
        )
        if managed_fact_types:
            raise ApiError(
                422,
                "managed_fact_type",
                "已登记事实类型由当前事项的事实档案提供",
                next_step="在事项事实接口保存该类型的值后重新发起运行",
                details={"fact_types": managed_fact_types},
            )

        expected_fact_versions, agent_facts = self._load_fact_context(
            matter_id, current_user
        )
        requires_transfer_consent = bool(
            body.confirmed_facts or agent_facts or matter_row["scope_attrs"]
        )
        backend = SqlWorkspaceBackend(current_user, self._session_factory)
        if requires_transfer_consent and any(
            not backend.has_valid_transfer_consent(
                str(current_user.user_id),
                purpose=purpose,
                field_categories=field_categories,
            )
            for purpose, field_categories in REQUIRED_TRANSFER_SCOPES
        ):
            raise ApiError(
                422,
                "model_transfer_consent_required",
                "携带个人事实或事项适用范围时必须先同意向外部模型传输公开资料",
                next_step="在个人信息授权同意选项中授予后重试",
            )

        confirmed_facts = dict(body.confirmed_facts)
        confirmed_facts.update(agent_facts)

        run_id = f"run-{uuid4().hex[:12]}"
        self._create_run(
            run_id=run_id,
            matter_id=matter_id,
            operation_id=body.operation_id,
            current_user=current_user,
        )

        source_reader = BackendSourceReader(
            current_user,
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
                current_user,
                self._config.current(),
                self._session_factory,
                self._clock,
                expected_fact_versions=expected_fact_versions,
            ),
            clock=self._clock.now,
        )
        context = RunContext(
            user_id=str(current_user.user_id),
            matter_id=str(matter_id),
            goal=body.goal or str(matter_row["goal"]),
            workspace_version=backend.get_workspace_version(str(matter_id)),
            source_urls=[str(url) for url in body.source_urls],
            confirmed_facts=confirmed_facts,
            model_transfer_facts=body.confirmed_facts,
            scope_year=scope_year,
            scope_attrs=dict(matter_row["scope_attrs"] or {}),
            operation_id=body.operation_id,
        )
        try:
            result = orchestrator.start_run(context, run_id=run_id)
        except Exception:
            self._mark_interrupted(run_id, current_user)
            raise
        saved = self._save_result(
            run_id=run_id,
            result=result,
            matter_id=str(matter_id),
            user_id=str(current_user.user_id),
            workspace_version=context.workspace_version,
            current_user=current_user,
        )
        with self._lock:
            self._runs[run_id] = orchestrator
            if operation_key is not None:
                self._operations[operation_key] = saved
        return saved

    def get(self, run_id: str, current_user: CurrentUser) -> AgentRunResult:
        row = self._load_run(run_id, current_user)
        if row is None:
            raise _run_not_found()
        return self._result_from_row(row)

    def confirm(
        self,
        run_id: str,
        current_user: CurrentUser,
        *,
        candidate_version: int,
        operation_id: str,
        plan_id: str | None = None,
    ) -> AgentRunResult:
        row = self._require_run(run_id, current_user)
        checkpoint = self._checkpoint_from_row(row)
        target_plan_id = plan_id or (
            checkpoint.persisted_plan_id if checkpoint is not None else None
        )

        if checkpoint is not None:
            if checkpoint.status == RunStatus.COMPLETED:
                return self._result_from_checkpoint(checkpoint)
            if checkpoint.status != RunStatus.WAITING_CONFIRMATION:
                err = AgentError(
                    code=AgentErrorCode.VALIDATION_FAILED,
                    message=(
                        f"当前运行状态为 {checkpoint.status.value}，无法执行确认写入"
                    ),
                )
                return self._result_from_checkpoint(checkpoint, error=err)
            if (
                checkpoint.candidate_plan is not None
                and checkpoint.candidate_plan.candidate_version != candidate_version
            ):
                err = AgentError(
                    code=AgentErrorCode.VERSION_CONFLICT,
                    message=(
                        "候选版本已失效："
                        f"期望 {checkpoint.candidate_plan.candidate_version}，"
                        f"收到 {candidate_version}"
                    ),
                )
                return self._result_from_checkpoint(checkpoint, error=err)

        if row["status"] == "interrupted" or target_plan_id is None:
            return self._interrupted_result(row)

        orchestrator = self._runtime_orchestrator(run_id, current_user)
        matter_id = str(row["matter_id"])
        user_id = str(row["user_id"])
        workspace_version = SqlWorkspaceBackend(
            current_user, self._session_factory
        ).get_workspace_version(matter_id)
        result = orchestrator.confirm_plan(
            run_id,
            candidate_version=candidate_version,
            operation_id=operation_id,
            plan_id=target_plan_id,
            user_id=user_id,
            matter_id=matter_id,
            workspace_version=workspace_version,
        )
        return self._save_result(
            run_id=run_id,
            result=result,
            matter_id=matter_id,
            user_id=user_id,
            workspace_version=workspace_version,
            current_user=current_user,
        )

    def reject(
        self,
        run_id: str,
        current_user: CurrentUser,
        *,
        operation_id: str,
    ) -> AgentRunResult:
        row = self._require_run(run_id, current_user)
        checkpoint = self._checkpoint_from_row(row)
        target_plan_id = (
            checkpoint.persisted_plan_id if checkpoint is not None else None
        )

        if checkpoint is not None:
            if checkpoint.status == RunStatus.COMPLETED:
                err = AgentError(
                    code=AgentErrorCode.VALIDATION_FAILED,
                    message="候选计划已确认并生成正式任务，不能拒绝",
                )
                return self._result_from_checkpoint(checkpoint, error=err)
            if checkpoint.status == RunStatus.CANCELLED:
                return self._result_from_checkpoint(checkpoint)
            if checkpoint.status != RunStatus.WAITING_CONFIRMATION:
                err = AgentError(
                    code=AgentErrorCode.VALIDATION_FAILED,
                    message=(
                        f"当前运行状态为 {checkpoint.status.value}，无法执行拒绝操作"
                    ),
                )
                return self._result_from_checkpoint(checkpoint, error=err)

        if row["status"] == "interrupted" or target_plan_id is None:
            return self._interrupted_result(row)

        orchestrator = self._runtime_orchestrator(run_id, current_user)
        matter_id = str(row["matter_id"])
        user_id = str(row["user_id"])
        workspace_version = SqlWorkspaceBackend(
            current_user, self._session_factory
        ).get_workspace_version(matter_id)
        result = orchestrator.reject_plan(
            run_id,
            operation_id=operation_id,
            plan_id=target_plan_id,
            user_id=user_id,
            matter_id=matter_id,
            workspace_version=workspace_version,
        )
        return self._save_result(
            run_id=run_id,
            result=result,
            matter_id=matter_id,
            user_id=user_id,
            workspace_version=workspace_version,
            current_user=current_user,
        )

    def cancel(self, run_id: str, current_user: CurrentUser) -> AgentRunResult:
        row = self._require_run(run_id, current_user)
        checkpoint = self._checkpoint_from_row(row)
        if checkpoint is not None:
            if checkpoint.status in (
                RunStatus.COMPLETED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.INTERRUPTED,
            ):
                return self._result_from_checkpoint(checkpoint)
            checkpoint.status = RunStatus.CANCELLED
            checkpoint.error = AgentError(
                code=AgentErrorCode.CANCELLED, message="运行已被用户取消"
            )
            result = self._result_from_checkpoint(checkpoint)
        elif row["status"] == "interrupted":
            return self._interrupted_result(row)
        else:
            result = AgentRunResult(
                run_id=run_id,
                status=RunStatus.CANCELLED,
                error=AgentError(
                    code=AgentErrorCode.CANCELLED, message="运行已被用户取消"
                ),
            )
        return self._save_result(
            run_id=run_id,
            result=result,
            matter_id=str(row["matter_id"]),
            user_id=str(row["user_id"]),
            workspace_version=(
                checkpoint.workspace_version if checkpoint is not None else 0
            ),
            current_user=current_user,
        )

    def _runtime_orchestrator(
        self, run_id: str, current_user: CurrentUser
    ) -> AgentOrchestrator:
        with self._lock:
            orchestrator = self._runs.get(run_id)
        if orchestrator is not None:
            return orchestrator
        backend = SqlWorkspaceBackend(current_user, self._session_factory)
        return AgentOrchestrator(
            source_reader=_UnavailableSourceReader(),
            model_adapter=self._model_adapter,
            backend=backend,
            persistence=SqlCandidatePersistence(
                current_user,
                self._config.current(),
                self._session_factory,
                self._clock,
            ),
            clock=self._clock.now,
        )

    def _load_fact_context(
        self, matter_id: UUID, current_user: CurrentUser
    ) -> tuple[dict[str, int | None], dict[str, Any]]:
        with (
            self._session_factory() as session,
            transaction(session, current_user),
        ):
            require_matter(session, current_user, matter_id)
            relevant = fact_service.relevant_fact_types(session, matter_id)
            fact_types = set(relevant) | set(supported_fact_types())
            versions = fact_service.expected_fact_versions(
                session, matter_id, fact_types
            )
            values = fact_service.agent_fact_values(session, matter_id, fact_types)
        return versions, values

    def _create_run(
        self,
        *,
        run_id: str,
        matter_id: UUID,
        operation_id: str | None,
        current_user: CurrentUser,
    ) -> None:
        now = self._clock.now()
        with (
            self._session_factory() as session,
            transaction(session, current_user),
        ):
            session.execute(
                insert(agent_run).values(
                    run_id=run_id,
                    matter_id=matter_id,
                    user_id=current_user.user_id,
                    status="running",
                    operation_id=operation_id,
                    checkpoint=None,
                    created_at=now,
                    updated_at=now,
                )
            )

    def _load_run(
        self, run_id: str, current_user: CurrentUser
    ) -> dict[str, Any] | None:
        with (
            self._session_factory() as session,
            transaction(session, current_user),
        ):
            row = (
                session.execute(
                    select(agent_run).where(
                        agent_run.c.run_id == run_id,
                        agent_run.c.user_id == current_user.user_id,
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row is not None else None

    def _require_run(self, run_id: str, current_user: CurrentUser) -> dict[str, Any]:
        row = self._load_run(run_id, current_user)
        if row is None:
            raise _run_not_found()
        return row

    def _checkpoint_from_row(self, row: dict[str, Any]) -> RunCheckpoint | None:
        payload = row.get("checkpoint")
        if not isinstance(payload, dict):
            return None
        return RunCheckpoint.model_validate(payload)

    def _save_result(
        self,
        *,
        run_id: str,
        result: AgentRunResult,
        matter_id: str,
        user_id: str,
        workspace_version: int,
        current_user: CurrentUser,
    ) -> AgentRunResult:
        checkpoint = RunCheckpoint(
            run_id=result.run_id,
            user_id=user_id,
            matter_id=matter_id,
            workspace_version=workspace_version,
            **result.model_dump(exclude={"run_id"}),
        )
        payload = checkpoint.model_dump(mode="json", exclude={"sources"})
        with (
            self._session_factory() as session,
            transaction(session, current_user),
        ):
            existing = session.execute(
                select(agent_run.c.checkpoint)
                .where(
                    agent_run.c.run_id == run_id,
                    agent_run.c.user_id == current_user.user_id,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if isinstance(existing, dict):
                for field in _PERSISTED_DETAIL_FIELDS:
                    if not payload.get(field) and existing.get(field):
                        payload[field] = existing[field]
            merged = RunCheckpoint.model_validate(payload)
            session.execute(
                update(agent_run)
                .where(
                    agent_run.c.run_id == run_id,
                    agent_run.c.user_id == current_user.user_id,
                )
                .values(
                    status=_RUN_STATUS_KEYS[merged.status],
                    checkpoint=payload,
                    updated_at=self._clock.now(),
                )
            )
        return self._result_from_checkpoint(merged)

    def _mark_interrupted(self, run_id: str, current_user: CurrentUser) -> None:
        with (
            self._session_factory() as session,
            transaction(session, current_user),
        ):
            session.execute(
                update(agent_run)
                .where(
                    agent_run.c.run_id == run_id,
                    agent_run.c.user_id == current_user.user_id,
                )
                .values(status="interrupted", updated_at=self._clock.now())
            )

    def _result_from_row(self, row: dict[str, Any]) -> AgentRunResult:
        checkpoint = self._checkpoint_from_row(row)
        if checkpoint is not None:
            return self._result_from_checkpoint(checkpoint)
        status = _RUN_STATUS_BY_KEY.get(str(row["status"]), RunStatus.FAILED)
        if status == RunStatus.INTERRUPTED:
            return self._interrupted_result(row)
        return AgentRunResult(run_id=str(row["run_id"]), status=status)

    def _interrupted_result(self, row: dict[str, Any]) -> AgentRunResult:
        checkpoint = RunCheckpoint(
            run_id=str(row["run_id"]),
            user_id=str(row["user_id"]),
            matter_id=str(row["matter_id"]),
            workspace_version=0,
            status=RunStatus.INTERRUPTED,
            error=AgentError(
                code=AgentErrorCode.RUN_INTERRUPTED,
                message=(
                    "Agent 运行在服务重启时中断，未完成的步骤不会继续；请重新发起运行。"
                ),
                details={"retryable": True},
            ),
        )
        return self._result_from_checkpoint(checkpoint)

    def _result_from_checkpoint(
        self,
        checkpoint: RunCheckpoint,
        *,
        error: AgentError | None = None,
    ) -> AgentRunResult:
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
            error=error if error is not None else checkpoint.error,
            execution_records=checkpoint.execution_records,
        )


def _run_not_found() -> ApiError:
    return ApiError(
        404,
        "agent_run_not_found",
        "未找到 Agent 运行",
        next_step="核对运行标识，或通过候选计划接口继续处理已持久化候选",
    )
