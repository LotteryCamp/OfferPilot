"""Check the published fixture set offline. This is a reference comparison, with no task writes."""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
MATCH = "按现有信息符合"
FAIL = "按现有信息不符合"
MISSING = "待补充信息"
REVIEW = "待用户核对"


def load_file(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def indexed(rows, key):
    result = {row[key]: row for row in rows}
    require(len(result) == len(rows), f"{key} 有重复标识")
    return result


def instant(value):
    stamp = datetime.fromisoformat(value)
    require(stamp.utcoffset() is not None, f"时间缺少时区 {value}")
    return stamp


def matched_scope(rule, source, context):
    missing = []
    for key, expected in (source["scope"] | rule["scope"]).items():
        actual = context.get(key)
        if actual is None:
            missing.append(key)
        elif actual not in (expected if isinstance(expected, list) else [expected]):
            return "不匹配", []
    return ("范围不明", missing) if missing else ("匹配", [])


def deadline_result(params, facts, kind):
    start = None
    if kind == "fixed_deadline":
        due = instant(params["before"])
        fact = params["fact"]
    elif kind == "relative_deadline":
        field = params["received_fact"]
        if not facts.get(field):
            return MISSING, [field], None
        start = instant(facts[field])
        due = start + timedelta(hours=params["duration_hours"])
        fact = params["action_fact"]
    else:
        field = params["deadline_fact"]
        if not facts.get(field):
            return MISSING, [field], None
        due = instant(facts[field])
        fact = params["action_fact"]

    if not facts.get(fact):
        return MISSING, [fact], due.isoformat()
    action = instant(facts[fact])
    within = action < due if kind == "fixed_deadline" else action <= due
    if start is not None:
        within = start <= action <= due
    return MATCH if within else FAIL, [], due.isoformat()


def check_clause(rule, facts):
    kind, p = rule["kind"], rule["parameters"]
    if kind == "coverage_gap":
        return REVIEW, p["missing_documents"], None
    if kind in {"fixed_deadline", "relative_deadline", "notice_deadline"}:
        return deadline_result(p, facts, kind)
    if kind == "materials":
        gaps = [f for f in p["required_facts"] if facts.get(f) is not True]
        return (MISSING if gaps else MATCH), gaps, None
    if kind == "any_minimum":
        if any(facts.get(k) is not None and facts[k] >= n for k, n in p["minimum"].items()):
            return MATCH, [], None
        gaps = [k for k in p["minimum"] if facts.get(k) is None]
        return (MISSING if gaps else FAIL), gaps, None
    if kind == "letters":
        eligible = {
            letter["alias"] for letter in facts.get("letters", [])
            if letter.get("rank") in p["accepted_ranks"]
            and all(letter.get(k) is v for k, v in p["checks"].items())
        }
        shortfall = p["min_distinct"] - len(eligible)
        gaps = [f"合规{p['document_name']}还缺{shortfall}份"] if shortfall > 0 else []
        return (MISSING if gaps else MATCH), gaps, None
    if kind == "catalog_row":
        # Membership of the single indexed row is established by the two citations.
        return MATCH, [], None
    raise ValueError(f"未知样例类型 {kind}")


def evaluate_case(case, context, rule, sources, versions, default_mode):
    context = context | case.get("scope_overrides", {})
    src = sources[rule["source_id"]]
    scope, gaps = matched_scope(rule, src, context)
    status, deadline, used = None, None, []
    if scope == "范围不明":
        status = REVIEW
    elif scope == "匹配":
        mode = case.get("mode", default_mode)
        require(mode in {"历史回放", "当前办理"}, f"未知模式 {mode}")
        if mode == "当前办理" and src["use_as_of_check"] == "历史批次":
            status, gaps = REVIEW, ["历史批次"]
        else:
            unavailable = case.get("source_state", {})
            require(set(unavailable) <= sources.keys(), "来源状态引用未知来源")
            require(set(unavailable.values()) <= {"读取失败", "附件不可读"}, "未知的来源缺口状态")
            main_sources = [versions[c["source_version_id"]]["source_id"] for c in rule["basis"]]
            missing = [s for s in main_sources if s in unavailable]
            used = [s for s in main_sources if s not in unavailable]
            if rule["source_id"] in missing and rule.get("fallback_basis"):
                alternatives = [versions[c["source_version_id"]]["source_id"] for c in rule["fallback_basis"]]
                available = [s for s in alternatives if s not in unavailable]
                if available:
                    used.append(available[0])
                    missing.remove(rule["source_id"])
                else:
                    missing.extend(alternatives)
            if missing:
                status, gaps = REVIEW, missing
            else:
                status, gaps, deadline = check_clause(rule, case["confirmed_facts"])
    return dict(scope_match=scope, status=status, gaps=gaps, official_deadline=deadline, used_sources=used)


def citation_key(cite):
    return cite["source_version_id"], cite["locator"], cite["excerpt"]


def replay_decisions(path, tasks, source_versions):
    basis = {cite["source_version_id"] for task in tasks.values() for cite in task["basis"]}
    current = set(source_versions)
    state = "待确认"
    confirmed_operation = None
    confirmation_error = None
    new_tasks = []

    for step in path["steps"]:
        action = step["action"]
        written = 0
        if action == "查看":
            pass
        elif action == "来源换版":
            old = step["previous_source_version_id"]
            replacement = step["new_source_version_id"]
            require(state == "待确认", "换版样例需要待确认的候选")
            require(old in current and replacement not in current, "来源换版前后版本不匹配")
            current.remove(old)
            current.add(replacement)
        elif action == "确认":
            operation = step["operation_id"]
            require(isinstance(operation, str) and operation.strip(), "确认操作缺少操作编号")
            if operation != confirmed_operation:
                require(state == "待确认", "只有待确认候选可以首次确认")
                if basis <= current:
                    state, confirmed_operation = "已确认", operation
                    written = len(tasks)
                else:
                    state, confirmation_error = "需重新生成", "basis_changed"
        elif action == "拒绝":
            require(state == "待确认", "只有待确认候选可以拒绝")
            state = "已拒绝"
        elif action == "切换到当前办理":
            as_of = instant(step["as_of"])
            expired = any(t["official_deadline"] and instant(t["official_deadline"]) < as_of
                          for t in tasks.values())
            require(state == "待确认" and expired, "当前办理样例需要已过官方期限的待确认候选")
            state = "仅供历史参考"
        else:
            raise ValueError(f"未知候选决定操作 {action}")
        new_tasks.append(written)

    return {
        "candidate_state": state,
        "confirmation_error": confirmation_error,
        "new_tasks_per_step": new_tasks,
        "final_formal_tasks": path["starting_formal_tasks"] + sum(new_tasks),
    }


def check_plan(example, cases, contexts, rules, versions):
    plan = example["candidate_plan"]
    tasks = indexed(plan["tasks"], "task_id")
    trace = indexed(example["trace"], "task_id")
    base_case = cases[example["input_case_id"]]
    require(base_case["context_id"] == example["context_id"], "候选来源事项不一致")
    require(base_case["confirmed_facts"] == example["inputs"]["confirmed_facts"], "候选输入事实不一致")
    require(example["as_of"] == contexts[example["context_id"]]["as_of"], "候选时钟不一致")
    require(plan["workspace_version"] == example["inputs"]["workspace_version"], "候选工作区版本不一致")
    require(trace.keys() == tasks.keys(), "任务引用表与候选不匹配")
    for tid, task in tasks.items():
        entry = trace[tid]
        linked = [rules[r] for r in entry["requirement_ids"]]
        inputs = [cases[c] for c in entry["input_case_ids"]]
        require(all(c["context_id"] == example["context_id"] for c in inputs), f"{tid} 跨事项")
        require({r["requirement_id"] for r in linked} == {c["requirement_id"] for c in inputs}, f"{tid} 规则与样例不符")
        expected = {citation_key(c) for r in linked for c in r["basis"]}
        require(expected == {citation_key(c) for c in task["basis"]}, f"{tid} 出处不一致")
        for version, _, _ in expected:
            require(version in versions and version in example["inputs"]["current_source_versions"], "快照版本不匹配")
        deadlines = [r["parameters"]["before"] for r in linked if r["kind"] == "fixed_deadline"]
        require(deadlines == [task["official_deadline"]], "官方期限缺少依据")
        require(date.fromisoformat(task["suggested_date"]) <= instant(deadlines[0]).date(), "建议日超出官方期限")
        require(set(task["depends_on"]) <= tasks.keys() - {tid}, "无效的任务依赖")
    for path in indexed(example["decision_cases"], "case_id").values():
        actual = replay_decisions(path, tasks, example["inputs"]["current_source_versions"])
        for field, value in actual.items():
            expected = path["expected"][field]
            require(expected == value, f"{path['case_id']} {field} 实际 {value!r}，预期 {expected!r}")


def main():
    catalog, ruleset, suite, plan = [load_file(n) for n in ("sources.json", "rules.json", "cases.json", "plan.json")]
    require(len({x["fixture_version"] for x in (catalog, ruleset, suite, plan)}) == 1, "文件版本不一致")
    sources = indexed(catalog["sources"], "source_id")
    versions = indexed(catalog["sources"], "source_version_id")
    rules = indexed(ruleset["rules"], "requirement_id")
    cases = indexed(suite["cases"], "case_id")
    for src in sources.values():
        digest = src["sha256"]
        require(bool(re.fullmatch("[0-9a-f]{64}", digest)), f"来源摘要无效 {src['source_id']}")
        require(src["source_version_id"] == f"{src['source_id']}-{digest[:12]}", "来源版本不匹配")
        require(urlsplit(src["url"]).scheme == "https" and src["http_status"] == 200, "来源记录不完整")
        require(date.fromisoformat(src["published_on"]) <= instant(src["fetched_at"]).date(), "来源日期不一致")
        if src.get("parent_source_id"):
            require(sources[src["parent_source_id"]]["scope"] == src["scope"], "附件与原通知范围不一致")
    for rule in rules.values():
        require(rule["basis"] and rule["domain_rules"], f"{rule['requirement_id']} 缺少依据")
        for c in rule["basis"] + rule.get("fallback_basis", []):
            src = versions[c["source_version_id"]]
            require(src["scope"] == sources[rule["source_id"]]["scope"], "引用越过院校或年度范围")
            require(all(c[k] for k in ("locator", "excerpt", "section_start", "section_end")), "引用缺少定位")
    require({c["requirement_id"] for c in cases.values()} == rules.keys(), "存在未覆盖或未知规则")
    for cid, case in cases.items():
        ctx = suite["contexts"][case["context_id"]]
        as_of = instant((ctx | case.get("scope_overrides", {}))["as_of"])
        for key, value in case["confirmed_facts"].items():
            if key.endswith("_at") and value is not None:
                require(instant(value) <= as_of, f"{cid} 已发生事件晚于回放时刻")
        actual = evaluate_case(case, ctx, rules[case["requirement_id"]], sources, versions, suite["default_mode"])
        for field, value in case["expected"].items():
            require(actual[field] == value, f"{cid} {field} 实际 {actual[field]!r}，预期 {value!r}")
    check_plan(plan, cases, suite["contexts"], rules, versions)
    print(f"离线校验通过：{len(sources)} 个来源版本，{len(rules)} 条规则，{len(cases)} 个领域用例。")
    print(f"候选引用及 {len(plan['decision_cases'])} 组决定的状态、原因和任务数一致。")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, TypeError, OSError) as error:
        sys.exit(f"校验失败：{error}")
