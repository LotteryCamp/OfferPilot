"""Exercise model failures and recovery through HTTP, Agent API and PostgreSQL.

The local HTTP endpoint replays protocol responses, not live model inference.
Source HTML uses the public fixture already used by backend integration tests.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.clock import Clock
from backend.config import Settings
from backend.main import create_app
from backend.sources import PublicSourceResult, parse_public_html

SOURCE_URL = "https://math.fzu.edu.cn/info/1171/10393.htm"
NOTICE_HTML = Path(__file__).parent / "fixtures" / "sources" / "fzu_notice.html.gz"
FETCHED_AT = datetime.fromisoformat("2026-09-09T01:00:00+00:00")


@dataclass
class ProtocolReplay:
    failure: str = ""
    failure_stage: str = "extraction"
    requests: list[str] = field(default_factory=list)
    release: Event = field(default_factory=Event)
    api_url: str = ""


@pytest.fixture()
def protocol_replay() -> Iterator[ProtocolReplay]:
    state = ProtocolReplay()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            if self.path != "/v1/chat/completions":
                self.send_error(404)
                return
            request = json.loads(
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
            )
            payload = json.loads(request["messages"][1]["content"])
            stage = "planning" if "evaluations" in payload else "extraction"
            state.requests.append(stage)
            failure = state.failure if stage == state.failure_stage else ""
            status = 200
            finish_reason = "stop"
            if failure == "timeout":
                state.release.wait(timeout=15)
                self.close_connection = True
                return
            if failure == "server-error":
                status = 500
                response = {"error": {"message": "Temporary upstream failure"}}
            else:
                if failure == "invalid-json":
                    content = "这不是 JSON"
                elif failure == "wrong-field-type":
                    content = json.dumps(
                        {"tasks" if stage == "planning" else "requirements": "成绩单"}
                    )
                else:
                    content = json.dumps(
                        _valid_payload(payload, stage), ensure_ascii=False
                    )
                if failure == "truncated":
                    finish_reason = "length"
                response = {
                    "id": "protocol-replay",
                    "object": "chat.completion",
                    "created": 1,
                    "model": request["model"],
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": finish_reason,
                            "message": {"role": "assistant", "content": content},
                        }
                    ],
                }
            encoded = json.dumps(response, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        state.api_url = f"http://127.0.0.1:{server.server_port}/v1"
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield state
        finally:
            state.release.set()
            server.shutdown()
            thread.join(timeout=5)


def _valid_payload(payload: dict[str, Any], stage: str) -> dict[str, Any]:
    if stage == "planning":
        return {
            "tasks": [
                {
                    "task_id": "T-01",
                    "title": "准备并提交申请表、证明材料和成绩单",
                    "requirement_id": "R-01",
                    "basis": payload["evaluations"][0]["basis"],
                    "obligation": "官方必需",
                    "evidence_required": "申请表、证明材料和成绩单",
                }
            ]
        }
    source = payload["sources"][0]
    fragment = next(
        item for item in source["fragments"] if item["quote"].startswith("（5）")
    )
    return {
        "requirements": [
            {
                "requirement_id": "R-01",
                "title": "准备并提交申请表、证明材料和成绩单",
                "field_key": "application.materials",
                "value_text": fragment["quote"],
                "obligation": "官方必需",
                "basis": [
                    {
                        "source_version_id": source["source_version_id"],
                        "locator_kind": fragment["locator_kind"],
                        "locator": fragment["locator"],
                        "excerpt": fragment["quote"],
                    }
                ],
            }
        ]
    }


def _read_fixture(request: dict[str, Any]) -> PublicSourceResult:
    return parse_public_html(
        gzip.decompress(NOTICE_HTML.read_bytes()),
        content_type="text/html; charset=UTF-8",
        final_url=str(request["url"]),
        request=request,
        fetched_at=FETCHED_AT,
    )


@pytest.mark.parametrize("stage", ["extraction", "planning"])
@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        ("timeout", "TIMEOUT"),
        ("invalid-json", "VALIDATION_FAILED"),
        ("wrong-field-type", "VALIDATION_FAILED"),
        ("truncated", "VALIDATION_FAILED"),
        ("server-error", "MODEL_ERROR"),
    ],
)
def test_agent_model_failure_then_new_operation_recovers(
    database_urls: tuple[str, str],
    admin: psycopg.Connection,
    clock: Clock,
    login: Callable[[TestClient], None],
    monkeypatch: pytest.MonkeyPatch,
    protocol_replay: ProtocolReplay,
    stage: str,
    failure: str,
    expected_code: str,
) -> None:
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    protocol_replay.failure = failure
    protocol_replay.failure_stage = stage
    app = create_app(
        Settings(
            database_url=database_urls[0],
            model_api_url=protocol_replay.api_url,
            model_api_key="local-protocol-test-token",
            model_name="protocol-replay",
            model_timeout_seconds=1.0,
        ),
        clock=clock,
        agent_source_reader=_read_fixture,
    )
    with TestClient(app) as client:
        login(client)
        created = client.post(
            "/api/v1/matters",
            json={
                "goal": "申请 2027 年福州大学数学与统计学院推免",
                "scope_year": 2027,
            },
        )
        assert created.status_code == 201, created.text
        matter_id = created.json()["matter"]["id"]
        consent = client.post("/api/v1/model-transfer-consent")
        assert consent.status_code == 200, consent.text
        path = f"/api/v1/matters/{matter_id}/agent-runs"
        request = {"source_urls": [SOURCE_URL], "operation_id": "first-attempt"}
        failed_response = client.post(path, json=request)
        assert failed_response.status_code == 200, failed_response.text
        failed = failed_response.json()["run"]
        assert failed["status"] == "失败"
        assert failed["error"]["code"] == expected_code
        assert failed["persisted_plan_id"] is None
        assert failed["written_tasks"] == []
        expected_requests = (
            ["extraction"] if stage == "extraction" else ["extraction", "planning"]
        )
        assert protocol_replay.requests == expected_requests

        plans = client.get(f"/api/v1/matters/{matter_id}/candidate-plans")
        assert plans.status_code == 200, plans.text
        assert plans.json()["plans"] == []
        tasks = client.get(f"/api/v1/matters/{matter_id}/tasks")
        assert tasks.status_code == 200, tasks.text
        assert tasks.json()["tasks"] == []
        row = admin.execute(
            "SELECT count(*) FROM core.candidate_plan WHERE matter_id = %s",
            (matter_id,),
        ).fetchone()
        assert row is not None and row[0] == 0

        protocol_replay.failure = ""
        protocol_replay.release.set()
        replay = client.post(path, json=request)
        assert replay.status_code == 200, replay.text
        assert replay.json()["run"]["run_id"] == failed["run_id"]
        assert replay.json()["run"]["status"] == "失败"
        assert protocol_replay.requests == expected_requests

        recovered_response = client.post(
            path, json={**request, "operation_id": "recovery-attempt"}
        )
        assert recovered_response.status_code == 200, recovered_response.text
        recovered = recovered_response.json()["run"]
        assert recovered["run_id"] != failed["run_id"]
        assert recovered["status"] == "等待确认", recovered["error"]
        assert recovered["error"] is None
        assert len(recovered["persisted_requirement_ids"]) == 1
        assert recovered["persisted_plan_id"] is not None
        assert recovered["written_tasks"] == []
        assert protocol_replay.requests == expected_requests + [
            "extraction",
            "planning",
        ]
        plan = client.get(f"/api/v1/candidate-plans/{recovered['persisted_plan_id']}")
        assert plan.status_code == 200, plan.text
        assert plan.json()["plan"]["status"] == "pending"
        assert len(plan.json()["plan"]["items"]) == 1
        assert plan.json()["plan"]["items"][0]["sources"]
        assert plan.json()["plan"]["tasks"] == []
        plans = client.get(f"/api/v1/matters/{matter_id}/candidate-plans")
        assert plans.status_code == 200, plans.text
        assert len(plans.json()["plans"]) == 1
        stored_failure = client.get(f"/api/v1/agent-runs/{failed['run_id']}")
        assert stored_failure.status_code == 200, stored_failure.text
        assert stored_failure.json()["run"]["status"] == "失败"
        assert stored_failure.json()["run"]["error"]["code"] == expected_code
        tasks = client.get(f"/api/v1/matters/{matter_id}/tasks")
        assert tasks.status_code == 200, tasks.text
        assert tasks.json()["tasks"] == []
