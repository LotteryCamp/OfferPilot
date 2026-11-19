"""Acceptance tests for the Alpha core flow tracked by issue #34.

The tests run against the real FastAPI app and the PostgreSQL test database
provided by the backend integration fixtures. They do not mock the API,
persistence layer, or authorization checks.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient

FX_URL = "https://math.fzu.edu.cn/info/1171/10393.htm"
FX_TEXT = (
    "（5）符合推荐条件的学生，由本人自愿向学院提出申请，并于2026年9月10日"
    "下午15:00前提交《推荐免试攻读研究生资格申请表》以及相应科研成果和学科"
    "竞赛等奖项证明材料及成绩单（符合推免条件但放弃的同学需要提供放弃推免资格"
    "承诺书，本人签字按手印）。"
)
FX_HASH = "34599dc85bf72ca19837918f55c7cd275b9505bde994bbbea898ac7fa7b3abea"


def test_acceptance_main_flow_creates_tasks(client: TestClient) -> None:
    """Scenario 1/2/4: create, read source, confirm plan, read tasks."""
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
    assert replay.json()["replayed"] is True
    assert [task["id"] for task in replay.json()["tasks"]] == first_task_ids

    conflict = client.post(
        f"/api/v1/candidate-plans/{plan_id}/confirm",
        headers={"Idempotency-Key": "33333333-3333-7333-8333-333333333333"},
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "plan_already_decided"

    tasks = client.get(f"/api/v1/matters/{matter_id}/tasks").json()["tasks"]
    assert [task["title"] for task in tasks] == ["提交申请表", "准备成绩单"]
    application_task = next(task for task in tasks if task["title"] == "提交申请表")
    assert application_task["sources"][0]["locator"] == "第（5）项"
    assert application_task["sources"][0]["quote"] == FX_TEXT

    matter = client.get(f"/api/v1/matters/{matter_id}").json()["matter"]
    assert matter["tasks"] == {"total": 2, "done": 0, "open": 2}
    assert matter["latest_plan"]["status"] == "confirmed"


def test_acceptance_reject_does_not_create_tasks(client: TestClient) -> None:
    """Scenario 5: rejecting a plan must not create formal tasks."""
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
    assert response.json()["status"] == "rejected"
    assert response.json()["tasks"] == []
    assert client.get(f"/api/v1/matters/{matter_id}/tasks").json()["tasks"] == []


def test_acceptance_missing_required_fields(client: TestClient) -> None:
    """Missing required matter fields return 422 and create no matter."""
    response = client.post("/api/v1/matters", json={"scope_year": 2027})
    assert response.status_code == 422, response.text
    assert client.get("/api/v1/matters").json()["matters"] == []


def test_acceptance_invalid_source_url(client: TestClient) -> None:
    """An invalid source URL returns 422 and stores no source."""
    matter_id = _create_matter(client)
    payload = _source_payload()
    payload["url"] = "not-a-url"

    response = client.post(f"/api/v1/matters/{matter_id}/sources", json=payload)
    assert response.status_code == 422, response.text
    sources = client.get(f"/api/v1/matters/{matter_id}/sources").json()["sources"]
    assert sources == []


def test_acceptance_unknown_plan_returns_404(client: TestClient) -> None:
    """An unknown plan returns a structured 404, not a success-shaped body."""
    response = client.get(f"/api/v1/candidate-plans/{uuid4()}")
    assert response.status_code == 404
    body = response.json()
    assert "error" in body or "detail" in body


def test_acceptance_cross_workspace_matter_is_hidden(
    client: TestClient, admin: psycopg.Connection
) -> None:
    """Cross-user access must not reveal another workspace's matter."""
    other_user = UUID("99999999-9999-7999-8999-999999999999")
    other_workspace = UUID("99999999-9999-7999-8999-999999999998")
    other_matter = UUID("99999999-9999-7999-8999-999999999997")
    admin.execute(
        """
        INSERT INTO core.app_user
            (id, email, display_name, password_hash, account_type, status)
        VALUES (%s, 'acceptance-other@offerpilot.local', '其他用户', 'x',
                'applicant', 'active')
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

    assert client.get(f"/api/v1/matters/{other_matter}").status_code == 404
    listed = client.get("/api/v1/matters").json()["matters"]
    assert all(item["id"] != str(other_matter) for item in listed)


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
