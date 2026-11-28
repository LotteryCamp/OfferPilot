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
    SourceGap,
    collect_source_gaps,
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


def test_evaluate_any_of_handles_oversized_ints_malformed_shapes_and_all_operators() -> (
    None
):
    docs = _rank_doc()
    huge_int = 10**400

    for params in (
        {
            "all_required": "bad",
            "paths": [{"checks": [{"fact": "a", "operator": "==", "value": True}]}],
        },
        {"paths": ["bad"]},
        {"paths": [{}]},
        {"paths": [{"checks": ["bad"]}]},
        {"paths": [{"checks": [{"fact": " ", "operator": "==", "value": True}]}]},
        {
            "paths": [
                {"checks": [{"fact": "gpa.rank", "operator": "<=", "value": huge_int}]}
            ]
        },
        {
            "paths": [
                {"checks": [{"fact": "gpa.rank", "operator": "==", "value": huge_int}]}
            ]
        },
        {"paths": [{"checks": [{"fact": "tag", "operator": "==", "value": "   "}]}]},
    ):
        req = ExtractedRequirement(
            requirement_id="GR-SHAPE",
            title="格式边界",
            obligation=ObligationType.OFFICIAL_REQUIRED,
            basis=[_cite()],
            rule_kind="any_of",
            rule_parameters=params,
        )
        evals, err = evaluate_requirements([req], docs, {"gpa.rank": 10.0})
        assert evals[0].status == EvaluationStatus.NEEDS_USER_REVIEW
        assert err is not None

    huge_fact_req = ExtractedRequirement(
        requirement_id="GR-HUGE-FACT",
        title="超大整数事实",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[_cite()],
        rule_kind="any_of",
        rule_parameters={
            "paths": [
                {"checks": [{"fact": "gpa.rank", "operator": "<=", "value": 35}]},
            ]
        },
    )
    for bad_fact in (huge_int, "1" + ("0" * 400)):
        evals, err = evaluate_requirements(
            [huge_fact_req], docs, {"gpa.rank": bad_fact}
        )
        assert evals[0].status == EvaluationStatus.NEEDS_USER_REVIEW
        assert evals[0].missing_fields == ["gpa.rank"]
        assert err is not None

    ops_req = ExtractedRequirement(
        requirement_id="GR-OPS",
        title="全操作符覆盖",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[_cite()],
        rule_kind="any_of",
        rule_parameters={
            "all_required": [
                {"fact": "credits", "operator": ">", "value": 10},
                {"fact": "flag", "operator": "==", "value": "Yes"},
            ],
            "paths": [
                {
                    "checks": [
                        {"fact": "rank", "operator": "<", "value": 20},
                        {"fact": "gpa", "operator": ">=", "value": 3.5},
                        {"fact": "tier", "operator": "==", "value": 1},
                        {"fact": "active", "operator": "==", "value": True},
                    ]
                }
            ],
        },
    )
    ok_evals, ok_err = evaluate_requirements(
        [ops_req],
        docs,
        {
            "credits": 12,
            "flag": "yes",
            "rank": 15,
            "gpa": 3.8,
            "tier": 1,
            "active": "true",
        },
    )
    assert ok_evals[0].status == EvaluationStatus.MATCHED
    assert "路径 1" in ok_evals[0].reason
    assert ok_err is None

    fail_eq_evals, _ = evaluate_requirements(
        [ops_req],
        docs,
        {
            "credits": 12,
            "flag": "no",
            "rank": 15,
            "gpa": 3.8,
            "tier": 2,
            "active": "false",
        },
    )
    assert fail_eq_evals[0].status == EvaluationStatus.NOT_MATCHED

    bad_facts_list: tuple[dict[str, object], ...] = (
        {"credits": 12, "flag": 123, "rank": 15, "gpa": 3.8, "tier": 1, "active": True},
        {
            "credits": 12,
            "flag": "yes",
            "rank": 15,
            "gpa": 3.8,
            "tier": "abc",
            "active": True,
        },
        {
            "credits": 12,
            "flag": "yes",
            "rank": 15,
            "gpa": 3.8,
            "tier": 1,
            "active": "maybe",
        },
    )
    for bad_facts in bad_facts_list:
        inv_evals, inv_err = evaluate_requirements([ops_req], docs, bad_facts)
        assert inv_evals[0].status == EvaluationStatus.NEEDS_USER_REVIEW
        assert inv_err is not None

    # passed path with invalid or missing all_required prereq
    inv_req_evals, _ = evaluate_requirements(
        [ops_req],
        docs,
        {
            "credits": "nan",
            "flag": "yes",
            "rank": 15,
            "gpa": 3.8,
            "tier": 1,
            "active": True,
        },
    )
    assert inv_req_evals[0].status == EvaluationStatus.NEEDS_USER_REVIEW
    assert inv_req_evals[0].missing_fields == ["credits"]

    miss_req_evals, _ = evaluate_requirements(
        [ops_req],
        docs,
        {"credits": 12, "rank": 15, "gpa": 3.8, "tier": 1, "active": True},
    )
    assert miss_req_evals[0].status == EvaluationStatus.MISSING_INFO
    assert miss_req_evals[0].missing_fields == ["flag"]

    # pending path + invalid prereq -> needs_user_review
    pending_inv_evals, _ = evaluate_requirements(
        [ops_req],
        docs,
        {"credits": "bad", "flag": "yes", "rank": 15},
    )
    assert pending_inv_evals[0].status == EvaluationStatus.NEEDS_USER_REVIEW
    assert pending_inv_evals[0].missing_fields == ["credits"]

    # failed path + pending path with invalid prereq
    both_invalid_evals, _ = evaluate_requirements(
        [ops_req],
        docs,
        {"credits": "bad", "flag": "yes", "tier": "bad"},
    )
    assert both_invalid_evals[0].status == EvaluationStatus.NEEDS_USER_REVIEW
    assert both_invalid_evals[0].missing_fields == ["credits", "tier"]


