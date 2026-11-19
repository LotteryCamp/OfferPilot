"""Compare selected fixture outcomes with the real Agent branch validator, without invoking an LLM."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from verify import MISSING, indexed, instant, load_file

PROBES = (
    "A01", "A02", "A03", "A04", "A05", "A07", "A09",
    "A10", "A11", "A12", "A13", "A14", "A15", "A16",
    "A17", "A18", "A19", "A20", "A21", "A22",
    "A26", "A27", "A28", "A29", "A31", "A32", "A33", "A36", "A39",
)


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

    if not {"rule_kind", "rule_parameters", "required_attachments"} <= ExtractedRequirement.model_fields.keys():
        cli.exit(2, "Agent 分支需支持结构化规则和条款级附件依赖。\n")

    catalog = load_file("sources.json")["sources"]
    sources = indexed(catalog, "source_id")
    versions = indexed(catalog, "source_version_id")
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
                source_id=src["source_id"], source_version_id=version,
                title=src["title"], url=src["url"], publisher=src["publisher"],
                year=src["scope"]["intake_year"], content="\n".join(refs), missing_attachments=missing_attachments,
                is_expired=(case.get("mode") == "当前办理" and src["use_as_of_check"] == "历史批次"),
            )
        attachments = [versions[c["source_version_id"]] for c in rule["basis"]]
        req = ExtractedRequirement(
            requirement_id=rule["requirement_id"], title=rule["title"],
            obligation="待核实" if rule["kind"] == "any_minimum" else "官方必需",
            rule_kind=rule["kind"], rule_parameters=rule["parameters"],
            required_attachments=[s["title"] for s in attachments if s.get("parent_source_id")],
            basis=[citation(c) for c in rule["basis"]],
            official_deadline=(rule["parameters"]["before"] if rule["kind"] == "fixed_deadline" else None),
        )
        outcomes, _ = evaluate_requirements([req], docs, case["confirmed_facts"])
        if len(outcomes) != 1:
            differences += 1
            print(f"{cid} 判定返回 {len(outcomes)} 项，预期 1 项")
            continue
        outcome = outcomes[0]
        expected = case["expected"]
        due = instant(expected["official_deadline"]) if expected["official_deadline"] else None
        fields = {
            "状态": (outcome.status.value, expected["status"]),
            "期限": (outcome.computed_deadline, due),
            "原文定位": ([citation(c.model_dump()) for c in outcome.basis], [citation(c) for c in rule["basis"]]),
        }
        if expected["status"] == MISSING:
            fields["缺失字段"] = (outcome.missing_fields, expected["gaps"])
        if req.rule_kind == "any_minimum":
            fields["原则性限定"] = (rule["parameters"]["qualifier"] in outcome.reason, True)
        mismatch = [(field, actual, want) for field, (actual, want) in fields.items() if actual != want]
        differences += bool(mismatch)
        for field, actual, want in mismatch:
            print(f"{cid} {field} 实际 {actual!r}，预期 {want!r}")
    print(f"{len(PROBES)} 项 Agent 对照，{len(PROBES)-differences} 项一致，{differences} 项有差异。")
    return 1 if errors or differences else 0


if __name__ == "__main__":
    sys.exit(main())
