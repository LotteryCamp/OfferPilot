"""Opt-in recovery checks using a real model service and public notice."""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.conninfo import conninfo_to_dict

from backend.config import Settings
from backend.main import create_app
from backend.runtime_config import RuntimeConfig

SOURCE_URL = "https://cl.fzu.edu.cn/info/1072/19700.htm"
SHORT_TIMEOUT_SECONDS = 0.001


@dataclass(frozen=True)
class LiveRecoveryEnvironment:
    settings: Settings = field(repr=False)


@pytest.fixture()
def live_environment(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> LiveRecoveryEnvironment:
    if os.environ.get("OFFERPILOT_MODEL_LIVE_RECOVERY") != "1":
        pytest.skip(
            "set OFFERPILOT_MODEL_LIVE_RECOVERY=1 for real model recovery checks"
        )

    names = ("OFFERPILOT_TEST_DATABASE_URL", "OFFERPILOT_TEST_ADMIN_DATABASE_URL")
    if any(not os.environ.get(name, "").strip() for name in names):
        pytest.fail("real recovery checks require both dedicated test database URLs")
    urls = cast(tuple[str, str], request.getfixturevalue("database_urls"))
    connection_info = [conninfo_to_dict(url) for url in urls]
    for info in connection_info:
        database_name = info.get("dbname")
        if not isinstance(database_name, str) or not database_name.endswith("_test"):
            pytest.fail("recovery checks require a database name ending in _test")
    if any(
        connection_info[0].get(key) != connection_info[1].get(key)
        for key in ("host", "port", "dbname")
    ):
        pytest.fail(
            "application and administrator URLs must target the same test database"
        )

    monkeypatch.setenv("OFFERPILOT_DATABASE_URL", urls[0])
    base = Settings.from_env()
    config_path = Path(base.config_file) if base.config_file else None
    effective = RuntimeConfig(base, config_path).current()
    if not all(
        value.strip()
        for value in (
            effective.model_api_url,
            effective.model_api_key,
            effective.model_name,
        )
    ):
        pytest.fail("configure a real model URL, model name and API key locally")
    if effective.model_timeout_seconds <= SHORT_TIMEOUT_SECONDS:
        pytest.fail("normal model timeout must exceed the short failure timeout")
    return LiveRecoveryEnvironment(
        replace(effective, database_url=urls[0], config_file=None, cookie_secure=False)
    )


@pytest.fixture()
def live_admin(
    live_environment: LiveRecoveryEnvironment,
    request: pytest.FixtureRequest,
) -> psycopg.Connection:
    # Validate the opt-in and database targets before the shared cleanup fixture runs.
    return cast(psycopg.Connection, request.getfixturevalue("admin"))


def _post_run(client: TestClient, matter_id: str, operation_id: str) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/matters/{matter_id}/agent-runs",
        json={
            "source_urls": [SOURCE_URL],
            "publisher": "福州大学材料科学与工程学院",
            "scope": "2027届推免接收",
            "operation_id": operation_id,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["run"]


def _read_plans(client: TestClient, matter_id: str) -> list[dict[str, Any]]:
    response = client.get(f"/api/v1/matters/{matter_id}/candidate-plans")
    assert response.status_code == 200, response.text
    return response.json()["plans"]


def _assert_no_tasks(client: TestClient, matter_id: str) -> None:
    response = client.get(f"/api/v1/matters/{matter_id}/tasks")
    assert response.status_code == 200, response.text
    assert response.json()["tasks"] == []


@pytest.mark.parametrize(
    "restart_before_retry", [False, True], ids=["same-process", "new-app"]
)
def test_live_model_timeout_then_same_operation_recovers(
    live_environment: LiveRecoveryEnvironment,
    live_admin: psycopg.Connection,
    request: pytest.FixtureRequest,
    tmp_path: Path,
    restart_before_retry: bool,
) -> None:
    login = cast(Callable[[TestClient], None], request.getfixturevalue("login"))
    runtime_file = tmp_path / "recovery.yaml"
    runtime_file.write_text(
        f"model:\n  timeout_seconds: {SHORT_TIMEOUT_SECONDS}\n", encoding="utf-8"
    )
    settings = replace(live_environment.settings, config_file=str(runtime_file))
    app = create_app(settings)
    operation_id = "live-timeout-recovery"

    with ExitStack() as stack:
        client = stack.enter_context(TestClient(app))
        login(client)
        created = client.post(
            "/api/v1/matters",
            json={
                "goal": "分析福州大学材料科学与工程学院2027届推免接收通知，提取条件、材料及期限",
                "scope_year": 2027,
                "scope_attrs": {"school": "福州大学", "college": "材料科学与工程学院"},
            },
        )
        assert created.status_code == 201, created.text
        matter_id = created.json()["matter"]["id"]
        consent = client.post("/api/v1/model-transfer-consent")
        assert consent.status_code == 200, consent.text
        failed = _post_run(client, matter_id, operation_id)
        assert failed["status"] == "失败", failed["error"]
        assert failed["error"]["code"] == "TIMEOUT", failed["error"]
        assert any(
            record["tool_name"] == "fetch_official_sources" and record["succeeded"]
            for record in failed["execution_records"]
        )
        assert failed["persisted_plan_id"] is None
        assert failed["persisted_requirement_ids"] == []
        assert failed["written_tasks"] == []
        assert _read_plans(client, matter_id) == []
        _assert_no_tasks(client, matter_id)
        count = live_admin.execute(
            "SELECT count(*) FROM core.candidate_plan WHERE matter_id = %s",
            (matter_id,),
        ).fetchone()
        assert count is not None and count[0] == 0

        app.state.runtime_config.update(
            {
                "model": {
                    "timeout_seconds": live_environment.settings.model_timeout_seconds
                }
            }
        )
        if restart_before_retry:
            stack.close()
            app = create_app(settings)
            client = stack.enter_context(TestClient(app))
            login(client)

        recovered = _post_run(client, matter_id, operation_id)
        assert recovered["run_id"] != failed["run_id"]
        assert recovered["status"] == "等待确认", recovered["error"]
        assert recovered["error"] is None
        assert recovered["persisted_requirement_ids"]
        assert recovered["persisted_plan_id"] is not None
        assert recovered["written_tasks"] == []
        assert all(record["succeeded"] for record in recovered["execution_records"])
        plan_id = recovered["persisted_plan_id"]
        plan_response = client.get(f"/api/v1/candidate-plans/{plan_id}")
        assert plan_response.status_code == 200, plan_response.text
        plan = plan_response.json()["plan"]
        assert plan["status"] == "pending"
        assert plan["items"]
        assert all(item["sources"] for item in plan["items"])
        assert len(_read_plans(client, matter_id)) == 1

        replayed = _post_run(client, matter_id, operation_id)
        assert replayed["run_id"] == recovered["run_id"]
        assert replayed["persisted_plan_id"] == plan_id
        assert len(_read_plans(client, matter_id)) == 1
        previous = client.get(f"/api/v1/agent-runs/{failed['run_id']}")
        assert previous.status_code == 200, previous.text
        assert previous.json()["run"]["status"] == "失败"
        assert previous.json()["run"]["error"]["code"] == "TIMEOUT"
        _assert_no_tasks(client, matter_id)
