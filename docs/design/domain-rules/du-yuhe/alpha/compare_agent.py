"""Compare selected fixture outcomes with the real Agent branch validator, without invoking an LLM."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from verify import indexed, load_file

PROBES = ("A04", "A05", "A09", "A10", "A11", "A12", "A13", "A14", "A17", "A21", "A22", "A28", "A29")


def fact_keys(rule):
    p = rule["parameters"]
    if rule["kind"] == "any_minimum":
        return list(p["minimum"])
    if rule["kind"] == "relative_deadline":
        return [p["received_fact"], p["action_fact"]]
    if rule["kind"] == "fixed_deadline":
        return [p["fact"]]
    return p.get("required_facts", [])


def citation(c):
    return {key: c[key] for key in ("source_version_id", "locator", "excerpt")}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("checkout", type=Path, help="含 backend/src/backend/agent 的本地项目根目录")
    args = cli.parse_args()
    source_root = args.checkout.resolve() / "backend" / "src"
    if not (source_root / "backend" / "agent" / "validators.py").is_file():
        cli.exit(2, "给定目录缺少 Agent 判定器。\n")
    sys.path.insert(0, str(source_root))
    from backend.agent.schemas import CandidatePlan, ExtractedRequirement, SourceDocument
    from backend.agent.validators import evaluate_requirements, validate_candidate_plan

    sources = indexed(load_file("sources.json")["sources"], "source_id")
    rules = indexed(load_file("rules.json")["rules"], "requirement_id")
    cases = indexed(load_file("cases.json")["cases"], "case_id")
    plan = load_file("plan.json")
    errors = validate_candidate_plan(CandidatePlan.model_validate(plan["candidate_plan"]),
                                     expected_workspace_version=plan["inputs"]["workspace_version"])
    print("候选计划结构与分支校验", errors or "通过")
    differences = 0
    for cid in PROBES:
        case = cases[cid]
        rule = rules[case["requirement_id"]]
        main_source = sources[rule["source_id"]]
        missing = case.get("source_state", {})
        docs = {}
        for src in sources.values():
            if src["source_id"] in missing:
                continue
            version = src["source_version_id"]
            refs = [c["excerpt"] for c in rule["basis"] if c["source_version_id"] == version]
            if not refs:
                continue
            missing_attachments = [sources[k]["title"] for k in missing
                                   if sources[k].get("parent_source_id") == src["source_id"]]
            docs[version] = SourceDocument(
                source_version_id=version, title=src["title"], url=src["url"], publisher=src["publisher"],
                year=src["scope"]["intake_year"], content="\n".join(refs), missing_attachments=missing_attachments,
                is_expired=(case.get("mode") == "当前办理" and src["use_as_of_check"] == "历史批次"),
            )
        req = ExtractedRequirement(
            requirement_id=rule["requirement_id"], title=rule["title"],
            obligation="待核实" if rule["kind"] == "any_minimum" else "官方必需",
            required_fact_keys=fact_keys(rule), basis=[citation(c) for c in rule["basis"]],
            official_deadline=(rule["parameters"]["before"] if rule["kind"] == "fixed_deadline" else None),
        )
        outcomes, _ = evaluate_requirements([req], docs, case["confirmed_facts"])
        status = outcomes[0].status.value if len(outcomes) == 1 else f"返回{len(outcomes)}项"
        expected = case["expected"]["status"]
        equal = status == expected
        differences += not equal
        print(f"{cid}  {main_source['source_id']:2}  预期 {expected}  实际 {status}  {'一致' if equal else '有差异'}")
    print(f"{len(PROBES)} 项状态对照，{len(PROBES)-differences} 项一致，{differences} 项有差异。")
    return 1 if errors or differences else 0


if __name__ == "__main__":
    sys.exit(main())
