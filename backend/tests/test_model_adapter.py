import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread

import pytest
from pydantic import BaseModel

from backend.model_adapter import ModelAdapterError, call_model


class ExtractionResult(BaseModel):
    requirements: list[str]


@pytest.mark.parametrize(
    ("content", "expected_code"),
    [
        (None, "TIMEOUT"),
        ("这不是 JSON", "INVALID_RESPONSE"),
        ('{"requirements": "成绩单"}', "INVALID_RESPONSE"),
    ],
    ids=["timeout", "invalid-json", "wrong-field-type"],
)
def test_model_adapter_reports_request_failure(
    monkeypatch: pytest.MonkeyPatch,
    content: str | None,
    expected_code: str,
) -> None:
    request_received = Event()
    release = Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            request_received.set()

            if content is None:
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
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": content},
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
            monkeypatch.setenv("OFFERPILOT_MODEL_API_KEY", "local-test-token")
            monkeypatch.setenv(
                "OFFERPILOT_MODEL_API_URL", f"http://127.0.0.1:{server.server_port}/v1"
            )
            monkeypatch.setenv("OFFERPILOT_MODEL_NAME", "local-test-model")

            with pytest.raises(ModelAdapterError) as error:
                call_model("提取材料", "申请人须提交成绩单。", ExtractionResult)

            assert request_received.is_set()
            assert error.value.code == expected_code
        finally:
            release.set()
            server.shutdown()
            thread.join()