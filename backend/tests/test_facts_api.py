"""End-to-end tests for matter-scoped personal fact persistence."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app

FX_URL = "https://example.edu/admission/notice"
FX_TEXT = "申请条件：成绩排名位于专业前 10%。"
USER_ID = UUID("00000000-0000-7000-8000-000000000001")
FOREIGN_USER_ID = UUID("99999999-9999-7999-8999-999999999991")
FOREIGN_WORKSPACE_ID = UUID("99999999-9999-7999-8999-999999999992")
FOREIGN_MATTER_ID = UUID("99999999-9999-7999-8999-999999999993")


def test_first_rank_fact_is_saved_as_version_one(client: TestClient) -> None:
    matter_id = _create_matter(client)
    response = client.put(
        _fact_url(matter_id, "gpa.rank"),
        json={"value": {"position": 5, "cohort_size": 120}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    fact = body["fact"]
    assert body["created"] is True
    assert fact["matter_id"] == matter_id
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
    matter_id = _create_matter(client)
    response = client.put(
        _fact_url(matter_id, "gpa.rank"),
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
    matter_id = _create_matter(client)
    payload = {
        "value": {"position": 5, "cohort_size": 120},
        "scope": "2027 届本科",
        "valid_from": "2026-09-01",
    }
    first = client.put(_fact_url(matter_id, "gpa.rank"), json=payload)
    assert first.status_code == 200, first.text
    replay = client.put(_fact_url(matter_id, "gpa.rank"), json=payload)
    assert replay.status_code == 200, replay.text
    body = replay.json()
    assert body["created"] is False
    assert body["fact"]["version_no"] == 1
    assert body["fact"]["id"] == first.json()["fact"]["id"]
    versions = client.get(_fact_url(matter_id, "gpa.rank")).json()["versions"]
    assert len(versions) == 1


def test_new_value_supersedes_previous_version(client: TestClient) -> None:
    matter_id = _create_matter(client)
    first = client.put(
        _fact_url(matter_id, "gpa.rank"),
        json={"value": {"position": 5, "cohort_size": 120}},
    )
    assert first.status_code == 200, first.text
    first_id = first.json()["fact"]["id"]

    second = client.put(
        _fact_url(matter_id, "gpa.rank"),
        json={"value": {"position": 8, "cohort_size": 120}},
    )
    assert second.status_code == 200, second.text
    fact = second.json()["fact"]
    assert second.json()["created"] is True
    assert fact["version_no"] == 2
    assert fact["value_text"] == "8/120"
    assert fact["id"] != first_id

    body = client.get(_fact_url(matter_id, "gpa.rank")).json()
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
    matter_id = _create_matter(client)
    client.put(
        _fact_url(matter_id, "gpa.rank"),
        json={"value": {"position": 5, "cohort_size": 120}},
    )
    client.put(
        _fact_url(matter_id, "gpa.rank"),
        json={"value": {"position": 8, "cohort_size": 120}},
    )
    response = client.get(_fact_url(matter_id))
    assert response.status_code == 200, response.text
    facts = response.json()["facts"]
    assert len(facts) == 1
    assert facts[0]["matter_id"] == matter_id
    assert facts[0]["fact_type"] == "gpa.rank"
    assert facts[0]["version_no"] == 2
    assert facts[0]["status"] == "confirmed"


def test_fact_versions_are_returned_latest_first(client: TestClient) -> None:
    matter_id = _create_matter(client)
    client.put(
        _fact_url(matter_id, "gpa.rank"),
        json={"value": {"position": 5, "cohort_size": 120}},
    )
    client.put(
        _fact_url(matter_id, "gpa.rank"),
        json={"value": {"position": 8, "cohort_size": 120}},
    )
    client.put(
        _fact_url(matter_id, "gpa.rank"),
        json={"value": {"position": 6, "cohort_size": 120}},
    )
    response = client.get(_fact_url(matter_id, "gpa.rank"))
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

    first = _save_rank(client, matter_id, position=5)
    affected = first["affected_plans"]
    assert len(affected) == 1
    assert affected[0]["plan_id"] == before_fact["plan"]["id"]
    assert affected[0]["matter_id"] == matter_id
    assert affected[0]["version_no"] == 1
    assert affected[0]["stored_version_no"] is None

    after_fact = _create_plan(client, matter_id, requirement["id"])
    second = _save_rank(client, matter_id, position=8)
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
    matter_id = _create_matter(client)
    _save_rank(client, matter_id, position=5)
    source = _create_source(client, matter_id)
    requirement = _create_requirement(client, matter_id, source)
    plan = _create_plan(client, matter_id, requirement["id"])
    plan_id = plan["plan"]["id"]

    _save_rank(client, matter_id, position=8)

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
    matter_id = _create_matter(client)
    _save_rank(client, matter_id, position=5)
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

    _save_rank(client, matter_id, position=8)

    stale_plan = client.get(f"/api/v1/candidate-plans/{plan_id}").json()["plan"]
    assert stale_plan["basis_status"] == "stale"
    assert stale_plan["stale_facts"] == [
        {
            "fact_type": "gpa.rank",
            "stored_version_no": 1,
            "current_version_no": 2,
            "current_fact_id": client.get(_fact_url(matter_id, "gpa.rank")).json()[
                "fact"
            ]["id"],
        }
    ]

    listed_stale = client.get(f"/api/v1/matters/{matter_id}/candidate-plans")
    assert listed_stale.json()["plans"][0]["basis_status"] == "stale"
    matter_stale = client.get(f"/api/v1/matters/{matter_id}").json()["matter"]
    assert matter_stale["latest_plan"]["basis_status"] == "stale"
    assert matter_stale["latest_plan"]["stale_facts"] == stale_plan["stale_facts"]


def test_facts_are_isolated_per_matter(client: TestClient) -> None:
    matter_a = _create_matter(client)
    matter_b = _create_matter(client)

    _save_rank(client, matter_a, position=5)

    fact_a = client.get(_fact_url(matter_a, "gpa.rank")).json()
    assert fact_a["fact"]["version_no"] == 1
    assert fact_a["fact"]["value_text"] == "5/120"

    fact_b = client.get(_fact_url(matter_b, "gpa.rank")).json()
    assert fact_b["fact"] is None
    assert fact_b["versions"] == []
    assert client.get(_fact_url(matter_b)).json()["facts"] == []

    _save_rank(client, matter_b, position=8)
    fact_b = client.get(_fact_url(matter_b, "gpa.rank")).json()
    assert fact_b["fact"]["version_no"] == 1
    assert fact_b["fact"]["value_text"] == "8/120"
    assert (
        client.get(_fact_url(matter_a, "gpa.rank")).json()["fact"]["value_text"]
        == "5/120"
    )


def test_fact_changes_only_affect_the_current_matter(client: TestClient) -> None:
    matter_a = _create_matter(client)
    matter_b = _create_matter(client)
    source_a = _create_source(client, matter_a, url=f"{FX_URL}?matter=a")
    source_b = _create_source(client, matter_b, url=f"{FX_URL}?matter=b")
    requirement_a = _create_requirement(client, matter_a, source_a)
    requirement_b = _create_requirement(client, matter_b, source_b)

    _save_rank(client, matter_a, position=5)
    _save_rank(client, matter_b, position=5)
    plan_a = _create_plan(client, matter_a, requirement_a["id"])
    plan_b = _create_plan(client, matter_b, requirement_b["id"])

    changed = _save_rank(client, matter_a, position=8)
    assert [item["plan_id"] for item in changed["affected_plans"]] == [
        plan_a["plan"]["id"]
    ]

    fact_b = client.get(_fact_url(matter_b, "gpa.rank")).json()["fact"]
    assert fact_b["version_no"] == 1
    assert fact_b["value_text"] == "5/120"
    detail_b = client.get(f"/api/v1/candidate-plans/{plan_b['plan']['id']}").json()[
        "plan"
    ]
    assert detail_b["basis_status"] == "current"
    assert detail_b["stale_facts"] == []

    confirmed = client.post(
        f"/api/v1/candidate-plans/{plan_b['plan']['id']}/confirm",
        headers={"Idempotency-Key": "f0000000-0000-4000-8000-000000000002"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"


def test_facts_survive_application_restart(
    client: TestClient,
    database_urls: tuple[str, str],
    clock,
    login,
) -> None:
    matter_id = _create_matter(client)
    saved = _save_rank(client, matter_id, position=5)["fact"]

    app_url, _ = database_urls
    restarted_app = create_app(
        Settings(
            database_url=app_url,
            demo_timezone="Asia/Shanghai",
        ),
        clock=clock,
    )
    with TestClient(restarted_app) as restarted:
        login(restarted)
        restored = restarted.get(_fact_url(matter_id, "gpa.rank")).json()
        assert restored["fact"]["id"] == saved["id"]
        assert restored["fact"]["version_no"] == 1
        assert restored["fact"]["value_text"] == "5/120"


def test_inaccessible_matter_is_rejected(
    client: TestClient, admin: psycopg.Connection
) -> None:
    template = admin.execute(
        "SELECT id FROM core.template_version"
        " WHERE type_code = 'pre_recommend' AND status = 'published'"
        " LIMIT 1"
    ).fetchone()
    assert template is not None
    admin.execute(
        "INSERT INTO core.app_user"
        " (id, email, display_name, password_hash, status)"
        " VALUES (%s, 'foreign@offerpilot.local', '其他用户', 'x', 'active')",
        (FOREIGN_USER_ID,),
    )
    admin.execute(
        "INSERT INTO core.workspace (id, owner_id) VALUES (%s, %s)",
        (FOREIGN_WORKSPACE_ID, FOREIGN_USER_ID),
    )
    admin.execute(
        "INSERT INTO core.matter"
        " (id, workspace_id, type_code, template_version_id, goal, status,"
        "  scope_year, scope_attrs)"
        " VALUES (%s, %s, 'pre_recommend', %s, '他人的事项', 'active', 2027, '{}')",
        (FOREIGN_MATTER_ID, FOREIGN_WORKSPACE_ID, template[0]),
    )

    missing = "00000000-0000-4000-8000-000000000099"
    for matter_id in (missing, str(FOREIGN_MATTER_ID)):
        read = client.get(_fact_url(matter_id))
        assert read.status_code == 404, read.text
        assert read.json()["error"]["code"] == "matter_not_found"
        write = client.put(
            _fact_url(matter_id, "gpa.rank"),
            json={"value": {"position": 5, "cohort_size": 120}},
        )
        assert write.status_code == 404, write.text
        assert write.json()["error"]["code"] == "matter_not_found"


def test_legacy_user_level_fact_is_not_reused(
    client: TestClient, admin: psycopg.Connection
) -> None:
    matter_id = _create_matter(client)
    admin.execute(
        "INSERT INTO core.fact"
        " (id, owner_id, matter_id, fact_type, value_text, value_json, value_hash,"
        "  confirm_status, version_no, confirmed_at)"
        " VALUES (%s, %s, NULL, 'gpa.rank', '3/100', %s, %s, 'confirmed', 1, %s)",
        (
            UUID("77777777-7777-7777-8777-777777777777"),
            USER_ID,
            '{"position": 3, "cohort_size": 100, "percentile": 3.0}',
            "c" * 64,
            "2026-09-09T09:00:00+00:00",
        ),
    )

    assert client.get(_fact_url(matter_id)).json()["facts"] == []
    assert client.get(_fact_url(matter_id, "gpa.rank")).json() == {
        "fact": None,
        "versions": [],
    }

    saved = _save_rank(client, matter_id, position=5)
    assert saved["fact"]["version_no"] == 1


def test_unregistered_fact_type_is_rejected(client: TestClient) -> None:
    matter_id = _create_matter(client)
    response = client.put(
        _fact_url(matter_id, "gre.score"),
        json={"value": {"score": 600}},
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "unsupported_fact_type"
    assert error["details"] == {
        "supported_fact_types": [
            "cert",
            "cet4",
            "cet6",
            "comp",
            "gpa.rank",
            "gpa.score",
            "ielts",
            "toefl",
        ]
    }

    read = client.get(_fact_url(matter_id, "gre.score"))
    assert read.status_code == 422
    assert read.json()["error"]["code"] == "unsupported_fact_type"


def test_gpa_score_is_saved_on_four_point_scale(client: TestClient) -> None:
    matter_id = _create_matter(client)
    response = client.put(
        _fact_url(matter_id, "gpa.score"),
        json={"value": {"value": 3.725}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] is True
    fact = body["fact"]
    assert fact["version_no"] == 1
    assert fact["value"] == {"value": 3.73, "scale": 4.0}
    assert fact["value_text"] == "3.73/4.0"

    maximum = client.put(
        _fact_url(matter_id, "gpa.score"),
        json={"value": {"value": 4}},
    )
    assert maximum.status_code == 200, maximum.text
    assert maximum.json()["fact"]["value_text"] == "4.0/4.0"
    assert maximum.json()["fact"]["version_no"] == 2


def test_english_scores_are_saved_and_rendered(client: TestClient) -> None:
    matter_id = _create_matter(client)
    cases = [
        ("cet4", {"score": 500}, {"score": 500}, "CET-4 500"),
        ("cet6", {"score": 425}, {"score": 425}, "CET-6 425"),
        ("toefl", {"score": 105}, {"score": 105}, "TOEFL 105"),
        ("ielts", {"overall": 7.25}, {"overall": 7.3}, "IELTS 7.3"),
    ]
    for fact_type, value, normalized, text in cases:
        response = client.put(_fact_url(matter_id, fact_type), json={"value": value})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["created"] is True
        assert body["fact"]["version_no"] == 1
        assert body["fact"]["value"] == normalized
        assert body["fact"]["value_text"] == text

    listed = client.get(_fact_url(matter_id)).json()["facts"]
    assert [item["fact_type"] for item in listed] == [
        "cet4",
        "cet6",
        "ielts",
        "toefl",
    ]


def test_fact_ranges_are_validated(client: TestClient) -> None:
    matter_id = _create_matter(client)
    cases = [
        ("gpa.score", {"value": 4.5}, "value.value", "gpa_out_of_range"),
        ("cet6", {"score": 711}, "value.score", "score_out_of_range"),
        ("toefl", {"score": 121}, "value.score", "score_out_of_range"),
        ("ielts", {"overall": 9.1}, "value.overall", "score_out_of_range"),
    ]
    for fact_type, value, path, code in cases:
        response = client.put(_fact_url(matter_id, fact_type), json={"value": value})
        assert response.status_code == 422, response.text
        error = response.json()["error"]
        assert error["code"] == "invalid_fact_value"
        issues = error["details"]["issues"]
        assert issues[0]["path"] == path
        assert issues[0]["code"] == code

    assert client.get(_fact_url(matter_id)).json()["facts"] == []


def test_certificate_and_competition_levels_are_saved(client: TestClient) -> None:
    matter_id = _create_matter(client)
    cases = [
        ("cert", {"level": "  高级  "}, {"level": "高级"}, "证书 高级"),
        (
            "comp",
            {"level": "国家级一等奖"},
            {"level": "国家级一等奖"},
            "竞赛 国家级一等奖",
        ),
    ]
    for fact_type, value, normalized, text in cases:
        response = client.put(_fact_url(matter_id, fact_type), json={"value": value})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["created"] is True
        assert body["fact"]["version_no"] == 1
        assert body["fact"]["value"] == normalized
        assert body["fact"]["value_text"] == text

    listed = client.get(_fact_url(matter_id)).json()["facts"]
    assert [item["fact_type"] for item in listed] == ["cert", "comp"]


def test_certificate_and_competition_levels_are_validated(
    client: TestClient,
) -> None:
    matter_id = _create_matter(client)
    for fact_type in ("cert", "comp"):
        missing = client.put(_fact_url(matter_id, fact_type), json={"value": {}})
        assert missing.status_code == 422, missing.text
        assert missing.json()["error"]["details"]["issues"][0] == {
            "path": "value.level",
            "code": "required",
            "message": (
                "证书需要提供 level" if fact_type == "cert" else "竞赛需要提供 level"
            ),
        }

        blank = client.put(
            _fact_url(matter_id, fact_type),
            json={"value": {"level": "   "}},
        )
        assert blank.status_code == 422, blank.text
        issue = blank.json()["error"]["details"]["issues"][0]
        assert issue["path"] == "value.level"
        assert issue["code"] == "invalid_level"

        too_long = client.put(
            _fact_url(matter_id, fact_type),
            json={"value": {"level": "等" * 33}},
        )
        assert too_long.status_code == 422, too_long.text
        assert too_long.json()["error"]["details"]["issues"][0]["code"] == (
            "invalid_level"
        )


def test_rank_greater_than_cohort_is_rejected(client: TestClient) -> None:
    matter_id = _create_matter(client)
    response = client.put(
        _fact_url(matter_id, "gpa.rank"),
        json={"value": {"position": 130, "cohort_size": 120}},
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "invalid_fact_value"
    issues = error["details"]["issues"]
    assert len(issues) == 1
    assert issues[0]["path"] == "value.position"
    assert issues[0]["code"] == "greater_than_cohort"

    stored = client.get(_fact_url(matter_id, "gpa.rank")).json()
    assert stored["fact"] is None
    assert stored["versions"] == []


def _fact_url(matter_id: str, fact_type: str | None = None) -> str:
    base = f"/api/v1/matters/{matter_id}/facts"
    return f"{base}/{fact_type}" if fact_type is not None else base


def _save_rank(
    client: TestClient,
    matter_id: str,
    *,
    position: int,
    cohort_size: int = 120,
) -> dict[str, Any]:
    response = client.put(
        _fact_url(matter_id, "gpa.rank"),
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


def _create_source(client: TestClient, matter_id: str, *, url: str = FX_URL) -> dict:
    response = client.post(
        f"/api/v1/matters/{matter_id}/sources",
        json={
            "url": url,
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
