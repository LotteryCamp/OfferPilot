"""Tests for AgentOrchestrator lifecycle, ToolGateway enforcement, and failure handling."""

from __future__ import annotations

from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.agent import (
    AgentErrorCode,
    AgentOrchestrator,
    AuthLevel,
    CandidatePlan,
    CandidateTask,
    ExecutionRecord,
    ExtractedRequirement,
    GatewayError,
    ObligationType,
    PersistenceApiError,
    RequirementEvaluation,
    RunContext,
    RunStatus,
    SourceCitation,
    SourceDocument,
    ToolGateway,
    WrittenTask,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")


class InMemorySourceReader:
    def __init__(self, docs: list[SourceDocument]) -> None:
        self._docs = docs
        self.last_scope_year: int | None = None

    def fetch_sources(
        self,
        urls: list[str],
        goal: str,
        *,
        scope_year: int | None = None,
    ) -> list[SourceDocument]:
        self.last_scope_year = scope_year
        return list(self._docs)


class InMemoryModelAdapter:
    def __init__(
        self,
        requirements: list[ExtractedRequirement],
        *,
        fail_on_plan: bool = False,
        cycle_plan: bool = False,
    ) -> None:
        self._requirements = requirements
        self._fail_on_plan = fail_on_plan
        self._cycle_plan = cycle_plan

    def extract_requirements(
        self, goal: str, sources: list[SourceDocument]
    ) -> list[ExtractedRequirement]:
        return list(self._requirements)

    def generate_candidate_plan(
        self,
        context: RunContext,
        sources: list[SourceDocument],
        evaluations: list[RequirementEvaluation],
    ) -> CandidatePlan:
        if self._fail_on_plan:
            raise TimeoutError("模型响应超时")

        tasks = [
            CandidateTask(
                task_id="t1",
                title="准备个人陈述",
                basis=[
                    SourceCitation(
                        source_version_id=sources[0].source_version_id, locator="第三条"
                    )
                ],
                obligation=ObligationType.OFFICIAL_REQUIRED,
                depends_on=["t1"] if self._cycle_plan else [],
                evidence_required="导出的 DOCX 副本",
            )
        ]
        return CandidatePlan(
            candidate_id="cand-1",
            workspace_version=context.workspace_version,
            candidate_version=1,
            input_snapshot_id="snap-1",
            tasks=tasks,
        )


class InMemoryWorkspaceBackend:
    def __init__(
        self, *, workspace_version: int = 1, consent_valid: bool = True
    ) -> None:
        self.workspace_version = workspace_version
        self.consent_valid = consent_valid
        self.records: list[ExecutionRecord] = []

    def check_permission(
        self, user_id: str, matter_id: str, auth_level: AuthLevel
    ) -> bool:
        return user_id == "u1" and matter_id == "m1"

    def has_valid_transfer_consent(
        self,
        user_id: str,
        *,
        purpose: str,
        field_categories: tuple[str, ...],
    ) -> bool:
        return self.consent_valid

    def get_workspace_version(self, matter_id: str) -> int:
        return self.workspace_version

    def consume_candidate_and_write_tasks(
        self,
        user_id: str,
        matter_id: str,
        candidate_plan: CandidatePlan,
        expected_workspace_version: int,
        operation_id: str,
    ) -> list[WrittenTask]:
        return []

    def record_execution(self, matter_id: str, record: ExecutionRecord) -> None:
        self.records.append(record)


class InMemoryCandidatePersistence:
    def __init__(self, *, fail_first_confirm_timeout: bool = False) -> None:
        self.plans: dict[str, dict[str, Any]] = {}
        self.decisions: dict[str, str] = {}
        self.write_calls = 0
        self.fail_first_confirm_timeout = fail_first_confirm_timeout
        self._confirm_attempts = 0

    def persist_requirements(
        self, matter_id: str, payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return [{"id": str(uuid4()), **item} for item in payload["requirements"]]

    def persist_candidate_plan(
        self, matter_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        plan_id = str(uuid4())
        plan = {
            "id": plan_id,
            "matter_id": matter_id,
            "status": "pending",
            "items": payload["items"],
            "tasks": [],
        }
        self.plans[plan_id] = plan
        return plan

    def get_candidate_plan(self, plan_id: str) -> dict[str, Any]:
        if plan_id not in self.plans:
            raise PersistenceApiError(
                404, "plan_not_found", error_code="plan_not_found"
            )
        return self.plans[plan_id]

    def confirm_candidate_plan(
        self, plan_id: str, *, operation_id: str
    ) -> dict[str, Any]:
        self._confirm_attempts += 1
        if self.fail_first_confirm_timeout and self._confirm_attempts == 1:
            raise PersistenceApiError(
                503,
                "请求超时",
                error_code="connection_uncertain",
                retryable=True,
            )

        plan = self.plans[plan_id]
        if operation_id in self.decisions:
            return {
                "plan_id": plan_id,
                "status": plan["status"],
                "decision": self.decisions[operation_id],
                "tasks": plan["tasks"],
                "replayed": True,
            }
        if plan["status"] != "pending":
            raise PersistenceApiError(
                409,
                "候选计划已有终态决定",
                error_code="plan_already_decided",
            )

        self.write_calls += 1
        tasks = [
            {
                "id": str(uuid4()),
                "matter_id": plan["matter_id"],
                "title": item["title"],
                "obligation_nature": item["obligation_nature"],
                "evidence_required": "已确认" if item.get("evidence_required") else "",
            }
            for item in plan["items"]
        ]
        plan["status"] = "confirmed"
        plan["tasks"] = tasks
        self.decisions[operation_id] = "confirmed"
        return {
            "plan_id": plan_id,
            "status": "confirmed",
            "decision": "confirmed",
            "tasks": tasks,
            "replayed": False,
        }

    def reject_candidate_plan(
        self, plan_id: str, *, operation_id: str
    ) -> dict[str, Any]:
        plan = self.plans[plan_id]
        if plan["status"] != "pending":
            raise PersistenceApiError(
                409,
                "候选计划已有终态决定",
                error_code="plan_already_decided",
            )
        plan["status"] = "rejected"
        self.decisions[operation_id] = "rejected"
        return {
            "plan_id": plan_id,
            "status": "rejected",
            "decision": "rejected",
            "tasks": [],
            "replayed": False,
        }


_SRC_ID = "b0000000-0000-4000-8000-000000000101"
_SNAP_ID = "b0000000-0000-4000-8000-000000000102"


def _sample_doc() -> SourceDocument:
    return SourceDocument(
        source_version_id=_SNAP_ID,
        source_id=_SRC_ID,
        snapshot_id=_SNAP_ID,
        title="夏令营招生简章",
        publisher="某大学计算机学院",
        content="申请者须提交个人陈述。",
    )


def _sample_req() -> ExtractedRequirement:
    return ExtractedRequirement(
        requirement_id="r1",
        title="提交个人陈述",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[SourceCitation(source_version_id=_SNAP_ID, locator="第三条")],
        required_fact_keys=["major"],
    )


def test_happy_path_waits_for_confirmation_then_writes_idempotently() -> None:
    backend = InMemoryWorkspaceBackend(workspace_version=5)
    persistence = InMemoryCandidatePersistence()
    orch = AgentOrchestrator(
        timezone=SHANGHAI,
        source_reader=InMemorySourceReader([_sample_doc()]),
        model_adapter=InMemoryModelAdapter([_sample_req()]),
        backend=backend,
        persistence=persistence,
    )

    ctx = RunContext(
        user_id="u1",
        matter_id="m1",
        goal="整理夏令营申请计划",
        workspace_version=5,
        confirmed_facts={"major": "软件工程"},
    )

    start_res = orch.start_run(ctx)
    assert start_res.status == RunStatus.WAITING_CONFIRMATION
    assert start_res.persisted_plan_id is not None
    assert persistence.write_calls == 0

    confirm_res = orch.confirm_plan(
        start_res.run_id, candidate_version=1, operation_id="op-001"
    )
    assert confirm_res.status == RunStatus.COMPLETED
    assert len(confirm_res.written_tasks) == 1
    assert persistence.write_calls == 1

    # Repeated confirmation returns same result without duplicating writes
    replay_res = orch.confirm_plan(
        start_res.run_id, candidate_version=1, operation_id="op-001"
    )
    assert replay_res.status == RunStatus.COMPLETED
    assert len(replay_res.written_tasks) == 1
    assert persistence.write_calls == 1


def test_reject_plan_persists_rejected_and_cannot_override_completed() -> None:
    backend = InMemoryWorkspaceBackend(workspace_version=1)
    persistence = InMemoryCandidatePersistence()
    orch = AgentOrchestrator(
        timezone=SHANGHAI,
        source_reader=InMemorySourceReader([_sample_doc()]),
        model_adapter=InMemoryModelAdapter([_sample_req()]),
        backend=backend,
        persistence=persistence,
    )
    ctx = RunContext(
        user_id="u1",
        matter_id="m1",
        goal="整理夏令营申请计划",
        workspace_version=1,
        confirmed_facts={"major": "软件工程"},
    )
    res = orch.start_run(ctx)
    assert res.persisted_plan_id is not None
    reject_res = orch.reject_plan(res.run_id, operation_id="op-reject-1")
    assert reject_res.status == RunStatus.CANCELLED
    assert persistence.get_candidate_plan(res.persisted_plan_id)["status"] == "rejected"
    assert persistence.write_calls == 0

    # Completed run cannot be rejected or lose its tasks
    res2 = orch.start_run(ctx)
    orch.confirm_plan(res2.run_id, candidate_version=1, operation_id="op-confirm-2")
    bad_reject = orch.reject_plan(res2.run_id, operation_id="op-reject-2")
    assert bad_reject.status == RunStatus.COMPLETED
    assert len(bad_reject.written_tasks) == 1
    assert bad_reject.error is not None
    assert bad_reject.error.code == AgentErrorCode.VALIDATION_FAILED


def test_confirm_timeout_allows_retry_and_version_conflict_blocks() -> None:
    backend = InMemoryWorkspaceBackend(workspace_version=1)
    persistence = InMemoryCandidatePersistence(fail_first_confirm_timeout=True)
    orch = AgentOrchestrator(
        timezone=SHANGHAI,
        source_reader=InMemorySourceReader([_sample_doc()]),
        model_adapter=InMemoryModelAdapter([_sample_req()]),
        backend=backend,
        persistence=persistence,
    )
    ctx = RunContext(
        user_id="u1",
        matter_id="m1",
        goal="整理夏令营申请计划",
        workspace_version=1,
        confirmed_facts={"major": "软件工程"},
    )
    res = orch.start_run(ctx)

    # First confirm times out -> remains WAITING_CONFIRMATION so retry with same operation_id works
    first_try = orch.confirm_plan(
        res.run_id, candidate_version=1, operation_id="op-retry-1"
    )
    assert first_try.status == RunStatus.WAITING_CONFIRMATION
    assert first_try.error is not None
    assert first_try.error.code == AgentErrorCode.TIMEOUT

    retry_ok = orch.confirm_plan(
        res.run_id, candidate_version=1, operation_id="op-retry-1"
    )
    assert retry_ok.status == RunStatus.COMPLETED
    assert len(retry_ok.written_tasks) == 1

    # Version change before confirmation blocks stale write
    res_stale = orch.start_run(ctx)
    backend.workspace_version = 2
    stale_res = orch.confirm_plan(
        res_stale.run_id, candidate_version=1, operation_id="op-stale-1"
    )
    assert stale_res.status == RunStatus.FAILED
    assert stale_res.error is not None
    assert stale_res.error.code == AgentErrorCode.VERSION_CONFLICT


def test_cold_start_recovery_and_missing_persistence_guard() -> None:
    backend = InMemoryWorkspaceBackend(workspace_version=1)
    orch_no_persist = AgentOrchestrator(
        timezone=SHANGHAI,
        source_reader=InMemorySourceReader([_sample_doc()]),
        model_adapter=InMemoryModelAdapter([_sample_req()]),
        backend=backend,
    )
    ctx = RunContext(
        user_id="u1",
        matter_id="m1",
        goal="测试缺少持久化",
        workspace_version=1,
        confirmed_facts={"major": "软件工程"},
    )
    fail_res = orch_no_persist.start_run(ctx)
    assert fail_res.status == RunStatus.FAILED
    assert fail_res.error is not None
    assert fail_res.error.code == AgentErrorCode.VALIDATION_FAILED

    persistence = InMemoryCandidatePersistence()
    orch1 = AgentOrchestrator(
        timezone=SHANGHAI,
        source_reader=InMemorySourceReader([_sample_doc()]),
        model_adapter=InMemoryModelAdapter([_sample_req()]),
        backend=backend,
        persistence=persistence,
    )
    start_res = orch1.start_run(ctx)
    plan_id = start_res.persisted_plan_id
    assert plan_id is not None

    # Simulate process restart with a fresh orchestrator instance
    orch2 = AgentOrchestrator(
        timezone=SHANGHAI,
        source_reader=InMemorySourceReader([_sample_doc()]),
        model_adapter=InMemoryModelAdapter([_sample_req()]),
        backend=backend,
        persistence=persistence,
    )
    loaded = orch2.get_persisted_plan(plan_id)
    assert loaded["status"] == "pending"
    confirmed = orch2.confirm_plan(
        plan_id,
        candidate_version=1,
        operation_id="op-recover-1",
        user_id="u1",
        matter_id="m1",
        workspace_version=1,
    )
    assert confirmed.status == RunStatus.COMPLETED
    assert len(confirmed.written_tasks) == 1


def test_missing_consent_or_model_timeout_reports_failure() -> None:
    backend = InMemoryWorkspaceBackend(workspace_version=1, consent_valid=False)
    orch = AgentOrchestrator(
        timezone=SHANGHAI,
        source_reader=InMemorySourceReader([_sample_doc()]),
        model_adapter=InMemoryModelAdapter([_sample_req()]),
        backend=backend,
        persistence=InMemoryCandidatePersistence(),
    )
    ctx = RunContext(
        user_id="u1",
        matter_id="m1",
        goal="整理夏令营申请计划",
        workspace_version=1,
        confirmed_facts={"major": "软件工程"},
    )
    res_no_consent = orch.start_run(ctx)
    assert res_no_consent.status == RunStatus.FAILED
    assert res_no_consent.error is not None
    assert res_no_consent.error.code == AgentErrorCode.CONSENT_REQUIRED_OR_REVOKED

    backend_ok = InMemoryWorkspaceBackend(workspace_version=1, consent_valid=True)
    orch_timeout = AgentOrchestrator(
        timezone=SHANGHAI,
        source_reader=InMemorySourceReader([_sample_doc()]),
        model_adapter=InMemoryModelAdapter([_sample_req()], fail_on_plan=True),
        backend=backend_ok,
        persistence=InMemoryCandidatePersistence(),
    )
    res_timeout = orch_timeout.start_run(ctx)
    assert res_timeout.status == RunStatus.FAILED
    assert res_timeout.error is not None
    assert res_timeout.error.code == AgentErrorCode.TIMEOUT


def test_gateway_blocks_unlisted_tool_and_cross_scope_idempotency() -> None:
    backend = InMemoryWorkspaceBackend(workspace_version=1)
    gateway = ToolGateway(backend)
    try:
        gateway.invoke(
            tool_name="auto_submit_official_portal",
            user_id="u1",
            matter_id="m1",
            expected_workspace_version=1,
            fn=lambda: None,
        )
        raise AssertionError("Expected GatewayError")
    except GatewayError as exc:
        assert exc.error.code == AgentErrorCode.TOOL_NOT_ALLOWED

    # First write succeeds and advances workspace version -> retry with same op_id still replays
    res1, _ = gateway.invoke(
        tool_name="write_personal_tasks",
        user_id="u1",
        matter_id="m1",
        expected_workspace_version=1,
        operation_id="op-shared",
        idempotency_binding="confirm:plan-1",
        fn=lambda: ["task-1"],
    )
    assert res1 == ["task-1"]
    backend.workspace_version = 2

    res_replay, rec_replay = gateway.invoke(
        tool_name="write_personal_tasks",
        user_id="u1",
        matter_id="m1",
        expected_workspace_version=1,
        operation_id="op-shared",
        idempotency_binding="confirm:plan-1",
        fn=lambda: ["should-not-run"],
    )
    assert res_replay == ["task-1"]
    assert rec_replay.output_summary.get("idempotent_replay") is True

    # Reusing same operation_id across another matter/action is rejected
    try:
        gateway.invoke(
            tool_name="reject_personal_plan",
            user_id="u1",
            matter_id="m1",
            expected_workspace_version=2,
            operation_id="op-shared",
            idempotency_binding="reject:plan-1",
            fn=lambda: None,
        )
        raise AssertionError("Expected GatewayError")
    except GatewayError as exc:
        assert exc.error.code == AgentErrorCode.VALIDATION_FAILED


def test_ownership_consent_retry_and_recorder_resilience() -> None:
    backend = InMemoryWorkspaceBackend(workspace_version=1, consent_valid=False)
    persistence = InMemoryCandidatePersistence()
    orch = AgentOrchestrator(
        timezone=SHANGHAI,
        source_reader=InMemorySourceReader([_sample_doc()]),
        model_adapter=InMemoryModelAdapter([_sample_req()]),
        backend=backend,
        persistence=persistence,
    )

    # scope_attrs without confirmed_facts still requires transfer consent
    no_consent_res = orch.start_run(
        RunContext(
            user_id="u1",
            matter_id="m1",
            goal="整理计划",
            workspace_version=1,
            scope_attrs={"school": "福州大学"},
        )
    )
    assert no_consent_res.status == RunStatus.FAILED
    assert no_consent_res.error is not None
    assert no_consent_res.error.code == AgentErrorCode.CONSENT_REQUIRED_OR_REVOKED

    backend.consent_valid = True

    # Revoking consent after model call blocks saving candidate artifacts
    class RevokingModelAdapter(InMemoryModelAdapter):
        def generate_candidate_plan(self, context, sources, evaluations):
            backend.consent_valid = False
            return super().generate_candidate_plan(context, sources, evaluations)

    orch_revoke = AgentOrchestrator(
        timezone=SHANGHAI,
        source_reader=InMemorySourceReader([_sample_doc()]),
        model_adapter=RevokingModelAdapter([_sample_req()]),
        backend=backend,
        persistence=persistence,
    )
    revoked_res = orch_revoke.start_run(
        RunContext(
            user_id="u1",
            matter_id="m1",
            goal="整理计划",
            workspace_version=1,
            confirmed_facts={"major": "软件工程"},
        )
    )
    assert revoked_res.status == RunStatus.FAILED
    assert revoked_res.error is not None
    assert revoked_res.error.code == AgentErrorCode.CONSENT_REQUIRED_OR_REVOKED

    # Re-enable consent for ownership & run idempotency tests
    backend.consent_valid = True
    ctx_op = RunContext(
        user_id="u1",
        matter_id="m1",
        goal="整理计划",
        workspace_version=1,
        confirmed_facts={"major": "软件工程"},
        operation_id="run-op-1",
    )
    r1 = orch.start_run(ctx_op)
    r2 = orch.start_run(ctx_op)
    assert r1.run_id == r2.run_id
    assert r1.persisted_plan_id == r2.persisted_plan_id

    # Caller ownership checks
    assert orch.get_checkpoint(r1.run_id, caller_user_id="u2") is None
    assert orch.get_checkpoint(r1.run_id, caller_user_id="u1") is not None
    bad_confirm = orch.confirm_plan(
        r1.run_id,
        candidate_version=1,
        operation_id="op-own-1",
        user_id="u2",
    )
    assert bad_confirm.status == RunStatus.FAILED
    assert bad_confirm.error is not None
    assert bad_confirm.error.code == AgentErrorCode.PERMISSION_DENIED

    # Recorder failure does not hide committed tasks
    def failing_record_execution(matter_id: str, record: ExecutionRecord) -> None:
        raise RuntimeError("audit db down")

    backend.record_execution = failing_record_execution  # type: ignore[method-assign]
    ok_confirm = orch.confirm_plan(
        r1.run_id,
        candidate_version=1,
        operation_id="op-own-2",
        user_id="u1",
    )
    assert ok_confirm.status == RunStatus.COMPLETED
    assert len(ok_confirm.written_tasks) == 1


def test_gateway_requires_valid_transfer_consent_when_required() -> None:
    class ToggleConsentBackend(InMemoryWorkspaceBackend):
        def __init__(self) -> None:
            super().__init__(workspace_version=1, consent_valid=False)
            self.consent_calls = 0

        def has_valid_transfer_consent(
            self,
            user_id: str,
            *,
            purpose: str,
            field_categories: tuple[str, ...],
        ) -> bool:
            self.consent_calls += 1
            return self.consent_valid

    backend = ToggleConsentBackend()
    gateway = ToolGateway(backend)

    try:
        gateway.invoke(
            tool_name="extract_requirements",
            user_id="u1",
            matter_id="m1",
            expected_workspace_version=1,
            requires_transfer_consent=True,
            fn=list,
        )
        raise AssertionError("Expected GatewayError")
    except GatewayError as exc:
        assert exc.error.code == AgentErrorCode.CONSENT_REQUIRED_OR_REVOKED
    assert backend.consent_calls == 1

    backend.consent_valid = True
    result, record = gateway.invoke(
        tool_name="extract_requirements",
        user_id="u1",
        matter_id="m1",
        expected_workspace_version=1,
        requires_transfer_consent=True,
        fn=list,
    )
    assert result == []
    assert record.succeeded is True
    assert backend.consent_calls == 2


def test_cancelled_before_persist_leaves_no_candidate() -> None:
    class CancelAfterPlanModel(InMemoryModelAdapter):
        def __init__(self, requirements: list[ExtractedRequirement]) -> None:
            super().__init__(requirements)
            self.cancelled = False

        def generate_candidate_plan(
            self,
            context: RunContext,
            sources: list[SourceDocument],
            evaluations: list[RequirementEvaluation],
        ) -> CandidatePlan:
            plan = super().generate_candidate_plan(context, sources, evaluations)
            self.cancelled = True
            return plan

    backend = InMemoryWorkspaceBackend(workspace_version=1)
    persistence = InMemoryCandidatePersistence()
    model = CancelAfterPlanModel([_sample_req()])
    orch = AgentOrchestrator(
        timezone=SHANGHAI,
        source_reader=InMemorySourceReader([_sample_doc()]),
        model_adapter=model,
        backend=backend,
        persistence=persistence,
        is_cancelled=lambda: model.cancelled,
    )
    ctx = RunContext(
        user_id="u1",
        matter_id="m1",
        goal="整理夏令营申请计划",
        workspace_version=1,
        confirmed_facts={"major": "软件工程"},
    )

    res = orch.start_run(ctx)
    assert res.status == RunStatus.CANCELLED
    assert res.error is not None
    assert res.error.code == AgentErrorCode.CANCELLED
    assert res.persisted_plan_id is None
    assert persistence.plans == {}


def test_cancelled_after_persist_returns_artifacts_for_cleanup() -> None:
    backend = InMemoryWorkspaceBackend(workspace_version=1)
    persistence = InMemoryCandidatePersistence()
    orch = AgentOrchestrator(
        timezone=SHANGHAI,
        source_reader=InMemorySourceReader([_sample_doc()]),
        model_adapter=InMemoryModelAdapter([_sample_req()]),
        backend=backend,
        persistence=persistence,
        is_cancelled=lambda: bool(persistence.plans),
    )
    ctx = RunContext(
        user_id="u1",
        matter_id="m1",
        goal="整理夏令营申请计划",
        workspace_version=1,
        confirmed_facts={"major": "软件工程"},
    )

    res = orch.start_run(ctx)
    assert res.status == RunStatus.CANCELLED
    assert res.error is not None
    assert res.error.code == AgentErrorCode.CANCELLED
    plan_id = res.persisted_plan_id
    assert plan_id is not None
    assert res.persisted_requirement_ids
    assert persistence.get_candidate_plan(plan_id)["status"] == "pending"
    assert persistence.write_calls == 0
