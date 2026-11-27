"""Deterministic domain-constraint validators for Agent outputs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
from typing import Any, Literal

from backend.agent.contracts import build_client_item_id_map
from backend.agent.schemas import (
    AgentError,
    AgentErrorCode,
    CandidatePlan,
    EvaluationStatus,
    ExtractedRequirement,
    RequirementEvaluation,
    SourceDocument,
    SourceGap,
)


def normalize_candidate_deadlines(plan: CandidatePlan, timezone: tzinfo) -> list[str]:
    """Derive deadline dates from timestamps in the configured business timezone."""
    violations: list[str] = []
    for task in plan.tasks:
        if task.official_deadline_at is None:
            continue
        local_date = task.official_deadline_at.astimezone(timezone).date()
        if task.official_deadline_date is None:
            task.official_deadline_date = local_date
        elif task.official_deadline_date != local_date:
            violations.append(
                f"任务 {task.task_id} 的 official_deadline_date 与 "
                f"official_deadline_at 在 {timezone} 下的日期不一致"
            )
    return violations


def validate_candidate_plan(
    plan: CandidatePlan,
    expected_workspace_version: int,
    sources_by_id: dict[str, SourceDocument] | None = None,
    *,
    timezone: tzinfo,
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
    try:
        build_client_item_id_map(plan.tasks)
    except ValueError as exc:
        violations.append(str(exc))

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
                violations.append(
                    f"任务 {task.task_id} 依赖了不存在的前置任务 {dep_id}"
                )

        effective_deadline_date = _task_deadline_date(
            task.official_deadline_date,
            task.official_deadline_at or task.official_deadline,
            timezone=timezone,
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
    *,
    timezone: tzinfo,
) -> date | None:
    if deadline_at is not None:
        return deadline_at.astimezone(timezone).date()
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
            reason = (
                "；".join(source_issues) if source_issues else "条款含义需结合原文确认"
            )
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

    if kind == "any_of":
        return _eval_any_of(req, params, confirmed_facts)

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
        params.get("fact")
        or (req.required_fact_keys[0] if req.required_fact_keys else "submitted_at")
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
        reason="操作时间在官方期限内"
        if passed
        else f"操作时间晚于或超出官方期限 ({due.isoformat()})",
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
        reason="在相对时限内完成确认"
        if passed
        else f"已超出 {int(duration_hours)} 小时时限 ({due.isoformat()})",
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
        reason="在通知期限内完成确认"
        if passed
        else f"晚于通知截止时间 ({due.isoformat()})",
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

    invalid_fields: list[str] = []
    for key, threshold in minimum.items():
        val = confirmed_facts.get(key)
        numeric_val = _parse_finite_float(val)
        if numeric_val is not None:
            met = (
                numeric_val >= float(threshold)
                if operator == ">="
                else numeric_val > float(threshold)
            )
            if met:
                return RequirementEvaluation(
                    requirement_id=req.requirement_id,
                    title=req.title,
                    status=EvaluationStatus.MATCHED,
                    reason=f"{key}={val} 满足任一最低要求{qualifier_note}",
                    basis=req.basis,
                    scope=req.scope,
                )
        elif val is not None:
            invalid_fields.append(key)

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

    if invalid_fields:
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.NEEDS_USER_REVIEW,
            reason=f"以下字段格式非有效数值，待核对：{', '.join(invalid_fields)}{qualifier_note}",
            missing_fields=invalid_fields,
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


_ORDER_OPS = {"<=", "<", ">=", ">"}
_CONDITION_OPS = frozenset({*_ORDER_OPS, "=="})


@dataclass(frozen=True)
class _ConditionCheck:
    fact: str
    operator: str
    value: float | bool | str


def _format_num(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


def _format_scalar(value: float | bool | str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _format_num(float(value))
    return value


def _parse_condition_checks(
    raw_checks: object, *, label: str
) -> tuple[list[_ConditionCheck], str | None]:
    if not isinstance(raw_checks, list):
        return [], f"{label} 须为条件列表"
    checks: list[_ConditionCheck] = []
    for item in raw_checks:
        if not isinstance(item, dict):
            return [], f"{label} 包含非对象条件项"
        raw_fact = item.get("fact")
        if not isinstance(raw_fact, str) or not raw_fact.strip():
            return [], f"{label} 缺少有效的 fact 键名"
        fact = raw_fact.strip()

        operator = item.get("operator")
        if not isinstance(operator, str) or operator not in _CONDITION_OPS:
            return [], f"{label} 的条件 {fact} 使用了不支持的操作符"

        raw_val = item.get("value")
        parsed_val: float | bool | str
        if operator in _ORDER_OPS:
            if (
                isinstance(raw_val, bool)
                or not isinstance(raw_val, (int, float))
                or not math.isfinite(float(raw_val))
            ):
                return [], f"{label} 的比较条件 {fact} 缺少有限数值阈值"
            parsed_val = float(raw_val)
        elif isinstance(raw_val, bool):
            parsed_val = raw_val
        elif isinstance(raw_val, (int, float)) and math.isfinite(float(raw_val)):
            parsed_val = float(raw_val)
        elif isinstance(raw_val, str) and raw_val.strip():
            parsed_val = raw_val.strip()
        else:
            return [], f"{label} 的等值条件 {fact} 缺少有效的目标值"

        checks.append(_ConditionCheck(fact=fact, operator=operator, value=parsed_val))
    return checks, None


def _parse_any_of_params(
    params: dict[str, Any],
) -> tuple[
    tuple[list[_ConditionCheck], list[tuple[str, list[_ConditionCheck]]]] | None,
    str | None,
]:
    raw_all = params.get("all_required")
    all_required: list[_ConditionCheck] = []
    if raw_all is not None:
        all_required, err = _parse_condition_checks(
            raw_all, label="any_of 规则 all_required"
        )
        if err is not None:
            return None, err

    raw_paths = params.get("paths")
    if not isinstance(raw_paths, list) or not raw_paths:
        return None, "any_of 规则缺少有效的 paths 路径列表"

    paths: list[tuple[str, list[_ConditionCheck]]] = []
    for idx, raw_path in enumerate(raw_paths, start=1):
        if not isinstance(raw_path, dict):
            return None, f"any_of 路径 {idx} 须为对象"
        raw_checks = raw_path.get("checks")
        if not isinstance(raw_checks, list) or not raw_checks:
            return None, f"any_of 路径 {idx} 缺少有效条件列表 checks"
        checks, err = _parse_condition_checks(raw_checks, label=f"any_of 路径 {idx}")
        if err is not None:
            return None, err
        raw_label = raw_path.get("label")
        label = (
            raw_label.strip()
            if isinstance(raw_label, str) and raw_label.strip()
            else f"路径 {idx}"
        )
        paths.append((label, checks))

    return (all_required, paths), None


def _evaluate_condition_check(
    check: _ConditionCheck,
    confirmed_facts: dict[str, object],
) -> tuple[Literal["passed", "failed", "missing", "invalid"], str]:
    raw_val = confirmed_facts.get(check.fact)
    if _is_missing(raw_val):
        return "missing", check.fact

    expr = f"{check.fact} {check.operator} {_format_scalar(check.value)}"
    if check.operator in _ORDER_OPS:
        actual = _parse_finite_float(raw_val)
        if actual is None:
            return "invalid", check.fact
        target = float(check.value)
        if check.operator == "<=":
            ok = actual <= target
        elif check.operator == "<":
            ok = actual < target
        elif check.operator == ">=":
            ok = actual >= target
        else:
            ok = actual > target
        actual_text = _format_num(actual)
        return (
            "passed" if ok else "failed",
            f"{check.fact}={actual_text} {check.operator} {_format_num(target)}"
            if ok
            else f"{check.fact}={actual_text} 未满足 {expr}",
        )

    if isinstance(check.value, bool):
        if isinstance(raw_val, bool):
            actual_bool = raw_val
        elif isinstance(raw_val, str) and raw_val.strip().lower() in {"true", "false"}:
            actual_bool = raw_val.strip().lower() == "true"
        else:
            return "invalid", check.fact
        actual_text = "true" if actual_bool else "false"
        ok = actual_bool is check.value
    elif isinstance(check.value, (int, float)):
        actual = _parse_finite_float(raw_val)
        if actual is None:
            return "invalid", check.fact
        actual_text = _format_num(actual)
        ok = actual == float(check.value)
    else:
        if not isinstance(raw_val, str) or not raw_val.strip():
            return "invalid", check.fact
        actual_text = raw_val.strip()
        ok = actual_text.lower() == check.value.lower()

    return (
        "passed" if ok else "failed",
        f"{check.fact}={actual_text} == {_format_scalar(check.value)}"
        if ok
        else f"{check.fact}={actual_text} 未满足 {expr}",
    )


def _evaluate_check_group(
    checks: list[_ConditionCheck],
    confirmed_facts: dict[str, object],
) -> tuple[list[str], list[str], list[str], list[str]]:
    passed: list[str] = []
    failed: list[str] = []
    missing: list[str] = []
    invalid: list[str] = []
    for check in checks:
        outcome, detail = _evaluate_condition_check(check, confirmed_facts)
        if outcome == "passed":
            passed.append(detail)
        elif outcome == "failed":
            failed.append(detail)
        elif outcome == "missing":
            missing.append(detail)
        else:
            invalid.append(detail)
    return passed, failed, missing, invalid


def _eval_any_of(
    req: ExtractedRequirement,
    params: dict[str, Any],
    confirmed_facts: dict[str, object],
) -> RequirementEvaluation:
    parsed, parse_error = _parse_any_of_params(params)
    if parsed is None:
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.NEEDS_USER_REVIEW,
            reason=parse_error or "any_of 规则参数无效",
            basis=req.basis,
            scope=req.scope,
        )

    all_required, paths = parsed
    req_passed, req_failed, req_missing, req_invalid = _evaluate_check_group(
        all_required, confirmed_facts
    )
    if req_failed:
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.NOT_MATCHED,
            reason=f"未满足前置条件：{'；'.join(req_failed)}",
            basis=req.basis,
            scope=req.scope,
        )

    passed_paths: list[tuple[str, list[str]]] = []
    pending_paths: list[tuple[str, list[str], list[str]]] = []
    failed_paths: list[tuple[str, list[str]]] = []
    invalid_paths: list[tuple[str, list[str]]] = []

    for label, checks in paths:
        p_passed, p_failed, p_missing, p_invalid = _evaluate_check_group(
            checks, confirmed_facts
        )
        if p_failed:
            failed_paths.append((label, p_failed))
        elif p_invalid:
            invalid_paths.append((label, p_invalid))
        elif p_missing:
            pending_paths.append((label, p_passed, p_missing))
        else:
            passed_paths.append((label, p_passed))

    if passed_paths:
        label, p_passed = passed_paths[0]
        if req_invalid:
            dedup_invalid = list(dict.fromkeys(req_invalid))
            return RequirementEvaluation(
                requirement_id=req.requirement_id,
                title=req.title,
                status=EvaluationStatus.NEEDS_USER_REVIEW,
                reason=f"以下前置字段格式无效，待核对：{', '.join(dedup_invalid)}",
                missing_fields=dedup_invalid,
                basis=req.basis,
                scope=req.scope,
            )
        if req_missing:
            dedup_missing = list(dict.fromkeys(req_missing))
            return RequirementEvaluation(
                requirement_id=req.requirement_id,
                title=req.title,
                status=EvaluationStatus.MISSING_INFO,
                reason=(
                    f"已核验 {label}（{'；'.join(p_passed)}）；"
                    f"待补充前置条件：{', '.join(dedup_missing)}"
                ),
                missing_fields=dedup_missing,
                basis=req.basis,
                scope=req.scope,
            )
        verified = [*req_passed, *p_passed]
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.MATCHED,
            reason=f"满足条件（{label}）：{'；'.join(verified)}",
            basis=req.basis,
            scope=req.scope,
        )

    if len(failed_paths) == len(paths):
        failed_summary = "；".join(
            f"{label}（{'；'.join(msgs)}）" for label, msgs in failed_paths
        )
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.NOT_MATCHED,
            reason=f"未满足任一路径条件：{failed_summary}",
            basis=req.basis,
            scope=req.scope,
        )

    if req_invalid:
        dedup_invalid = list(
            dict.fromkeys([*req_invalid, *(f for _, inv in invalid_paths for f in inv)])
        )
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.NEEDS_USER_REVIEW,
            reason=f"以下字段格式无效，待核对：{', '.join(dedup_invalid)}",
            missing_fields=dedup_invalid,
            basis=req.basis,
            scope=req.scope,
        )

    if pending_paths:
        dedup_missing = list(
            dict.fromkeys(
                [*req_missing, *(f for _, _, pm in pending_paths for f in pm)]
            )
        )
        verified = list(
            dict.fromkeys(
                [*req_passed, *(chk for _, pp, _ in pending_paths for chk in pp)]
            )
        )
        reason = (
            f"已核验 {'；'.join(verified)}；待补充：{', '.join(dedup_missing)}"
            if verified
            else f"缺少已确认条件信息：{', '.join(dedup_missing)}"
        )
        return RequirementEvaluation(
            requirement_id=req.requirement_id,
            title=req.title,
            status=EvaluationStatus.MISSING_INFO,
            reason=reason,
            missing_fields=dedup_missing,
            basis=req.basis,
            scope=req.scope,
        )

    dedup_invalid = list(dict.fromkeys(f for _, inv in invalid_paths for f in inv))
    return RequirementEvaluation(
        requirement_id=req.requirement_id,
        title=req.title,
        status=EvaluationStatus.NEEDS_USER_REVIEW,
        reason=f"以下字段格式无效，待核对：{', '.join(dedup_invalid)}",
        missing_fields=dedup_invalid,
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
                status=EvaluationStatus.MATCHED
                if passed
                else EvaluationStatus.NOT_MATCHED,
                reason="操作时间在官方期限内" if passed else "操作时间超出官方期限",
                basis=req.basis,
                computed_deadline=req.official_deadline,
                scope=req.scope,
            )

    req_missing = [
        k
        for k in req.required_fact_keys
        if k not in confirmed_facts or confirmed_facts[k] is None
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
            relevant_missing = [
                a for a in doc.missing_attachments if a in required_attachments
            ]
            if relevant_missing:
                issues.append(
                    f"来源 {doc.title} 缺失关联附件：{', '.join(relevant_missing)}"
                )
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
        if (
            doc.auto_check_status in ("failed", "conflict")
            or doc.roi_status == "ambiguous"
        ):
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
                    source_version_id=ev.basis[0].source_version_id
                    if ev.basis
                    else None,
                    locator=ev.basis[0].locator if ev.basis else None,
                    related_requirement_ids=[ev.requirement_id],
                )
            )
        elif ev.status == EvaluationStatus.MISSING_INFO:
            gap_type = "missing_personal_fact" if ev.missing_fields else "missing_basis"
            gaps.append(
                SourceGap(
                    gap_type=gap_type,
                    description=f"{ev.title}：{ev.reason}",
                    source_version_id=ev.basis[0].source_version_id
                    if ev.basis
                    else None,
                    locator=ev.basis[0].locator if ev.basis else None,
                    related_requirement_ids=[ev.requirement_id],
                )
            )
    return gaps


def find_expired_plan_tasks(
    plan: CandidatePlan, now: datetime, *, timezone: tzinfo
) -> list[str]:
    """Return task_ids in plan whose official deadline has already passed relative to now."""
    local_now = (
        now.astimezone(timezone)
        if now.tzinfo is not None
        else now.replace(tzinfo=timezone)
    )
    expired_ids: list[str] = []
    for task in plan.tasks:
        deadline_at = task.official_deadline_at or task.official_deadline
        if deadline_at is not None:
            if deadline_at < local_now:
                expired_ids.append(task.task_id)
        elif (
            task.official_deadline_date is not None
            and task.official_deadline_date < local_now.date()
        ):
            expired_ids.append(task.task_id)
    return expired_ids


def _parse_finite_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        num = float(value)
        return num if math.isfinite(num) else None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            num = float(stripped)
        except ValueError:
            return None
        return num if math.isfinite(num) else None
    return None


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
