"""Deterministic domain-constraint validators for Agent outputs."""

from __future__ import annotations

from backend.agent.schemas import (
    AgentError,
    AgentErrorCode,
    CandidatePlan,
    EvaluationStatus,
    ExtractedRequirement,
    RequirementEvaluation,
    SourceDocument,
)


def validate_candidate_plan(
    plan: CandidatePlan,
    expected_workspace_version: int,
) -> list[str]:
    """Validate domain constraints on a candidate plan (DYH-R03, R11, R15).

    Returns a list of human-readable violation messages; empty means valid.
    """
    violations: list[str] = []

    if plan.workspace_version != expected_workspace_version:
        violations.append(
            f"工作区版本不匹配：期望 {expected_workspace_version}，实际 {plan.workspace_version}"
        )

    task_ids = [t.task_id for t in plan.tasks]
    if len(task_ids) != len(set(task_ids)):
        violations.append("候选任务存在重复的 task_id")

    known_ids = set(task_ids)
    adjacency: dict[str, list[str]] = {}

    for task in plan.tasks:
        if not task.basis:
            violations.append(f"任务 {task.task_id} 缺少来源依据 (basis)")

        for dep_id in task.depends_on:
            if dep_id == task.task_id:
                violations.append(f"任务 {task.task_id} 不能依赖自身")
            elif dep_id not in known_ids:
                violations.append(f"任务 {task.task_id} 依赖了不存在的前置任务 {dep_id}")

        if (
            task.official_deadline is not None
            and task.suggested_date is not None
            and task.suggested_date > task.official_deadline.date()
        ):
            violations.append(
                f"任务 {task.task_id} 的建议准备日 ({task.suggested_date}) "
                f"晚于官方期限 ({task.official_deadline.date()})"
            )

        adjacency[task.task_id] = list(task.depends_on)

    if _has_cycle(adjacency):
        violations.append("候选任务依赖关系存在环路")

    return violations


def _has_cycle(adjacency: dict[str, list[str]]) -> bool:
    """Detect cycles in task dependency graph via three-color DFS."""
    unvisited, visiting, visited = 0, 1, 2
    state: dict[str, int] = {node: unvisited for node in adjacency}

    def dfs(node: str) -> bool:
        state[node] = visiting
        for dep in adjacency.get(node, []):
            if dep not in state:
                continue
            dep_state = state[dep]
            if dep_state == visiting:
                return True
            if dep_state == unvisited and dfs(dep):
                return True
        state[node] = visited
        return False

    return any(state[node] == unvisited and dfs(node) for node in adjacency)


def evaluate_requirements(
    requirements: list[ExtractedRequirement],
    sources_by_id: dict[str, SourceDocument],
    confirmed_facts: dict[str, object],
) -> tuple[list[RequirementEvaluation], AgentError | None]:
    """Deterministically evaluate extracted requirements into the four-state contract."""
    evaluations: list[RequirementEvaluation] = []
    missing_fields: list[str] = []
    has_review_gap = False

    for req in requirements:
        source_issues = _collect_source_issues(req, sources_by_id)
        if req.is_ambiguous or source_issues:
            has_review_gap = True
            reason = "；".join(source_issues) if source_issues else "条款含义需结合原文确认"
            evaluations.append(
                RequirementEvaluation(
                    requirement_id=req.requirement_id,
                    title=req.title,
                    status=EvaluationStatus.NEEDS_USER_REVIEW,
                    reason=reason,
                    basis=req.basis,
                )
            )
            continue

        req_missing = [k for k in req.required_fact_keys if k not in confirmed_facts or confirmed_facts[k] is None]
        if req_missing:
            missing_fields.extend(f for f in req_missing if f not in missing_fields)
            evaluations.append(
                RequirementEvaluation(
                    requirement_id=req.requirement_id,
                    title=req.title,
                    status=EvaluationStatus.MISSING_INFO,
                    reason=f"缺少已确认个人字段：{', '.join(req_missing)}",
                    missing_fields=req_missing,
                    basis=req.basis,
                )
            )
            continue

        evaluations.append(
            RequirementEvaluation(
                requirement_id=req.requirement_id,
                title=req.title,
                status=EvaluationStatus.MATCHED,
                reason="规则依据与所需已确认事实齐全",
                basis=req.basis,
            )
        )

    if missing_fields:
        return evaluations, AgentError(
            code=AgentErrorCode.MISSING_PERSONAL_FACT,
            message="部分要求缺少已确认个人事实，需用户补充后复查",
            missing_fields=missing_fields,
        )

    if has_review_gap:
        return evaluations, AgentError(
            code=AgentErrorCode.RULE_CONFLICT_OR_AMBIGUOUS,
            message="部分来源或条款存在缺项或歧义，待用户核对",
        )

    return evaluations, None


def _collect_source_issues(
    req: ExtractedRequirement,
    sources_by_id: dict[str, SourceDocument],
) -> list[str]:
    issues: list[str] = []
    for cite in req.basis:
        doc = sources_by_id.get(cite.source_version_id)
        if doc is None:
            issues.append(f"引用来源 {cite.source_version_id} 不存在")
            continue
        if doc.is_repost:
            issues.append(f"来源 {doc.title} 为转载，未经官方原文核验")
        if doc.is_expired:
            issues.append(f"来源 {doc.title} 已过期")
        if doc.missing_attachments:
            issues.append(f"来源 {doc.title} 缺失附件：{', '.join(doc.missing_attachments)}")
    return issues
