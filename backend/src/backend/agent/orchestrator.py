"""Main Agent orchestrator implementing the Run lifecycle and candidate-then-confirm flow."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from backend.agent.contracts import (
    build_candidate_plan_create_payload,
    build_requirements_batch_payload,
)
from backend.agent.gateway import GatewayError, ToolGateway
from backend.agent.ports import (
    CandidatePersistencePort,
    ModelAdapterPort,
    SourceReaderPort,
    WorkspaceBackendPort,
)
from backend.agent.schemas import (
    AgentError,
    AgentErrorCode,
    AgentRunResult,
    CandidatePlan,
    ExtractedRequirement,
    RequirementEvaluation,
    RunCheckpoint,
    RunContext,
    RunStatus,
    SourceDocument,
    SourceGap,
)
from backend.agent.validators import (
    collect_source_gaps,
    evaluate_requirements,
    find_expired_plan_tasks,
    validate_candidate_plan,
)


class AgentOrchestrator:
    """Coordinates source retrieval, four-state evaluation, candidate planning, and confirmed writes."""

    def __init__(
        self,
        *,
        source_reader: SourceReaderPort,
        model_adapter: ModelAdapterPort,
        backend: WorkspaceBackendPort,
        gateway: ToolGateway | None = None,
        persistence: CandidatePersistencePort | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._source_reader = source_reader
        self._model_adapter = model_adapter
        self._backend = backend
        self._gateway = gateway or ToolGateway(backend)
        self._persistence = persistence
        self._clock = clock or (lambda: datetime.now(UTC))
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

        if context.source_documents:
            sources = list(context.source_documents)
        else:
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
        gaps = collect_source_gaps(sources, evaluations)
        adapter_gaps = getattr(self._model_adapter, "last_gaps", None)
        if isinstance(adapter_gaps, list):
            for gap in adapter_gaps:
                if isinstance(gap, SourceGap) and gap not in gaps:
                    gaps.append(gap)

        scope_summary: dict[str, Any] = {}
        if context.scope_year is not None:
            scope_summary["scope_year"] = context.scope_year
        if context.scope_attrs:
            scope_summary.update(context.scope_attrs)
        adapter_scope = getattr(self._model_adapter, "last_scope_summary", None)
        if isinstance(adapter_scope, dict):
            scope_summary.update(adapter_scope)

        if not requirements:
            err = eval_error or AgentError(
                code=AgentErrorCode.RULE_CONFLICT_OR_AMBIGUOUS,
                message="未能从来源中提取出有效要求，待用户补充或核对",
            )
            return self._save_terminal_or_wait(
                run_id=run_id,
                context=context,
                status=RunStatus.WAITING_USER,
                error=err,
                records=records,
                sources=sources,
                extracted_requirements=requirements,
                evaluations=evaluations,
                gaps=gaps,
                scope_summary=scope_summary,
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
                extracted_requirements=requirements,
                evaluations=evaluations,
                gaps=gaps,
                scope_summary=scope_summary,
            )

        violations = validate_candidate_plan(
            candidate_plan,
            context.workspace_version,
            sources_by_id=sources_by_id,
        )
        if violations:
            err = AgentError(
                code=AgentErrorCode.VALIDATION_FAILED,
                message="候选计划未通过领域约束校验",
                details={"violations": violations},
            )
            return self._save_terminal_or_wait(
                run_id=run_id,
                context=context,
                status=RunStatus.FAILED,
                error=err,
                records=records,
                sources=sources,
                extracted_requirements=requirements,
                evaluations=evaluations,
                gaps=gaps,
                scope_summary=scope_summary,
            )

        merged_gaps = list(gaps) + [g for g in candidate_plan.gaps if g not in gaps]
        merged_scope = dict(scope_summary) | dict(candidate_plan.scope_summary)

        now = context.as_of or self._clock()
        expired_tasks = find_expired_plan_tasks(candidate_plan, now)
        if expired_tasks:
            merged_gaps.append(
                SourceGap(
                    gap_type="expired_source",
                    description=f"候选任务 {', '.join(expired_tasks)} 对应的官方截止时间已过，仅供历史参考",
                )
            )

        candidate_plan = candidate_plan.model_copy(
            update={"gaps": merged_gaps, "scope_summary": merged_scope}
        )

        persisted_req_ids: list[str] = []
        persisted_plan_id: str | None = None
        if self._persistence is not None and _can_persist_uuids(
            requirements, candidate_plan, sources_by_id
        ):
            try:
                (persisted_req_ids, persisted_plan_id), rec_persist = self._gateway.invoke(
                    tool_name="persist_candidate_artifacts",
                    user_id=context.user_id,
                    matter_id=context.matter_id,
                    expected_workspace_version=context.workspace_version,
                    fn=lambda: self._persist_candidates(
                        context.matter_id,
                        requirements,
                        evaluations,
                        candidate_plan,
                        sources_by_id,
                    ),
                )
                records.append(rec_persist)
            except GatewayError as exc:
                return self._save_terminal_or_wait(
                    run_id=run_id,
                    context=context,
                    status=RunStatus.FAILED,
                    error=exc.error,
                    records=records,
                    sources=sources,
                    extracted_requirements=requirements,
                    evaluations=evaluations,
                    gaps=merged_gaps,
                    scope_summary=merged_scope,
                )

        checkpoint = RunCheckpoint(
            run_id=run_id,
            user_id=context.user_id,
            matter_id=context.matter_id,
            workspace_version=context.workspace_version,
            status=RunStatus.WAITING_CONFIRMATION,
            sources=sources,
            extracted_requirements=requirements,
            evaluations=evaluations,
            gaps=merged_gaps,
            scope_summary=merged_scope,
            candidate_plan=candidate_plan,
            persisted_requirement_ids=persisted_req_ids,
            persisted_plan_id=persisted_plan_id,
            execution_records=records,
        )
        self._checkpoints[run_id] = checkpoint
        return AgentRunResult(
            run_id=run_id,
            status=RunStatus.WAITING_CONFIRMATION,
            extracted_requirements=requirements,
            evaluations=evaluations,
            gaps=merged_gaps,
            scope_summary=merged_scope,
            candidate_plan=candidate_plan,
            persisted_requirement_ids=persisted_req_ids,
            persisted_plan_id=persisted_plan_id,
            execution_records=records,
        )

    def confirm_plan(
        self,
        run_id: str,
        *,
        candidate_version: int,
        operation_id: str,
        as_of: datetime | None = None,
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
                extracted_requirements=cp.extracted_requirements,
                evaluations=cp.evaluations,
                gaps=cp.gaps,
                scope_summary=cp.scope_summary,
                candidate_plan=cp.candidate_plan,
                persisted_requirement_ids=cp.persisted_requirement_ids,
                persisted_plan_id=cp.persisted_plan_id,
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
                extracted_requirements=cp.extracted_requirements,
                evaluations=cp.evaluations,
                gaps=cp.gaps,
                scope_summary=cp.scope_summary,
                candidate_plan=cp.candidate_plan,
                persisted_requirement_ids=cp.persisted_requirement_ids,
                persisted_plan_id=cp.persisted_plan_id,
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
                extracted_requirements=cp.extracted_requirements,
                evaluations=cp.evaluations,
                gaps=cp.gaps,
                scope_summary=cp.scope_summary,
                candidate_plan=cp.candidate_plan,
                persisted_requirement_ids=cp.persisted_requirement_ids,
                persisted_plan_id=cp.persisted_plan_id,
                error=err,
                execution_records=cp.execution_records,
            )

        plan = cp.candidate_plan
        expired_tasks = find_expired_plan_tasks(plan, as_of or self._clock())
        if expired_tasks:
            err = AgentError(
                code=AgentErrorCode.DEADLINE_EXPIRED,
                message=f"候选任务 {', '.join(expired_tasks)} 的官方截止时间已过，阻止生成正式任务",
                details={"expired_task_ids": expired_tasks},
            )
            cp.error = err
            return AgentRunResult(
                run_id=run_id,
                status=RunStatus.WAITING_CONFIRMATION,
                extracted_requirements=cp.extracted_requirements,
                evaluations=cp.evaluations,
                gaps=cp.gaps,
                scope_summary=cp.scope_summary,
                candidate_plan=plan,
                persisted_requirement_ids=cp.persisted_requirement_ids,
                persisted_plan_id=cp.persisted_plan_id,
                error=err,
                execution_records=cp.execution_records,
            )

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
                extracted_requirements=cp.extracted_requirements,
                evaluations=cp.evaluations,
                gaps=cp.gaps,
                scope_summary=cp.scope_summary,
                candidate_plan=plan,
                persisted_requirement_ids=cp.persisted_requirement_ids,
                persisted_plan_id=cp.persisted_plan_id,
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
            extracted_requirements=cp.extracted_requirements,
            evaluations=cp.evaluations,
            gaps=cp.gaps,
            scope_summary=cp.scope_summary,
            candidate_plan=plan,
            persisted_requirement_ids=cp.persisted_requirement_ids,
            persisted_plan_id=cp.persisted_plan_id,
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
            extracted_requirements=cp.extracted_requirements,
            evaluations=cp.evaluations,
            gaps=cp.gaps,
            scope_summary=cp.scope_summary,
            candidate_plan=cp.candidate_plan,
            persisted_requirement_ids=cp.persisted_requirement_ids,
            persisted_plan_id=cp.persisted_plan_id,
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
                extracted_requirements=cp.extracted_requirements,
                evaluations=cp.evaluations,
                gaps=cp.gaps,
                scope_summary=cp.scope_summary,
                candidate_plan=cp.candidate_plan,
                persisted_requirement_ids=cp.persisted_requirement_ids,
                persisted_plan_id=cp.persisted_plan_id,
                written_tasks=cp.written_tasks,
                error=cp.error,
                execution_records=cp.execution_records,
            )

        cp.status = RunStatus.CANCELLED
        cp.error = AgentError(code=AgentErrorCode.CANCELLED, message="运行已被用户取消")
        return AgentRunResult(
            run_id=run_id,
            status=RunStatus.CANCELLED,
            extracted_requirements=cp.extracted_requirements,
            evaluations=cp.evaluations,
            gaps=cp.gaps,
            scope_summary=cp.scope_summary,
            candidate_plan=cp.candidate_plan,
            persisted_requirement_ids=cp.persisted_requirement_ids,
            persisted_plan_id=cp.persisted_plan_id,
            written_tasks=cp.written_tasks,
            error=cp.error,
            execution_records=cp.execution_records,
        )

    def _persist_candidates(
        self,
        matter_id: str,
        requirements: list[ExtractedRequirement],
        evaluations: list[RequirementEvaluation],
        candidate_plan: CandidatePlan,
        sources_by_id: dict[str, SourceDocument],
    ) -> tuple[list[str], str | None]:
        assert self._persistence is not None
        req_payload = build_requirements_batch_payload(requirements, evaluations, sources_by_id)
        created_reqs = self._persistence.persist_requirements(matter_id, req_payload)
        req_id_map: dict[str, str] = {}
        persisted_ids: list[str] = []
        for req_obj, created in zip(requirements, created_reqs, strict=False):
            created_id = created.get("id")
            if isinstance(created_id, str) and created_id:
                req_id_map[req_obj.requirement_id] = created_id
                persisted_ids.append(created_id)

        plan_payload = build_candidate_plan_create_payload(
            candidate_plan,
            sources_by_id,
            requirement_id_map=req_id_map,
        )
        plan_resp = self._persistence.persist_candidate_plan(matter_id, plan_payload)
        raw_plan_id = plan_resp.get("id")
        plan_id = str(raw_plan_id) if raw_plan_id is not None else None
        return persisted_ids, plan_id

    def _save_terminal_or_wait(
        self,
        *,
        run_id: str,
        context: RunContext,
        status: RunStatus,
        error: AgentError,
        records: list,
        sources: list[SourceDocument] | None = None,
        extracted_requirements: list[ExtractedRequirement] | None = None,
        evaluations: list[RequirementEvaluation] | None = None,
        gaps: list[SourceGap] | None = None,
        scope_summary: dict[str, Any] | None = None,
    ) -> AgentRunResult:
        cp = RunCheckpoint(
            run_id=run_id,
            user_id=context.user_id,
            matter_id=context.matter_id,
            workspace_version=context.workspace_version,
            status=status,
            sources=sources or [],
            extracted_requirements=extracted_requirements or [],
            evaluations=evaluations or [],
            gaps=gaps or [],
            scope_summary=scope_summary or {},
            error=error,
            execution_records=records,
        )
        self._checkpoints[run_id] = cp
        return AgentRunResult(
            run_id=run_id,
            status=status,
            extracted_requirements=extracted_requirements or [],
            evaluations=evaluations or [],
            gaps=gaps or [],
            scope_summary=scope_summary or {},
            error=error,
            execution_records=records,
        )


def _can_persist_uuids(
    requirements: list[ExtractedRequirement],
    plan: CandidatePlan,
    sources_by_id: dict[str, SourceDocument],
) -> bool:
    for req in requirements:
        for cite in req.basis:
            doc = sources_by_id.get(cite.source_version_id)
            sid = cite.source_id or (doc.source_id if doc else None)
            snap = cite.snapshot_id or (doc.snapshot_id if doc else None)
            if not _is_uuid(sid) or not _is_uuid(snap):
                return False
    for task in plan.tasks:
        for cite in task.basis:
            doc = sources_by_id.get(cite.source_version_id)
            sid = cite.source_id or (doc.source_id if doc else None)
            snap = cite.snapshot_id or (doc.snapshot_id if doc else None)
            if not _is_uuid(sid) or not _is_uuid(snap):
                return False
    return True


def _is_uuid(value: str | None) -> bool:
    if not value:
        return False
    try:
        UUID(value)
    except ValueError:
        return False
    return True
