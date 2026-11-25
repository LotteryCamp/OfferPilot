"""Exercise candidate decisions through the business API and an isolated PostgreSQL database."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

from verify import indexed, instant, load_file, require

API = "/api/v1"


def payload(response, status):
    require(response.status_code == status, f"{response.request.method} {response.request.url.path}: "
            f"预期 HTTP {status}，实际 {response.status_code} {response.text}")
    return response.json()


def prepare_pending_plan(client, matter, task, citations, as_of):
    from backend.basis import compute_basis_version
    from backend.services.common import transaction
    from backend.services.plans import collect_basis_input
    from backend.tables import candidate_plan, candidate_plan_item, candidate_plan_item_source
    from sqlalchemy import insert, update

    matter_id, plan_id, item_id = UUID(matter), uuid4(), uuid4()
    deadline = instant(task["official_deadline"])
    state = client.app.state
    with state.session_factory() as session, transaction(session, state.settings):
        session.execute(insert(candidate_plan).values(
            id=plan_id, matter_id=matter_id, version_no=1, status="draft",
            basis_version="0" * 64, basis_input={}, generated_at=as_of,
        ))
        session.execute(insert(candidate_plan_item).values(
            id=item_id, plan_id=plan_id, seq=1, title=task["title"], obligation_nature="required",
            official_deadline_date=deadline.date(), official_deadline_at=deadline,
            suggested_date=date.fromisoformat(task["suggested_date"]), evidence_required=True,
            depends_on_item_ids=[], created_at=as_of,
        ))
        session.execute(insert(candidate_plan_item_source), [
            {**citation, "id": uuid4(), "plan_item_id": item_id,
             "source_id": UUID(citation["source_id"]), "snapshot_id": UUID(citation["snapshot_id"])}
            for citation in citations
        ])
        basis = collect_basis_input(session, matter_id, plan_id)
        session.execute(update(candidate_plan).where(candidate_plan.c.id == plan_id).values(
            status="pending", basis_version=compute_basis_version(basis), basis_input=basis,
        ))
    return str(plan_id)


def create_example(client, matter, source, context, task, as_of):
    fragments = [
        {"locator_kind": "section", "locator": c["locator"], "quote": c["excerpt"]}
        for c in task["basis"]
    ]
    source_input = {
        "url": source["url"],
        "publisher": source["publisher"],
        "title": source["title"],
        "scope": "2027届本院本科生校内推荐",
        "scope_year": context["intake_year"],
        "published_date": source["published_on"],
        "content": "\n".join(f["quote"] for f in fragments),
        "fragments": fragments,
    }
    registered = payload(client.post(f"{API}/matters/{matter}/sources", json=source_input), 201)
    require(registered["snapshot"]["is_current"], "回放开始时需要原文快照处于当前版本")
    citations = [
        {**fragment, "source_id": registered["source"]["id"], "snapshot_id": registered["snapshot"]["id"]}
        for fragment in fragments
    ]
    plan_id = prepare_pending_plan(client, matter, task, citations, as_of)
    return plan_id, source_input, registered["snapshot"]


def decision(client, plan_id, verb, key, status=200):
    return payload(client.post(f"{API}/candidate-plans/{plan_id}/{verb}", headers={"Idempotency-Key": key}), status)


def persisted_result(client, matter, plan_id, status, expected_count, decision_value):
    plan = payload(client.get(f"{API}/candidate-plans/{plan_id}"), 200)["plan"]
    tasks = payload(client.get(f"{API}/matters/{matter}/tasks"), 200)["tasks"]
    require(plan["status"] == status, f"候选终态预期 {status}，实际 {plan['status']}")
    actual_decision = plan["decision"]["decision"] if plan["decision"] is not None else None
    require(actual_decision == decision_value, f"决定记录预期 {decision_value}，实际 {actual_decision}")
    require(len(tasks) == expected_count, f"正式任务预期 {expected_count} 条，实际 {len(tasks)} 条")
    require({row["id"] for row in tasks} == {row["id"] for row in plan["tasks"]}, "候选与事项的任务不一致")
    return plan, tasks


def check_api(client, matter_ids, source, context, task, paths, as_of):
    matter, confirmed_matter, stale_matter = matter_ids
    plan_id, _, _ = create_example(client, matter, source, context, task, as_of)
    persisted_result(client, matter, plan_id, "pending", paths["P01"]["expected"]["final_formal_tasks"], None)
    rejection = decision(client, plan_id, "reject", str(uuid4()))
    require(rejection["status"] == "rejected", "拒绝未返回 rejected")
    persisted_result(client, matter, plan_id, "rejected", paths["P02"]["expected"]["final_formal_tasks"], "rejected")

    matter = confirmed_matter
    plan_id, _, snapshot = create_example(client, matter, source, context, task, as_of)
    key = str(uuid4())
    confirmed = decision(client, plan_id, "confirm", key)
    require(confirmed["status"] == "confirmed" and not confirmed["replayed"], "首次确认状态异常")
    _, tasks = persisted_result(client, matter, plan_id, "confirmed", paths["P03"]["expected"]["final_formal_tasks"], "confirmed")
    expected_citations = {(snapshot["id"], c["locator"]) for c in task["basis"]}
    require({(c["snapshot_id"], c["locator"]) for c in tasks[0]["sources"]} == expected_citations,
            "确认写入的任务须保留原快照和两处定位")
    repeated = decision(client, plan_id, "confirm", key)
    require(repeated["replayed"], "同一确认操作须返回重放结果")
    require([t["id"] for t in repeated["tasks"]] == [t["id"] for t in confirmed["tasks"]], "重试改变了任务标识")
    persisted_result(client, matter, plan_id, "confirmed", paths["P04"]["expected"]["final_formal_tasks"], "confirmed")

    matter = stale_matter
    plan_id, source_input, old_snapshot = create_example(client, matter, source, context, task, as_of)
    # Register a new test capture of the same source through the public API.
    new_input = {**source_input, "content": source_input["content"] + "\n【回归测试用新快照】"}
    new = payload(client.post(f"{API}/matters/{matter}/sources", json=new_input), 201)["snapshot"]
    require(new["id"] != old_snapshot["id"] and new["is_current"]
            and new["version_no"] > old_snapshot["version_no"], "登记后当前快照应前进")
    expected = paths["P05"]["expected"]
    refused = decision(client, plan_id, "confirm", str(uuid4()), 409)
    require(refused["error"]["code"] == expected["confirmation_error"], f"换版确认返回 {refused['error']['code']}")
    detail, _ = persisted_result(client, matter, plan_id, "expired", expected["final_formal_tasks"], None)
    require(detail["expired_at"] is not None, "换版应持久化候选的失效时间")
    print("P01–P05 后端验证通过：待确认、拒绝、确认、同键重试和来源换版。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path, help="提供业务 API 的 OfferPilot 本地目录")
    parser.add_argument("matter_ids", nargs=3, help="三个新的推免测试事项 ID")
    args = parser.parse_args()
    require(len(set(args.matter_ids)) == 3, "需要三个不同的测试事项")
    database_url = os.environ.get("OFFERPILOT_TEST_DATABASE_URL")
    if not database_url:
        parser.exit(2, "请设置指向独立测试库的 OFFERPILOT_TEST_DATABASE_URL。\n")
    source_root = args.checkout.resolve() / "backend" / "src"
    if not (source_root / "backend" / "services" / "decisions.py").is_file():
        parser.exit(2, "检出目录尚无候选确认业务服务。\n")
    sys.path.insert(0, str(source_root))
    from backend.clock import FixedClock
    from backend.config import Settings
    from backend.main import create_app
    from fastapi.testclient import TestClient

    example = load_file("plan.json")
    context = load_file("cases.json")["contexts"][example["context_id"]]
    sources = indexed(load_file("sources.json")["sources"], "source_version_id")
    paths = indexed(example["decision_cases"], "case_id")
    (task,) = example["candidate_plan"]["tasks"]
    source = sources[task["basis"][0]["source_version_id"]]
    settings = Settings(database_url=database_url)
    as_of = instant(example["as_of"])
    with TestClient(create_app(settings, clock=FixedClock(as_of))) as client:
        check_api(client, args.matter_ids, source, context, task, paths, as_of)


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, OSError) as error:
        sys.exit(f"后端验证失败：{error}")
