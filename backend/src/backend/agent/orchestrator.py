"""Main Agent orchestrator implementing the Run lifecycle and candidate-then-confirm flow."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from backend.agent.contracts import (
    PersistenceApiError,
    build_candidate_plan_create_payload,
    build_client_item_id_map,
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
    ObligationType,
    RequirementEvaluation,
    RunCheckpoint,
    RunContext,
    RunStatus,
    SourceDocument,
    SourceGap,
    WrittenTask,
)
from backend.agent.validators import (
    collect_source_gaps,
    evaluate_requirements,
    find_expired_plan_tasks,
    validate_candidate_plan,
)
from backend.basis import CRITICAL_BASIS_GAP_TYPES

_API_OBLIGATION_TO_ENUM: dict[str, ObligationType] = {
    "required": ObligationType.OFFICIAL_REQUIRED,
    "advised": ObligationType.OFFICIAL_RECOMMENDED,
    "optional": ObligationType.OPTIONAL,
    "to_verify": ObligationType.PENDING_VERIFICATION,
}
_NON_TERMINAL_CONFIRM_ERRORS = frozenset({"basis_unresolved", "source_unavailable"})


class AgentOrchestrator:
    """Coordinates source retrieval, four-state evaluation, candidate planning, and persisted decisions."""

    def __init__(
        self,
        *,
        source_reader: SourceReaderPort,
        model_adapter: ModelAdapterPort,
        backend: WorkspaceBackendPort,
        persistence: CandidatePersistencePort | None = None,
        gateway: ToolGateway | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._source_reader = source_reader
        self._model_adapter = model_adapter
        self._backend = backend
        self._persistence = persistence
        self._gateway = gateway or ToolGateway(backend)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._checkpoints: dict[str, RunCheckpoint] = {}
        self._run_idempotency: dict[tuple[str, str, str], AgentRunResult] = {}
        self._persisted_req_cache: dict[
            tuple[str, str], tuple[list[str], dict[str, str]]
        ] = {}
        self._run_locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _get_run_lock(self, run_id: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._run_locks.get(run_id)
            if lock is None:
                lock = threading.Lock()
                self._run_locks[run_id] = lock
            return lock

    def get_checkpoint(
        self,
        run_id: str,
        *,
        caller_user_id: str | None = None,
    ) -> RunCheckpoint | None:
        """Return saved in-memory checkpoint for an existing run owned by caller_user_id."""
        cp = self._checkpoints.get(run_id)
        if cp is None:
            return None
        if caller_user_id is not None and cp.user_id != caller_user_id:
            return None
        return cp

    def get_persisted_plan(self, plan_id: str) -> dict[str, Any]:
        """Read a persisted candidate plan directly from the backend persistence port."""
        if self._persistence is None:
            raise RuntimeError("未配置候选持久化服务，无法读取持久化计划")
        return self._persistence.get_candidate_plan(plan_id)

    def start_run(
        self, context: RunContext, *, run_id: str | None = None
    ) -> AgentRunResult:
        """Execute retrieval, extraction, four-state check, candidate generation, and persistence.

        The normal path requires candidate persistence to succeed before returning WAITING_CONFIRMATION.
        Never creates formal tasks prior to user confirmation.
        """
        if context.operation_id:
            cached_result = self._run_idempotency.get(
                (context.user_id, context.matter_id, context.operation_id)
            )
            if cached_result is not None:
                return cached_result

        run_id = run_id or f"run-{uuid4().hex[:12]}"
        records = []
        transfer_facts = (
            context.model_transfer_facts
            if context.model_transfer_facts is not None
            else context.confirmed_facts
        )
        requires_transfer_consent = bool(transfer_facts or context.scope_attrs)

        if self._persistence is None:
            err = AgentError(
                code=AgentErrorCode.VALIDATION_FAILED,
                message="未配置候选持久化服务，无法保存待确认候选计划",
            )
            return self._save_terminal_or_wait(
                run_id=run_id,
                context=context,
                status=RunStatus.FAILED,
                error=err,
                records=records,
            )

        if context.source_documents:
            sources = list(context.source_documents)
        else:
            try:
                sources, rec_src = self._gateway.invoke(
                    tool_name="fetch_official_sources",
                    user_id=context.user_id,
                    matter_id=context.matter_id,
                    expected_workspace_version=context.workspace_version,
                    fn=lambda: self._fetch_sources(context),
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

        extract_with_meta = getattr(
            self._model_adapter, "extract_requirements_with_metadata", None
        )
        adapter_gaps: list[SourceGap] = []
        adapter_scope: dict[str, Any] = {}
        try:
            if callable(extract_with_meta):
                (requirements, adapter_gaps, adapter_scope), rec_ext = (
                    self._gateway.invoke(
                        tool_name="extract_requirements",
                        user_id=context.user_id,
                        matter_id=context.matter_id,
                        expected_workspace_version=context.workspace_version,
                        requires_transfer_consent=requires_transfer_consent,
                        fn=lambda: extract_with_meta(context.goal, sources),
                    )
                )
            else:
                requirements, rec_ext = self._gateway.invoke(
                    tool_name="extract_requirements",
                    user_id=context.user_id,
                    matter_id=context.matter_id,
                    expected_workspace_version=context.workspace_version,
                    requires_transfer_consent=requires_transfer_consent,
                    fn=lambda: self._model_adapter.extract_requirements(
                        context.goal, sources
                    ),
                )
                raw_gaps = getattr(self._model_adapter, "last_gaps", None)
                if isinstance(raw_gaps, list):
                    adapter_gaps = [g for g in raw_gaps if isinstance(g, SourceGap)]
                raw_scope = getattr(self._model_adapter, "last_scope_summary", None)
                if isinstance(raw_scope, dict):
                    adapter_scope = dict(raw_scope)
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
        for gap in adapter_gaps:
            if gap not in gaps:
                gaps.append(gap)

        scope_summary: dict[str, Any] = {}
        if context.scope_year is not None:
            scope_summary["scope_year"] = context.scope_year
        if context.scope_attrs:
            scope_summary.update(context.scope_attrs)
        if adapter_scope:
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
                requires_transfer_consent=requires_transfer_consent,
                fn=lambda: self._model_adapter.generate_candidate_plan(
                    context, sources, evaluations
                ),
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

        if not _can_persist_uuids(requirements, candidate_plan, sources_by_id):
            err = AgentError(
                code=AgentErrorCode.VALIDATION_FAILED,
                message="来源或快照缺少有效 UUID 标识，无法持久化待确认候选计划",
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
                gaps=merged_gaps,
                scope_summary=merged_scope,
            )

        persist_op_id = (
            f"{context.operation_id}:persist" if context.operation_id else None
        )
        persist_binding = (
            f"persist:{context.matter_id}:{context.goal}:{context.workspace_version}"
        )
        try:
            (persisted_req_ids, persisted_plan_id), rec_persist = self._gateway.invoke(
                tool_name="persist_candidate_artifacts",
                user_id=context.user_id,
                matter_id=context.matter_id,
                expected_workspace_version=context.workspace_version,
                operation_id=persist_op_id,
                idempotency_binding=persist_binding,
                requires_transfer_consent=requires_transfer_consent,
                fn=lambda: self._persist_candidates(
                    context.matter_id,
                    requirements,
                    evaluations,
                    candidate_plan,
                    sources_by_id,
                    gaps=merged_gaps,
                    operation_id=context.operation_id,
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

        if not persisted_plan_id:
            err = AgentError(
                code=AgentErrorCode.VALIDATION_FAILED,
                message="候选计划持久化未返回有效计划标识",
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
        result = AgentRunResult(
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
        if context.operation_id:
            self._run_idempotency[
                (context.user_id, context.matter_id, context.operation_id)
            ] = result
        return result

    def confirm_plan(
        self,
        run_id: str,
        *,
        candidate_version: int,
        operation_id: str,
        plan_id: str | None = None,
        user_id: str | None = None,
        matter_id: str | None = None,
        workspace_version: int | None = None,
    ) -> AgentRunResult:
        """Delegate confirmation transaction to the backend persistence port.

        Supports recovery from persisted plan_id when in-memory checkpoint is absent.
        Retains WAITING_CONFIRMATION on uncertain timeouts so retries with the same operation_id succeed.
        """
        with self._get_run_lock(run_id):
            return self._confirm_plan_locked(
                run_id=run_id,
                candidate_version=candidate_version,
                operation_id=operation_id,
                plan_id=plan_id,
                user_id=user_id,
                matter_id=matter_id,
                workspace_version=workspace_version,
            )

    def _confirm_plan_locked(
        self,
        *,
        run_id: str,
        candidate_version: int,
        operation_id: str,
        plan_id: str | None = None,
        user_id: str | None = None,
        matter_id: str | None = None,
        workspace_version: int | None = None,
    ) -> AgentRunResult:
        cp = self._resolve_or_recover_checkpoint(
            run_id=run_id,
            plan_id=plan_id,
            user_id=user_id,
            matter_id=matter_id,
            workspace_version=workspace_version,
        )
        if cp is None or cp.persisted_plan_id is None:
            err = AgentError(
                code=AgentErrorCode.VALIDATION_FAILED,
                message="不存在可确认的持久化候选计划",
            )
            return AgentRunResult(run_id=run_id, status=RunStatus.FAILED, error=err)

        if user_id is not None and cp.user_id != user_id:
            err = AgentError(
                code=AgentErrorCode.PERMISSION_DENIED,
                message="无权操作其他用户的运行记录",
            )
            return AgentRunResult(run_id=run_id, status=RunStatus.FAILED, error=err)

        if cp.status == RunStatus.COMPLETED:
            return self._result_from_checkpoint(cp)

        if cp.status != RunStatus.WAITING_CONFIRMATION:
            err = AgentError(
                code=AgentErrorCode.VALIDATION_FAILED,
                message=f"当前运行状态为 {cp.status.value}，无法执行确认写入",
            )
            return self._result_from_checkpoint(cp, error=err)

        if (
            cp.candidate_plan is not None
            and cp.candidate_plan.candidate_version != candidate_version
        ):
            err = AgentError(
                code=AgentErrorCode.VERSION_CONFLICT,
                message=(
                    f"候选版本已失效：期望 {cp.candidate_plan.candidate_version}，"
                    f"收到 {candidate_version}"
                ),
            )
            cp.error = err
            return self._result_from_checkpoint(cp, error=err)

        if cp.candidate_plan is not None:
            expired_tasks = find_expired_plan_tasks(cp.candidate_plan, self._clock())
            if expired_tasks:
                err = AgentError(
                    code=AgentErrorCode.DEADLINE_EXPIRED,
                    message=f"候选任务 {', '.join(expired_tasks)} 的官方截止时间已过，无法确认创建正式任务",
                )
                cp.status = RunStatus.FAILED
                cp.error = err
                return self._result_from_checkpoint(cp, error=err)

            critical_gaps = [
                g for g in cp.gaps if g.gap_type in CRITICAL_BASIS_GAP_TYPES
            ]
            unusable_sources = [
                s
                for s in cp.sources
                if s.source_status != "active"
                or s.auto_check_status in ("failed", "conflict")
                or s.is_repost
                or s.is_expired
                or s.roi_status in ("reposted", "expired", "ambiguous")
            ]
            if critical_gaps or unusable_sources:
                err = AgentError(
                    code=AgentErrorCode.VALIDATION_FAILED,
                    message="候选计划存在未解决的关键来源缺口或不可用来源，请先核对来源后再确认",
                )
                cp.error = err
                return self._result_from_checkpoint(cp, error=err)

        persistence = self._persistence
        assert persistence is not None
        target_plan_id = cp.persisted_plan_id
        binding = f"confirm:{target_plan_id}:{candidate_version}"

        try:
            resp, rec_write = self._gateway.invoke(
                tool_name="write_personal_tasks",
                user_id=cp.user_id,
                matter_id=cp.matter_id,
                expected_workspace_version=cp.workspace_version,
                operation_id=operation_id,
                idempotency_binding=binding,
                fn=lambda: persistence.confirm_candidate_plan(
                    target_plan_id,
                    operation_id=operation_id,
                ),
            )
        except GatewayError as exc:
            cp.error = exc.error
            backend_code = str(exc.error.details.get("backend_code", ""))
            if (
                exc.error.code != AgentErrorCode.TIMEOUT
                and backend_code not in _NON_TERMINAL_CONFIRM_ERRORS
            ):
                cp.status = RunStatus.FAILED
            return self._result_from_checkpoint(cp, error=exc.error)

        cp.execution_records.append(rec_write)
        cp.written_tasks = _parse_written_tasks(resp, cp.matter_id)
        cp.status = RunStatus.COMPLETED
        cp.error = None
        return self._result_from_checkpoint(cp)

    def reject_plan(
        self,
        run_id: str,
        *,
        operation_id: str | None = None,
        plan_id: str | None = None,
        user_id: str | None = None,
        matter_id: str | None = None,
        workspace_version: int | None = None,
    ) -> AgentRunResult:
        """Persist candidate rejection on the backend without creating tasks or altering completed runs."""
        with self._get_run_lock(run_id):
            return self._reject_plan_locked(
                run_id=run_id,
                operation_id=operation_id,
                plan_id=plan_id,
                user_id=user_id,
                matter_id=matter_id,
                workspace_version=workspace_version,
            )

    def _reject_plan_locked(
        self,
        *,
        run_id: str,
        operation_id: str | None = None,
        plan_id: str | None = None,
        user_id: str | None = None,
        matter_id: str | None = None,
        workspace_version: int | None = None,
    ) -> AgentRunResult:
        cp = self._resolve_or_recover_checkpoint(
            run_id=run_id,
            plan_id=plan_id,
            user_id=user_id,
            matter_id=matter_id,
            workspace_version=workspace_version,
        )
        if cp is None or cp.persisted_plan_id is None:
            err = AgentError(
                code=AgentErrorCode.VALIDATION_FAILED, message="运行或持久化计划不存在"
            )
            return AgentRunResult(run_id=run_id, status=RunStatus.FAILED, error=err)

        if user_id is not None and cp.user_id != user_id:
            err = AgentError(
                code=AgentErrorCode.PERMISSION_DENIED,
                message="无权操作其他用户的运行记录",
            )
            return AgentRunResult(run_id=run_id, status=RunStatus.FAILED, error=err)

        if cp.status == RunStatus.COMPLETED:
            err = AgentError(
                code=AgentErrorCode.VALIDATION_FAILED,
                message="候选计划已确认并生成正式任务，不能拒绝",
            )
            return self._result_from_checkpoint(cp, error=err)

        if cp.status == RunStatus.CANCELLED:
            return self._result_from_checkpoint(cp)

        if cp.status != RunStatus.WAITING_CONFIRMATION:
            err = AgentError(
                code=AgentErrorCode.VALIDATION_FAILED,
                message=f"当前运行状态为 {cp.status.value}，无法执行拒绝操作",
            )
            return self._result_from_checkpoint(cp, error=err)

        persistence = self._persistence
        assert persistence is not None
        op_id = operation_id or str(uuid4())
        target_plan_id = cp.persisted_plan_id
        binding = f"reject:{target_plan_id}"

        try:
            _, rec_reject = self._gateway.invoke(
                tool_name="reject_personal_plan",
                user_id=cp.user_id,
                matter_id=cp.matter_id,
                expected_workspace_version=cp.workspace_version,
                operation_id=op_id,
                idempotency_binding=binding,
                fn=lambda: persistence.reject_candidate_plan(
                    target_plan_id,
                    operation_id=op_id,
                ),
            )
        except GatewayError as exc:
            cp.error = exc.error
            if exc.error.code != AgentErrorCode.TIMEOUT:
                cp.status = RunStatus.FAILED
            return self._result_from_checkpoint(cp, error=exc.error)

        cp.execution_records.append(rec_reject)
        cp.status = RunStatus.CANCELLED
        cp.written_tasks = []
        cp.error = AgentError(
            code=AgentErrorCode.CANCELLED, message="用户已拒绝候选计划，未创建正式任务"
        )
        return self._result_from_checkpoint(cp)

    def cancel_run(
        self,
        run_id: str,
        *,
        user_id: str | None = None,
    ) -> AgentRunResult:
        """Cancel an active or waiting run without masking already-written tasks."""
        with self._get_run_lock(run_id):
            cp = self._checkpoints.get(run_id)
            if cp is None:
                err = AgentError(
                    code=AgentErrorCode.VALIDATION_FAILED, message="运行记录不存在"
                )
                return AgentRunResult(run_id=run_id, status=RunStatus.FAILED, error=err)

            if user_id is not None and cp.user_id != user_id:
                err = AgentError(
                    code=AgentErrorCode.PERMISSION_DENIED,
                    message="无权操作其他用户的运行记录",
                )
                return AgentRunResult(run_id=run_id, status=RunStatus.FAILED, error=err)

            if cp.status in (
                RunStatus.COMPLETED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
            ):
                return self._result_from_checkpoint(cp)

            cp.status = RunStatus.CANCELLED
            cp.error = AgentError(
                code=AgentErrorCode.CANCELLED, message="运行已被用户取消"
            )
            return self._result_from_checkpoint(cp)

    def _fetch_sources(self, context: RunContext) -> list[SourceDocument]:
        if context.scope_year is not None:
            return self._source_reader.fetch_sources(
                context.source_urls,
                context.goal,
                scope_year=context.scope_year,
            )
        return self._source_reader.fetch_sources(context.source_urls, context.goal)

    def _resolve_or_recover_checkpoint(
        self,
        *,
        run_id: str,
        plan_id: str | None,
        user_id: str | None,
        matter_id: str | None,
        workspace_version: int | None,
    ) -> RunCheckpoint | None:
        cp = self._checkpoints.get(run_id)
        if cp is not None:
            return cp

        target_plan_id = plan_id or run_id
        if self._persistence is None or not target_plan_id:
            return None

        try:
            plan_data = self._persistence.get_candidate_plan(target_plan_id)
        except (PersistenceApiError, KeyError, RuntimeError):
            return None

        resolved_matter_id = matter_id or str(plan_data.get("matter_id", ""))
        resolved_user_id = user_id or "demo-user"
        if not resolved_matter_id:
            return None

        resolved_ws_version = (
            workspace_version
            if workspace_version is not None
            else self._backend.get_workspace_version(resolved_matter_id)
        )
        backend_status = str(plan_data.get("status", "pending"))
        if backend_status == "confirmed":
            run_status = RunStatus.COMPLETED
        elif backend_status == "rejected":
            run_status = RunStatus.CANCELLED
        elif backend_status == "expired":
            run_status = RunStatus.FAILED
        else:
            run_status = RunStatus.WAITING_CONFIRMATION

        recovered = RunCheckpoint(
            run_id=run_id,
            user_id=resolved_user_id,
            matter_id=resolved_matter_id,
            workspace_version=resolved_ws_version,
            status=run_status,
            persisted_plan_id=str(plan_data.get("id", target_plan_id)),
            written_tasks=_parse_written_tasks(plan_data, resolved_matter_id),
        )
        self._checkpoints[run_id] = recovered
        return recovered

    def _persist_candidates(
        self,
        matter_id: str,
        requirements: list[ExtractedRequirement],
        evaluations: list[RequirementEvaluation],
        candidate_plan: CandidatePlan,
        sources_by_id: dict[str, SourceDocument],
        *,
        gaps: list[SourceGap] | None = None,
        operation_id: str | None = None,
    ) -> tuple[list[str], str | None]:
        assert self._persistence is not None
        build_client_item_id_map(candidate_plan.tasks)
        cache_key = (matter_id, operation_id) if operation_id else None
        if cache_key is not None and cache_key in self._persisted_req_cache:
            persisted_ids, req_id_map = self._persisted_req_cache[cache_key]
        else:
            req_payload = build_requirements_batch_payload(
                requirements, evaluations, sources_by_id, gaps
            )
            created_reqs = self._persistence.persist_requirements(
                matter_id, req_payload
            )
            req_id_map = {}
            persisted_ids = []
            for req_obj, created in zip(requirements, created_reqs, strict=False):
                created_id = created.get("id")
                if isinstance(created_id, str) and created_id:
                    req_id_map[req_obj.requirement_id] = created_id
                    persisted_ids.append(created_id)
            if cache_key is not None:
                self._persisted_req_cache[cache_key] = (persisted_ids, req_id_map)

        plan_payload = build_candidate_plan_create_payload(
            candidate_plan,
            sources_by_id,
            requirement_id_map=req_id_map,
        )
        plan_resp = self._persistence.persist_candidate_plan(matter_id, plan_payload)
        raw_plan_id = plan_resp.get("id")
        plan_id = str(raw_plan_id) if raw_plan_id is not None else None
        return persisted_ids, plan_id

    def _result_from_checkpoint(
        self,
        cp: RunCheckpoint,
        *,
        error: AgentError | None = None,
    ) -> AgentRunResult:
        return AgentRunResult(
            run_id=cp.run_id,
            status=cp.status,
            extracted_requirements=cp.extracted_requirements,
            evaluations=cp.evaluations,
            gaps=cp.gaps,
            scope_summary=cp.scope_summary,
            candidate_plan=cp.candidate_plan,
            persisted_requirement_ids=cp.persisted_requirement_ids,
            persisted_plan_id=cp.persisted_plan_id,
            written_tasks=cp.written_tasks,
            error=error if error is not None else cp.error,
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


def _parse_written_tasks(payload: dict[str, Any], matter_id: str) -> list[WrittenTask]:
    raw_tasks = payload.get("tasks")
    if not isinstance(raw_tasks, list):
        return []
    written: list[WrittenTask] = []
    for item in raw_tasks:
        if not isinstance(item, dict):
            continue
        raw_obligation = item.get("obligation_nature")
        obligation = (
            _API_OBLIGATION_TO_ENUM.get(
                str(raw_obligation), ObligationType.PENDING_VERIFICATION
            )
            if raw_obligation is not None
            else ObligationType.OFFICIAL_REQUIRED
        )
        written.append(
            WrittenTask(
                task_id=str(item.get("id") or item.get("task_id") or ""),
                matter_id=str(item.get("matter_id") or matter_id),
                title=str(item.get("title") or ""),
                obligation=obligation,
                official_deadline=item.get("official_deadline_at")
                or item.get("official_deadline"),
                suggested_date=item.get("suggested_date"),
                depends_on=[str(d) for d in item.get("depends_on", [])],
                evidence_required=str(item.get("evidence_required") or ""),
            )
        )
    return written


def _can_persist_uuids(
    requirements: list[ExtractedRequirement],
    plan: CandidatePlan,
    sources_by_id: dict[str, SourceDocument],
) -> bool:
    for req in requirements:
        for cite in req.basis:
            doc = sources_by_id.get(cite.source_version_id)
            sid = doc.source_id if doc else cite.source_id
            snap = doc.snapshot_id if doc else cite.snapshot_id
            if not _is_uuid(sid) or not _is_uuid(snap):
                return False
    for task in plan.tasks:
        for cite in task.basis:
            doc = sources_by_id.get(cite.source_version_id)
            sid = doc.source_id if doc else cite.source_id
            snap = doc.snapshot_id if doc else cite.snapshot_id
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
