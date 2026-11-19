"""Tests for deterministic domain-constraint validators and four-state evaluation."""

from datetime import UTC, date, datetime

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
    validate_candidate_plan,
)


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
            _task("t1", deadline=datetime(2027, 6, 10, 17, 0, tzinfo=UTC), suggested_date=date(2027, 6, 3)),
            _task("t2", depends_on=["t1"]),
        ],
    )
    assert validate_candidate_plan(plan, expected_workspace_version=3) == []


def test_validate_candidate_plan_detects_cycle_and_bad_dates() -> None:
    plan = CandidatePlan(
        candidate_id="plan-2",
        workspace_version=2,
        candidate_version=1,
        input_snapshot_id="snap-1",
        tasks=[
            _task("t1", depends_on=["t2"], deadline=datetime(2027, 6, 10, tzinfo=UTC), suggested_date=date(2027, 6, 12)),
            _task("t2", depends_on=["t1"]),
        ],
    )
    violations = validate_candidate_plan(plan, expected_workspace_version=3)
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