def test_evaluate_any_of_rejects_subsumed_paths_and_unmodeled_required_facts() -> None:
    docs = _rank_doc()

    degraded_rank_only = ExtractedRequirement(
        requirement_id="R-004",
        title="排名及补考/重修课程限制",
        field_key="gpa.rank",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[_cite()],
        rule_kind="any_of",
        rule_parameters={
            "paths": [
                {
                    "label": "前35%",
                    "checks": [{"fact": "gpa.rank", "operator": "<=", "value": 35}],
                },
                {
                    "label": "前20%",
                    "checks": [{"fact": "gpa.rank", "operator": "<=", "value": 20}],
                },
            ]
        },
    )
    partial_omission = ExtractedRequirement(
        requirement_id="R-004-PARTIAL",
        title="排名及补考/重修课程限制",
        field_key="gpa.rank",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[_cite()],
        rule_kind="any_of",
        rule_parameters={
            "paths": [
                {
                    "label": "前35%（缺失补考条件）",
                    "checks": [{"fact": "gpa.rank", "operator": "<=", "value": 35}],
                },
                {
                    "label": "前20%至多1门补考重修",
                    "checks": [
                        {"fact": "gpa.rank", "operator": "<=", "value": 20},
                        {
                            "fact": "makeup_or_repeat_courses",
                            "operator": "<=",
                            "value": 1,
                        },
                    ],
                },
            ]
        },
    )
    lower_bound_subsumed = ExtractedRequirement(
        requirement_id="R-ENG-SUBSUMED",
        title="外语成绩分层冗余路径",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[_cite()],
        rule_kind="any_of",
        rule_parameters={
            "paths": [
                {"checks": [{"fact": "cet6", "operator": ">=", "value": 425}]},
                {"checks": [{"fact": "cet6", "operator": ">=", "value": 500}]},
            ]
        },
    )
    eq_and_bound_subsumed = ExtractedRequirement(
        requirement_id="R-EQ-SUBSUMED",
        title="档位包含路径",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[_cite()],
        rule_kind="any_of",
        rule_parameters={
            "paths": [
                {"checks": [{"fact": "tier", "operator": "<=", "value": 1}]},
                {
                    "checks": [
                        {"fact": "tier", "operator": "==", "value": 1},
                        {"fact": "bonus", "operator": ">=", "value": 2},
                    ]
                },
            ]
        },
    )
    strict_bound_subsumed = ExtractedRequirement(
        requirement_id="R-STRICT-SUBSUMED",
        title="严格不等式包含路径",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[_cite()],
        rule_kind="any_of",
        rule_parameters={
            "paths": [
                {"checks": [{"fact": "score", "operator": "<=", "value": 60}]},
                {"checks": [{"fact": "score", "operator": "<", "value": 60}]},
            ]
        },
    )
    subsumed_cases: tuple[tuple[ExtractedRequirement, dict[str, object]], ...] = (
        (degraded_rank_only, {"gpa.rank": 10.0}),
        (partial_omission, {"gpa.rank": 10.0}),
        (lower_bound_subsumed, {"cet6": 520}),
        (eq_and_bound_subsumed, {"tier": 1, "bonus": 3}),
        (strict_bound_subsumed, {"score": 50}),
    )
    for req, facts in subsumed_cases:
        evals, err = evaluate_requirements([req], docs, facts)
        assert evals[0].status == EvaluationStatus.NEEDS_USER_REVIEW
        assert "包含" in evals[0].reason
        assert err is not None
        assert err.code == AgentErrorCode.RULE_CONFLICT_OR_AMBIGUOUS

    single_path_with_extra_keys = ExtractedRequirement(
        requirement_id="R-004-EXTRA",
        title="排名及补考/重修课程限制",
        field_key="gpa.rank",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[_cite()],
        required_fact_keys=[
            "gpa.rank",
            "makeup_or_repeat_courses",
            "all_required_credits",
        ],
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
    # Only gpa.rank=10 is provided; credits and makeup/repeat are missing -> MISSING_INFO
    evals_missing, err_missing = evaluate_requirements(
        [single_path_with_extra_keys], docs, {"gpa.rank": 10.0}
    )
    assert evals_missing[0].status == EvaluationStatus.MISSING_INFO
    assert evals_missing[0].missing_fields == [
        "makeup_or_repeat_courses",
        "all_required_credits",
    ]
    assert err_missing is not None
    assert err_missing.code == AgentErrorCode.MISSING_PERSONAL_FACT

    # Even when extra keys are populated, unmodeled checks keep NEEDS_USER_REVIEW
    evals_unmodeled, err_unmodeled = evaluate_requirements(
        [single_path_with_extra_keys],
        docs,
        {
            "gpa.rank": 10.0,
            "makeup_or_repeat_courses": 0,
            "all_required_credits": True,
        },
    )
    assert evals_unmodeled[0].status == EvaluationStatus.NEEDS_USER_REVIEW
    assert "makeup_or_repeat_courses" in evals_unmodeled[0].reason
    assert err_unmodeled is not None
    assert err_unmodeled.code == AgentErrorCode.RULE_CONFLICT_OR_AMBIGUOUS

    # Modeled rank failure still reports NOT_MATCHED
    evals_failed, _ = evaluate_requirements(
        [single_path_with_extra_keys], docs, {"gpa.rank": 40.0}
    )
    assert evals_failed[0].status == EvaluationStatus.NOT_MATCHED


def test_evaluate_conservative_fallbacks_for_legacy_and_empty_materials() -> None:
    docs = _rank_doc()
    deadline = datetime(2026, 9, 10, 15, 0, tzinfo=SHANGHAI)

    # Ruleless requirement without required facts (e.g. unmodeled credit requirement)
    r003 = ExtractedRequirement(
        requirement_id="R-003",
        title="应修学分要求",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[_cite()],
    )
    ev_r003, err_r003 = evaluate_requirements([r003], docs, {"gpa.rank": 10.0})
    assert ev_r003[0].status == EvaluationStatus.NEEDS_USER_REVIEW
    assert err_r003 is not None
    assert err_r003.code == AgentErrorCode.RULE_CONFLICT_OR_AMBIGUOUS

    # Empty or malformed materials rule stays conservative
    empty_mat = ExtractedRequirement(
        requirement_id="R-MAT-EMPTY",
        title="未定义字段的材料要求",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[_cite()],
        rule_kind="materials",
        rule_parameters={},
    )
    bad_mat = ExtractedRequirement(
        requirement_id="R-MAT-BAD",
        title="非列表参数材料要求",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[_cite()],
        rule_kind="materials",
        rule_parameters={"required_facts": "all_required_credits"},
    )
    merged_mat = ExtractedRequirement(
        requirement_id="R-MAT-MERGE",
        title="合并清单材料要求",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[_cite()],
        required_fact_keys=["sealed_transcript"],
        rule_kind="materials",
        rule_parameters={"required_facts": ["paper_transcript"]},
    )
    for req in (empty_mat, bad_mat):
        ev, err = evaluate_requirements([req], docs, {})
        assert ev[0].status == EvaluationStatus.NEEDS_USER_REVIEW
        assert err is not None
    ev_merged, _ = evaluate_requirements([merged_mat], docs, {"paper_transcript": True})
    assert ev_merged[0].status == EvaluationStatus.MISSING_INFO
    assert ev_merged[0].missing_fields == ["sealed_transcript"]

    # Legacy official_deadline with no required_fact_keys confirms deadline basis without inventing facts
    legacy_dl = ExtractedRequirement(
        requirement_id="GR-02",
        title="提交申请材料截止",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[_cite()],
        official_deadline=deadline,
    )
    ev_dl_basis, err_dl_basis = evaluate_requirements([legacy_dl], docs, {})
    assert ev_dl_basis[0].status == EvaluationStatus.MATCHED
    assert ev_dl_basis[0].missing_fields == []
    assert ev_dl_basis[0].computed_deadline == deadline
    assert err_dl_basis is None

    naive_dl = ExtractedRequirement(
        requirement_id="GR-02-NAIVE",
        title="未带时区的提交截止",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[_cite()],
        official_deadline=datetime(2026, 9, 10, 15, 0),
    )
    ev_dl_naive_rule, _ = evaluate_requirements([naive_dl], docs, {})
    assert ev_dl_naive_rule[0].status == EvaluationStatus.NEEDS_USER_REVIEW

    # Legacy official_deadline declaring one time fact checks that fact cleanly
    legacy_dl_with_key = ExtractedRequirement(
        requirement_id="GR-02-FACT",
        title="按操作时间核对提交截止",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[_cite()],
        official_deadline=deadline,
        required_fact_keys=["submitted_at"],
    )
    ev_dl_missing, err_dl_missing = evaluate_requirements(
        [legacy_dl_with_key], docs, {}
    )
    assert ev_dl_missing[0].status == EvaluationStatus.MISSING_INFO
    assert ev_dl_missing[0].missing_fields == ["submitted_at"]
    assert ev_dl_missing[0].computed_deadline == deadline
    assert err_dl_missing is not None
    assert err_dl_missing.code == AgentErrorCode.MISSING_PERSONAL_FACT
    assert "missing_personal_fact" in {
        g.gap_type for g in collect_source_gaps(list(docs.values()), ev_dl_missing)
    }

    ev_dl_naive, _ = evaluate_requirements(
        [legacy_dl_with_key], docs, {"submitted_at": "2026-09-10T14:00:00"}
    )
    assert ev_dl_naive[0].status == EvaluationStatus.NEEDS_USER_REVIEW
    assert ev_dl_naive[0].computed_deadline == deadline

    ev_dl_ok, _ = evaluate_requirements(
        [legacy_dl_with_key], docs, {"submitted_at": "2026-09-10T14:59:00+08:00"}
    )
    assert ev_dl_ok[0].status == EvaluationStatus.MATCHED

    ev_dl_late, _ = evaluate_requirements(
        [legacy_dl_with_key], docs, {"submitted_at": "2026-09-10T15:01:00+08:00"}
    )
    assert ev_dl_late[0].status == EvaluationStatus.NOT_MATCHED

    legacy_dl_multi = ExtractedRequirement(
        requirement_id="GR-02-MULTI",
        title="多字段截止核对",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[_cite()],
        official_deadline=deadline,
        required_fact_keys=["submitted_at", "stamped_at"],
    )
    ev_dl_multi_missing, _ = evaluate_requirements(
        [legacy_dl_multi], docs, {"submitted_at": "2026-09-10T14:59:00+08:00"}
    )
    assert ev_dl_multi_missing[0].status == EvaluationStatus.MISSING_INFO
    assert ev_dl_multi_missing[0].missing_fields == ["stamped_at"]

    ev_dl_multi_review, _ = evaluate_requirements(
        [legacy_dl_multi],
        docs,
        {
            "submitted_at": "2026-09-10T14:59:00+08:00",
            "stamped_at": "2026-09-10T14:30:00+08:00",
        },
    )
    assert ev_dl_multi_review[0].status == EvaluationStatus.NEEDS_USER_REVIEW


def test_evaluate_reconciles_adapter_gaps_without_false_matched() -> None:
    docs = _rank_doc()
    rank_only_req = ExtractedRequirement(
        requirement_id="R-004",
        title="排名及补考/重修课程限制",
        field_key="gpa.rank",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[SourceCitation(source_version_id="src-v1", locator="一、2（3）")],
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
    unrelated_req = ExtractedRequirement(
        requirement_id="R-005",
        title="外语水平要求",
        field_key="cet4",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[SourceCitation(source_version_id="src-v1", locator="一、2（4）")],
        rule_kind="any_minimum",
        rule_parameters={"minimum": {"cet4": 480}, "operator": ">="},
    )
    similar_prefix_req = ExtractedRequirement(
        requirement_id="R-0040",
        title="其他独立材料要求",
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[SourceCitation(source_version_id="src-v1", locator="二、1")],
        required_fact_keys=["extra_doc_ready"],
    )

    # 1. Matched by related_requirement_ids
    ev_by_id, err_by_id = evaluate_requirements(
        [rank_only_req, unrelated_req],
        docs,
        {"gpa.rank": 10.0, "cet4": 520},
        adapter_gaps=[
            SourceGap(
                gap_type="missing_personal_fact",
                description="缺少补考/重修门数与学分事实，未纳入可执行检查",
                source_version_id="src-v1",
                related_requirement_ids=["R-004"],
            )
        ],
    )
    assert ev_by_id[0].status == EvaluationStatus.NEEDS_USER_REVIEW
    assert "缺少补考/重修门数" in ev_by_id[0].reason
    assert ev_by_id[1].status == EvaluationStatus.MATCHED
    assert err_by_id is not None
    assert err_by_id.code == AgentErrorCode.RULE_CONFLICT_OR_AMBIGUOUS

    # 2. Matched by exact (source_version_id, locator) when related_requirement_ids is empty
    ev_by_loc, _ = evaluate_requirements(
        [rank_only_req, unrelated_req],
        docs,
        {"gpa.rank": 10.0, "cet4": 520},
        adapter_gaps=[
            SourceGap(
                gap_type="missing_personal_fact",
                description="一、2（3）仅校验了排名阈值",
                source_version_id="src-v1",
                locator="  一、2（3）\n ",
            )
        ],
    )
    assert ev_by_loc[0].status == EvaluationStatus.NEEDS_USER_REVIEW
    assert ev_by_loc[1].status == EvaluationStatus.MATCHED

    # 3. Matched by standalone requirement_id mention in description without matching R-0040
    ev_by_desc, _ = evaluate_requirements(
        [rank_only_req, similar_prefix_req],
        docs,
        {"gpa.rank": 10.0, "extra_doc_ready": True},
        adapter_gaps=[
            SourceGap(
                gap_type="ambiguous_clause",
                description="R-004 的补考条款需核对教务记录",
            )
        ],
    )
    assert ev_by_desc[0].status == EvaluationStatus.NEEDS_USER_REVIEW
    assert ev_by_desc[1].status == EvaluationStatus.MATCHED

    # 4. Keeps MISSING_INFO and keeps NOT_MATCHED unless critical basis gap applies
    compound = _rank_compound_requirement()
    ev_missing_kept, _ = evaluate_requirements(
        [compound],
        docs,
        {"gpa.rank": 10.0},
        adapter_gaps=[
            SourceGap(
                gap_type="missing_personal_fact",
                description="缺少补考和学分事实",
                related_requirement_ids=["GR-01"],
            )
        ],
    )
    assert ev_missing_kept[0].status == EvaluationStatus.MISSING_INFO
    assert ev_missing_kept[0].missing_fields == [
        "all_required_credits",
        "makeup_or_repeat_courses",
    ]

    ev_not_matched_kept, _ = evaluate_requirements(
        [compound],
        docs,
        {"gpa.rank": 40.0},
        adapter_gaps=[
            SourceGap(
                gap_type="missing_personal_fact",
                description="缺少补考和学分事实",
                related_requirement_ids=["GR-01"],
            )
        ],
    )
    assert ev_not_matched_kept[0].status == EvaluationStatus.NOT_MATCHED

    ev_not_matched_critical, _ = evaluate_requirements(
        [compound],
        docs,
        {"gpa.rank": 40.0},
        adapter_gaps=[
            SourceGap(
                gap_type="ambiguous_clause",
                description="条款适用范围尚待明确",
                related_requirement_ids=["GR-01"],
            )
        ],
    )
    assert ev_not_matched_critical[0].status == EvaluationStatus.NEEDS_USER_REVIEW
