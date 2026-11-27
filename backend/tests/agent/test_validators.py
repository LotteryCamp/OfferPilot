"""Tests for deterministic domain-constraint validators and four-state evaluation."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from backend.agent import (
    AgentErrorCode,
    CandidatePlan,
    CandidateTask,
    EvaluationStatus,
    ExtractedRequirement,
    ObligationType,
    SourceCitation,
    SourceDocument,
    evaluate_requirements,
    find_expired_plan_tasks,
    validate_candidate_plan,
)
from backend.agent.validators import normalize_candidate_deadlines
from backend.fact_types import get_fact_type

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _cite() -> SourceCitation:
    return SourceCitation(source_version_id="src-v1", locator="第三条第1款")


def _task(
    task_id: str,
    *,
    depends_on: list[str] | None = None,
    deadline: datetime | None = None,
    suggested_date: date | None = None,
) -> CandidateTask:
    return CandidateTask(
        task_id=task_id,
        title=f"任务 {task_id}",
        basis=[_cite()],
        obligation=ObligationType.OFFICIAL_REQUIRED,
        official_deadline=deadline,
        suggested_date=suggested_date,
        depends_on=depends_on or [],
        evidence_required="导出的 DOCX 副本",
    )


def test_validate_candidate_plan_valid() -> None:
    plan = CandidatePlan(
        candidate_id="plan-1",
        workspace_version=3,
        candidate_version=1,
        input_snapshot_id="snap-1",
        tasks=[
            _task(
                "t1",
                deadline=datetime(2027, 6, 10, 17, 0, tzinfo=UTC),
                suggested_date=date(2027, 6, 3),
            ),
            _task("t2", depends_on=["t1"]),
        ],
    )
    assert (
        validate_candidate_plan(plan, expected_workspace_version=3, timezone=SHANGHAI)
        == []
    )


def test_validate_candidate_plan_detects_cycle_and_bad_dates() -> None:
    plan = CandidatePlan(
        candidate_id="plan-2",
        workspace_version=2,
        candidate_version=1,
        input_snapshot_id="snap-1",
        tasks=[
            _task(
                "t1",
                depends_on=["t2"],
                deadline=datetime(2027, 6, 10, tzinfo=UTC),
                suggested_date=date(2027, 6, 12),
            ),
            _task("t2", depends_on=["t1"]),
        ],
    )
    violations = validate_candidate_plan(
        plan, expected_workspace_version=3, timezone=SHANGHAI
    )
    assert any("工作区版本不匹配" in v for v in violations)
    assert any("晚于官方期限" in v for v in violations)
    assert any("存在环路" in v for v in violations)


def test_evaluate_requirements_four_states() -> None:
    sources = {
        "src-ok": SourceDocument(
            source_version_id="src-ok",
            title="某校夏令营通知",
            publisher="某校研招办",
            content="要求提交成绩单与个人陈述。",
        ),
        "src-repost": SourceDocument(
            source_version_id="src-repost",
            title="论坛转载通知",
            publisher="第三方论坛",
            content="转载内容",
            is_repost=True,
        ),
    }

    reqs = [
        ExtractedRequirement(
            requirement_id="req-1",
            title="成绩排名",
            obligation=ObligationType.OFFICIAL_REQUIRED,
            basis=[SourceCitation(source_version_id="src-ok", locator="第二条")],
            required_fact_keys=["gpa_rank"],
        ),
        ExtractedRequirement(
            requirement_id="req-2",
            title="转载条款",
            obligation=ObligationType.PENDING_VERIFICATION,
            basis=[SourceCitation(source_version_id="src-repost", locator="全文")],
        ),
    ]

    evals_missing, err_missing = evaluate_requirements(reqs[:1], sources, {})
    assert err_missing is not None
    assert err_missing.code == AgentErrorCode.MISSING_PERSONAL_FACT
    assert err_missing.missing_fields == ["gpa_rank"]
    assert evals_missing[0].status == EvaluationStatus.MISSING_INFO

    evals_review, err_review = evaluate_requirements(reqs, sources, {"gpa_rank": "5%"})
    assert err_review is not None
    assert err_review.code == AgentErrorCode.RULE_CONFLICT_OR_AMBIGUOUS
    assert evals_review[0].status == EvaluationStatus.MATCHED
    assert evals_review[1].status == EvaluationStatus.NEEDS_USER_REVIEW


def test_normalize_candidate_deadlines_uses_configured_timezone() -> None:
    plan = CandidatePlan(
        candidate_id="plan-tz",
        workspace_version=1,
        candidate_version=1,
        input_snapshot_id="snap-1",
        tasks=[
            CandidateTask(
                task_id="t1",
                title="提交材料",
                basis=[_cite()],
                obligation=ObligationType.OFFICIAL_REQUIRED,
                official_deadline_at=datetime(2026, 9, 11, 6, 0, tzinfo=UTC),
                evidence_required="回执",
            )
        ],
    )

    assert normalize_candidate_deadlines(plan, ZoneInfo("America/Los_Angeles")) == []
    assert plan.tasks[0].official_deadline_date == date(2026, 9, 10)

    plan.tasks[0].official_deadline_date = date(2026, 9, 11)
    violations = normalize_candidate_deadlines(plan, ZoneInfo("America/Los_Angeles"))
    assert len(violations) == 1
    assert "official_deadline_date" in violations[0]


def test_find_expired_plan_tasks_uses_configured_timezone() -> None:
    plan = CandidatePlan(
        candidate_id="plan-expiry",
        workspace_version=1,
        candidate_version=1,
        input_snapshot_id="snap-1",
        tasks=[
            CandidateTask(
                task_id="t1",
                title="提交材料",
                basis=[_cite()],
                obligation=ObligationType.OFFICIAL_REQUIRED,
                official_deadline_date=date(2026, 9, 10),
                evidence_required="回执",
            )
        ],
    )
    now = datetime(2026, 9, 11, 6, 0, tzinfo=UTC)

    assert (
        find_expired_plan_tasks(plan, now, timezone=ZoneInfo("America/Los_Angeles"))
        == []
    )
    assert find_expired_plan_tasks(plan, now, timezone=SHANGHAI) == ["t1"]


def test_validate_candidate_plan_uses_configured_timezone() -> None:
    plan = CandidatePlan(
        candidate_id="plan-suggested-date",
        workspace_version=1,
        candidate_version=1,
        input_snapshot_id="snap-1",
        tasks=[
            CandidateTask(
                task_id="t1",
                title="准备材料",
                basis=[_cite()],
                obligation=ObligationType.OFFICIAL_REQUIRED,
                official_deadline_at=datetime(2026, 9, 11, 6, 0, tzinfo=UTC),
                suggested_date=date(2026, 9, 11),
                evidence_required="回执",
            )
        ],
    )

    la_violations = validate_candidate_plan(
        plan, 1, timezone=ZoneInfo("America/Los_Angeles")
    )
    assert any("晚于官方期限" in violation for violation in la_violations)
    assert validate_candidate_plan(plan, 1, timezone=SHANGHAI) == []


def _rank_compound_requirement() -> ExtractedRequirement:
    return ExtractedRequirement(
        requirement_id="GR-01",
        title="校内学业排名与课程条件",
        field_key="gpa.rank",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[SourceCitation(source_version_id="src-v1", locator="一、2（3）")],
        rule_kind="any_of",
        rule_parameters={
            "all_required": [
                {
                    "fact": "all_required_credits",
                    "operator": "==",
                    "value": True,
                }
            ],
            "paths": [
                {
                    "label": "前35%无补考重修路径",
                    "checks": [
                        {"fact": "gpa.rank", "operator": "<=", "value": 35},
                        {
                            "fact": "makeup_or_repeat_courses",
                            "operator": "<=",
                            "value": 0,
                        },
                    ],
                },
                {
                    "label": "前20%至多1门补考重修路径",
                    "checks": [
                        {"fact": "gpa.rank", "operator": "<=", "value": 20},
                        {
                            "fact": "makeup_or_repeat_courses",
                            "operator": "<=",
                            "value": 1,
                        },
                    ],
                },
            ],
        },
    )


def _rank_doc() -> dict[str, SourceDocument]:
    return {
        "src-v1": SourceDocument(
            source_version_id="src-v1",
            title="材料学院2027届推荐工作方案",
            publisher="福州大学材料科学与工程学院",
            content="排名前35%且无补考或重修，或前20%且允许1门补考或重修。",
        )
    }


def test_evaluate_any_of_rank_compound_rule_truth_table() -> None:
    rank_spec = get_fact_type("gpa.rank")
    assert rank_spec is not None
    req = _rank_compound_requirement()
    docs = _rank_doc()

    cases = [
        (35, 100, 0, True, EvaluationStatus.MATCHED),
        (20, 100, 1, True, EvaluationStatus.MATCHED),
        (21, 100, 1, True, EvaluationStatus.NOT_MATCHED),
        (36, 100, 0, True, EvaluationStatus.NOT_MATCHED),
        (1, 100, 0, False, EvaluationStatus.NOT_MATCHED),
    ]
    for position, cohort_size, makeup_count, credits_ok, expected_status in cases:
        normalized = rank_spec.normalize(
            {"position": position, "cohort_size": cohort_size}
        )
        rank_percentile = rank_spec.render(normalized).agent_value
        assert rank_percentile is not None
        evals, err = evaluate_requirements(
            [req],
            docs,
            {
                "gpa.rank": rank_percentile,
                "makeup_or_repeat_courses": makeup_count,
                "all_required_credits": credits_ok,
            },
        )
        assert evals[0].status == expected_status
        assert err is None


def test_evaluate_any_of_rank_partial_facts_and_single_path() -> None:
    rank_spec = get_fact_type("gpa.rank")
    assert rank_spec is not None
    req = _rank_compound_requirement()
    docs = _rank_doc()

    evals_empty, err_empty = evaluate_requirements([req], docs, {})
    assert evals_empty[0].status == EvaluationStatus.MISSING_INFO
    assert "gpa.rank" in evals_empty[0].missing_fields
    assert err_empty is not None
    assert err_empty.code == AgentErrorCode.MISSING_PERSONAL_FACT

    rank_10 = rank_spec.render(
        rank_spec.normalize({"position": 10, "cohort_size": 100})
    ).agent_value
    assert rank_10 == 10.0
    evals_rank_10, err_rank_10 = evaluate_requirements(
        [req], docs, {"gpa.rank": rank_10}
    )
    assert evals_rank_10[0].status == EvaluationStatus.MISSING_INFO
    assert "gpa.rank" not in evals_rank_10[0].missing_fields
    assert evals_rank_10[0].missing_fields == [
        "all_required_credits",
        "makeup_or_repeat_courses",
    ]
    assert "gpa.rank" in evals_rank_10[0].reason
    assert err_rank_10 is not None
    assert err_rank_10.missing_fields == [
        "all_required_credits",
        "makeup_or_repeat_courses",
    ]

    evals_rank_25, _ = evaluate_requirements([req], docs, {"gpa.rank": 25.0})
    assert evals_rank_25[0].status == EvaluationStatus.MISSING_INFO
    assert "gpa.rank" not in evals_rank_25[0].missing_fields
    assert evals_rank_25[0].missing_fields == [
        "all_required_credits",
        "makeup_or_repeat_courses",
    ]
    assert "gpa.rank=25 <= 35" in evals_rank_25[0].reason

    evals_rank_40, err_rank_40 = evaluate_requirements([req], docs, {"gpa.rank": 40.0})
    assert evals_rank_40[0].status == EvaluationStatus.NOT_MATCHED
    assert err_rank_40 is None

    single_rank_req = ExtractedRequirement(
        requirement_id="GR-RANK",
        title="学业排名前35%",
        field_key="gpa.rank",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[_cite()],
        rule_kind="any_of",
        rule_parameters={
            "paths": [
                {
                    "label": "前35%",
                    "checks": [{"fact": "gpa.rank", "operator": "<=", "value": 35}],
                }
            ]
        },
    )
    assert (
        evaluate_requirements([single_rank_req], docs, {})[0][0].status
        == EvaluationStatus.MISSING_INFO
    )
    assert (
        evaluate_requirements([single_rank_req], docs, {"gpa.rank": 10.0})[0][0].status
        == EvaluationStatus.MATCHED
    )
    assert (
        evaluate_requirements([single_rank_req], docs, {"gpa.rank": 36.0})[0][0].status
        == EvaluationStatus.NOT_MATCHED
    )


def test_evaluate_any_of_invalid_params_or_fact_values_require_review() -> None:
    docs = _rank_doc()
    bad_param_sets = [
        {"paths": []},
        {"paths": [{"checks": [{"fact": "gpa.rank", "operator": "!=", "value": 35}]}]},
        {
            "paths": [
                {"checks": [{"fact": "gpa.rank", "operator": "<=", "value": True}]}
            ]
        },
        {
            "paths": [
                {
                    "checks": [
                        {"fact": "gpa.rank", "operator": "<=", "value": float("nan")}
                    ]
                }
            ]
        },
    ]
    for params in bad_param_sets:
        req = ExtractedRequirement(
            requirement_id="GR-BAD",
            title="异常规则参数",
            obligation=ObligationType.OFFICIAL_REQUIRED,
            basis=[_cite()],
            rule_kind="any_of",
            rule_parameters=params,
        )
        evals, err = evaluate_requirements([req], docs, {"gpa.rank": 10.0})
        assert evals[0].status == EvaluationStatus.NEEDS_USER_REVIEW
        assert err is not None
        assert err.code == AgentErrorCode.RULE_CONFLICT_OR_AMBIGUOUS

    req = _rank_compound_requirement()
    evals_bad_fact, err_bad_fact = evaluate_requirements(
        [req],
        docs,
        {
            "gpa.rank": "前十名",
            "all_required_credits": True,
            "makeup_or_repeat_courses": 0,
        },
    )
    assert evals_bad_fact[0].status == EvaluationStatus.NEEDS_USER_REVIEW
    assert evals_bad_fact[0].missing_fields == ["gpa.rank"]
    assert err_bad_fact is not None
    assert err_bad_fact.code == AgentErrorCode.RULE_CONFLICT_OR_AMBIGUOUS
