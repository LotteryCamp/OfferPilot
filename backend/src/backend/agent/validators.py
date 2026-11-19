"""Deterministic domain-constraint validators for Agent outputs."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from backend.agent.schemas import (
    SHANGHAI,
    AgentError,
    AgentErrorCode,
    CandidatePlan,
    EvaluationStatus,
    ExtractedRequirement,
    RequirementEvaluation,
    SourceDocument,
    SourceGap,
)


def validate_candidate_plan(
    plan: CandidatePlan,
    expected_workspace_version: int,
    sources_by_id: dict[str, SourceDocument] | None = None,
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
        elif sources_by_id is not None:
            for cite in task.basis:
                if cite.source_version_id not in sources_by_id:
                    violations.append(
                        f"任务 {task.task_id} 引用了不存在的来源版本 {cite.source_version_id}"
                    )

        for dep_id in task.depends_on:
            if dep_id == task.task_id:
                violations.append(f"任务 {task.task_id} 不能依赖自身")
            elif dep_id not in known_ids:
                violations.append(f"任务 {task.task_id} 依赖了不存在的前置任务 {dep_id}")

        effective_deadline_date = _task_deadline_date(
            task.official_deadline_date,
            task.official_deadline_at or task.official_deadline,
        )
        if (
            effective_deadline_date is not None
            and task.suggested_date is not None
            and task.suggested_date > effective_deadline_date
        ):
            violations.append(
                f"任务 {task.task_id} 的建议准备日 ({task.suggested_date}) "
                f"晚于官方期限 ({effective_deadline_date})"
            )

        adjacency[task.task_id] = list(task.depends_on)

    if _has_cycle(adjacency):
        violations.append("候选任务依赖关系存在环路")

    return violations


def _task_deadline_date(
    deadline_date: date | None,
    deadline_at: datetime | None,
) -> date | None:
    if deadline_at is not None:
        return deadline_at.astimezone(SHANGHAI).date()
    return deadline_date


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
                    scope=req.scope,
                )
            )
            continue

        ev = _evaluate_single_requirement(req, confirmed_facts)
        evaluations.append(ev)
        if ev.status == EvaluationStatus.MISSING_INFO:
            for f in ev.missing_fields:
                if f not in missing_fields:
                    missing_fields.append(f)
        elif ev.status == EvaluationStatus.NEEDS_USER_REVIEW:
            has_review_gap = True

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


def _evaluate_single_requirement(
    req: ExtractedRequirement,
    confirmed_facts: dict[str, object],
) -> RequirementEvaluation:
    kind = req.rule_kind
    params = req.rule_parameters

    if kind == "coverage_gap":
        docs = [str(d) for d in params.get("missing_documents", [])]
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.NEEDS_USER_REVIEW,
            reason="缺少上位依据文件" + (f"：{', '.join(docs)}" if docs else ""),
            missing_fields=docs,
            basis=req.basis,
            scope=req.scope,
        )

    if kind == "fixed_deadline":
        return _eval_fixed_deadline(req, params, confirmed_facts)

    if kind == "relative_deadline":
        return _eval_relative_deadline(req, params, confirmed_facts)

    if kind == "notice_deadline":
        return _eval_notice_deadline(req, params, confirmed_facts)

    if kind == "any_minimum":
        return _eval_any_minimum(req, params, confirmed_facts)

    if kind == "materials":
        return _eval_materials(req, params, confirmed_facts)

    if kind == "letters":
        return _eval_letters(req, params, confirmed_facts)

    if kind == "catalog_row":
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.MATCHED,
            reason="目录条目与来源依据已确认",
            basis=req.basis,
            scope=req.scope,
        )

    return _eval_legacy(req, confirmed_facts)


def _eval_fixed_deadline(
    req: ExtractedRequirement,
    params: dict[str, Any],
    confirmed_facts: dict[str, object],
) -> RequirementEvaluation:
    raw_before = params.get("before", req.official_deadline)
    due = _parse_aware_datetime(raw_before)
    if due is None:
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.NEEDS_USER_REVIEW,
            reason="固定期限缺少带时区的有效时间",
            basis=req.basis,
            scope=req.scope,
        )

    fact_key = str(
        params.get("fact") or (req.required_fact_keys[0] if req.required_fact_keys else "submitted_at")
    )
    raw_action = confirmed_facts.get(fact_key)
    if _is_missing(raw_action):
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.MISSING_INFO,
            reason=f"缺少已确认时间字段：{fact_key}",
            missing_fields=[fact_key],
            basis=req.basis,
            computed_deadline=due,
            scope=req.scope,
        )

    action = _parse_aware_datetime(raw_action)
    if action is None:
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.NEEDS_USER_REVIEW,
            reason=f"时间字段 {fact_key} 格式无法识别或缺少时区",
            basis=req.basis,
            computed_deadline=due,
            scope=req.scope,
        )

    op = str(params.get("operator", "<"))
    passed = action < due if op == "<" else action <= due
    return RequirementEvaluation(
        requirement_id=req.requirement_id,
        title=req.title,
        status=EvaluationStatus.MATCHED if passed else EvaluationStatus.NOT_MATCHED,
        reason="操作时间在官方期限内" if passed else f"操作时间晚于或超出官方期限 ({due.isoformat()})",
        basis=req.basis,
        computed_deadline=due,
        scope=req.scope,
    )


def _eval_relative_deadline(
    req: ExtractedRequirement,
    params: dict[str, Any],
    confirmed_facts: dict[str, object],
) -> RequirementEvaluation:
    received_key = params.get("received_fact")
    action_key = params.get("action_fact")
    raw_hours = params.get("duration_hours")
    if (
        not isinstance(received_key, str)
        or not received_key.strip()
        or not isinstance(action_key, str)
        or not action_key.strip()
        or not isinstance(raw_hours, (int, float))
        or isinstance(raw_hours, bool)
        or raw_hours <= 0
    ):
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.NEEDS_USER_REVIEW,
            reason="相对时限规则缺少有效的 received_fact、action_fact 或 duration_hours 参数",
            basis=req.basis,
            scope=req.scope,
        )
    duration_hours = float(raw_hours)

    raw_start = confirmed_facts.get(received_key)
    if _is_missing(raw_start):
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.MISSING_INFO,
            reason=f"缺少触发时点：{received_key}",
            missing_fields=[received_key],
            basis=req.basis,
            computed_deadline=None,
            scope=req.scope,
        )

    start = _parse_aware_datetime(raw_start)
    if start is None:
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.NEEDS_USER_REVIEW,
            reason=f"触发时点 {received_key} 缺少时区或格式无效",
            basis=req.basis,
            scope=req.scope,
        )

    due = start + timedelta(hours=duration_hours)
    raw_action = confirmed_facts.get(action_key)
    if _is_missing(raw_action):
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.MISSING_INFO,
            reason=f"缺少确认操作时点：{action_key}",
            missing_fields=[action_key],
            basis=req.basis,
            computed_deadline=due,
            scope=req.scope,
        )

    action = _parse_aware_datetime(raw_action)
    if action is None:
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.NEEDS_USER_REVIEW,
            reason=f"操作时点 {action_key} 缺少时区或格式无效",
            basis=req.basis,
            computed_deadline=due,
            scope=req.scope,
        )

    passed = start <= action <= due
    return RequirementEvaluation(
        requirement_id=req.requirement_id,
        title=req.title,
        status=EvaluationStatus.MATCHED if passed else EvaluationStatus.NOT_MATCHED,
        reason="在相对时限内完成确认" if passed else f"已超出 {int(duration_hours)} 小时时限 ({due.isoformat()})",
        basis=req.basis,
        computed_deadline=due,
        scope=req.scope,
    )


def _eval_notice_deadline(
    req: ExtractedRequirement,
    params: dict[str, Any],
    confirmed_facts: dict[str, object],
) -> RequirementEvaluation:
    deadline_key = params.get("deadline_fact")
    action_key = params.get("action_fact")
    if (
        not isinstance(deadline_key, str)
        or not deadline_key.strip()
        or not isinstance(action_key, str)
        or not action_key.strip()
    ):
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.NEEDS_USER_REVIEW,
            reason="通知时限规则缺少有效的 deadline_fact 或 action_fact 参数",
            basis=req.basis,
            scope=req.scope,
        )

    raw_due = confirmed_facts.get(deadline_key)
    if _is_missing(raw_due):
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.MISSING_INFO,
            reason=f"缺少通知截止时间：{deadline_key}",
            missing_fields=[deadline_key],
            basis=req.basis,
            computed_deadline=None,
            scope=req.scope,
        )

    due = _parse_aware_datetime(raw_due)
    if due is None:
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.NEEDS_USER_REVIEW,
            reason=f"通知截止时间 {deadline_key} 格式无效或缺少时区",
            basis=req.basis,
            scope=req.scope,
        )

    raw_action = confirmed_facts.get(action_key)
    if _is_missing(raw_action):
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.MISSING_INFO,
            reason=f"缺少操作完成时间：{action_key}",
            missing_fields=[action_key],
            basis=req.basis,
            computed_deadline=due,
            scope=req.scope,
        )

    action = _parse_aware_datetime(raw_action)
    if action is None:
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.NEEDS_USER_REVIEW,
            reason=f"操作完成时间 {action_key} 格式无效或缺少时区",
            basis=req.basis,
            computed_deadline=due,
            scope=req.scope,
        )

    passed = action <= due
    return RequirementEvaluation(
        requirement_id=req.requirement_id,
        title=req.title,
        status=EvaluationStatus.MATCHED if passed else EvaluationStatus.NOT_MATCHED,
        reason="在通知期限内完成确认" if passed else f"晚于通知截止时间 ({due.isoformat()})",
        basis=req.basis,
        computed_deadline=due,
        scope=req.scope,
    )


def _eval_any_minimum(
    req: ExtractedRequirement,
    params: dict[str, Any],
    confirmed_facts: dict[str, object],
) -> RequirementEvaluation:
    raw_minimum = params.get("minimum")
    if not isinstance(raw_minimum, dict) or not raw_minimum:
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.NEEDS_USER_REVIEW,
            reason="任一最低标准规则缺少有效的 minimum 参数映射",
            basis=req.basis,
            scope=req.scope,
        )
    minimum: dict[str, float] = {}
    for key, threshold in raw_minimum.items():
        if (
            not isinstance(key, str)
            or not isinstance(threshold, (int, float))
            or isinstance(threshold, bool)
        ):
            return RequirementEvaluation(
                requirement_id=req.requirement_id,
                title=req.title,
                status=EvaluationStatus.NEEDS_USER_REVIEW,
                reason="任一最低标准规则包含非数值阈值",
                basis=req.basis,
                scope=req.scope,
            )
        minimum[key] = float(threshold)
    operator = str(params.get("operator", ">="))
    qualifier = str(params.get("qualifier", "")).strip()
    qualifier_note = f"（规则限定：{qualifier}）" if qualifier else ""

    for key, threshold in minimum.items():
        val = confirmed_facts.get(key)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            met = float(val) >= float(threshold) if operator == ">=" else float(val) > float(threshold)
            if met:
                return RequirementEvaluation(
                    requirement_id=req.requirement_id,
                    title=req.title,
                    status=EvaluationStatus.MATCHED,
                    reason=f"{key}={val} 满足任一最低要求{qualifier_note}",
                    basis=req.basis,
                    scope=req.scope,
                )

    missing = [k for k in minimum if confirmed_facts.get(k) is None]
    if missing:
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.MISSING_INFO,
            reason=f"尚无达标项，待补充其他可替代项：{', '.join(missing)}{qualifier_note}",
            missing_fields=missing,
            basis=req.basis,
            scope=req.scope,
        )

    return RequirementEvaluation(
        requirement_id=req.requirement_id,
        title=req.title,
        status=EvaluationStatus.NOT_MATCHED,
        reason=f"所有替代项均未达到最低标准{qualifier_note}",
        basis=req.basis,
        scope=req.scope,
    )


def _eval_materials(
    req: ExtractedRequirement,
    params: dict[str, Any],
    confirmed_facts: dict[str, object],
) -> RequirementEvaluation:
    required = [str(k) for k in params.get("required_facts", req.required_fact_keys)]
    gaps = [k for k in required if confirmed_facts.get(k) is not True]
    if gaps:
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.MISSING_INFO,
            reason=f"缺少已确认材料或条件：{', '.join(gaps)}",
            missing_fields=gaps,
            basis=req.basis,
            scope=req.scope,
        )
    return RequirementEvaluation(
        requirement_id=req.requirement_id,
        title=req.title,
        status=EvaluationStatus.MATCHED,
        reason="所需材料与已确认事实齐全",
        basis=req.basis,
        scope=req.scope,
    )


def _eval_letters(
    req: ExtractedRequirement,
    params: dict[str, Any],
    confirmed_facts: dict[str, object],
) -> RequirementEvaluation:
    accepted_ranks = set(params.get("accepted_ranks", []))
    checks: dict[str, object] = params.get("checks", {})
    min_distinct = int(params.get("min_distinct", 1))
    doc_name = str(params.get("document_name", "推荐信"))

    raw_letters = confirmed_facts.get("letters")
    eligible: set[str] = set()
    if isinstance(raw_letters, list):
        for letter in raw_letters:
            if not isinstance(letter, dict):
                continue
            alias = letter.get("alias")
            if not isinstance(alias, str) or not alias:
                continue
            if accepted_ranks and letter.get("rank") not in accepted_ranks:
                continue
            if all(letter.get(k) is expected for k, expected in checks.items()):
                eligible.add(alias)

    shortfall = min_distinct - len(eligible)
    if shortfall > 0:
        gap_text = f"合规{doc_name}还缺{shortfall}份"
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.MISSING_INFO,
            reason=gap_text,
            missing_fields=[gap_text],
            basis=req.basis,
            scope=req.scope,
        )

    return RequirementEvaluation(
        requirement_id=req.requirement_id,
        title=req.title,
        status=EvaluationStatus.MATCHED,
        reason=f"合规{doc_name}数量已达到 {min_distinct} 份",
        basis=req.basis,
        scope=req.scope,
    )


def _eval_legacy(
    req: ExtractedRequirement,
    confirmed_facts: dict[str, object],
) -> RequirementEvaluation:
    if req.official_deadline is not None and len(req.required_fact_keys) == 1:
        fact_key = req.required_fact_keys[0]
        raw_val = confirmed_facts.get(fact_key)
        if _is_missing(raw_val):
            return RequirementEvaluation(
                requirement_id=req.requirement_id,
                title=req.title,
                status=EvaluationStatus.MISSING_INFO,
                reason=f"缺少已确认个人字段：{fact_key}",
                missing_fields=[fact_key],
                basis=req.basis,
                computed_deadline=req.official_deadline,
                scope=req.scope,
            )
        parsed = _parse_aware_datetime(raw_val)
        if parsed is not None and req.official_deadline.tzinfo is not None:
            passed = parsed < req.official_deadline
            return RequirementEvaluation(
                requirement_id=req.requirement_id,
                title=req.title,
                status=EvaluationStatus.MATCHED if passed else EvaluationStatus.NOT_MATCHED,
                reason="操作时间在官方期限内" if passed else "操作时间超出官方期限",
                basis=req.basis,
                computed_deadline=req.official_deadline,
                scope=req.scope,
            )

    req_missing = [
        k for k in req.required_fact_keys if k not in confirmed_facts or confirmed_facts[k] is None
    ]
    if req_missing:
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.MISSING_INFO,
            reason=f"缺少已确认个人字段：{', '.join(req_missing)}",
            missing_fields=req_missing,
            basis=req.basis,
            scope=req.scope,
        )

    return RequirementEvaluation(
        requirement_id=req.requirement_id,
        title=req.title,
        status=EvaluationStatus.MATCHED,
        reason="规则依据与所需已确认事实齐全",
        basis=req.basis,
        scope=req.scope,
    )


def _collect_source_issues(
    req: ExtractedRequirement,
    sources_by_id: dict[str, SourceDocument],
) -> list[str]:
    issues: list[str] = []
    required_attachments = set(req.required_attachments)
    for cite in req.basis:
        doc = sources_by_id.get(cite.source_version_id)
        if doc is None:
            issues.append(f"引用来源 {cite.source_version_id} 不存在")
            continue
        if doc.source_status != "active":
            issues.append(f"来源 {doc.title} 当前状态为 {doc.source_status}")
        if doc.auto_check_status in ("failed", "conflict"):
            issues.append(f"来源 {doc.title} 自动检查状态为 {doc.auto_check_status}")
        if doc.is_repost or doc.roi_status == "reposted":
            issues.append(f"来源 {doc.title} 为转载，未经官方原文核验")
        if doc.is_expired or doc.roi_status == "expired":
            issues.append(f"来源 {doc.title} 已过期")
        if doc.roi_status == "ambiguous":
            issues.append(f"来源 {doc.title} 适用范围或表述不明确")
        if required_attachments and doc.missing_attachments:
            relevant_missing = [a for a in doc.missing_attachments if a in required_attachments]
            if relevant_missing:
                issues.append(f"来源 {doc.title} 缺失关联附件：{', '.join(relevant_missing)}")
    return issues


def collect_source_gaps(
    sources: list[SourceDocument],
    evaluations: list[RequirementEvaluation],
) -> list[SourceGap]:
    """Collect explicit source and evaluation gaps for UI review."""
    gaps: list[SourceGap] = []
    for doc in sources:
        if doc.is_repost or doc.roi_status == "reposted":
            gaps.append(
                SourceGap(
                    gap_type="repost_only",
                    description=f"来源《{doc.title}》为转载内容，需核对官方原文",
                    source_version_id=doc.source_version_id,
                )
            )
        if doc.is_expired or doc.roi_status == "expired":
            gaps.append(
                SourceGap(
                    gap_type="expired_source",
                    description=f"来源《{doc.title}》已超过适用窗口或标记过期",
                    source_version_id=doc.source_version_id,
                )
            )
        if doc.auto_check_status in ("failed", "conflict") or doc.roi_status == "ambiguous":
            gaps.append(
                SourceGap(
                    gap_type="scope_unclear",
                    description=(
                        f"来源《{doc.title}》状态异常"
                        f"（auto_check={doc.auto_check_status}, roi={doc.roi_status}）"
                    ),
                    source_version_id=doc.source_version_id,
                )
            )
        for att in doc.missing_attachments:
            gaps.append(
                SourceGap(
                    gap_type="missing_attachment",
                    description=f"来源《{doc.title}》缺少附件：{att}",
                    source_version_id=doc.source_version_id,
                )
            )
        for rng in doc.unread_ranges:
            gaps.append(
                SourceGap(
                    gap_type="read_failed",
                    description=f"来源《{doc.title}》存在未读取范围：{rng}",
                    source_version_id=doc.source_version_id,
                )
            )

    for ev in evaluations:
        if ev.status == EvaluationStatus.NEEDS_USER_REVIEW:
            gaps.append(
                SourceGap(
                    gap_type="ambiguous_clause",
                    description=f"{ev.title}：{ev.reason}",
                    source_version_id=ev.basis[0].source_version_id if ev.basis else None,
                    locator=ev.basis[0].locator if ev.basis else None,
                    related_requirement_ids=[ev.requirement_id],
                )
            )
        elif ev.status == EvaluationStatus.MISSING_INFO:
            gaps.append(
                SourceGap(
                    gap_type="missing_basis",
                    description=f"{ev.title}：{ev.reason}",
                    source_version_id=ev.basis[0].source_version_id if ev.basis else None,
                    locator=ev.basis[0].locator if ev.basis else None,
                    related_requirement_ids=[ev.requirement_id],
                )
            )
    return gaps


def find_expired_plan_tasks(plan: CandidatePlan, now: datetime) -> list[str]:
    """Return task_ids in plan whose official deadline has already passed relative to now."""
    now_shanghai = now.astimezone(SHANGHAI) if now.tzinfo is not None else now.replace(tzinfo=SHANGHAI)
    expired_ids: list[str] = []
    for task in plan.tasks:
        deadline_at = task.official_deadline_at or task.official_deadline
        if deadline_at is not None:
            if deadline_at < now_shanghai:
                expired_ids.append(task.task_id)
        elif task.official_deadline_date is not None and task.official_deadline_date < now_shanghai.date():
            expired_ids.append(task.task_id)
    return expired_ids


def _parse_aware_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else None
    return None


def _is_missing(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())
