"""End-to-end tests for Agent runs driven by the backend business API."""

from __future__ import annotations

import gzip
import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
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


class _ReplayState:
    def __init__(self) -> None:
        self.source: PublicSourceResult | None = None
        self.requirement_field_key = "application.deadline"
        self.before_candidate_plan: Callable[[], None] | None = None


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
                        field_key=state.requirement_field_key,
                        scope="2027 届、福州大学数学与统计学院、校内推荐申请",
                        value_text="2026-09-10T15:00:00+08:00",
                        value_type="text",
                        confidence=0.95,
                        basis=[
                            SourceCitation(
                                source_version_id=source_version_id,
                                locator_kind=fragment.locator.kind,
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

        if state.before_candidate_plan is not None:
            state.before_candidate_plan()

        plan_payload = CandidatePlanDraftPayload(
            tasks=[
                CandidateTaskDraft(
                    task_id="T-01",
                    title="准备并提交申请表、奖项证明及成绩单",
                    requirement_id="GR-02",
                    basis=[
                        SourceCitation(
                            source_version_id=source_version_id,
                            locator_kind=fragment.locator.kind,
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
    login,
) -> Iterator[TestClient]:
    app_url, _ = database_urls
    settings = Settings(
        database_url=app_url,
        timezone="Asia/Shanghai",
    )
    state = _ReplayState()
    app: FastAPI = create_app(
        settings,
        clock=clock,
        model_adapter=StructuredModelAdapter(_replay_call_model(state)),
        agent_source_reader=_fixture_reader(state),
    )
    app.state.replay_state = state
    with TestClient(app) as client:
        login(client)
        yield client


def test_agent_run_generates_candidate_then_confirms(agent_client: TestClient) -> None:
    matter_id = _create_matter(agent_client)
    _grant_consent(agent_client)

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


def test_agent_run_without_transfer_consent_returns_422(
    agent_client: TestClient, admin: psycopg.Connection
) -> None:
    matter_id = _create_matter(agent_client)
    created = agent_client.post(
        f"/api/v1/matters/{matter_id}/agent-runs",
        json={
            "source_urls": [SOURCE_URL],
            "publisher": "福州大学数学与统计学院",
            "scope": "2027 届、本院、校内推免推荐",
            "operation_id": "run-without-consent",
        },
    )

    assert created.status_code == 422, created.text
    assert created.json()["error"]["code"] == "model_transfer_consent_required"
    run_count = admin.execute("SELECT count(*) FROM core.agent_run").fetchone()
    assert run_count is not None
    assert run_count[0] == 0
    assert agent_client.get(f"/api/v1/matters/{matter_id}/tasks").json()["tasks"] == []


def test_fact_archive_requires_consent_without_scope_attrs(
    agent_client: TestClient,
) -> None:
    created = agent_client.post(
        "/api/v1/matters",
        json={
            "goal": "申请 2027 年福州大学数学与统计学院推免",
            "type_code": "pre_recommend",
            "scope_year": 2027,
        },
    )
    assert created.status_code == 201, created.text
    matter_id = created.json()["matter"]["id"]
    saved = agent_client.put(
        f"/api/v1/matters/{matter_id}/facts/gpa.rank",
        json={"value": {"position": 5, "cohort_size": 120}},
    )
    assert saved.status_code == 200, saved.text

    response = agent_client.post(
        f"/api/v1/matters/{matter_id}/agent-runs",
        json={
            "source_urls": [SOURCE_URL],
            "publisher": "福州大学数学与统计学院",
            "scope": "2027 届、本院、校内推免推荐",
            "operation_id": "fact-archive-consent",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "model_transfer_consent_required"


def test_model_transfer_consent_entry_returns_current_consent(
    agent_client: TestClient,
) -> None:
    before = agent_client.get("/api/v1/model-transfer-consent")
    assert before.status_code == 200, before.text
    body = before.json()
    assert body["consent"] is None
    disclosure = body["disclosure"]
    assert disclosure["provider"]
    assert disclosure["field_categories"] == [
        "matter_goal",
        "public_scope",
        "public_sources",
    ]
    assert disclosure["purposes"] == [
        "requirement_extraction",
        "candidate_planning",
    ]
    assert disclosure["consent_scope"]
    assert disclosure["data_handling"]

    granted = agent_client.post("/api/v1/model-transfer-consent")
    assert granted.status_code == 200, granted.text
    granted_body = granted.json()
    assert granted_body["created"] is True
    consent = granted_body["consent"]
    assert consent["status"] == "active"
    assert "matter_id" not in consent
    assert "provider" not in consent
    assert consent["version_no"] == 1
    assert consent["revoked_at"] is None

    replayed = agent_client.post("/api/v1/model-transfer-consent")
    assert replayed.status_code == 200, replayed.text
    assert replayed.json()["created"] is False
    assert replayed.json()["consent"]["consent_id"] == consent["consent_id"]

    current = agent_client.get("/api/v1/model-transfer-consent")
    assert current.status_code == 200, current.text
    assert current.json()["consent"]["consent_id"] == consent["consent_id"]


def test_revoked_consent_blocks_agent_run(agent_client: TestClient) -> None:
    matter_id = _create_matter(agent_client)
    consent_id = _grant_consent(agent_client)
    revoked = agent_client.delete(f"/api/v1/model-transfer-consent/{consent_id}")
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked"] is True
    assert revoked.json()["consent"]["status"] == "revoked"

    created = agent_client.post(
        f"/api/v1/matters/{matter_id}/agent-runs",
        json={
            "source_urls": [SOURCE_URL],
            "publisher": "福州大学数学与统计学院",
            "scope": "2027 届、本院、校内推免推荐",
            "operation_id": "revoked-consent",
        },
    )
    assert created.status_code == 422, created.text
    assert created.json()["error"]["code"] == "model_transfer_consent_required"

    current = agent_client.get("/api/v1/model-transfer-consent")
    assert current.json()["consent"] is None

    repeated = agent_client.delete(f"/api/v1/model-transfer-consent/{consent_id}")
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["revoked"] is False

    regranted = agent_client.post("/api/v1/model-transfer-consent")
    assert regranted.status_code == 200, regranted.text
    renewed = regranted.json()["consent"]
    assert regranted.json()["created"] is True
    assert renewed["consent_id"] != consent_id
    assert renewed["version_no"] == 2

    retried = agent_client.post(
        f"/api/v1/matters/{matter_id}/agent-runs",
        json={
            "source_urls": [SOURCE_URL],
            "publisher": "福州大学数学与统计学院",
            "scope": "2027 届、本院、校内推免推荐",
            "operation_id": "regranted-consent",
        },
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["run"]["status"] == "等待确认"


def test_global_consent_covers_all_matters(
    agent_client: TestClient, admin: psycopg.Connection
) -> None:
    matter_a = _create_matter(agent_client)
    matter_b = _create_matter(agent_client)
    _grant_consent(agent_client)

    for matter_id, operation_id in (
        (matter_a, "global-consent-matter-a"),
        (matter_b, "global-consent-matter-b"),
    ):
        created = agent_client.post(
            f"/api/v1/matters/{matter_id}/agent-runs",
            json={
                "source_urls": [SOURCE_URL],
                "publisher": "福州大学数学与统计学院",
                "scope": "2027 届、本院、校内推免推荐",
                "operation_id": operation_id,
            },
        )
        assert created.status_code == 200, created.text
        assert created.json()["run"]["status"] == "等待确认"

    run_count = admin.execute("SELECT count(*) FROM core.agent_run").fetchone()
    assert run_count is not None
    assert run_count[0] == 2


def test_consent_survives_model_provider_change(
    agent_client: TestClient,
    database_urls: tuple[str, str],
    clock,
    login,
) -> None:
    matter_id = _create_matter(agent_client)
    _grant_consent(agent_client)

    app_url, _ = database_urls
    state = _ReplayState()
    changed_app: FastAPI = create_app(
        Settings(
            database_url=app_url,
            timezone="Asia/Shanghai",
            model_provider="另一模型服务",
            model_name="another-model",
        ),
        clock=clock,
        model_adapter=StructuredModelAdapter(_replay_call_model(state)),
        agent_source_reader=_fixture_reader(state),
    )
    with TestClient(changed_app) as changed_client:
        login(changed_client)
        current = changed_client.get("/api/v1/model-transfer-consent")
        assert current.status_code == 200, current.text
        assert current.json()["consent"] is not None
        assert current.json()["disclosure"]["provider"] == "另一模型服务"

        created = changed_client.post(
            f"/api/v1/matters/{matter_id}/agent-runs",
            json={
                "source_urls": [SOURCE_URL],
                "publisher": "福州大学数学与统计学院",
                "scope": "2027 届、本院、校内推免推荐",
                "operation_id": "provider-change-run",
            },
        )
        assert created.status_code == 200, created.text
        assert created.json()["run"]["status"] == "等待确认"


def test_agent_run_reject_creates_no_tasks(agent_client: TestClient) -> None:
    matter_id = _create_matter(agent_client)
    _grant_consent(agent_client)
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


def test_agent_run_cancel_during_model_call_leaves_no_candidate(
    agent_client: TestClient, admin: psycopg.Connection
) -> None:
    state = cast(FastAPI, agent_client.app).state.replay_state
    matter_id = _create_matter(agent_client)
    _grant_consent(agent_client)

    def cancel_running_run() -> None:
        state.before_candidate_plan = None
        running = admin.execute(
            "SELECT run_id FROM core.agent_run WHERE status = 'running'"
        ).fetchone()
        assert running is not None
        cancelled = agent_client.post(f"/api/v1/agent-runs/{running[0]}/cancel")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["run"]["status"] == "已取消"

    state.before_candidate_plan = cancel_running_run
    created = agent_client.post(
        f"/api/v1/matters/{matter_id}/agent-runs",
        json={
            "source_urls": [SOURCE_URL],
            "publisher": "福州大学数学与统计学院",
            "scope": "2027 届、本院、校内推免推荐",
            "operation_id": "cancel-during-model-call",
        },
    )
    assert created.status_code == 200, created.text
    run = created.json()["run"]
    assert run["status"] == "已取消"
    assert run["error"]["code"] == "CANCELLED"
    assert run["persisted_plan_id"] is None

    fetched = agent_client.get(f"/api/v1/agent-runs/{run['run_id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["run"]["status"] == "已取消"

    plan_count = admin.execute(
        "SELECT count(*) FROM core.candidate_plan WHERE matter_id = %s",
        (UUID(matter_id),),
    ).fetchone()
    assert plan_count is not None
    assert plan_count[0] == 0
    requirement_count = admin.execute(
        "SELECT count(*) FROM core.requirement WHERE matter_id = %s",
        (UUID(matter_id),),
    ).fetchone()
    assert requirement_count is not None
    assert requirement_count[0] == 0


def test_agent_run_cancel_rejects_pending_candidate(
    agent_client: TestClient, admin: psycopg.Connection
) -> None:
    matter_id = _create_matter(agent_client)
    _grant_consent(agent_client)
    created = agent_client.post(
        f"/api/v1/matters/{matter_id}/agent-runs",
        json={
            "source_urls": [SOURCE_URL],
            "publisher": "福州大学数学与统计学院",
            "scope": "2027 届、本院、校内推免推荐",
            "operation_id": "cancel-after-plan",
        },
    )
    run = created.json()["run"]
    assert run["status"] == "等待确认", run["error"]
    plan_id = run["persisted_plan_id"]
    assert plan_id is not None

    cancelled = agent_client.post(f"/api/v1/agent-runs/{run['run_id']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["run"]["status"] == "已取消"

    plan = agent_client.get(f"/api/v1/candidate-plans/{plan_id}")
    assert plan.status_code == 200, plan.text
    assert plan.json()["plan"]["status"] == "rejected"

    requirements = admin.execute(
        "SELECT extract_status FROM core.requirement WHERE matter_id = %s",
        (UUID(matter_id),),
    ).fetchall()
    assert requirements
    assert {row[0] for row in requirements} == {"rejected"}

    confirmed = agent_client.post(
        f"/api/v1/candidate-plans/{plan_id}/confirm",
        headers={"Idempotency-Key": "33333333-3333-7333-8333-333333333333"},
    )
    assert confirmed.status_code == 409, confirmed.text
    assert confirmed.json()["error"]["code"] == "plan_already_decided"

    confirmed_run = agent_client.post(
        f"/api/v1/agent-runs/{run['run_id']}/confirm",
        json={"candidate_version": 1},
        headers={"Idempotency-Key": "44444444-4444-7444-8444-444444444444"},
    )
    assert confirmed_run.status_code == 200, confirmed_run.text
    assert confirmed_run.json()["run"]["status"] == "已取消"
    assert confirmed_run.json()["run"]["written_tasks"] == []
    assert agent_client.get(f"/api/v1/matters/{matter_id}/tasks").json()["tasks"] == []


def test_agent_run_cancel_preserves_failed_result(
    agent_client: TestClient, admin: psycopg.Connection
) -> None:
    state = cast(FastAPI, agent_client.app).state.replay_state
    state.requirement_field_key = "gpa.rank"
    matter_id = _create_matter(agent_client)
    saved = agent_client.put(
        f"/api/v1/matters/{matter_id}/facts/gpa.rank",
        json={"value": {"position": 5, "cohort_size": 120}},
    )
    assert saved.status_code == 200, saved.text
    _grant_consent(agent_client)

    def change_fact() -> None:
        state.before_candidate_plan = None
        changed = agent_client.put(
            f"/api/v1/matters/{matter_id}/facts/gpa.rank",
            json={"value": {"position": 8, "cohort_size": 120}},
        )
        assert changed.status_code == 200, changed.text

    state.before_candidate_plan = change_fact
    created = agent_client.post(
        f"/api/v1/matters/{matter_id}/agent-runs",
        json={
            "source_urls": [SOURCE_URL],
            "publisher": "福州大学数学与统计学院",
            "scope": "2027 届、本院、校内推免推荐",
            "operation_id": "cancel-failed-run",
        },
    )
    assert created.status_code == 200, created.text
    run = created.json()["run"]
    assert run["status"] == "失败"
    assert run["error"]["code"] == "VERSION_CONFLICT"

    admin.execute(
        "UPDATE core.agent_run SET checkpoint = NULL WHERE run_id = %s",
        (run["run_id"],),
    )
    cancelled = agent_client.post(f"/api/v1/agent-runs/{run['run_id']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["run"]["status"] == "失败"

    stored = admin.execute(
        "SELECT status FROM core.agent_run WHERE run_id = %s",
        (run["run_id"],),
    ).fetchone()
    assert stored == ("failed",)


def test_agent_run_retry_after_cancel_starts_new_run(
    agent_client: TestClient,
) -> None:
    matter_id = _create_matter(agent_client)
    _grant_consent(agent_client)
    payload = {
        "source_urls": [SOURCE_URL],
        "publisher": "福州大学数学与统计学院",
        "scope": "2027 届、本院、校内推免推荐",
        "operation_id": "cancel-then-retry",
    }
    created = agent_client.post(f"/api/v1/matters/{matter_id}/agent-runs", json=payload)
    assert created.status_code == 200, created.text
    run = created.json()["run"]
    assert run["status"] == "等待确认"

    cancelled = agent_client.post(f"/api/v1/agent-runs/{run['run_id']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["run"]["status"] == "已取消"

    retried = agent_client.post(f"/api/v1/matters/{matter_id}/agent-runs", json=payload)
    assert retried.status_code == 200, retried.text
    retried_run = retried.json()["run"]
    assert retried_run["run_id"] != run["run_id"]
    assert retried_run["status"] == "等待确认"


def test_agent_run_reads_and_confirms_after_restart(
    agent_client: TestClient,
    database_urls: tuple[str, str],
    clock,
    login,
) -> None:
    matter_id = _create_matter(agent_client)
    _grant_consent(agent_client)
    created = agent_client.post(
        f"/api/v1/matters/{matter_id}/agent-runs",
        json={
            "source_urls": [SOURCE_URL],
            "publisher": "福州大学数学与统计学院",
            "scope": "2027 届、本院、校内推免推荐",
            "operation_id": "restart-operation-1",
        },
    )
    assert created.status_code == 200, created.text
    run = created.json()["run"]
    assert run["status"] == "等待确认"

    app_url, _ = database_urls
    restarted_app = create_app(
        Settings(
            database_url=app_url,
            timezone="Asia/Shanghai",
        ),
        clock=clock,
    )
    with TestClient(restarted_app) as restarted:
        login(restarted)
        fetched = restarted.get(f"/api/v1/agent-runs/{run['run_id']}")
        assert fetched.status_code == 200, fetched.text
        fetched_run = fetched.json()["run"]
        assert fetched_run["status"] == "等待确认"
        assert fetched_run["persisted_plan_id"] == run["persisted_plan_id"]

        confirmed = restarted.post(
            f"/api/v1/agent-runs/{run['run_id']}/confirm",
            json={"candidate_version": 1},
            headers={"Idempotency-Key": "77777777-7777-7777-8777-777777777777"},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["run"]["status"] == "已完成"
        assert confirmed.json()["run"]["candidate_plan"] is not None
        assert confirmed.json()["run"]["extracted_requirements"]

        refetched = restarted.get(f"/api/v1/agent-runs/{run['run_id']}")
        assert refetched.status_code == 200, refetched.text
        final_run = refetched.json()["run"]
        assert final_run["status"] == "已完成"
        assert final_run["candidate_plan"]["candidate_version"] == 1
        assert final_run["evaluations"]


def test_confirm_uses_timezone_from_request_time(
    database_urls: tuple[str, str],
    clock,
    login,
    tmp_path: Path,
) -> None:
    app_url, _ = database_urls
    config_path = tmp_path / "config.yaml"
    config_path.write_text("timezone: Pacific/Honolulu\n", encoding="utf-8")
    state = _ReplayState()
    app: FastAPI = create_app(
        Settings(
            database_url=app_url,
            timezone="Asia/Shanghai",
            config_file=str(config_path),
        ),
        clock=clock,
        model_adapter=StructuredModelAdapter(_replay_call_model(state)),
        agent_source_reader=_fixture_reader(state),
    )

    with TestClient(app) as client:
        clock.value = datetime(2026, 9, 10, 6, 0, tzinfo=UTC)
        login(client)
        matter_id = _create_matter(client)
        _grant_consent(client)
        created = client.post(
            f"/api/v1/matters/{matter_id}/agent-runs",
            json={
                "source_urls": [SOURCE_URL],
                "publisher": "福州大学数学与统计学院",
                "scope": "2027 届、本院、校内推免推荐",
                "operation_id": "timezone-change-run",
            },
        )
        assert created.status_code == 200, created.text
        run = created.json()["run"]
        assert run["status"] == "等待确认", run["error"]

        app.state.runtime_config.update({"timezone": "Asia/Shanghai"})

        confirmed = client.post(
            f"/api/v1/agent-runs/{run['run_id']}/confirm",
            json={"candidate_version": 1},
            headers={"Idempotency-Key": "99999999-9999-7999-8999-999999999999"},
        )
        assert confirmed.status_code == 200, confirmed.text
        failed = confirmed.json()["run"]
        assert failed["status"] == "失败"
        assert failed["error"]["code"] == "DEADLINE_EXPIRED"
        assert client.get(f"/api/v1/matters/{matter_id}/tasks").json()["tasks"] == []


def test_interrupted_run_is_reported_and_can_restart(
    agent_client: TestClient,
    admin: psycopg.Connection,
    database_urls: tuple[str, str],
    clock,
    login,
) -> None:
    matter_id = _create_matter(agent_client)
    _grant_consent(agent_client)
    admin.execute(
        """
        INSERT INTO core.agent_run
            (run_id, matter_id, user_id, status, operation_id)
        VALUES ('run-interrupted', %s, %s, 'interrupted', 'retry-after-interrupt')
        """,
        (UUID(matter_id), USER_ID),
    )

    app_url, _ = database_urls
    restarted_app = create_app(
        Settings(
            database_url=app_url,
            timezone="Asia/Shanghai",
        ),
        clock=clock,
    )
    with TestClient(restarted_app) as restarted:
        login(restarted)
        fetched = restarted.get("/api/v1/agent-runs/run-interrupted")
        assert fetched.status_code == 200, fetched.text
        interrupted = fetched.json()["run"]
        assert interrupted["status"] == "已中断"
        assert interrupted["error"]["code"] == "RUN_INTERRUPTED"
        assert interrupted["error"]["details"]["retryable"] is True

    retried = agent_client.post(
        f"/api/v1/matters/{matter_id}/agent-runs",
        json={
            "source_urls": [SOURCE_URL],
            "publisher": "福州大学数学与统计学院",
            "scope": "2027 届、本院、校内推免推荐",
            "operation_id": "retry-after-interrupt",
        },
    )
    assert retried.status_code == 200, retried.text
    retried_run = retried.json()["run"]
    assert retried_run["run_id"] != "run-interrupted"
    assert retried_run["status"] == "等待确认"


def test_blocked_candidate_stays_pending_after_restart(
    agent_client: TestClient,
    admin: psycopg.Connection,
    database_urls: tuple[str, str],
    clock,
    login,
) -> None:
    matter_id = _create_matter(agent_client)
    _grant_consent(agent_client)
    created = agent_client.post(
        f"/api/v1/matters/{matter_id}/agent-runs",
        json={
            "source_urls": [SOURCE_URL],
            "publisher": "福州大学数学与统计学院",
            "scope": "2027 届、本院、校内推免推荐",
            "operation_id": "restart-block-operation-1",
        },
    )
    assert created.status_code == 200, created.text
    run = created.json()["run"]
    assert run["status"] == "等待确认"

    admin.execute("UPDATE ops.source SET auto_check_status = 'conflict'")

    app_url, _ = database_urls
    restarted_app = create_app(
        Settings(
            database_url=app_url,
            timezone="Asia/Shanghai",
        ),
        clock=clock,
    )
    with TestClient(restarted_app) as restarted:
        login(restarted)
        confirmed = restarted.post(
            f"/api/v1/agent-runs/{run['run_id']}/confirm",
            json={"candidate_version": 1},
            headers={"Idempotency-Key": "88888888-8888-7888-8888-888888888888"},
        )
        assert confirmed.status_code == 200, confirmed.text
        blocked = confirmed.json()["run"]
        assert blocked["status"] == "等待确认"
        assert blocked["error"]["details"]["backend_code"] == "source_unavailable"

        plan = restarted.get(f"/api/v1/candidate-plans/{run['persisted_plan_id']}")
        assert plan.status_code == 200, plan.text
        assert plan.json()["plan"]["status"] == "pending"


def test_unknown_run_returns_not_found(agent_client: TestClient) -> None:
    response = agent_client.get("/api/v1/agent-runs/run-missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "agent_run_not_found"


def test_agent_run_records_confirmed_rank_fact(
    agent_client: TestClient, admin: psycopg.Connection
) -> None:
    state = cast(FastAPI, agent_client.app).state.replay_state
    state.requirement_field_key = "gpa.rank"
    matter_id = _create_matter(agent_client)
    saved = agent_client.put(
        f"/api/v1/matters/{matter_id}/facts/gpa.rank",
        json={"value": {"position": 5, "cohort_size": 120}},
    )
    assert saved.status_code == 200, saved.text
    fact = saved.json()["fact"]
    _grant_consent(agent_client)

    created = agent_client.post(
        f"/api/v1/matters/{matter_id}/agent-runs",
        json={
            "source_urls": [SOURCE_URL],
            "publisher": "福州大学数学与统计学院",
            "scope": "2027 届、本院、校内推免推荐",
            "operation_id": "rank-fact-operation",
        },
    )
    assert created.status_code == 200, created.text
    run = created.json()["run"]
    assert run["status"] == "等待确认", run["error"]

    plan_row = admin.execute(
        "SELECT basis_input FROM core.candidate_plan WHERE id = %s",
        (UUID(run["persisted_plan_id"]),),
    ).fetchone()
    assert plan_row is not None
    assert plan_row[0]["confirmed_facts"] == [
        {
            "fact_type": "gpa.rank",
            "fact_id": fact["id"],
            "version_no": 1,
            "value_hash": fact["value_hash"],
        }
    ]


def test_agent_run_rejects_fact_version_change(
    agent_client: TestClient, admin: psycopg.Connection
) -> None:
    state = cast(FastAPI, agent_client.app).state.replay_state
    state.requirement_field_key = "gpa.rank"
    matter_id = _create_matter(agent_client)
    saved = agent_client.put(
        f"/api/v1/matters/{matter_id}/facts/gpa.rank",
        json={"value": {"position": 5, "cohort_size": 120}},
    )
    assert saved.status_code == 200, saved.text
    _grant_consent(agent_client)

    def change_fact() -> None:
        state.before_candidate_plan = None
        changed = agent_client.put(
            f"/api/v1/matters/{matter_id}/facts/gpa.rank",
            json={"value": {"position": 8, "cohort_size": 120}},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["fact"]["version_no"] == 2

    state.before_candidate_plan = change_fact
    created = agent_client.post(
        f"/api/v1/matters/{matter_id}/agent-runs",
        json={
            "source_urls": [SOURCE_URL],
            "publisher": "福州大学数学与统计学院",
            "scope": "2027 届、本院、校内推免推荐",
            "operation_id": "rank-version-conflict",
        },
    )
    assert created.status_code == 200, created.text
    run = created.json()["run"]
    assert run["status"] == "失败"
    assert run["error"]["code"] == "VERSION_CONFLICT"
    assert run["persisted_plan_id"] is None

    plan_count = admin.execute(
        "SELECT count(*) FROM core.candidate_plan WHERE matter_id = %s",
        (UUID(matter_id),),
    ).fetchone()
    assert plan_count is not None
    assert plan_count[0] == 0


def test_agent_run_reads_facts_only_from_current_matter(
    agent_client: TestClient, admin: psycopg.Connection
) -> None:
    state = cast(FastAPI, agent_client.app).state.replay_state
    state.requirement_field_key = "gpa.rank"
    matter_a = _create_matter(agent_client)
    saved = agent_client.put(
        f"/api/v1/matters/{matter_a}/facts/gpa.rank",
        json={"value": {"position": 5, "cohort_size": 120}},
    )
    assert saved.status_code == 200, saved.text
    matter_b = _create_matter(agent_client)
    _grant_consent(agent_client)

    created = agent_client.post(
        f"/api/v1/matters/{matter_b}/agent-runs",
        json={
            "source_urls": [SOURCE_URL],
            "publisher": "福州大学数学与统计学院",
            "scope": "2027 届、本院、校内推免推荐",
            "operation_id": "other-matter-fact",
        },
    )
    assert created.status_code == 200, created.text
    run = created.json()["run"]
    assert run["status"] == "等待确认", run["error"]

    plan_row = admin.execute(
        "SELECT basis_input FROM core.candidate_plan WHERE id = %s",
        (UUID(run["persisted_plan_id"]),),
    ).fetchone()
    assert plan_row is not None
    assert plan_row[0]["confirmed_facts"] == [
        {
            "fact_type": "gpa.rank",
            "fact_id": None,
            "version_no": None,
            "value_hash": None,
        }
    ]


def test_agent_run_rejects_managed_fact_payload(agent_client: TestClient) -> None:
    matter_id = _create_matter(agent_client)
    _grant_consent(agent_client)
    response = agent_client.post(
        f"/api/v1/matters/{matter_id}/agent-runs",
        json={
            "source_urls": [SOURCE_URL],
            "publisher": "福州大学数学与统计学院",
            "scope": "2027 届、本院、校内推免推荐",
            "confirmed_facts": {"gpa.rank": {"percentile": 4.2}},
            "operation_id": "managed-fact-payload",
        },
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "managed_fact_type"
    assert error["details"] == {"fact_types": ["gpa.rank"]}


def test_agent_run_ignores_other_matter_fact_version_change(
    agent_client: TestClient,
) -> None:
    state = cast(FastAPI, agent_client.app).state.replay_state
    state.requirement_field_key = "gpa.rank"
    matter_a = _create_matter(agent_client)
    saved = agent_client.put(
        f"/api/v1/matters/{matter_a}/facts/gpa.rank",
        json={"value": {"position": 5, "cohort_size": 120}},
    )
    assert saved.status_code == 200, saved.text
    matter_b = _create_matter(agent_client)
    saved = agent_client.put(
        f"/api/v1/matters/{matter_b}/facts/gpa.rank",
        json={"value": {"position": 5, "cohort_size": 120}},
    )
    assert saved.status_code == 200, saved.text
    _grant_consent(agent_client)

    def change_other_matter() -> None:
        state.before_candidate_plan = None
        changed = agent_client.put(
            f"/api/v1/matters/{matter_a}/facts/gpa.rank",
            json={"value": {"position": 8, "cohort_size": 120}},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["fact"]["version_no"] == 2

    state.before_candidate_plan = change_other_matter
    created = agent_client.post(
        f"/api/v1/matters/{matter_b}/agent-runs",
        json={
            "source_urls": [SOURCE_URL],
            "publisher": "福州大学数学与统计学院",
            "scope": "2027 届、本院、校内推免推荐",
            "operation_id": "other-matter-version-change",
        },
    )
    assert created.status_code == 200, created.text
    run = created.json()["run"]
    assert run["status"] == "等待确认", run["error"]
    assert run["persisted_plan_id"] is not None


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


def _grant_consent(client: TestClient) -> str:
    response = client.post("/api/v1/model-transfer-consent")
    assert response.status_code == 200, response.text
    return response.json()["consent"]["consent_id"]
