"""Structured model invocation through an OpenAI-compatible endpoint."""

from __future__ import annotations

import json
import math
import os

from openai import APIError, APIResponseValidationError, APITimeoutError, OpenAI
from pydantic import BaseModel, ValidationError

DEFAULT_MODEL_TIMEOUT_SECONDS = 180.0


class ModelAdapterError(Exception):
    """Raised when model configuration or response handling fails."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _model_timeout() -> float:
    raw = os.getenv("OFFERPILOT_MODEL_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_MODEL_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except ValueError:
        raise ModelAdapterError("CONFIG_ERROR", "模型请求超时须为秒数。") from None
    if not math.isfinite(timeout) or timeout <= 0:
        raise ModelAdapterError(
            "CONFIG_ERROR", "模型请求超时须为有限且大于 0 的秒数。"
        )
    return timeout


def call_model[T: BaseModel](
    instruction: str,
    text: str,
    response_model: type[T],
) -> T:
    """Invoke the configured model and validate its JSON response."""
    api_key = os.getenv("OFFERPILOT_MODEL_API_KEY", "").strip()
    api_url = os.getenv("OFFERPILOT_MODEL_API_URL", "").strip()
    model = os.getenv("OFFERPILOT_MODEL_NAME", "").strip()

    if not api_key or not api_url or not model:
        raise ModelAdapterError("CONFIG_ERROR", "缺少模型地址、模型名或 API Key。")

    timeout = _model_timeout()
    schema = json.dumps(response_model.model_json_schema(), ensure_ascii=False)

    try:
        with OpenAI(
            api_key=api_key,
            base_url=api_url,
            timeout=timeout,
            max_retries=0,
        ) as client:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": f"{instruction}\n只返回符合以下结构的 JSON：\n{schema}",
                    },
                    {"role": "user", "content": text},
                ],
                response_format={"type": "json_object"},
            )
    except APITimeoutError:
        raise ModelAdapterError("TIMEOUT", "模型请求超时。") from None
    except APIResponseValidationError:
        raise ModelAdapterError("INVALID_RESPONSE", "模型服务回包格式异常。") from None
    except APIError:
        raise ModelAdapterError("SERVICE_ERROR", "模型服务调用失败。") from None

    if not response.choices:
        raise ModelAdapterError("INVALID_RESPONSE", "模型服务未返回候选结果。")

    choice = response.choices[0]
    content = choice.message.content
    if choice.finish_reason != "stop" or not content or not content.strip():
        raise ModelAdapterError("INVALID_RESPONSE", "模型未返回完整的 JSON。")

    try:
        return response_model.model_validate_json(content, strict=True)
    except ValidationError:
        raise ModelAdapterError(
            "INVALID_RESPONSE", "模型输出不符合约定的字段结构。"
        ) from None
