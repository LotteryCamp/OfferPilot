import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from typing import Any

import pytest
from pydantic import BaseModel

from backend.config import Settings
from backend.model_adapter import ModelAdapterError, _model_timeout, call_model


class ExtractionResult(BaseModel):
    requirements: list[str]


@pytest.mark.parametrize(
    ("content", "status", "finish_reason", "expected_code"),
    [
        (None, 200, "stop", "TIMEOUT"),
        ("这不是 JSON", 200, "stop", "INVALID_RESPONSE"),
        ('{"requirements": "成绩单"}', 200, "stop", "INVALID_RESPONSE"),
        ('{"requirements": ["成绩单"]}', 200, "stop", None),
        (None, 500, "stop", "SERVICE_ERROR"),
        ('{"requirements": []}', 200, "length", "INVALID_RESPONSE"),
    ],
    ids=[
        "timeout",
        "invalid-json",
        "wrong-field-type",
        "valid-response",
        "server-error",
        "truncated-response",
    ],
)
def test_model_adapter_handles_model_response(
    monkeypatch: pytest.MonkeyPatch,
    content: str | None,
    status: int,
    finish_reason: str,
    expected_code: str | None,
) -> None:
    request_received = Event()
    release = Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            request_received.set()

            if status == 200 and content is None:
                # 等客户端按适配器配置超时；测试结束后立即释放。
                release.wait(timeout=45)
                return

            body = json.dumps(
                {
                    "id": "local-completion",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "local-test-model",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": finish_reason,
                            "message": {"role": "assistant", "content": content},
                        }
                    ],
                }
            ).encode("utf-8")

            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            monkeypatch.setenv("NO_PROXY", "127.0.0.1")
            monkeypatch.setenv("OFFERPILOT_MODEL_TIMEOUT_SECONDS", "5")
            monkeypatch.setenv("OFFERPILOT_MODEL_API_KEY", "local-test-token")
            monkeypatch.setenv(
                "OFFERPILOT_MODEL_API_URL", f"http://127.0.0.1:{server.server_port}/v1"
            )
            monkeypatch.setenv("OFFERPILOT_MODEL_NAME", "local-test-model")

            if expected_code is None:
                result = call_model(
                    "提取材料", "申请人须提交成绩单。", ExtractionResult
                )
                assert result.requirements == ["成绩单"]
            else:
                with pytest.raises(ModelAdapterError) as error:
                    call_model("提取材料", "申请人须提交成绩单。", ExtractionResult)
                assert error.value.code == expected_code

            assert request_received.is_set()
        finally:
            release.set()
            server.shutdown()
            thread.join()


@pytest.mark.parametrize("raw_timeout", ["abc", "0", "-1", "nan", "inf"])
def test_model_timeout_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    raw_timeout: str,
) -> None:
    monkeypatch.setenv("OFFERPILOT_MODEL_TIMEOUT_SECONDS", raw_timeout)

    with pytest.raises(ModelAdapterError) as error:
        _model_timeout()

    assert error.value.code == "CONFIG_ERROR"


@pytest.mark.parametrize(
    ("raw_timeout", "expected_timeout"),
    [("", 180.0), ("2.5", 2.5)],
)
def test_model_timeout_uses_default_or_configured_value(
    monkeypatch: pytest.MonkeyPatch,
    raw_timeout: str,
    expected_timeout: float,
) -> None:
    monkeypatch.setenv("OFFERPILOT_MODEL_TIMEOUT_SECONDS", raw_timeout)

    assert _model_timeout() == expected_timeout


@pytest.mark.parametrize(
    "timeout",
    [5.0, float("nan"), float("inf"), 0.0, -1.0],
    ids=["valid", "nan", "inf", "zero", "negative"],
)
def test_model_adapter_uses_explicit_settings(
    monkeypatch: pytest.MonkeyPatch,
    timeout: float,
) -> None:
    captured: dict[str, Any] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            captured["path"] = self.path
            captured["authorization"] = self.headers.get("Authorization")
            captured["model"] = payload.get("model")

            body = json.dumps(
                {
                    "id": "local-completion",
                    "object": "chat.completion",
                    "created": 1,
                    "model": payload.get("model"),
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": '{"requirements": ["成绩单"]}',
                            },
                        }
                    ],
                }
            ).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            monkeypatch.setenv("NO_PROXY", "127.0.0.1")
            monkeypatch.setenv("OFFERPILOT_MODEL_NAME", "env-model")
            settings = Settings(
                database_url="postgresql://unused",
                model_api_key="settings-token",
                model_api_url=f"http://127.0.0.1:{server.server_port}/v1",
                model_name="settings-model",
                model_timeout_seconds=timeout,
            )

            if timeout != 5.0:
                with pytest.raises(ModelAdapterError, match="有限且大于 0") as error:
                    call_model(
                        "提取材料",
                        "申请人须提交成绩单。",
                        ExtractionResult,
                        settings=settings,
                    )
                assert error.value.code == "CONFIG_ERROR"
                assert not captured
                return

            result = call_model(
                "提取材料",
                "申请人须提交成绩单。",
                ExtractionResult,
                settings=settings,
            )

            assert result.requirements == ["成绩单"]
            assert captured["path"] == "/v1/chat/completions"
            assert captured["authorization"] == "Bearer settings-token"
            assert captured["model"] == "settings-model"
        finally:
            server.shutdown()
            thread.join()
