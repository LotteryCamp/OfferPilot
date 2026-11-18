from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from backend.model_adapter import ModelAdapterError, call_model

import httpx
from openai import APITimeoutError, InternalServerError

class ExampleResult(BaseModel):
    requirements: list[str]


@pytest.mark.parametrize(
    "content",
    [
        "这不是 JSON",
        '{"requirements": "提交本科成绩单"}',
    ],
    ids=["invalid-json", "wrong-field-type"],
)
def test_call_model_rejects_invalid_response(monkeypatch, content):
    monkeypatch.setenv("OFFERPILOT_MODEL_API_KEY", "test-key")
    monkeypatch.setenv("OFFERPILOT_MODEL_API_URL", "https://example.invalid")
    monkeypatch.setenv("OFFERPILOT_MODEL_NAME", "test-model")

    with patch("backend.model_adapter.OpenAI") as mock_openai:
        client = mock_openai.return_value.__enter__.return_value
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content=content),
                )
            ]
        )

        with pytest.raises(ModelAdapterError) as error:
            call_model("提取申请材料", "申请人须提交本科成绩单。", ExampleResult)

        assert error.value.code == "INVALID_RESPONSE"
        client.chat.completions.create.assert_called_once()


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [("timeout", "TIMEOUT"), ("server-error", "SERVICE_ERROR")],
)
def test_call_model_reports_request_failure(monkeypatch, failure, expected_code):
    monkeypatch.setenv("OFFERPILOT_MODEL_API_KEY", "test-key")
    monkeypatch.setenv("OFFERPILOT_MODEL_API_URL", "https://example.invalid")
    monkeypatch.setenv("OFFERPILOT_MODEL_NAME", "test-model")

    request = httpx.Request("POST", "https://example.invalid/chat/completions")
    if failure == "timeout":
        sdk_error = APITimeoutError(request=request)
    else:
        sdk_error = InternalServerError(
            "Simulated server error",
            response=httpx.Response(500, request=request),
            body=None,
        )

    with patch("backend.model_adapter.OpenAI") as mock_openai:
        client = mock_openai.return_value.__enter__.return_value
        client.chat.completions.create.side_effect = sdk_error

        with pytest.raises(ModelAdapterError) as error:
            call_model("提取申请材料", "申请人须提交本科成绩单。", ExampleResult)

        assert error.value.code == expected_code