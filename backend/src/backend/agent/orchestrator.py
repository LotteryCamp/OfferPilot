"""Main Agent orchestrator implementing the Run lifecycle and candidate-then-confirm flow."""

from __future__ import annotations

from uuid import uuid4

from backend.agent.gateway import GatewayError, ToolGateway
from backend.agent.ports import ModelAdapterPort, SourceReaderPort, WorkspaceBackendPort
from backend.agent.schemas import (
    AgentError,
    AgentErrorCode,
    AgentRunResult,
    RunCheckpoint,
    RunContext,
    RunStatus,
)
from backend.agent.validators import evaluate_requirements, validate_candidate_plan


class AgentOrchestrator:
    """Coordinates source retrieval, four-state evaluation, candidate planning, and confirmed writes."""

    def __init__(
        self,
        *,
        source_reader: SourceReaderPort,
        model_adapter: ModelAdapterPort,
        backend: WorkspaceBackendPort,
        gateway: ToolGateway | None = None,
    ) -> None:
        self._source_reader = source_reader
        self._model_adapter = model_adapter
        self._backend = backend
        self._gateway = gateway or ToolGateway(backend)
        self._checkpoints: dict[str, RunCheckpoint] = {}

    def get_checkpoint(self, run_id: str) -> RunCheckpoint | None:
        """Return saved checkpoint for an existing run."""
        return self._checkpoints.get(run_id)

    def start_run(self, context: RunContext) -> AgentRunResult:
        """Execute retrieval, extraction, four-state check, and candidate plan generation.

        Never creates formal tasks; pauses at WAITING_CONFIRMATION or WAITING_USER.
        """
        run_id = f"run-{uuid4().hex[:12]}"
        records = []

        try:
            sources, rec_src = self._gateway.invoke(
                tool_name="fetch_official_sources",
                user_id=context.user_id,
                matter_id=context.matter_id,
                expected_workspace_version=context.workspace_version,
                fn=lambda: self._source_reader.fetch_sources(context.source_urls, context.goal),
            )
            records.append(rec_src)
        except GatewayError as exc:
            return self._save_terminal_or_wait(
                run_id=run_id,
                context=context,
                status=RunStatus.FAILED,
                error=exc.error,
                records=records,
            )

        if not sources:
            err = AgentError(
                code=AgentErrorCode.SOURCE_UNAVAILABLE,
                message="未获取到可用的官方来源，暂存探索草稿",
            )
            return self._save_terminal_or_wait(
                run_id=run_id,
                context=context,
                status=RunStatus.WAITING_USER,
                error=err,
                records=records,
            )

        try:
            requirements, rec_ext = self._gateway.invoke(
                tool_name="extract_requirements",
                user_id=context.user_id,
                matter_id=context.matter_id,
                expected_workspace_version=context.workspace_version,
                requires_transfer_consent=bool(context.confirmed_facts),
                consent_id=context.model_transfer_consent_id,
                fn=lambda: self._model_adapter.extract_requirements(context.goal, sources),
            )
            records.append(rec_ext)
        except GatewayError as exc:
            return self._save_terminal_or_wait(
                run_id=run_id,
                context=context,
                status=RunStatus.FAILED,
                error=exc.error,
                records=records,
                sources=sources,
            )

        sources_by_id = {s.source_version_id: s for s in sources}
        evaluations, eval_error = evaluate_requirements(
            requirements,
            sources_by_id,
            context.confirmed_facts,
        )

        if eval_error is not None:
            checkpoint = RunCheckpoint(
                run_id=run_id,
                user_id=context.user_id,
                matter_id=context.matter_id,
                workspace_version=context.workspace_version,
                status=RunStatus.WAITING_USER,
                sources=sources,
                evaluations=evaluations,
                error=eval_error,
                execution_records=records,
            )
            self._checkpoints[run_id] = checkpoint
            return AgentRunResult(
                run_id=run_id,
                status=RunStatus.WAITING_USER,
                evaluations=evaluations,
                error=eval_error,
                execution_records=records,
            )

        try:
            candidate_plan, rec_plan = self._gateway.invoke(
                tool_name="generate_candidate_plan",
                user_id=context.user_id,
                matter_id=context.matter_id,
                expected_workspace_version=context.workspace_version,
                requires_transfer_consent=bool(context.confirmed_facts),
                consent_id=context.model_transfer_consent_id,
                fn=lambda: self._model_adapter.generate_candidate_plan(context, sources, evaluations),
            )
            records.append(rec_plan)
        except GatewayError as exc:
            return self._save_terminal_or_wait(
                run_id=run_id,
                context=context,
                status=RunStatus.FAILED,
                error=exc.error,
                records=records,
                sources=sources,
            )

        violations = validate_candidate_plan(candidate_plan, context.workspace_version)
        if violations:
            err = AgentError(
                code=AgentErrorCode.VALIDATION_FAILED,
                message="候选计划未通过领域约束校验",
                details={"violations": violations},
            )
            checkpoint = RunCheckpoint(
                run_id=run_id,
                user_id=context.user_id,
                matter_id=context.matter_id,
                workspace_version=context.workspace_version,
                status=RunStatus.FAILED,
                sources=sources,
                evaluations=evaluations,
                error=err,
                execution_records=records,
            )
            self._checkpoints[run_id] = checkpoint
            return AgentRunResult(
                run_id=run_id,
                status=RunStatus.FAILED,
                evaluations=evaluations,
                error=err,
                execution_records=records,
            )

        checkpoint = RunCheckpoint(
            run_id=run_id,
            user_id=context.user_id,
            matter_id=context.matter_id,
            workspace_version=context.workspace_version,
            status=RunStatus.WAITING_CONFIRMATION,
            sources=sources,
            evaluations=evaluations,
            candidate_plan=candidate_plan,
            execution_records=records,
        )
        self._checkpoints[run_id] = checkpoint
        return AgentRunResult(
            run_id=run_id,
            status=RunStatus.WAITING_CONFIRMATION,
            evaluations=evaluations,
            candidate_plan=candidate_plan,
            execution_records=records,
        )

    def confirm_plan(
        self,
        run_id: str,
        *,
        candidate_version: int,
        operation_id: str,
    ) -> AgentRunResult:
        """Resume a waiting run and persist formal tasks after user confirmation."""
        cp = self._checkpoints.get(run_id)
        if cp is None or cp.candidate_plan is None:
            err = AgentError(
                code=AgentErrorCode.VALIDATION_FAILED,
                message="不存在待确认的候选计划",
            )
            return AgentRunResult(run_id=run_id, status=RunStatus.FAILED, error=err)

        if cp.status == RunStatus.COMPLETED:
            return AgentRunResult(
                run_id=run_id,
                status=RunStatus.COMPLETED,
                evaluations=cp.evaluations,
                candidate_plan=cp.candidate_plan,
                written_tasks=cp.written_tasks,
                execution_records=cp.execution_records,
            )

        if cp.status != RunStatus.WAITING_CONFIRMATION:
            err = AgentError(
                code=AgentErrorCode.VALIDATION_FAILED,
                message=f"当前运行状态为 {cp.status.value}，无法执行确认写入",
            )
            return AgentRunResult(
                run_id=run_id,
                status=cp.status,
                evaluations=cp.evaluations,
                candidate_plan=cp.candidate_plan,
                error=err,
                execution_records=cp.execution_records,
            )

        if cp.candidate_plan.candidate_version != candidate_version:
            err = AgentError(
                code=AgentErrorCode.VERSION_CONFLICT,
                message=(
                    f"候选版本已失效：期望 {cp.candidate_plan.candidate_version}，"
                    f"收到 {candidate_version}"
                ),
            )
            cp.error = err
            return AgentRunResult(
                run_id=run_id,
                status=RunStatus.WAITING_CONFIRMATION,
                evaluations=cp.evaluations,
                candidate_plan=cp.candidate_plan,
                error=err,
                execution_records=cp.execution_records,
            )

        plan = cp.candidate_plan
        try:
            written, rec_write = self._gateway.invoke(
                tool_name="write_personal_tasks",
                user_id=cp.user_id,
                matter_id=cp.matter_id,
                expected_workspace_version=cp.workspace_version,
                operation_id=operation_id,
                fn=lambda: self._backend.consume_candidate_and_write_tasks(
                    user_id=cp.user_id,
                    matter_id=cp.matter_id,
                    candidate_plan=plan,
                    expected_workspace_version=cp.workspace_version,
                    operation_id=operation_id,
                ),
            )
        except GatewayError as exc:
            cp.error = exc.error
            cp.status = RunStatus.FAILED
            return AgentRunResult(
                run_id=run_id,
                status=RunStatus.FAILED,
                evaluations=cp.evaluations,
                candidate_plan=plan,
                error=exc.error,
                execution_records=cp.execution_records,
            )

        cp.execution_records.append(rec_write)
        cp.written_tasks = written
        cp.status = RunStatus.COMPLETED
        cp.error = None
        return AgentRunResult(
            run_id=run_id,
            status=RunStatus.COMPLETED,
            evaluations=cp.evaluations,
            candidate_plan=plan,
            written_tasks=written,
            execution_records=cp.execution_records,
        )

    def reject_plan(self, run_id: str) -> AgentRunResult:
        """Reject the candidate plan; never writes formal tasks (HHY-AC05)."""
        cp = self._checkpoints.get(run_id)
        if cp is None:
            err = AgentError(code=AgentErrorCode.VALIDATION_FAILED, message="运行记录不存在")
            return AgentRunResult(run_id=run_id, status=RunStatus.FAILED, error=err)

        cp.status = RunStatus.CANCELLED
        cp.error = AgentError(code=AgentErrorCode.CANCELLED, message="用户已拒绝候选计划，未创建正式任务")
        return AgentRunResult(
            run_id=run_id,
            status=RunStatus.CANCELLED,
            evaluations=cp.evaluations,
            candidate_plan=cp.candidate_plan,
            written_tasks=[],
            error=cp.error,
            execution_records=cp.execution_records,
        )

    def cancel_run(self, run_id: str) -> AgentRunResult:
        """Cancel an active or waiting run without masking already-written tasks."""
        cp = self._checkpoints.get(run_id)
        if cp is None:
            err = AgentError(code=AgentErrorCode.VALIDATION_FAILED, message="运行记录不存在")
            return AgentRunResult(run_id=run_id, status=RunStatus.FAILED, error=err)

        if cp.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
            return AgentRunResult(
                run_id=run_id,
                status=cp.status,
                evaluations=cp.evaluations,
                candidate_plan=cp.candidate_plan,
                written_tasks=cp.written_tasks,
                error=cp.error,
                execution_records=cp.execution_records,
            )

        cp.status = RunStatus.CANCELLED
        cp.error = AgentError(code=AgentErrorCode.CANCELLED, message="运行已被用户取消")
        return AgentRunResult(
            run_id=run_id,
            status=RunStatus.CANCELLED,
            evaluations=cp.evaluations,
            candidate_plan=cp.candidate_plan,
            written_tasks=cp.written_tasks,
            error=cp.error,
            execution_records=cp.execution_records,
        )

    def _save_terminal_or_wait(
        self,
        *,
        run_id: str,
        context: RunContext,
        status: RunStatus,
        error: AgentError,
        records: list,
        sources: list | None = None,
    ) -> AgentRunResult:
        cp = RunCheckpoint(
            run_id=run_id,
            user_id=context.user_id,
            matter_id=context.matter_id,
            workspace_version=context.workspace_version,
            status=status,
            sources=sources or [],
            error=error,
            execution_records=records,
        )
        self._checkpoints[run_id] = cp
        return AgentRunResult(
            run_id=run_id,
            status=status,
            error=error,
            execution_records=records,
        )
