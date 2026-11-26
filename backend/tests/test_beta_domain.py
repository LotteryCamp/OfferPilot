"""Beta #74 source, rule and task regressions from reviewed public notices."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.agent.contracts import (
    build_candidate_plan_create_payload,
    build_requirements_batch_payload,
    to_api_self_check_conclusion,
)
from backend.agent.model_bridge import (
    ModelInvocationError,
    _validate_and_enrich_citations,
)
from backend.agent.schemas import (
    AgentErrorCode,
    CandidatePlan,
    CandidateTask,
    ExtractedRequirement,
    ObligationType,
    SourceCitation,
    SourceDocument,
    SourceFragmentRecord,
)
from backend.agent.validators import (
    collect_source_gaps,
    evaluate_requirements,
    validate_candidate_plan,
)
from backend.fact_types import get_fact_type
from backend.sources import read_public_html, source_document_from_registration

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "beta_domain.json").read_text(
        encoding="utf-8"
    )
)
SOURCES = FIXTURE["sources"]
RULES = FIXTURE["rules"]
PLANS = FIXTURE["plans"]


def _source_payload(source_key: str) -> dict[str, Any]:
    source = SOURCES[source_key]
    fragments = [
        {field: anchor[field] for field in ("locator_kind", "locator", "quote")}
        for anchor in source["anchors"].values()
    ]
    return {
        "url": source["url"],
        "title": source["title"],
        "publisher": source["publisher"],
        "scope": source["scope"],
        "scope_year": source["scope_year"],
        "published_date": source["published_date"],
        "fetched_at": source["fetched_at"],
        "content": "\n".join(fragment["quote"] for fragment in fragments),
        "fragments": fragments,
    }


def _document(source_key: str) -> SourceDocument:
    payload = _source_payload(source_key)
    return SourceDocument(
        source_version_id=source_key,
        title=payload["title"],
        publisher=payload["publisher"],
        url=payload["url"],
        scope=payload["scope"],
        year=payload["scope_year"],
        published_date=date.fromisoformat(payload["published_date"]),
        content=payload["content"],
        fragments=[
            SourceFragmentRecord.model_validate(fragment)
            for fragment in payload["fragments"]
        ],
    )


def _citation(source_key: str, anchor_key: str, doc: SourceDocument) -> SourceCitation:
    anchor = SOURCES[source_key]["anchors"][anchor_key]
    cite = SourceCitation(
        source_version_id=doc.source_version_id,
        locator_kind=anchor["locator_kind"],
        locator=anchor["locator"],
        excerpt=anchor["quote"],
    )
    return _validate_and_enrich_citations(
        [cite], {doc.source_version_id}, {doc.source_version_id: doc}
    )[0]


def _requirement(rule_id: str, doc: SourceDocument) -> ExtractedRequirement:
    rule = RULES[rule_id]
    return ExtractedRequirement(
        requirement_id=rule_id,
        field_key=f"beta.{rule_id.lower().replace('-', '_')}",
        title=rule["title"],
        scope=doc.scope,
        obligation=ObligationType.OFFICIAL_REQUIRED,
        basis=[
            _citation(rule["source"], anchor, doc)
            for anchor in (rule["anchor"], *rule.get("related_anchors", []))
        ],
        value_text=rule["expected"],
        is_ambiguous=rule.get("ambiguous", False),
        rule_kind=rule.get("kind"),
        rule_parameters=rule.get("parameters", {}),
        required_attachments=rule.get("required_attachments", []),
    )


@pytest.mark.parametrize("case", FIXTURE["checks"], ids=lambda case: case["id"])
def test_beta_domain_self_check(case: dict[str, Any]) -> None:
    source = _document(RULES[case["rule"]]["source"])
    requirement = _requirement(case["rule"], source)
    source = source.model_copy(update=case.get("source_override", {}))
    sources = {} if case.get("omit_source") else {source.source_version_id: source}
    evaluations, _ = evaluate_requirements([requirement], sources, case["facts"])
    (result,) = evaluations
    assert to_api_self_check_conclusion(result.status) == case["conclusion"]
    assert result.missing_fields == case.get("missing", [])
    assert result.basis == requirement.basis
    expected_deadline = case.get("deadline")
    assert result.computed_deadline == (
        datetime.fromisoformat(expected_deadline) if expected_deadline else None
    )
    if gap := case.get("gap"):
        assert gap in {
            item.gap_type
            for item in collect_source_gaps(list(sources.values()), evaluations)
        }


@pytest.mark.parametrize("case", FIXTURE["rank_examples"], ids=lambda case: case["id"])
def test_beta_domain_rank_examples(case: dict[str, Any]) -> None:
    """Check the fact contract and the reference decision table for this notice."""
    rank = get_fact_type("gpa.rank")
    assert rank is not None
    value = rank.normalize(
        {"position": case["position"], "cohort_size": case["cohort_size"]}
    )
    assert rank.render(value).agent_value == case["percentile"]
    expected = case["all_required_credits"] and any(
        value["position"] * 100 <= path["max_percentile"] * value["cohort_size"]
        and case["makeup_or_repeat_courses"] <= path["max_makeup_or_repeat_courses"]
        for path in RULES["GR-01"]["rank_paths"]
    )
    assert expected is case["passes_clause"]


@pytest.mark.parametrize("rule_id", RULES)
def test_beta_domain_rule_cites_its_source(rule_id: str) -> None:
    rule = RULES[rule_id]
    assert rule["expected"] and rule["review"]
    doc = _document(rule["source"])
    requirement = _requirement(rule_id, doc)
    assert doc.url and requirement.scope == doc.scope
    for evidence in requirement.basis:
        assert evidence.excerpt and evidence.excerpt in doc.content


@pytest.mark.parametrize(
    "change",
    [{"locator": "第9999段"}, {"excerpt": "次日补报均有效"}],
    ids=["unknown-location", "wrong-quote"],
)
def test_beta_domain_rejects_incorrect_citation(change: dict[str, str]) -> None:
    doc = _document("admission")
    cite = _citation("admission", "deadline", doc).model_copy(update=change)
    with pytest.raises(ModelInvocationError) as error:
        _validate_and_enrich_citations(
            [cite], {doc.source_version_id}, {doc.source_version_id: doc}
        )
    assert error.value.code == AgentErrorCode.VALIDATION_FAILED


@pytest.mark.skipif(
    os.environ.get("OFFERPILOT_BETA_DOMAIN_LIVE") != "1",
    reason="set OFFERPILOT_BETA_DOMAIN_LIVE=1 for an online notice recheck",
)
@pytest.mark.parametrize("source_key", SOURCES)
def test_beta_domain_live_source(source_key: str) -> None:
    source = SOURCES[source_key]
    result = read_public_html(
        {field: source[field] for field in ("url", "publisher", "scope", "scope_year")}
    )
    assert str(result.url) == source["url"]
    assert source["title"] in result.title
    for anchor in source["anchors"].values():
        assert any(
            anchor["quote"] in fragment.quote
            and anchor["locator_kind"] == fragment.locator.kind
            and anchor["locator"] == fragment.locator_text
            for fragment in result.fragments
        ), anchor["section"]


def _create_matter(
    client: TestClient, plan_key: str, *, scope_year: int | None = None
) -> str:
    plan = PLANS[plan_key]
    source = SOURCES[plan["source"]]
    response = client.post(
        "/api/v1/matters",
        json={
            "type_code": plan["type_code"],
            "goal": plan["goal"],
            "scope_year": scope_year or source["scope_year"],
        },
    )
    assert response.status_code == 201, response.text
    matter = response.json()["matter"]
    assert matter["type_code"] == plan["type_code"]
    return f"/api/v1/matters/{matter['id']}"


def _register_source(
    client: TestClient, matter_path: str, source_key: str
) -> SourceDocument:
    payload = _source_payload(source_key)
    response = client.post(f"{matter_path}/sources", json=payload)
    assert response.status_code == 201, response.text
    doc = SourceDocument.model_validate(
        source_document_from_registration(response.json())
    )
    assert doc.content_hash == hashlib.sha256(payload["content"].encode()).hexdigest()
    return doc


def _persist_candidate(
    client: TestClient, matter_path: str, plan_key: str, doc: SourceDocument
) -> dict[str, Any]:
    data = PLANS[plan_key]
    rule_id = data["rule"]
    requirement = _requirement(rule_id, doc)
    sources = {doc.source_version_id: doc}
    evaluations, _ = evaluate_requirements([requirement], sources, {})
    response = client.post(
        f"{matter_path}/requirements",
        json=build_requirements_batch_payload([requirement], evaluations, sources),
    )
    assert response.status_code == 201, response.text
    (saved_requirement,) = response.json()["requirements"]
    assert saved_requirement["self_check"]["conclusion"] == "missing_info"
    assert saved_requirement["evidence"][0]["snapshot_id"] == doc.snapshot_id

    candidate = CandidatePlan(
        candidate_id=f"beta-{plan_key}",
        workspace_version=1,
        candidate_version=1,
        input_snapshot_id=doc.source_version_id,
        tasks=[
            CandidateTask(
                task_id=task["id"],
                title=task["title"],
                obligation=ObligationType(task["obligation"]),
                basis=[_citation(data["source"], task["anchor"], doc)],
                suggested_date=date.fromisoformat(task["suggested_date"]),
                official_deadline_date=(
                    date.fromisoformat(data["official_deadline_date"])
                    if task["carries_official_deadline"]
                    else None
                ),
                official_deadline_at=(
                    datetime.fromisoformat(data["official_deadline_at"])
                    if task["carries_official_deadline"]
                    and data["official_deadline_at"]
                    else None
                ),
                depends_on=task["depends_on"],
                requirement_id=rule_id if task["carries_official_deadline"] else None,
                evidence_required=task["evidence_required"],
            )
            for task in data["tasks"]
        ],
    )
    assert validate_candidate_plan(candidate, 1, sources) == []
    missing_dependency = candidate.tasks[-1].model_copy(
        update={"depends_on": ["task-outside-this-plan"]}
    )
    invalid = candidate.model_copy(
        update={"tasks": [*candidate.tasks[:-1], missing_dependency]}
    )
    assert any(
        "不存在的前置任务" in error for error in validate_candidate_plan(invalid, 1)
    )
    response = client.post(
        f"{matter_path}/candidate-plans",
        json=build_candidate_plan_create_payload(
            candidate, sources, {rule_id: saved_requirement["id"]}
        ),
    )
    assert response.status_code == 201, response.text
    return response.json()["plan"]


@pytest.mark.parametrize("plan_key", PLANS)
def test_beta_domain_confirm_and_read_tasks(app, clock, login, plan_key: str) -> None:
    data = PLANS[plan_key]
    clock.value = datetime.fromisoformat(data["replay_at"])
    with TestClient(app) as client:
        login(client)
        matter_path = _create_matter(client, plan_key)
        other_path = _create_matter(client, plan_key)
        doc = _register_source(client, matter_path, data["source"])
        plan = _persist_candidate(client, matter_path, plan_key, doc)
        assert plan["status"] == "pending"
        assert client.get(f"{matter_path}/tasks").json()["tasks"] == []

        key = str(uuid4())
        confirm_url = f"/api/v1/candidate-plans/{plan['id']}/confirm"
        for replayed in (False, True):
            response = client.post(confirm_url, headers={"Idempotency-Key": key})
            assert response.status_code == 200, response.text
            assert response.json()["replayed"] is replayed

        tasks = client.get(f"{matter_path}/tasks").json()["tasks"]
        assert [task["title"] for task in tasks] == [
            task["title"] for task in data["tasks"]
        ]
        first, second = tasks
        assert first["official_deadline_date"] is None
        assert first["depends_on"] == []
        assert second["depends_on"] == [first["id"]]
        assert second["official_deadline_date"] == data["official_deadline_date"]
        actual_deadline = second["official_deadline_at"]
        assert (
            datetime.fromisoformat(actual_deadline) if actual_deadline else None
        ) == (
            datetime.fromisoformat(data["official_deadline_utc"])
            if data["official_deadline_utc"]
            else None
        )
        for task, expected in zip(tasks, data["tasks"], strict=True):
            (evidence,) = task["sources"]
            anchor = SOURCES[data["source"]]["anchors"][expected["anchor"]]
            assert evidence["url"] == doc.url
            assert evidence["snapshot_id"] == doc.snapshot_id
            assert evidence["locator"] == anchor["locator"]
            assert evidence["quote"] == anchor["quote"]
        assert client.get(f"{other_path}/tasks").json()["tasks"] == []


def test_beta_domain_rejects_mismatched_source_year(client: TestClient) -> None:
    matter_path = _create_matter(client, "admission", scope_year=2028)
    doc = _register_source(client, matter_path, "admission")
    req = _requirement("GR-07", doc)
    response = client.post(
        f"{matter_path}/requirements",
        json=build_requirements_batch_payload([req], [], {doc.source_version_id: doc}),
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "scope_year_mismatch"
    assert client.get(f"{matter_path}/tasks").json()["tasks"] == []


@pytest.mark.parametrize("action", ["reject", "confirm_after_deadline"])
def test_beta_domain_competition_decision_without_tasks(app, clock, login, action):
    data = PLANS["competition"]
    clock.value = datetime.fromisoformat(data["replay_at"])
    with TestClient(app) as client:
        login(client)
        matter_path = _create_matter(client, "competition")
        doc = _register_source(client, matter_path, data["source"])
        plan = _persist_candidate(client, matter_path, "competition", doc)
        plan_path = f"/api/v1/candidate-plans/{plan['id']}"
        headers = {"Idempotency-Key": str(uuid4())}
        if action == "reject":
            response = client.post(f"{plan_path}/reject", headers=headers)
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "rejected"
        else:
            clock.value = datetime.fromisoformat("2026-09-19T00:01:00+08:00")
            login(client)
            response = client.post(f"{plan_path}/confirm", headers=headers)
            assert response.status_code == 409, response.text
            assert response.json()["error"]["code"] == "official_deadline_passed"
        assert client.get(f"{matter_path}/tasks").json()["tasks"] == []
