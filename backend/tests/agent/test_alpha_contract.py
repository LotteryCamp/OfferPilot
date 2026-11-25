"""End-to-end Alpha contract, fixed-fixture replay, teammate bridge, and regression tests."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel

from backend.agent import (
    SHANGHAI,
    AgentErrorCode,
    AgentOrchestrator,
    AuthLevel,
    CandidatePlan,
    CandidatePlanDraftPayload,
    CandidateTask,
    CandidateTaskDraft,
    EvaluationStatus,
    ExecutionRecord,
    ExtractedRequirement,
    ExtractedRequirementDraft,
    ObligationType,
    PersistenceApiError,
    PublicHtmlSourceReader,
    RequirementExtractionPayload,
    RunContext,
    RunStatus,
    SourceCitation,
    SourceDocument,
    SourceFragmentRecord,
    SourceGap,
    SourceReadUnavailableError,
    StructuredModelAdapter,
    WrittenTask,
    build_candidate_plan_create_payload,
    build_requirements_batch_payload,
    evaluate_requirements,
    find_expired_plan_tasks,
    source_document_from_backend_record,
    source_document_from_public_result,
)
from backend.schemas import CandidatePlanCreate

FX_S4_EXCERPT = (
    "（5）符合推荐条件的学生，由本人自愿向学院提出申请，并于2026年9月10日下午15:00前提交"
    "《推荐免试攻读研究生资格申请表》以及相应科研成果和学科竞赛等奖项证明材料及成绩单"
    "（符合推免条件但放弃的同学需要提供放弃推免资格承诺书，本人签字按手印）。"
)
FX_S4_SHA256 = "34599dc85bf72ca19837918f55c7cd275b9505bde994bbbea898ac7fa7b3abea"

FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_.]{1,63}$")


class SimulatedModelError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


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
        return True

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


class InMemoryPersistence:
    def __init__(self, *, clock_fn: Any = None) -> None:
        self.requirement_payloads: list[dict[str, Any]] = []
        self.plan_payloads: list[dict[str, Any]] = []
        self.plans: dict[str, dict[str, Any]] = {}
        self.written_tasks: list[dict[str, Any]] = []
        self._clock_fn = clock_fn

    def persist_requirements(
        self, matter_id: str, payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        self.requirement_payloads.append(payload)
        return [{"id": str(uuid4()), **item} for item in payload["requirements"]]

    def persist_candidate_plan(
        self, matter_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.plan_payloads.append(payload)
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
        return self.plans[plan_id]

    def confirm_candidate_plan(
        self, plan_id: str, *, operation_id: str
    ) -> dict[str, Any]:
        plan = self.plans[plan_id]
        if self._clock_fn is not None:
            now: datetime = self._clock_fn()
            for item in plan["items"]:
                raw_at = item.get("official_deadline_at")
                if raw_at and datetime.fromisoformat(raw_at) < now:
                    raise PersistenceApiError(
                        409,
                        "候选计划包含已过的官方期限",
                        error_code="official_deadline_passed",
                    )
        tasks = [
            {"id": str(uuid4()), "matter_id": plan["matter_id"], "title": item["title"]}
            for item in plan["items"]
        ]
        plan["status"] = "confirmed"
        plan["tasks"] = tasks
        self.written_tasks.extend(tasks)
        return {"plan_id": plan_id, "status": "confirmed", "tasks": tasks}

    def reject_candidate_plan(
        self, plan_id: str, *, operation_id: str
    ) -> dict[str, Any]:
        plan = self.plans[plan_id]
        plan["status"] = "rejected"
        return {"plan_id": plan_id, "status": "rejected", "tasks": []}


def test_fx_s4_fixed_replay_a04_a05_a10_and_expiry() -> None:
    assert hashlib.sha256(FX_S4_EXCERPT.encode("utf-8")).hexdigest() == FX_S4_SHA256

    source_uuid = "b0000000-0000-4000-8000-000000000001"
    snapshot_uuid = "b0000000-0000-4000-8000-000000000002"
    matter_uuid = "a0000000-0000-4000-8000-000000000001"
    user_uuid = "00000000-0000-7000-8000-000000000001"

    doc = SourceDocument(
        source_version_id=snapshot_uuid,
        source_id=source_uuid,
        snapshot_id=snapshot_uuid,
        title="福州大学数学与统计学院2027年推荐优秀应届本科毕业生免试攻读研究生的工作方案",
        publisher="福州大学数学与统计学院",
        url="https://math.fzu.edu.cn/info/1171/10393.htm",
        year=2027,
        scope="2027 届、本院、校内推免推荐",
        published_date=date(2026, 9, 8),
        content=FX_S4_EXCERPT,
        content_hash=FX_S4_SHA256,
        fragments=[
            SourceFragmentRecord(
                locator_kind="section", locator="第（5）项", quote=FX_S4_EXCERPT
            ),
            SourceFragmentRecord(
                locator_kind="section",
                locator="第（5）项括号补充",
                quote="符合推免条件但放弃的同学需要提供放弃推免资格承诺书，本人签字按手印",
            ),
        ],
    )

    def replay_call_model[T: BaseModel](
        instruction: str,
        text: str,
        response_model: type[T],
    ) -> T:
        if response_model is RequirementExtractionPayload:
            payload = RequirementExtractionPayload(
                requirements=[
                    ExtractedRequirementDraft(
                        requirement_id="GR-02",
                        title="向学院提交申请材料截止",
                        obligation=ObligationType.OFFICIAL_REQUIRED,
                        field_key="application.deadline",
                        scope="2027 届、福州大学数学与统计学院、校内推荐申请",
                        value_text="2026-09-10T15:00:00+08:00",
                        value_type="text",
                        confidence=0.95,
                        basis=[
                            SourceCitation(
                                source_version_id=snapshot_uuid,
                                locator="第（5）项",
                                excerpt="于2026年9月10日下午15:00前提交",
                            )
                        ],
                        official_deadline=datetime(2026, 9, 10, 15, 0, tzinfo=SHANGHAI),
                        required_fact_keys=["submitted_at"],
                        rule_kind="fixed_deadline",
                        rule_parameters={
                            "before": "2026-09-10T15:00:00+08:00",
                            "operator": "<",
                            "fact": "submitted_at",
                        },
                    ),
                    ExtractedRequirementDraft(
                        requirement_id="GR-03-WAIVER",
                        title="放弃推免资格承诺书（条件适用）",
                        obligation=ObligationType.OPTIONAL,
                        field_key="waiver.commitment",
                        scope="仅限符合推免条件但放弃推免资格的同学",
                        basis=[
                            SourceCitation(
                                source_version_id=snapshot_uuid,
                                locator="第（5）项括号补充",
                                excerpt="符合推免条件但放弃的同学需要提供放弃推免资格承诺书",
                            )
                        ],
                        is_ambiguous=False,
                    ),
                ],
                gaps=[
                    SourceGap(
                        gap_type="missing_basis",
                        description="缺少校招考〔2026〕2号与福大招考〔2022〕5号上位文件及成绩排名，不能判定完整推荐资格",
                        source_version_id=snapshot_uuid,
                        locator="第（3）项",
                    )
                ],
                scope_summary={
                    "intake_year": 2027,
                    "school": "福州大学",
                    "college": "数学与统计学院",
                    "stage": "校内推免推荐",
                },
            )
            return response_model.model_validate(payload.model_dump())

        plan_payload = CandidatePlanDraftPayload(
            tasks=[
                CandidateTaskDraft(
                    task_id="T-01",
                    title="准备并提交《推荐免试攻读研究生资格申请表》、奖项证明及成绩单",
                    requirement_id="GR-02",
                    basis=[
                        SourceCitation(
                            source_version_id=snapshot_uuid,
                            locator="第（5）项",
                            excerpt=FX_S4_EXCERPT,
                        )
                    ],
                    obligation=ObligationType.OFFICIAL_REQUIRED,
                    official_deadline_at=datetime(2026, 9, 10, 15, 0, tzinfo=SHANGHAI),
                    suggested_date=date(2026, 9, 9),
                    depends_on=[],
                    evidence_required="已准备申请表、科研/竞赛证明与成绩单",
                ),
                CandidateTaskDraft(
                    task_id="T-02",
                    title="如放弃推免资格，准备手印签字放弃承诺书",
                    requirement_id="GR-03-WAIVER",
                    basis=[
                        SourceCitation(
                            source_version_id=snapshot_uuid,
                            locator="第（5）项括号补充",
                            excerpt="符合推免条件但放弃的同学需要提供放弃推免资格承诺书",
                        )
                    ],
                    obligation=ObligationType.OPTIONAL,
                    official_deadline_date=date(2026, 9, 10),
                    official_deadline_at=None,
                    suggested_date=date(2026, 9, 9),
                    depends_on=[],
                    evidence_required="本人签字按手印承诺书",
                ),
            ]
        )
        return response_model.model_validate(plan_payload.model_dump())

    backend = InMemoryWorkspaceBackend(workspace_version=1)
    replay_clock = datetime(2026, 9, 9, 9, 0, tzinfo=SHANGHAI)
    prod_clock = datetime(2026, 11, 18, 8, 0, tzinfo=SHANGHAI)
    current_clock = [replay_clock]
    persistence = InMemoryPersistence(clock_fn=lambda: current_clock[0])

    orch = AgentOrchestrator(
        source_reader=PublicHtmlSourceReader(preloaded_sources=[doc]),
        model_adapter=StructuredModelAdapter(replay_call_model),
        backend=backend,
        persistence=persistence,
        clock=lambda: current_clock[0],
    )

    ctx = RunContext(
        user_id=user_uuid,
        matter_id=matter_uuid,
        goal="梳理福州大学数统学院2027届校内推免材料",
        workspace_version=1,
        scope_year=2027,
        scope_attrs={"school": "福州大学", "college": "数学与统计学院"},
        confirmed_facts={"paper_transcript": True},
        as_of=replay_clock,
    )

    result = orch.start_run(ctx)
    assert result.status == RunStatus.WAITING_CONFIRMATION
    assert persistence.written_tasks == []
    assert result.persisted_plan_id is not None
    assert len(result.persisted_requirement_ids) == 2
    assert any(g.gap_type == "missing_personal_fact" for g in result.gaps)
    assert result.candidate_plan is not None

    # A-10: timestamp vs date-only preservation
    t1, t2 = result.candidate_plan.tasks
    assert t1.official_deadline_at == datetime(2026, 9, 10, 15, 0, tzinfo=SHANGHAI)
    assert t1.official_deadline_date == date(2026, 9, 10)
    assert t2.official_deadline_at is None
    assert t2.official_deadline_date == date(2026, 9, 10)

    # Verify PR #41 persisted payloads preserve evidence_required description in detail
    assert len(persistence.requirement_payloads) == 1
    assert len(persistence.plan_payloads) == 1
    req_batch = persistence.requirement_payloads[0]["requirements"]
    assert all(FIELD_KEY_RE.fullmatch(item["field_key"]) for item in req_batch)
    plan_items = persistence.plan_payloads[0]["items"]
    assert plan_items[0]["obligation_nature"] == "required"
    assert "所需证据：已准备申请表、科研/竞赛证明与成绩单" in plan_items[0]["detail"]
    assert plan_items[1]["obligation_nature"] == "optional"
    assert plan_items[1]["official_deadline_at"] is None
    assert plan_items[1]["official_deadline_date"] == "2026-09-10"

    # Production clock (2026-11-18) must refuse confirmation via backend with DEADLINE_EXPIRED
    current_clock[0] = prod_clock
    assert find_expired_plan_tasks(result.candidate_plan, prod_clock) == [
        "T-01",
        "T-02",
    ]
    expired_confirm = orch.confirm_plan(
        result.run_id,
        candidate_version=1,
        operation_id="op-expired-01",
    )
    assert expired_confirm.status == RunStatus.FAILED
    assert expired_confirm.error is not None
    assert expired_confirm.error.code == AgentErrorCode.DEADLINE_EXPIRED
    assert persistence.written_tasks == []

    # Production clock start_run flags expired_source gap
    prod_run = orch.start_run(ctx.model_copy(update={"as_of": prod_clock}))
    assert any(g.gap_type == "expired_source" for g in prod_run.gaps)


def test_p1_citation_rejects_fictional_locator_excerpt_or_mismatched_uuid() -> None:
    source_uuid = "b0000000-0000-4000-8000-000000000001"
    snapshot_uuid = "b0000000-0000-4000-8000-000000000002"
    doc = SourceDocument(
        source_version_id=snapshot_uuid,
        source_id=source_uuid,
        snapshot_id=snapshot_uuid,
        title="官方通知",
        publisher="某校",
        content=FX_S4_EXCERPT,
        fragments=[
            SourceFragmentRecord(
                locator_kind="section", locator="第（5）项", quote=FX_S4_EXCERPT
            )
        ],
    )

    bad_cases = [
        # Fictional locator not in fragments
        SourceCitation(
            source_version_id=snapshot_uuid,
            locator="第九十九条",
            excerpt="于2026年9月10日下午15:00前提交",
        ),
        # Fictional excerpt not in quote
        SourceCitation(
            source_version_id=snapshot_uuid,
            locator="第（5）项",
            excerpt="虚构的保研名额保证",
        ),
        # Mismatched snapshot_id UUID
        SourceCitation(
            source_version_id=snapshot_uuid,
            source_id=source_uuid,
            snapshot_id="b0000000-0000-4000-8000-999999999999",
            locator="第（5）项",
            excerpt="于2026年9月10日下午15:00前提交",
        ),
    ]

    for bad_cite in bad_cases:

        def bad_model[T: BaseModel](
            instruction: str,
            text: str,
            response_model: type[T],
            cite: SourceCitation = bad_cite,
        ) -> T:
            payload = RequirementExtractionPayload(
                requirements=[
                    ExtractedRequirementDraft(
                        requirement_id="R-BAD",
                        title="测试引用",
                        obligation=ObligationType.OFFICIAL_REQUIRED,
                        basis=[cite],
                    )
                ]
            )
            return response_model.model_validate(payload.model_dump())

        orch = AgentOrchestrator(
            source_reader=PublicHtmlSourceReader(preloaded_sources=[doc]),
            model_adapter=StructuredModelAdapter(bad_model),
            backend=InMemoryWorkspaceBackend(),
            persistence=InMemoryPersistence(),
        )
        res = orch.start_run(
            RunContext(
                user_id="u1", matter_id="m1", goal="测试引用校验", workspace_version=1
            )
        )
        assert res.status == RunStatus.FAILED
        assert res.error is not None
        assert res.error.code == AgentErrorCode.VALIDATION_FAILED


def test_a14_and_a03_failures_and_scope_year_forwarding() -> None:
    snapshot_uuid = "b0000000-0000-4000-8000-000000000002"
    doc = SourceDocument(
        source_version_id=snapshot_uuid,
        source_id="b0000000-0000-4000-8000-000000000001",
        snapshot_id=snapshot_uuid,
        title="官方通知",
        publisher="某校",
        content=FX_S4_EXCERPT,
    )

    for sim_code, expected_code in [
        ("TIMEOUT", AgentErrorCode.TIMEOUT),
        ("INVALID_RESPONSE", AgentErrorCode.VALIDATION_FAILED),
        ("CONFIG_ERROR", AgentErrorCode.MODEL_ERROR),
    ]:

        def fail_model[T: BaseModel](
            instruction: str,
            text: str,
            response_model: type[T],
            code: str = sim_code,
        ) -> T:
            raise SimulatedModelError(code, f"模拟失败: {code}")

        persistence = InMemoryPersistence()
        orch = AgentOrchestrator(
            source_reader=PublicHtmlSourceReader(preloaded_sources=[doc]),
            model_adapter=StructuredModelAdapter(fail_model),
            backend=InMemoryWorkspaceBackend(),
            persistence=persistence,
        )
        res = orch.start_run(
            RunContext(
                user_id="u1", matter_id="m1", goal="测试失败路径", workspace_version=1
            )
        )
        assert res.status == RunStatus.FAILED
        assert res.error is not None
        assert res.error.code == expected_code
        assert persistence.plan_payloads == []
        assert persistence.written_tasks == []

    # A-03 + scope_year pass-through check
    captured_requests: list[dict[str, Any]] = []

    def fail_reader(req: dict[str, Any]) -> Any:
        captured_requests.append(req)
        raise SourceReadUnavailableError("network_error", "source could not be reached")

    def dummy_model[T: BaseModel](
        instruction: str, text: str, response_model: type[T]
    ) -> T:
        return response_model.model_validate({})

    orch_src_fail = AgentOrchestrator(
        source_reader=PublicHtmlSourceReader(read_public_html_fn=fail_reader),
        model_adapter=StructuredModelAdapter(dummy_model),
        backend=InMemoryWorkspaceBackend(),
        persistence=InMemoryPersistence(),
    )
    res_src = orch_src_fail.start_run(
        RunContext(
            user_id="u1",
            matter_id="m1",
            goal="测试来源读取失败",
            workspace_version=1,
            scope_year=2026,
            source_urls=["https://math.fzu.edu.cn/info/1171/10393.htm"],
        )
    )
    assert captured_requests[0]["scope_year"] == 2026
    assert res_src.status == RunStatus.FAILED
    assert res_src.error is not None
    assert res_src.error.code == AgentErrorCode.SOURCE_UNAVAILABLE


def test_pr24_domain_probe_fixes_and_p2_malformed_params() -> None:
    s5_doc = SourceDocument(
        source_version_id="S5-v1",
        title="福大经管学院推免通知",
        publisher="福州大学经济与管理学院",
        content="二、报名与复试确认",
        missing_attachments=["S5-A1 专业目录"],
    )
    s6_doc = SourceDocument(
        source_version_id="S6-v1",
        title="东南大学信息学院通知",
        publisher="东南大学信息科学与工程学院",
        content="英语要求：原则上四级>=500或六级>=425或托福>=80或雅思>=6。",
    )
    failed_doc = SourceDocument(
        source_version_id="S-FAIL",
        title="校验失败通知",
        publisher="某校",
        content="内容",
        auto_check_status="failed",
    )
    ambiguous_doc = SourceDocument(
        source_version_id="S-AMB",
        title="范围不明通知",
        publisher="某校",
        content="内容",
        roi_status="ambiguous",
    )
    sources = {
        "S5-v1": s5_doc,
        "S6-v1": s6_doc,
        "S-FAIL": failed_doc,
        "S-AMB": ambiguous_doc,
    }

    # P2: failed / ambiguous source statuses must yield NEEDS_USER_REVIEW, never MATCHED
    req_fail = ExtractedRequirement(
        requirement_id="R-FAIL",
        title="失败来源条款",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[SourceCitation(source_version_id="S-FAIL", locator="第一条")],
    )
    req_amb = ExtractedRequirement(
        requirement_id="R-AMB",
        title="歧义来源条款",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[SourceCitation(source_version_id="S-AMB", locator="第一条")],
    )
    ev_src_bad, err_src_bad = evaluate_requirements([req_fail, req_amb], sources, {})
    assert err_src_bad is not None
    assert err_src_bad.code == AgentErrorCode.RULE_CONFLICT_OR_AMBIGUOUS
    assert ev_src_bad[0].status == EvaluationStatus.NEEDS_USER_REVIEW
    assert ev_src_bad[1].status == EvaluationStatus.NEEDS_USER_REVIEW

    # P2: empty/malformed relative_deadline parameters must not raise KeyError
    req_bad_rel = ExtractedRequirement(
        requirement_id="R-BAD-REL",
        title="参数缺失的相对时限",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[SourceCitation(source_version_id="S5-v1", locator="一（四）")],
        rule_kind="relative_deadline",
        rule_parameters={},
    )
    ev_bad_rel, err_bad_rel = evaluate_requirements([req_bad_rel], sources, {})
    assert err_bad_rel is not None
    assert err_bad_rel.code == AgentErrorCode.RULE_CONFLICT_OR_AMBIGUOUS
    assert ev_bad_rel[0].status == EvaluationStatus.NEEDS_USER_REVIEW

    # Issue 1 (A17, A21, A22): any_minimum
    req_eng = ExtractedRequirement(
        requirement_id="GR-07",
        title="英语水平",
        obligation=ObligationType.PENDING_VERIFICATION,
        basis=[SourceCitation(source_version_id="S6-v1", locator="二第5项")],
        rule_kind="any_minimum",
        rule_parameters={
            "qualifier": "原则上",
            "operator": ">=",
            "minimum": {"cet4": 500, "cet6": 425, "toefl": 80, "ielts": 6},
        },
    )
    ev_a17, _ = evaluate_requirements([req_eng], sources, {"cet4": 500})
    assert ev_a17[0].status == EvaluationStatus.MATCHED
    assert "原则上" in ev_a17[0].reason

    ev_a21, _ = evaluate_requirements(
        [req_eng], sources, {"cet4": 499, "cet6": 424, "toefl": 79, "ielts": 5.5}
    )
    assert ev_a21[0].status == EvaluationStatus.NOT_MATCHED

    ev_a22, _ = evaluate_requirements([req_eng], sources, {"cet4": 499})
    assert ev_a22[0].status == EvaluationStatus.MISSING_INFO
    assert ev_a22[0].missing_fields == ["cet6", "toefl", "ielts"]

    # Issue 2 (A12, A13, A14): relative_deadline
    req_rel = ExtractedRequirement(
        requirement_id="GR-05",
        title="24小时内确认复试",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[SourceCitation(source_version_id="S5-v1", locator="一（四）")],
        rule_kind="relative_deadline",
        rule_parameters={
            "duration_hours": 24,
            "received_fact": "retest_received_at",
            "action_fact": "retest_accepted_at",
        },
    )
    ev_a12, _ = evaluate_requirements(
        [req_rel],
        sources,
        {
            "retest_received_at": "2026-09-23T10:30:00+08:00",
            "retest_accepted_at": "2026-09-24T10:29:00+08:00",
        },
    )
    assert ev_a12[0].status == EvaluationStatus.MATCHED

    ev_a13, _ = evaluate_requirements([req_rel], sources, {})
    assert ev_a13[0].status == EvaluationStatus.MISSING_INFO
    assert ev_a13[0].computed_deadline is None

    ev_a14, _ = evaluate_requirements(
        [req_rel],
        sources,
        {
            "retest_received_at": "2026-09-23T10:30:00+08:00",
            "retest_accepted_at": "2026-09-24T10:31:00+08:00",
        },
    )
    assert ev_a14[0].status == EvaluationStatus.NOT_MATCHED

    # Fixed deadline strict comparison
    req_fixed = ExtractedRequirement(
        requirement_id="GR-03B",
        title="系统报名固定截止",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[SourceCitation(source_version_id="S5-v1", locator="二、报名")],
        official_deadline=datetime(2026, 9, 10, 15, 0, tzinfo=SHANGHAI),
        rule_kind="fixed_deadline",
        rule_parameters={"action_fact": "submitted_at"},
    )
    ev_fixed_ok, _ = evaluate_requirements(
        [req_fixed],
        sources,
        {"submitted_at": "2026-09-10T14:59:00+08:00"},
    )
    assert ev_fixed_ok[0].status == EvaluationStatus.MATCHED
    ev_fixed_late, _ = evaluate_requirements(
        [req_fixed],
        sources,
        {"submitted_at": "2026-09-10T15:00:00+08:00"},
    )
    assert ev_fixed_late[0].status == EvaluationStatus.NOT_MATCHED

    # Issue 3 (A11 vs A28): attachment scope isolation
    req_reg = ExtractedRequirement(
        requirement_id="GR-04",
        title="教育部系统正式报名",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[SourceCitation(source_version_id="S5-v1", locator="三（一）")],
        rule_kind="materials",
        rule_parameters={"required_facts": ["ministry_registration_record"]},
    )
    req_cat = ExtractedRequirement(
        requirement_id="GR-10",
        title="专业目录核对",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[SourceCitation(source_version_id="S5-v1", locator="附件1")],
        required_attachments=["S5-A1 专业目录"],
        rule_kind="catalog_row",
    )
    ev_scope, _ = evaluate_requirements(
        [req_reg, req_cat], sources, {"ministry_registration_record": True}
    )
    assert ev_scope[0].status == EvaluationStatus.MATCHED
    assert ev_scope[1].status == EvaluationStatus.NEEDS_USER_REVIEW


def test_source_bridges_and_pr41_contract_payloads() -> None:
    sid = "b0000000-0000-4000-8000-000000000010"
    snap_id = "b0000000-0000-4000-8000-000000000011"
    now = datetime(2026, 9, 9, 1, 0, tzinfo=UTC)

    pub_doc = source_document_from_public_result(
        {
            "source_id": sid,
            "snapshot_id": snap_id,
            "version_no": 1,
            "url": "https://math.fzu.edu.cn/info/1171/10393.htm",
            "title": "工作方案",
            "publisher": "福大数统学院",
            "scope_year": 2027,
            "normalized_text": FX_S4_EXCERPT,
            "content_hash": FX_S4_SHA256,
            "fetched_at": now,
            "fragments": [
                {
                    "locator": {"kind": "list_item", "list": "材料清单", "item": 3},
                    "locator_text": "材料清单 第3项",
                    "quote": "该成绩单电子版",
                }
            ],
        }
    )
    assert pub_doc.source_version_id == snap_id
    assert pub_doc.fragments[0].locator_kind == "list_item"

    be_doc = source_document_from_backend_record(
        {
            "id": sid,
            "publisher": "福大数统学院",
            "url": "https://math.fzu.edu.cn/info/1171/10393.htm",
            "scope_year": 2027,
            "status": "active",
            "auto_check_status": "passed",
            "roi_status": "original",
        },
        {
            "id": snap_id,
            "version_no": 1,
            "title": "工作方案",
            "text": FX_S4_EXCERPT,
            "content_hash": FX_S4_SHA256,
            "fetched_at": now,
            "fragments": [],
        },
    )
    assert be_doc.snapshot_id == snap_id

    req = ExtractedRequirement(
        requirement_id="R-1",
        title="提交成绩单电子版",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        field_key="Material-Transcript_PDF",
        basis=[
            SourceCitation(
                source_version_id=snap_id,
                locator="材料清单 第3项",
                locator_kind="list_item",
            )
        ],
    )
    sources_map = {snap_id: pub_doc}
    evals, _ = evaluate_requirements([req], sources_map, {})
    req_batch = build_requirements_batch_payload([req], evals, sources_map)
    item = req_batch["requirements"][0]
    assert FIELD_KEY_RE.fullmatch(item["field_key"])
    assert item["evidence"][0]["locator_kind"] == "section"

    plan = CandidatePlan(
        candidate_id="plan-pr41",
        workspace_version=1,
        candidate_version=1,
        input_snapshot_id=snap_id,
        tasks=[
            CandidateTask(
                task_id="t1",
                title="准备成绩单",
                requirement_id="R-1",
                basis=[
                    SourceCitation(
                        source_version_id=snap_id,
                        locator="材料清单 第3项",
                        locator_kind="list_item",
                    )
                ],
                obligation=ObligationType.OFFICIAL_REQUIRED,
                official_deadline_at=datetime(2026, 9, 10, 15, 0, tzinfo=SHANGHAI),
                suggested_date=date(2026, 9, 9),
                evidence_required="电子版PDF",
            )
        ],
    )
    plan_payload = build_candidate_plan_create_payload(
        plan, sources_map, {"R-1": str(uuid4())}
    )
    assert plan_payload["items"][0]["sources"][0]["locator_kind"] == "section"
    assert plan_payload["items"][0]["official_deadline_date"] == "2026-09-10"
    assert "所需证据：电子版PDF" in plan_payload["items"][0]["detail"]


def test_candidate_plan_payload_deduplicates_item_sources() -> None:
    snap_id, doc = _fragment_doc()
    cite = SourceCitation(
        source_version_id=snap_id,
        locator="正文第3段",
        excerpt="（3）成绩排名前 30%。",
    )
    plan = CandidatePlan(
        candidate_id="plan-duplicate-sources",
        workspace_version=1,
        candidate_version=1,
        input_snapshot_id=snap_id,
        tasks=[
            CandidateTask(
                task_id="t1",
                title="确认成绩排名",
                basis=[cite, cite.model_copy(update={"locator": "正文第3段  "})],
                obligation=ObligationType.OFFICIAL_REQUIRED,
                evidence_required="成绩排名证明",
            )
        ],
    )

    payload = build_candidate_plan_create_payload(plan, {snap_id: doc})

    assert payload["items"][0]["sources"] == [
        {
            "source_id": doc.source_id,
            "snapshot_id": doc.snapshot_id,
            "locator_kind": "section",
            "locator": "正文第3段",
            "quote": "（3）成绩排名前 30%。",
        }
    ]


def test_candidate_plan_payload_skips_blank_locators_and_truncates_after_trim() -> None:
    snap_id, doc = _fragment_doc()
    cite = SourceCitation(
        source_version_id=snap_id,
        locator="正文第3段",
        excerpt="（3）成绩排名前 30%。",
    )
    long_locator = " " * 300 + "定位" * 200
    plan = CandidatePlan(
        candidate_id="plan-normalized-sources",
        workspace_version=1,
        candidate_version=1,
        input_snapshot_id=snap_id,
        tasks=[
            CandidateTask(
                task_id="t1",
                title="确认成绩排名",
                basis=[
                    cite.model_copy(update={"locator": " \t "}),
                    cite,
                    cite.model_copy(update={"locator": " " * 300 + "正文第3段"}),
                    cite.model_copy(update={"locator": long_locator}),
                ],
                obligation=ObligationType.OFFICIAL_REQUIRED,
                evidence_required="成绩排名证明",
            )
        ],
    )

    payload = build_candidate_plan_create_payload(plan, {snap_id: doc})

    assert [source["locator"] for source in payload["items"][0]["sources"]] == [
        "正文第3段",
        ("定位" * 200)[:300],
    ]


def test_candidate_plan_payload_deduplicates_locator_after_final_normalization() -> (
    None
):
    snap_id, doc = _fragment_doc()
    short_locator = "定位" * 149 + "定"
    long_locator = short_locator + " 后续内容"
    cite = SourceCitation(
        source_version_id=snap_id,
        locator=short_locator,
        excerpt="（3）成绩排名前 30%。",
    )
    plan = CandidatePlan(
        candidate_id="plan-truncated-locator",
        workspace_version=1,
        candidate_version=1,
        input_snapshot_id=snap_id,
        tasks=[
            CandidateTask(
                task_id="t1",
                title="确认成绩排名",
                basis=[cite, cite.model_copy(update={"locator": long_locator})],
                obligation=ObligationType.OFFICIAL_REQUIRED,
                evidence_required="成绩排名证明",
            )
        ],
    )

    payload = build_candidate_plan_create_payload(plan, {snap_id: doc})

    assert [source["locator"] for source in payload["items"][0]["sources"]] == [
        short_locator
    ]
    CandidatePlanCreate.model_validate(payload)


def test_candidate_plan_create_rejects_duplicate_item_sources() -> None:
    citation = {
        "source_id": str(uuid4()),
        "snapshot_id": str(uuid4()),
        "locator_kind": "section",
        "locator": "第 3 条",
        "quote": "成绩排名前 30%",
    }

    try:
        CandidatePlanCreate.model_validate(
            {
                "items": [
                    {
                        "client_item_id": "t1",
                        "title": "确认成绩排名",
                        "sources": [citation, citation],
                    }
                ]
            }
        )
    except ValueError as exc:
        assert "sources must be unique by snapshot_id and locator" in str(exc)
    else:
        raise AssertionError("Expected duplicate item sources to be rejected")


def test_bot_fixes_string_scores_multisnap_and_concurrent_adapter() -> None:
    src_a = str(uuid4())
    snap_a = str(uuid4())
    src_b = str(uuid4())
    snap_b = str(uuid4())
    doc_a = SourceDocument(
        source_version_id=snap_a,
        source_id=src_a,
        snapshot_id=snap_a,
        title="英语要求A",
        publisher="某校",
        content="四级>=500",
    )
    doc_b = SourceDocument(
        source_version_id=snap_b,
        source_id=src_b,
        snapshot_id=snap_b,
        title="补充说明B",
        publisher="某校",
        content="补充材料说明",
    )
    sources_map = {snap_a: doc_a, snap_b: doc_b}

    req_eng = ExtractedRequirement(
        requirement_id="R-ENG",
        title="英语四级要求",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[
            SourceCitation(source_version_id=snap_a, locator="四级>=500"),
            SourceCitation(source_version_id=snap_b, locator="补充材料说明"),
        ],
        rule_kind="any_minimum",
        rule_parameters={"minimum": {"cet4": 500}, "operator": ">="},
    )
    # Numeric string score evaluates cleanly instead of failing as NOT_MATCHED
    ev_str_ok, _ = evaluate_requirements([req_eng], sources_map, {"cet4": "500"})
    assert ev_str_ok[0].status == EvaluationStatus.MATCHED

    # Non-numeric string flags NEEDS_USER_REVIEW instead of NOT_MATCHED
    ev_str_bad, _ = evaluate_requirements([req_eng], sources_map, {"cet4": "N/A"})
    assert ev_str_bad[0].status == EvaluationStatus.NEEDS_USER_REVIEW

    # Multiple snapshots in requirement basis are all preserved in payload
    batch = build_requirements_batch_payload([req_eng], ev_str_ok, sources_map)
    evidence = batch["requirements"][0]["evidence"]
    assert len(evidence) == 2
    assert {e["snapshot_id"] for e in evidence} == {snap_a, snap_b}

    # Concurrent calls to StructuredModelAdapter.extract_requirements_with_metadata stay isolated
    def fake_model(instruction: str, text: str, response_model: type[Any]) -> Any:
        payload = json.loads(text)
        goal = payload["goal"]
        snap = payload["sources"][0]["source_version_id"]
        return response_model.model_validate(
            {
                "requirements": [
                    {
                        "requirement_id": f"req-{goal}",
                        "title": f"要求-{goal}",
                        "obligation": "官方必需",
                        "basis": [{"source_version_id": snap, "locator": "四级>=500"}],
                    }
                ],
                "gaps": [{"gap_type": "scope_unclear", "description": f"gap-{goal}"}],
                "scope_summary": {"goal_tag": goal},
            }
        )

    adapter = StructuredModelAdapter(fake_model)
    _, gaps1, scope1 = adapter.extract_requirements_with_metadata("G1", [doc_a])
    _, gaps2, scope2 = adapter.extract_requirements_with_metadata("G2", [doc_a])
    assert gaps1[0].description == "gap-G1"
    assert scope1 == {"goal_tag": "G1"}
    assert gaps2[0].description == "gap-G2"
    assert scope2 == {"goal_tag": "G2"}


def test_requirement_payload_keeps_self_check_apart_from_extract_status() -> None:
    from backend.agent import collect_source_gaps

    src_id = str(uuid4())
    snap_id = str(uuid4())
    doc = SourceDocument(
        source_version_id=snap_id,
        source_id=src_id,
        snapshot_id=snap_id,
        title="英语要求",
        publisher="某校",
        content="四级>=500或六级>=425",
    )
    sources_map = {snap_id: doc}
    cite = SourceCitation(source_version_id=snap_id, locator="二第5项")
    req_eng = ExtractedRequirement(
        requirement_id="R-ENG",
        title="英语水平",
        obligation=ObligationType.PENDING_VERIFICATION,
        basis=[cite],
        rule_kind="any_minimum",
        rule_parameters={"minimum": {"cet4": 500, "cet6": 425}, "operator": ">="},
    )
    req_ok = ExtractedRequirement(
        requirement_id="R-OK",
        title="英语四级达标",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[cite],
        rule_kind="any_minimum",
        rule_parameters={"minimum": {"cet4": 500}, "operator": ">="},
    )
    req_no = ExtractedRequirement(
        requirement_id="R-NO",
        title="英语四级未达标",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[cite],
        rule_kind="any_minimum",
        rule_parameters={"minimum": {"cet4": 500}, "operator": ">="},
    )
    req_bad = ExtractedRequirement(
        requirement_id="R-BAD",
        title="参数缺失的规则",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[cite],
        rule_kind="relative_deadline",
        rule_parameters={},
    )
    requirements = [req_eng, req_ok, req_no, req_bad]

    # R-ENG: cet4 below minimum, cet6 unknown -> missing_info
    ev_eng, _ = evaluate_requirements([req_eng], sources_map, {"cet4": 499})
    ev_ok, _ = evaluate_requirements([req_ok], sources_map, {"cet4": 520})
    ev_no, _ = evaluate_requirements([req_no], sources_map, {"cet4": 400})
    ev_bad, _ = evaluate_requirements([req_bad], sources_map, {})
    evaluations = ev_eng + ev_ok + ev_no + ev_bad
    gaps = collect_source_gaps([doc], evaluations)

    payload = build_requirements_batch_payload(
        requirements, evaluations, sources_map, gaps
    )
    items = {item["label"]: item for item in payload["requirements"]}

    eng = items["英语水平"]
    assert eng["extract_status"] == "checked"
    assert eng["self_check"]["conclusion"] == "missing_info"
    assert eng["self_check"]["missing_fields"] == ["cet6"]
    assert eng["self_check"]["reason"] == ev_eng[0].reason
    assert [g["gap_type"] for g in eng["self_check"]["gaps"]] == [
        "missing_personal_fact"
    ]
    assert eng["self_check"]["gaps"][0]["source_id"] == src_id
    assert eng["evidence"][0]["locator"] == "二第5项"

    # matched and not_matched share extract_status but keep distinct conclusions
    assert items["英语四级达标"]["extract_status"] == "checked"
    assert items["英语四级达标"]["self_check"]["conclusion"] == "matched"
    assert items["英语四级未达标"]["extract_status"] == "checked"
    assert items["英语四级未达标"]["self_check"]["conclusion"] == "not_matched"
    assert items["英语四级未达标"]["self_check"]["gaps"] == []

    bad = items["参数缺失的规则"]
    assert bad["extract_status"] == "to_review"
    assert bad["self_check"]["conclusion"] == "needs_user_review"
    assert [g["gap_type"] for g in bad["self_check"]["gaps"]] == ["ambiguous_clause"]

    # Requirements without an evaluation stay extracted with no self_check
    bare = build_requirements_batch_payload([req_ok], [], sources_map)
    assert bare["requirements"][0]["extract_status"] == "extracted"
    assert bare["requirements"][0]["self_check"] is None


def test_outbound_model_payload_strips_personal_fields_and_unlisted_scope() -> None:
    snap_id = str(uuid4())
    doc = SourceDocument(
        source_version_id=snap_id,
        source_id=str(uuid4()),
        snapshot_id=snap_id,
        title="公开通知",
        publisher="某学院",
        content="提交申请表。",
    )
    captured_payloads: list[dict[str, Any]] = []

    def capture_model(instruction: str, text: str, response_model: type[Any]) -> Any:
        captured_payloads.append(json.loads(text))
        return response_model.model_validate(
            {
                "tasks": [
                    {
                        "task_id": "t1",
                        "title": "提交申请表",
                        "basis": [
                            {"source_version_id": snap_id, "locator": "提交申请表"}
                        ],
                        "obligation": "官方必需",
                        "evidence_required": "申请表",
                    }
                ],
                "gaps": [],
                "scope_summary": {},
            }
        )

    adapter = StructuredModelAdapter(capture_model)
    ctx = RunContext(
        user_id="u1",
        matter_id="m1",
        goal="整理申请计划",
        workspace_version=1,
        scope_year=2027,
        scope_attrs={
            "school": "福州大学",
            "college": "数学与统计学院",
            "rank_position": 3,
            "email": "secret@example.com",
        },
        confirmed_facts={"cet4": 550, "rank_position": 3},
    )
    ev = evaluate_requirements(
        [
            ExtractedRequirement(
                requirement_id="r1",
                title="英语四级",
                obligation=ObligationType.OFFICIAL_REQUIRED,
                basis=[SourceCitation(source_version_id=snap_id, locator="提交申请表")],
                rule_kind="any_minimum",
                rule_parameters={"minimum": {"cet4": 500}, "operator": ">="},
            ),
            ExtractedRequirement(
                requirement_id="r2",
                title="六级或雅思",
                obligation=ObligationType.OFFICIAL_RECOMMENDED,
                basis=[SourceCitation(source_version_id=snap_id, locator="提交申请表")],
                rule_kind="any_minimum",
                rule_parameters={
                    "minimum": {"cet6": 425, "ielts": 6},
                    "operator": ">=",
                },
            ),
        ],
        {snap_id: doc},
        ctx.confirmed_facts,
    )[0]

    adapter.generate_candidate_plan(ctx, [doc], ev)
    sent = captured_payloads[0]
    assert sent["scope_attrs"] == {"school": "福州大学", "college": "数学与统计学院"}
    assert "rank_position" not in sent["scope_attrs"]
    assert "email" not in sent["scope_attrs"]
    assert "confirmed_facts" not in sent
    for sent_ev in sent["evaluations"]:
        assert "reason" not in sent_ev
        assert "missing_fields" not in sent_ev
        assert sent_ev["basis"][0]["locator"] == "提交申请表"
    assert "550" not in json.dumps(sent, ensure_ascii=False)


def _fragment_doc() -> tuple[str, SourceDocument]:
    snap_id = str(uuid4())
    doc = SourceDocument(
        source_version_id=snap_id,
        source_id=str(uuid4()),
        snapshot_id=snap_id,
        title="推免工作办法",
        publisher="福州大学数统学院",
        content="（3）成绩排名前 30%。",
        fragments=[
            SourceFragmentRecord(
                locator_kind="section",
                locator="正文第3段",
                quote="（3）成绩排名前 30%。",
            )
        ],
    )
    return snap_id, doc


def test_model_inputs_carry_source_fragments_for_exact_locators() -> None:
    from backend.agent.model_bridge import build_extraction_input, build_planning_input

    snap_id, doc = _fragment_doc()
    extraction = build_extraction_input(
        "整理推免要求", [doc], strategy_version="alpha-1"
    )
    assert extraction["sources"][0]["content"] == ""
    assert extraction["sources"][0]["fragments"] == [
        {
            "locator_kind": "section",
            "locator": "正文第3段",
            "quote": "（3）成绩排名前 30%。",
        }
    ]

    ctx = RunContext(
        user_id="u1", matter_id="m1", goal="整理推免要求", workspace_version=1
    )
    planning = build_planning_input(ctx, [doc], [], strategy_version="alpha-1")
    assert planning["sources"][0]["fragments"] == [
        {"locator_kind": "section", "locator": "正文第3段"}
    ]

    no_fragment_doc = SourceDocument(
        source_version_id=snap_id,
        title="无片段来源",
        publisher="某校",
        content="完整正文",
    )
    fallback = build_extraction_input(
        "g", [no_fragment_doc], strategy_version="alpha-1"
    )
    assert fallback["sources"][0]["content"] == "完整正文"
    assert fallback["sources"][0]["fragments"] == []


def test_citation_validation_rejects_empty_excerpt_and_kind_mismatch() -> None:
    from backend.agent.model_bridge import (
        ModelInvocationError,
        _validate_and_enrich_citations,
    )

    snap_id, doc = _fragment_doc()
    valid_ids = {snap_id}
    docs = {snap_id: doc}

    bad_cites = [
        SourceCitation(source_version_id=snap_id, locator="正文第3段", excerpt="   "),
        SourceCitation(
            source_version_id=snap_id,
            locator_kind="table_row",
            locator="正文第3段",
            excerpt="成绩排名前 30%",
        ),
    ]
    for bad in bad_cites:
        try:
            _validate_and_enrich_citations([bad], valid_ids, docs)
            raise AssertionError("Expected ModelInvocationError")
        except ModelInvocationError as exc:
            assert exc.code == AgentErrorCode.VALIDATION_FAILED

    good = _validate_and_enrich_citations(
        [SourceCitation(source_version_id=snap_id, locator="正文第3段")],
        valid_ids,
        docs,
    )
    assert good[0].excerpt == "（3）成绩排名前 30%。"


def test_date_value_text_is_normalized_or_rejected() -> None:
    from backend.agent.model_bridge import (
        ModelInvocationError,
        _normalize_model_value_text,
    )

    assert (
        _normalize_model_value_text("2026年9月10日下午15:00前", "date") == "2026-09-10"
    )
    assert _normalize_model_value_text("2026-09-10", "date") == "2026-09-10"
    assert (
        _normalize_model_value_text(
            None,
            "date",
            official_deadline=datetime(2026, 9, 10, 15, 0, tzinfo=SHANGHAI),
        )
        == "2026-09-10"
    )
    assert _normalize_model_value_text("TRUE", "boolean") == "true"

    for bad in ("2026年2月30日", "下午三点前"):
        try:
            _normalize_model_value_text(bad, "date")
            raise AssertionError("Expected ModelInvocationError")
        except ModelInvocationError as exc:
            assert exc.code == AgentErrorCode.VALIDATION_FAILED

    snap_id, doc = _fragment_doc()
    req = ExtractedRequirement(
        requirement_id="r-date",
        title="提交申请材料截止",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        value_type="date",
        value_text=_normalize_model_value_text("2026年9月10日下午15:00前", "date"),
        basis=[SourceCitation(source_version_id=snap_id, locator="正文第3段")],
    )
    evals, _ = evaluate_requirements([req], {snap_id: doc}, {})
    batch = build_requirements_batch_payload([req], evals, {snap_id: doc})
    assert batch["requirements"][0]["value_text"] == "2026-09-10"


def test_task_dependency_prefix_resolution_and_missing_guard() -> None:
    from backend.agent import validate_candidate_plan
    from backend.agent.model_bridge import _resolve_task_dependency_prefixes

    snap_id, doc = _fragment_doc()
    cite = SourceCitation(source_version_id=snap_id, locator="正文第3段")
    t1 = CandidateTask(
        task_id="T01-check-eligibility",
        title="核对资格",
        basis=[cite],
        obligation=ObligationType.OFFICIAL_REQUIRED,
        evidence_required="资格确认",
    )
    t2 = CandidateTask(
        task_id="T02-prepare-application-form",
        title="准备申请表",
        basis=[cite],
        obligation=ObligationType.OFFICIAL_REQUIRED,
        depends_on=["T01"],
        evidence_required="申请表",
    )
    t3 = CandidateTask(
        task_id="T05-submit-application-package",
        title="提交材料",
        basis=[cite],
        obligation=ObligationType.OFFICIAL_REQUIRED,
        depends_on=["T02", "T01-check-eligibility"],
        evidence_required="回执",
    )
    resolved = _resolve_task_dependency_prefixes([t1, t2, t3])
    assert resolved[1].depends_on == ["T01-check-eligibility"]
    assert resolved[2].depends_on == [
        "T02-prepare-application-form",
        "T01-check-eligibility",
    ]
    plan = CandidatePlan(
        candidate_id="cand-m1",
        workspace_version=1,
        candidate_version=1,
        input_snapshot_id=snap_id,
        tasks=resolved,
    )
    assert validate_candidate_plan(plan, 1) == []

    # Missing or ambiguous prefix must still be rejected by validate_candidate_plan
    t_dup = CandidateTask(
        task_id="T01-other",
        title="另一前置",
        basis=[cite],
        obligation=ObligationType.OFFICIAL_REQUIRED,
        evidence_required="说明",
    )
    t_bad = CandidateTask(
        task_id="T03-bad",
        title="引用不存在或歧义前缀",
        basis=[cite],
        obligation=ObligationType.OFFICIAL_REQUIRED,
        depends_on=["T01", "T99"],
        evidence_required="说明",
    )
    ambiguous_resolved = _resolve_task_dependency_prefixes([t1, t_dup, t_bad])
    assert ambiguous_resolved[2].depends_on == ["T01", "T99"]
    bad_plan = CandidatePlan(
        candidate_id="cand-m1",
        workspace_version=1,
        candidate_version=1,
        input_snapshot_id=snap_id,
        tasks=ambiguous_resolved,
    )
    violations = validate_candidate_plan(bad_plan, 1)
    assert len(violations) == 2

    # Empty/whitespace dependency must not match task IDs starting with '-' or '_'
    t_leading = CandidateTask(
        task_id="-leading-dash",
        title="特殊前缀任务",
        basis=[cite],
        obligation=ObligationType.OFFICIAL_REQUIRED,
        evidence_required="说明",
    )
    for empty_dep in ("", "   "):
        t_blank_dep = CandidateTask(
            task_id="T04-blank",
            title="空白依赖",
            basis=[cite],
            obligation=ObligationType.OFFICIAL_REQUIRED,
            depends_on=[empty_dep],
            evidence_required="说明",
        )
        blank_resolved = _resolve_task_dependency_prefixes([t_leading, t_blank_dep])
        assert blank_resolved[1].depends_on == [empty_dep]
        assert (
            len(
                validate_candidate_plan(
                    plan.model_copy(update={"tasks": blank_resolved}), 1
                )
            )
            == 1
        )

    # Long task_id (>80 chars) truncates client_item_id and depends_on consistently
    long_id = "T01-" + ("x" * 90)
    t_long = CandidateTask(
        task_id=long_id,
        title="长编号任务",
        basis=[cite],
        obligation=ObligationType.OFFICIAL_REQUIRED,
        evidence_required="说明",
    )
    t_dep_long = CandidateTask(
        task_id="T02-next",
        title="依赖长编号",
        basis=[cite],
        obligation=ObligationType.OFFICIAL_REQUIRED,
        depends_on=["T01"],
        evidence_required="说明",
    )
    long_resolved = _resolve_task_dependency_prefixes([t_long, t_dep_long])
    long_plan_payload = build_candidate_plan_create_payload(
        CandidatePlan(
            candidate_id="cand-m1",
            workspace_version=1,
            candidate_version=1,
            input_snapshot_id=snap_id,
            tasks=long_resolved,
        ),
        {snap_id: doc},
    )
    CandidatePlanCreate.model_validate(long_plan_payload)
    assert len(long_plan_payload["items"][0]["client_item_id"]) == 80
    assert (
        long_plan_payload["items"][1]["depends_on"][0]
        == long_plan_payload["items"][0]["client_item_id"]
    )

    for first_id, second_id in (
        ("T-" + "a" * 80 + "-1", "T-" + "a" * 80 + "-2"),
        ("T-" + "a" * 77 + " x", "T-" + "a" * 77),
    ):
        conflicting_plan = plan.model_copy(
            update={
                "tasks": [
                    t1.model_copy(update={"task_id": first_id}),
                    t_dup.model_copy(update={"task_id": second_id}),
                ]
            }
        )
        with pytest.raises(ValueError, match="冲突"):
            build_candidate_plan_create_payload(conflicting_plan, {snap_id: doc})
