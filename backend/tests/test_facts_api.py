"""End-to-end tests for personal fact persistence and candidate basis states."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient

FX_URL = "https://example.edu/admission/notice"
FX_TEXT = "申请条件：成绩排名位于专业前 10%。"


def test_first_rank_fact_is_saved_as_version_one(client: TestClient) -> None:
    response = client.put(
        "/api/v1/facts/gpa.rank",
        json={"value": {"position": 5, "cohort_size": 120}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    fact = body["fact"]
    assert body["created"] is True
    assert fact["fact_type"] == "gpa.rank"
    assert fact["version_no"] == 1
    assert fact["status"] == "confirmed"
    assert fact["value"] == {
        "position": 5,
        "cohort_size": 120,
        "percentile": 4.1667,
    }
    assert fact["value_text"] == "5/120"
    assert fact["trust_level"] == "self"
    assert fact["confirmed_at"] == "2026-09-09T09:00:00+00:00"
    assert fact["superseded_at"] is None
    assert body["affected_plans"] == []


def test_percentile_fact_is_saved_as_version_one(client: TestClient) -> None:
    response = client.put(
        "/api/v1/facts/gpa.rank",
        json={"value": {"percentile": 4.2}},
    )
    assert response.status_code == 200, response.text
    fact = response.json()["fact"]
    assert fact["version_no"] == 1
    assert fact["value"] == {
        "position": None,
        "cohort_size": None,
        "percentile": 4.2,
    }
    assert fact["value_text"] == "前 4.2%"


def test_identical_save_does_not_create_a_version(client: TestClient) -> None:
    payload = {
        "value": {"position": 5, "cohort_size": 120},
        "scope": "2027 届本科",
        "valid_from": "2026-09-01",
    }
    first = client.put("/api/v1/facts/gpa.rank", json=payload)
    assert first.status_code == 200, first.text
    replay = client.put("/api/v1/facts/gpa.rank", json=payload)
    assert replay.status_code == 200, replay.text
    body = replay.json()
    assert body["created"] is False
    assert body["fact"]["version_no"] == 1
    assert body["fact"]["id"] == first.json()["fact"]["id"]
    versions = client.get("/api/v1/facts/gpa.rank").json()["versions"]
    assert len(versions) == 1


def test_new_value_supersedes_previous_version(client: TestClient) -> None:
    first = client.put(
        "/api/v1/facts/gpa.rank",
        json={"value": {"position": 5, "cohort_size": 120}},
    )
    assert first.status_code == 200, first.text
    first_id = first.json()["fact"]["id"]

    second = client.put(
        "/api/v1/facts/gpa.rank",
        json={"value": {"position": 8, "cohort_size": 120}},
    )
    assert second.status_code == 200, second.text
    fact = second.json()["fact"]
    assert second.json()["created"] is True
    assert fact["version_no"] == 2
    assert fact["value_text"] == "8/120"
    assert fact["id"] != first_id

    body = client.get("/api/v1/facts/gpa.rank").json()
    assert body["fact"]["id"] == fact["id"]
    versions = body["versions"]
    assert [item["version_no"] for item in versions] == [2, 1]
    previous = versions[1]
    assert previous["id"] == first_id
    assert previous["status"] == "superseded"
    assert previous["superseded_at"] == "2026-09-09T09:00:00+00:00"


def test_current_fact_list_returns_confirmed_versions_only(
    client: TestClient,
) -> None:
    client.put(
        "/api/v1/facts/gpa.rank",
        json={"value": {"position": 5, "cohort_size": 120}},
    )
    client.put(
        "/api/v1/facts/gpa.rank",
        json={"value": {"position": 8, "cohort_size": 120}},
    )
    response = client.get("/api/v1/facts")
    assert response.status_code == 200, response.text
    facts = response.json()["facts"]
    assert len(facts) == 1
    assert facts[0]["fact_type"] == "gpa.rank"
    assert facts[0]["version_no"] == 2
    assert facts[0]["status"] == "confirmed"


def test_fact_versions_are_returned_latest_first(client: TestClient) -> None:
    client.put(
        "/api/v1/facts/gpa.rank",
        json={"value": {"position": 5, "cohort_size": 120}},
    )
    client.put(
        "/api/v1/facts/gpa.rank",
        json={"value": {"position": 8, "cohort_size": 120}},
    )
    client.put(
        "/api/v1/facts/gpa.rank",
        json={"value": {"position": 6, "cohort_size": 120}},
    )
    response = client.get("/api/v1/facts/gpa.rank")
    assert response.status_code == 200, response.text
    versions = response.json()["versions"]
    assert [item["version_no"] for item in versions] == [3, 2, 1]
    assert [item["status"] for item in versions] == [
        "confirmed",
        "superseded",
        "superseded",
    ]


def test_save_reports_pending_plans_with_stale_or_missing_facts(
    client: TestClient,
) -> None:
    matter_id = _create_matter(client)
    source = _create_source(client, matter_id)
    requirement = _create_requirement(client, matter_id, source)
    before_fact = _create_plan(client, matter_id, requirement["id"])

    first = _save_rank(client, position=5)
    affected = first["affected_plans"]
    assert len(affected) == 1
    assert affected[0]["plan_id"] == before_fact["plan"]["id"]
    assert affected[0]["matter_id"] == matter_id
    assert affected[0]["version_no"] == 1
    assert affected[0]["stored_version_no"] is None

    after_fact = _create_plan(client, matter_id, requirement["id"])
    second = _save_rank(client, position=8)
    affected_by_plan = {item["plan_id"]: item for item in second["affected_plans"]}
    assert set(affected_by_plan) == {
        before_fact["plan"]["id"],
        after_fact["plan"]["id"],
    }
    assert affected_by_plan[before_fact["plan"]["id"]]["stored_version_no"] is None
    assert affected_by_plan[after_fact["plan"]["id"]]["stored_version_no"] == 1

    detail = client.get(f"/api/v1/candidate-plans/{before_fact['plan']['id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["plan"]["status"] == "pending"
    assert detail.json()["plan"]["decision"] is None
    assert detail.json()["plan"]["tasks"] == []
    assert client.get(f"/api/v1/matters/{matter_id}/tasks").json()["tasks"] == []


def test_changed_fact_expires_plan_on_confirm(client: TestClient) -> None:
    _save_rank(client, position=5)
    matter_id = _create_matter(client)
    source = _create_source(client, matter_id)
    requirement = _create_requirement(client, matter_id, source)
    plan = _create_plan(client, matter_id, requirement["id"])
    plan_id = plan["plan"]["id"]

    _save_rank(client, position=8)

    response = client.post(
        f"/api/v1/candidate-plans/{plan_id}/confirm",
        headers={"Idempotency-Key": "f0000000-0000-4000-8000-000000000001"},
    )
    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "basis_changed"
    assert error["details"]["plan_id"] == plan_id
    stale = error["details"]["stale_facts"]
    assert len(stale) == 1
    assert stale[0]["fact_type"] == "gpa.rank"
    assert stale[0]["stored_version_no"] == 1
    assert stale[0]["current_version_no"] == 2

    detail = client.get(f"/api/v1/candidate-plans/{plan_id}").json()["plan"]
    assert detail["status"] == "expired"
    assert detail["expired_at"] is not None
    assert detail["decision"] is None
    assert detail["tasks"] == []
    assert detail["basis_status"] == "not_applicable"
    assert detail["stale_facts"] == []


def test_plan_and_matter_reads_expose_basis_state(client: TestClient) -> None:
    _save_rank(client, position=5)
    matter_id = _create_matter(client)
    source = _create_source(client, matter_id)
    requirement = _create_requirement(client, matter_id, source)
    plan = _create_plan(client, matter_id, requirement["id"])
    plan_id = plan["plan"]["id"]

    current_plan = client.get(f"/api/v1/candidate-plans/{plan_id}").json()["plan"]
    assert current_plan["basis_status"] == "current"
    assert current_plan["stale_facts"] == []

    listed = client.get(f"/api/v1/matters/{matter_id}/candidate-plans")
    assert listed.status_code == 200, listed.text
    listed_plan = listed.json()["plans"][0]
    assert listed_plan["basis_status"] == "current"
    assert listed_plan["stale_facts"] == []

    matter = client.get(f"/api/v1/matters/{matter_id}").json()["matter"]
    assert matter["latest_plan"]["basis_status"] == "current"
    assert matter["latest_plan"]["stale_facts"] == []

    _save_rank(client, position=8)

    stale_plan = client.get(f"/api/v1/candidate-plans/{plan_id}").json()["plan"]
    assert stale_plan["basis_status"] == "stale"
    assert stale_plan["stale_facts"] == [
        {
            "fact_type": "gpa.rank",
            "stored_version_no": 1,
            "current_version_no": 2,
            "current_fact_id": client.get("/api/v1/facts/gpa.rank").json()["fact"][
                "id"
            ],
        }
    ]

    listed_stale = client.get(f"/api/v1/matters/{matter_id}/candidate-plans")
    assert listed_stale.json()["plans"][0]["basis_status"] == "stale"
    matter_stale = client.get(f"/api/v1/matters/{matter_id}").json()["matter"]
    assert matter_stale["latest_plan"]["basis_status"] == "stale"
    assert matter_stale["latest_plan"]["stale_facts"] == stale_plan["stale_facts"]


def test_unregistered_fact_type_is_rejected(client: TestClient) -> None:
    response = client.put(
        "/api/v1/facts/cet6.score",
        json={"value": {"score": 600}},
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "unsupported_fact_type"
    assert error["details"] == {"supported_fact_types": ["gpa.rank"]}

    read = client.get("/api/v1/facts/cet6.score")
    assert read.status_code == 422
    assert read.json()["error"]["code"] == "unsupported_fact_type"


def test_rank_greater_than_cohort_is_rejected(client: TestClient) -> None:
    response = client.put(
        "/api/v1/facts/gpa.rank",
        json={"value": {"position": 130, "cohort_size": 120}},
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "invalid_fact_value"
    issues = error["details"]["issues"]
    assert len(issues) == 1
    assert issues[0]["path"] == "value.position"
    assert issues[0]["code"] == "greater_than_cohort"

    stored = client.get("/api/v1/facts/gpa.rank").json()
    assert stored["fact"] is None
    assert stored["versions"] == []


def _save_rank(
    client: TestClient,
    *,
    position: int,
    cohort_size: int = 120,
) -> dict[str, Any]:
    response = client.put(
        "/api/v1/facts/gpa.rank",
        json={"value": {"position": position, "cohort_size": cohort_size}},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_matter(client: TestClient) -> str:
    response = client.post(
        "/api/v1/matters",
        json={
            "goal": "申请 2027 年福州大学数学与统计学院推免",
            "type_code": "pre_recommend",
            "scope_year": 2027,
            "scope_attrs": {
                "school": "福州大学",
                "college": "数学与统计学院",
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["matter"]["id"]


def _create_source(client: TestClient, matter_id: str) -> dict:
    response = client.post(
        f"/api/v1/matters/{matter_id}/sources",
        json={
            "url": FX_URL,
            "publisher": "福州大学数学与统计学院",
            "title": "2027 年推荐免试攻读研究生工作方案",
            "scope": "2027 届、本院",
            "scope_year": 2027,
            "published_date": "2026-09-08",
            "content": FX_TEXT,
            "fragments": [
                {
                    "locator_kind": "section",
                    "locator": "第（1）项",
                    "quote": FX_TEXT,
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_requirement(
    client: TestClient,
    matter_id: str,
    source: dict,
) -> dict:
    response = client.post(
        f"/api/v1/matters/{matter_id}/requirements",
        json={
            "requirements": [
                {
                    "field_key": "gpa.rank",
                    "label": "专业成绩排名",
                    "obligation_nature": "required",
                    "extract_status": "checked",
                    "scope": "2027 届、本院",
                    "value_text": "前 10%",
                    "value_type": "text",
                    "confidence": 0.9,
                    "snapshot_id": source["snapshot"]["id"],
                    "evidence": [
                        {
                            "source_id": source["source"]["id"],
                            "snapshot_id": source["snapshot"]["id"],
                            "locator_kind": "section",
                            "locator": "第（1）项",
                            "quote": FX_TEXT,
                        }
                    ],
                }
            ]
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["requirements"][0]


def _create_plan(
    client: TestClient, matter_id: str, requirement_id: UUID | str
) -> dict:
    response = client.post(
        f"/api/v1/matters/{matter_id}/candidate-plans",
        json={
            "items": [
                {
                    "client_item_id": "rank-check",
                    "title": "核对成绩排名",
                    "obligation_nature": "required",
                    "requirement_id": str(requirement_id),
                }
            ]
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
