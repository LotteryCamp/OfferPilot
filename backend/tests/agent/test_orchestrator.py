"""Tests for AgentOrchestrator lifecycle, ToolGateway enforcement, and failure handling."""

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
    RequirementEvaluation,
    RunContext,
    RunStatus,
    SourceCitation,
    SourceDocument,
    ToolGateway,
    WrittenTask,
)


class InMemorySourceReader:
    def __init__(self, docs: list[SourceDocument]) -> None:
        self._docs = docs

    def fetch_sources(self, urls: list[str], goal: str) -> list[SourceDocument]:
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

    def extract_requirements(self, goal: str, sources: list[SourceDocument]) -> list[ExtractedRequirement]:
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
                basis=[SourceCitation(source_version_id=sources[0].source_version_id, locator="第三条")],
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
    def __init__(self, *, workspace_version: int = 1, consent_valid: bool = True) -> None:
        self.workspace_version = workspace_version
        self.consent_valid = consent_valid
        self.written_tasks: list[WrittenTask] = []
        self.records: list[ExecutionRecord] = []
        self.write_calls = 0

    def check_permission(self, user_id: str, matter_id: str, auth_level: AuthLevel) -> bool:
        return user_id == "u1" and matter_id == "m1"

    def has_valid_transfer_consent(self, user_id: str, matter_id: str, consent_id: str | None) -> bool:
        return self.consent_valid and consent_id == "consent-1"

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
        self.write_calls += 1
        tasks = [
            WrittenTask(
                task_id=t.task_id,
                matter_id=matter_id,
                title=t.title,
                obligation=t.obligation,
                official_deadline=t.official_deadline,
                suggested_date=t.suggested_date,
                depends_on=t.depends_on,
                evidence_required=t.evidence_required,
            )
            for t in candidate_plan.tasks
        ]
        self.written_tasks.extend(tasks)
        return tasks

    def record_execution(self, matter_id: str, record: ExecutionRecord) -> None:
        self.records.append(record)


def _sample_doc() -> SourceDocument:
    return SourceDocument(
        source_version_id="src-2027-v1",
        title="夏令营招生简章",
        publisher="某大学计算机学院",
        content="申请者须提交个人陈述。",
    )


def _sample_req() -> ExtractedRequirement:
    return ExtractedRequirement(
        requirement_id="r1",
        title="提交个人陈述",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[SourceCitation(source_version_id="src-2027-v1", locator="第三条")],
        required_fact_keys=["major"],
    )


def test_happy_path_waits_for_confirmation_then_writes_idempotently() -> None:
    backend = InMemoryWorkspaceBackend(workspace_version=5)
    orch = AgentOrchestrator(
        source_reader=InMemorySourceReader([_sample_doc()]),
        model_adapter=InMemoryModelAdapter([_sample_req()]),
        backend=backend,
    )

    ctx = RunContext(
        user_id="u1",
        matter_id="m1",
        goal="整理夏令营申请计划",
        workspace_version=5,
        confirmed_facts={"major": "软件工程"},
        model_transfer_consent_id="consent-1",
    )

    start_res = orch.start_run(ctx)
    assert start_res.status == RunStatus.WAITING_CONFIRMATION
    assert start_res.candidate_plan is not None
    assert backend.written_tasks == []

    confirm_res = orch.confirm_plan(start_res.run_id, candidate_version=1, operation_id="op-001")
    assert confirm_res.status == RunStatus.COMPLETED
    assert len(confirm_res.written_tasks) == 1
    assert backend.write_calls == 1

    # Repeated confirmation returns same result without duplicating writes
    replay_res = orch.confirm_plan(start_res.run_id, candidate_version=1, operation_id="op-001")
    assert replay_res.status == RunStatus.COMPLETED
    assert len(replay_res.written_tasks) == 1
    assert backend.write_calls == 1


def test_reject_plan_creates_no_tasks() -> None:
    backend = InMemoryWorkspaceBackend(workspace_version=1)
    orch = AgentOrchestrator(
        source_reader=InMemorySourceReader([_sample_doc()]),
        model_adapter=InMemoryModelAdapter([_sample_req()]),
        backend=backend,
    )
    ctx = RunContext(
        user_id="u1",
        matter_id="m1",
        goal="整理夏令营申请计划",
        workspace_version=1,
        confirmed_facts={"major": "软件工程"},
        model_transfer_consent_id="consent-1",
    )
    res = orch.start_run(ctx)
    reject_res = orch.reject_plan(res.run_id)
    assert reject_res.status == RunStatus.CANCELLED
    assert backend.written_tasks == []


def test_version_change_before_confirmation_blocks_stale_write() -> None:
    backend = InMemoryWorkspaceBackend(workspace_version=1)
    orch = AgentOrchestrator(
        source_reader=InMemorySourceReader([_sample_doc()]),
        model_adapter=InMemoryModelAdapter([_sample_req()]),
        backend=backend,
    )
    ctx = RunContext(
        user_id="u1",
        matter_id="m1",
        goal="整理夏令营申请计划",
        workspace_version=1,
        confirmed_facts={"major": "软件工程"},
        model_transfer_consent_id="consent-1",
    )
    res = orch.start_run(ctx)
    backend.workspace_version = 2

    confirm_res = orch.confirm_plan(res.run_id, candidate_version=1, operation_id="op-002")
    assert confirm_res.status == RunStatus.FAILED
    assert confirm_res.error is not None
    assert confirm_res.error.code == AgentErrorCode.VERSION_CONFLICT
    assert backend.written_tasks == []


def test_missing_consent_or_model_timeout_reports_failure() -> None:
    backend = InMemoryWorkspaceBackend(workspace_version=1, consent_valid=False)
    orch = AgentOrchestrator(
        source_reader=InMemorySourceReader([_sample_doc()]),
        model_adapter=InMemoryModelAdapter([_sample_req()]),
        backend=backend,
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
        source_reader=InMemorySourceReader([_sample_doc()]),
        model_adapter=InMemoryModelAdapter([_sample_req()], fail_on_plan=True),
        backend=backend_ok,
    )
    res_timeout = orch_timeout.start_run(ctx.model_copy(update={"model_transfer_consent_id": "consent-1"}))
    assert res_timeout.status == RunStatus.FAILED
    assert res_timeout.error is not None
    assert res_timeout.error.code == AgentErrorCode.TIMEOUT


def test_gateway_blocks_unlisted_tool() -> None:
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
