"""End-to-end tests for Agent runs driven by the backend business API."""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend.agent import (
    CandidatePlanDraftPayload,
    CandidateTaskDraft,
    ExtractedRequirementDraft,
    ObligationType,
    RequirementExtractionPayload,
    SourceCitation,
    StructuredModelAdapter,
)
from backend.config import Settings
from backend.main import create_app
from backend.sources import PublicSourceResult, parse_public_html

SOURCE_URL = "https://math.fzu.edu.cn/info/1171/10393.htm"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sources"
NOTICE_HTML = FIXTURES / "fzu_notice.html.gz"
FETCHED_AT = datetime.fromisoformat("2026-09-09T01:00:00+00:00")
USER_ID = UUID("00000000-0000-7000-8000-000000000001")
WORKSPACE_ID = UUID("00000000-0000-7000-8000-000000000002")


class _ReplayState:
    def __init__(self) -> None:
        self.source: PublicSourceResult | None = None


def _fixture_reader(state: _ReplayState):
    def read(request: dict[str, Any]) -> PublicSourceResult:
        result = parse_public_html(
            gzip.decompress(NOTICE_HTML.read_bytes()),
            content_type="text/html; charset=UTF-8",
            final_url=str(request["url"]),
            request=request,
            fetched_at=FETCHED_AT,
        )
        state.source = result
        return result

    return read


def _replay_call_model(state: _ReplayState):
    def call_model[T: BaseModel](
        instruction: str,
        text: str,
        response_model: type[T],
    ) -> T:
        payload = json.loads(text)
        source_version_id = payload["sources"][0]["source_version_id"]
        assert state.source is not None
        fragment = next(
            item for item in state.source.fragments if item.quote.startswith("（5）")
        )

        if response_model is RequirementExtractionPayload:
            extracted = RequirementExtractionPayload(
                requirements=[
                    ExtractedRequirementDraft(
                        requirement_id="GR-02",
                        title="向学院提交申请材料截止",
                        obligation=ObligationType.OFFICIAL_REQUIRED,
                        field_key="application.deadline",
                        scope="2027 届、福州大学数学与统计学院、校内推荐申请",
                        value_text="2026-09-10T15:00:00+08:00",
                        value_type="text",
                        confidence=0.95,
                        basis=[
                            SourceCitation(
                                source_version_id=source_version_id,
                                locator=fragment.locator_text,
                                excerpt="2026年9月10日下午15:00前",
                            )
                        ],
                        official_deadline=datetime.fromisoformat(
                            "2026-09-10T15:00:00+08:00"
                        ),
                    )
                ],
                gaps=[],
                scope_summary={
                    "intake_year": 2027,
                    "school": "福州大学",
                    "college": "数学与统计学院",
                },
            )
            return response_model.model_validate(extracted.model_dump())

        plan_payload = CandidatePlanDraftPayload(
            tasks=[
                CandidateTaskDraft(
                    task_id="T-01",
                    title="准备并提交申请表、奖项证明及成绩单",
                    requirement_id="GR-02",
                    basis=[
                        SourceCitation(
                            source_version_id=source_version_id,
                            locator=fragment.locator_text,
                            excerpt="2026年9月10日下午15:00前",
                        )
                    ],
                    obligation=ObligationType.OFFICIAL_REQUIRED,
                    official_deadline_at=datetime.fromisoformat(
                        "2026-09-10T15:00:00+08:00"
                    ),
                    suggested_date=datetime.fromisoformat("2026-09-09").date(),
                    depends_on=[],
                    evidence_required="已准备申请表、科研与竞赛证明、成绩单",
                )
            ]
        )
        return response_model.model_validate(plan_payload.model_dump())

    return call_model


@pytest.fixture()
def agent_client(
    database_urls: tuple[str, str],
    admin: psycopg.Connection,
    clock,
) -> Iterator[TestClient]:
    app_url, _ = database_urls
    settings = Settings(
        database_url=app_url,
        demo_user_id=USER_ID,
        demo_workspace_id=WORKSPACE_ID,
        demo_timezone="Asia/Shanghai",
    )
    state = _ReplayState()
    app: FastAPI = create_app(
        settings,
        clock=clock,
        model_adapter=StructuredModelAdapter(_replay_call_model(state)),
        agent_source_reader=_fixture_reader(state),
    )
    with TestClient(app) as client:
        yield client


def test_agent_run_generates_candidate_then_confirms(agent_client: TestClient) -> None:
    matter_id = _create_matter(agent_client)

    created = agent_client.post(
        f"/api/v1/matters/{matter_id}/agent-runs",
        json={
            "source_urls": [SOURCE_URL],
            "publisher": "福州大学数学与统计学院",
            "scope": "2027 届、本院、校内推免推荐",
            "operation_id": "run-operation-1",
        },
    )
    assert created.status_code == 200, created.text
    run = created.json()["run"]
    assert run["status"] == "等待确认", run["error"]
    assert run["persisted_plan_id"] is not None
    assert run["error"] is None

    plan_id = run["persisted_plan_id"]
    plan = agent_client.get(f"/api/v1/candidate-plans/{plan_id}")
    assert plan.status_code == 200, plan.text
    assert plan.json()["plan"]["status"] == "pending"
    assert plan.json()["plan"]["tasks"] == []
    assert agent_client.get(f"/api/v1/matters/{matter_id}/tasks").json()["tasks"] == []

    confirmed = agent_client.post(
        f"/api/v1/agent-runs/{run['run_id']}/confirm",
        json={"candidate_version": 1},
        headers={"Idempotency-Key": "11111111-1111-7111-8111-111111111111"},
    )
    assert confirmed.status_code == 200, confirmed.text
    confirmed_run = confirmed.json()["run"]
    assert confirmed_run["status"] == "已完成"
    assert len(confirmed_run["written_tasks"]) == 1

    tasks = agent_client.get(f"/api/v1/matters/{matter_id}/tasks").json()["tasks"]
    assert [task["title"] for task in tasks] == ["准备并提交申请表、奖项证明及成绩单"]


def test_agent_run_reject_creates_no_tasks(agent_client: TestClient) -> None:
    matter_id = _create_matter(agent_client)
    created = agent_client.post(
        f"/api/v1/matters/{matter_id}/agent-runs",
        json={
            "source_urls": [SOURCE_URL],
            "publisher": "福州大学数学与统计学院",
            "scope": "2027 届、本院、校内推免推荐",
        },
    )
    run = created.json()["run"]
    assert run["status"] == "等待确认", run["error"]

    rejected = agent_client.post(
        f"/api/v1/agent-runs/{run['run_id']}/reject",
        headers={"Idempotency-Key": "22222222-2222-7222-8222-222222222222"},
    )
    assert rejected.status_code == 200, rejected.text
    rejected_run = rejected.json()["run"]
    assert rejected_run["status"] == "已取消"
    assert rejected_run["written_tasks"] == []
    assert agent_client.get(f"/api/v1/matters/{matter_id}/tasks").json()["tasks"] == []


def test_unknown_run_returns_not_found(agent_client: TestClient) -> None:
    response = agent_client.get("/api/v1/agent-runs/run-missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "agent_run_not_found"


def _create_matter(client: TestClient) -> str:
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
    return created.json()["matter"]["id"]
