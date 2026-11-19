"""End-to-end tests for matter, source, candidate, decision, and task flows."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers.deps import get_source_reader
from backend.sources import PublicSourceResult, parse_public_html

FX_URL = "https://math.fzu.edu.cn/info/1171/10393.htm"
FX_TEXT = (
    "（5）符合推荐条件的学生，由本人自愿向学院提出申请，并于2026年9月10日"
    "下午15:00前提交《推荐免试攻读研究生资格申请表》以及相应科研成果和学科"
    "竞赛等奖项证明材料及成绩单（符合推免条件但放弃的同学需要提供放弃推免资格"
    "承诺书，本人签字按手印）。"
)
FX_HASH = "34599dc85bf72ca19837918f55c7cd275b9505bde994bbbea898ac7fa7b3abea"

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sources"
NOTICE_HTML = FIXTURES / "fzu_notice.html.gz"
NOTICE_PROVENANCE = json.loads(
    (FIXTURES / "fzu_notice_provenance.json").read_text(encoding="utf-8")
)


def test_create_and_read_matter(client: TestClient) -> None:
    created = client.post(
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
    assert created.status_code == 201, created.text
    matter = created.json()["matter"]
    assert matter["status"] == "draft"
    assert matter["tasks"] == {"total": 0, "done": 0, "open": 0}

    read = client.get(f"/api/v1/matters/{matter['id']}")
    assert read.status_code == 200
    assert read.json()["matter"]["goal"] == matter["goal"]

    listed = client.get("/api/v1/matters")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["matters"]] == [matter["id"]]


def test_source_requirement_and_plan_read(client: TestClient) -> None:
    matter_id = _create_matter(client)
    source = _create_source(client, matter_id)
    assert source["snapshot"]["content_hash"] == FX_HASH
    requirement = _create_requirement(client, matter_id, source)
    plan = _create_plan(client, matter_id, source, requirement)

    sources = client.get(f"/api/v1/matters/{matter_id}/sources")
    assert sources.status_code == 200, sources.text
    source_body = sources.json()["sources"][0]
    assert source_body["url"] == FX_URL
    assert source_body["snapshots"][0]["title"].startswith("福州大学")
    assert source_body["snapshots"][0]["is_current"] is True
    assert source_body["snapshots"][0]["requirements"][0]["field_key"] == (
        "application.deadline"
    )
    assert (
        source_body["snapshots"][0]["requirements"][0]["evidence"][0]["locator"]
        == "第（5）项"
    )

    detail = client.get(f"/api/v1/candidate-plans/{plan['plan']['id']}")
    assert detail.status_code == 200, detail.text
    plan_body = detail.json()["plan"]
    assert plan_body["status"] == "pending"
    assert [item["title"] for item in plan_body["items"]] == [
        "提交申请表",
        "准备成绩单",
    ]
    assert plan_body["items"][1]["depends_on_item_ids"] == [plan_body["items"][0]["id"]]
    assert plan_body["items"][0]["sources"][0]["quote"] == FX_TEXT


def test_reject_does_not_create_tasks(client: TestClient) -> None:
    matter_id = _create_matter(client)
    source = _create_source(client, matter_id)
    requirement = _create_requirement(client, matter_id, source)
    plan = _create_plan(client, matter_id, source, requirement)
    plan_id = plan["plan"]["id"]

    response = client.post(
        f"/api/v1/candidate-plans/{plan_id}/reject",
        headers={"Idempotency-Key": "11111111-1111-7111-8111-111111111111"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "rejected"
    assert body["decision"]["decision"] == "rejected"
    assert body["tasks"] == []

    detail = client.get(f"/api/v1/candidate-plans/{plan_id}").json()["plan"]
    assert detail["status"] == "rejected"
    assert detail["decision"]["decision"] == "rejected"
    assert detail["tasks"] == []
    assert client.get(f"/api/v1/matters/{matter_id}/tasks").json()["tasks"] == []


def test_confirm_is_idempotent_and_tasks_trace_sources(
    client: TestClient,
) -> None:
    matter_id = _create_matter(client)
    source = _create_source(client, matter_id)
    requirement = _create_requirement(client, matter_id, source)
    plan = _create_plan(client, matter_id, source, requirement)
    plan_id = plan["plan"]["id"]
    key = "22222222-2222-7222-8222-222222222222"

    first = client.post(
        f"/api/v1/candidate-plans/{plan_id}/confirm",
        headers={"Idempotency-Key": key},
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["status"] == "confirmed"
    assert len(first_body["tasks"]) == 2
    assert first_body["replayed"] is False
    first_task_ids = [task["id"] for task in first_body["tasks"]]

    replay = client.post(
        f"/api/v1/candidate-plans/{plan_id}/confirm",
        headers={"Idempotency-Key": key},
    )
    assert replay.status_code == 200, replay.text
    replay_body = replay.json()
    assert replay_body["replayed"] is True
    assert [task["id"] for task in replay_body["tasks"]] == first_task_ids

    conflict = client.post(
        f"/api/v1/candidate-plans/{plan_id}/confirm",
        headers={"Idempotency-Key": "33333333-3333-7333-8333-333333333333"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "plan_already_decided"

    tasks = client.get(f"/api/v1/matters/{matter_id}/tasks").json()["tasks"]
    assert len(tasks) == 2
    assert [task["title"] for task in tasks] == ["提交申请表", "准备成绩单"]
    application_task = next(task for task in tasks if task["title"] == "提交申请表")
    assert application_task["official_deadline_at"] == "2026-09-10T07:00:00+00:00"
    assert application_task["sources"][0]["locator"] == "第（5）项"
    assert application_task["sources"][0]["quote"] == FX_TEXT

    matter = client.get(f"/api/v1/matters/{matter_id}").json()["matter"]
    assert matter["tasks"] == {"total": 2, "done": 0, "open": 2}
    assert matter["latest_plan"]["status"] == "confirmed"


def test_basis_change_expires_plan(
    client: TestClient, admin: psycopg.Connection
) -> None:
    matter_id = _create_matter(client)
    source = _create_source(client, matter_id)
    requirement = _create_requirement(client, matter_id, source)
    plan = _create_plan(client, matter_id, source, requirement)
    plan_id = plan["plan"]["id"]

    admin.execute(
        "UPDATE ops.source SET status = 'withdrawn' WHERE id = %s",
        (UUID(source["source"]["id"]),),
    )

    response = client.post(
        f"/api/v1/candidate-plans/{plan_id}/confirm",
        headers={"Idempotency-Key": "44444444-4444-7444-8444-444444444444"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "basis_changed"

    detail = client.get(f"/api/v1/candidate-plans/{plan_id}").json()["plan"]
    assert detail["status"] == "expired"
    assert detail["expired_at"] is not None
    assert detail["decision"] is None
    assert detail["tasks"] == []


def test_official_deadline_passed_blocks_confirm(client: TestClient, clock) -> None:
    matter_id = _create_matter(client)
    source = _create_source(client, matter_id)
    requirement = _create_requirement(client, matter_id, source)
    plan = _create_plan(client, matter_id, source, requirement)
    plan_id = plan["plan"]["id"]
    clock.value = datetime(2026, 9, 11, 0, 0, tzinfo=UTC)

    response = client.post(
        f"/api/v1/candidate-plans/{plan_id}/confirm",
        headers={"Idempotency-Key": "55555555-5555-7555-8555-555555555555"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "official_deadline_passed"
    detail = client.get(f"/api/v1/candidate-plans/{plan_id}").json()["plan"]
    assert detail["status"] == "pending"


def test_cross_workspace_matter_is_not_visible(
    client: TestClient, admin: psycopg.Connection
) -> None:
    other_user = UUID("99999999-9999-7999-8999-999999999999")
    other_workspace = UUID("99999999-9999-7999-8999-999999999998")
    other_matter = UUID("99999999-9999-7999-8999-999999999997")
    admin.execute(
        """
        INSERT INTO core.app_user
            (id, email, display_name, password_hash, account_type, status)
        VALUES (%s, 'other@offerpilot.local', '其他用户', 'x', 'applicant', 'active')
        """,
        (other_user,),
    )
    admin.execute(
        "INSERT INTO core.workspace (id, owner_id) VALUES (%s, %s)",
        (other_workspace, other_user),
    )
    admin.execute(
        """
        INSERT INTO core.matter
            (id, workspace_id, type_code, template_version_id, goal, status,
             scope_year, scope_attrs)
        SELECT %s, %s, 'pre_recommend', template_version.id, '其他用户的事项',
               'draft', 2027, '{}'
        FROM core.template_version
        WHERE type_code = 'pre_recommend' AND status = 'published'
        ORDER BY published_at DESC
        LIMIT 1
        """,
        (other_matter, other_workspace),
    )

    response = client.get(f"/api/v1/matters/{other_matter}")
    assert response.status_code == 404
    listed = client.get("/api/v1/matters").json()["matters"]
    assert all(item["id"] != str(other_matter) for item in listed)


def test_source_registration_versions_snapshots(client: TestClient) -> None:
    matter_id = _create_matter(client)
    first = _create_source(client, matter_id)
    _create_requirement(client, matter_id, first)
    second = client.post(
        f"/api/v1/matters/{matter_id}/sources",
        json=_source_payload(),
    )
    assert second.status_code == 201, second.text
    assert second.json()["created"] == {"source": False, "snapshot": False}
    assert second.json()["snapshot"]["id"] == first["snapshot"]["id"]

    changed = client.post(
        f"/api/v1/matters/{matter_id}/sources",
        json=_source_payload(content=FX_TEXT + "（更新）"),
    )
    assert changed.status_code == 201, changed.text
    assert changed.json()["snapshot"]["version_no"] == 2
    assert changed.json()["snapshot"]["is_current"] is True

    sources = client.get(f"/api/v1/matters/{matter_id}/sources").json()
    versions = {
        item["version_no"]: item["is_current"]
        for item in sources["sources"][0]["snapshots"]
    }
    assert versions == {1: False, 2: True}


def _captured_notice_reader(request: dict[str, Any]) -> PublicSourceResult:
    return parse_public_html(
        gzip.decompress(NOTICE_HTML.read_bytes()),
        content_type="text/html; charset=UTF-8",
        final_url=str(request["url"]),
        request=request,
        fetched_at=datetime.fromisoformat(NOTICE_PROVENANCE["retrieved_at"]),
    )


def test_read_public_source_registers_snapshot_for_citation(
    app: FastAPI, client: TestClient
) -> None:
    app.dependency_overrides[get_source_reader] = lambda: _captured_notice_reader
    try:
        matter_id = _create_matter(client)
        request_body = {
            "url": NOTICE_PROVENANCE["url"],
            "publisher": "福州大学数学与统计学院",
            "scope_year": 2027,
            "scope": "2027 届、本院、校内推免推荐",
        }
        response = client.post(
            f"/api/v1/matters/{matter_id}/sources/read", json=request_body
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["created"] == {"source": True, "snapshot": True}
        assert body["source"]["url"] == NOTICE_PROVENANCE["url"]
        assert (
            body["snapshot"]["content_hash"]
            == (NOTICE_PROVENANCE["fixture_html_sha256"])
        )
        assert body["snapshot"]["version_no"] == 1
        assert body["snapshot"]["published_date"] == "2026-09-08"
        assert body["snapshot"]["title"] == (
            "福州大学数学与统计学院2027年推荐优秀应届本科毕业生免试攻读研究生的工作方案"
            "-福州大学数学统计学院"
        )
        excerpt = next(
            fragment
            for fragment in body["snapshot"]["fragments"]
            if fragment["quote"].startswith("（5）")
        )
        assert excerpt["locator_kind"] == "text_span"
        assert excerpt["locator"] == "第31段，字符[0:124]"

        document = body["document"]
        assert document["source_id"] == body["source"]["id"]
        assert document["snapshot_id"] == document["source_version_id"]
        assert document["snapshot_id"] == body["snapshot"]["id"]
        assert document["version_no"] == 1
        assert document["fragments"] == body["snapshot"]["fragments"]
        assert document["is_expired"] is False

        replay = client.post(
            f"/api/v1/matters/{matter_id}/sources/read", json=request_body
        )
        assert replay.status_code == 201, replay.text
        assert replay.json()["created"] == {"source": False, "snapshot": False}
        assert replay.json()["snapshot"]["id"] == body["snapshot"]["id"]

        requirement = client.post(
            f"/api/v1/matters/{matter_id}/requirements",
            json={
                "requirements": [
                    {
                        "field_key": "application.material",
                        "label": "提交申请与材料",
                        "obligation_nature": "required",
                        "extract_status": "checked",
                        "snapshot_id": body["snapshot"]["id"],
                        "evidence": [
                            {
                                "source_id": body["source"]["id"],
                                "snapshot_id": body["snapshot"]["id"],
                                "locator_kind": excerpt["locator_kind"],
                                "locator": excerpt["locator"],
                                "quote": excerpt["quote"],
                            }
                        ],
                    }
                ]
            },
        )
        assert requirement.status_code == 201, requirement.text

        sources = client.get(f"/api/v1/matters/{matter_id}/sources").json()["sources"]
        assert len(sources) == 1
        assert (
            sources[0]["snapshots"][0]["requirements"][0]["evidence"][0]["locator"]
            == excerpt["locator"]
        )
    finally:
        app.dependency_overrides.clear()


def test_read_public_source_reports_unreadable_source(
    client: TestClient,
) -> None:
    matter_id = _create_matter(client)
    response = client.post(
        f"/api/v1/matters/{matter_id}/sources/read",
        json={
            "url": "http://127.0.0.1/notice",
            "publisher": "福州大学",
            "scope_year": 2027,
        },
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "source_read_failed"
    assert error["details"] == {"code": "unsafe_url", "retryable": False}


def test_read_public_source_requires_owned_matter(client: TestClient) -> None:
    response = client.post(
        "/api/v1/matters/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/sources/read",
        json={
            "url": NOTICE_PROVENANCE["url"],
            "publisher": "福州大学数学与统计学院",
            "scope_year": 2027,
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "matter_not_found"


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


def _source_payload(content: str = FX_TEXT) -> dict:
    return {
        "url": FX_URL,
        "publisher": "福州大学数学与统计学院",
        "title": "福州大学数学与统计学院2027年推荐优秀应届本科毕业生免试攻读研究生的工作方案",
        "scope": "2027 届、本院、校内推免推荐",
        "scope_year": 2027,
        "published_date": "2026-09-08",
        "content": content,
        "fragments": [
            {
                "locator_kind": "section",
                "locator": "第（5）项",
                "quote": content,
            }
        ],
    }


def _create_source(client: TestClient, matter_id: str) -> dict:
    response = client.post(
        f"/api/v1/matters/{matter_id}/sources",
        json=_source_payload(),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_requirement(client: TestClient, matter_id: str, source: dict) -> dict:
    response = client.post(
        f"/api/v1/matters/{matter_id}/requirements",
        json={
            "requirements": [
                {
                    "field_key": "application.deadline",
                    "label": "提交申请与材料截止",
                    "obligation_nature": "required",
                    "extract_status": "checked",
                    "scope": "2027 届、本院",
                    "value_text": "2026-09-10T15:00:00+08:00",
                    "value_type": "text",
                    "confidence": 0.9,
                    "snapshot_id": source["snapshot"]["id"],
                    "evidence": [
                        {
                            "source_id": source["source"]["id"],
                            "snapshot_id": source["snapshot"]["id"],
                            "locator_kind": "section",
                            "locator": "第（5）项",
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
    client: TestClient, matter_id: str, source: dict, requirement: dict
) -> dict:
    citation = {
        "source_id": source["source"]["id"],
        "snapshot_id": source["snapshot"]["id"],
        "locator_kind": "section",
        "locator": "第（5）项",
        "quote": FX_TEXT,
    }
    response = client.post(
        f"/api/v1/matters/{matter_id}/candidate-plans",
        json={
            "items": [
                {
                    "client_item_id": "t1",
                    "title": "提交申请表",
                    "detail": "按学院要求提交资格申请表",
                    "obligation_nature": "required",
                    "official_deadline_date": "2026-09-10",
                    "official_deadline_at": "2026-09-10T15:00:00+08:00",
                    "suggested_date": "2026-09-09",
                    "depends_on": [],
                    "evidence_required": True,
                    "requirement_id": requirement["id"],
                    "sources": [citation],
                },
                {
                    "client_item_id": "t2",
                    "title": "准备成绩单",
                    "obligation_nature": "required",
                    "official_deadline_date": "2026-09-10",
                    "suggested_date": "2026-09-09",
                    "depends_on": ["t1"],
                    "evidence_required": True,
                    "sources": [citation],
                },
            ]
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
