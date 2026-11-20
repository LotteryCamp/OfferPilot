"""Stable API error envelope and exception handlers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        next_step: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.next_step = next_step
        self.details = details or {}


def error_payload(
    code: str,
    message: str,
    *,
    next_step: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if next_step is not None:
        body["next"] = next_step
    if details:
        body["details"] = details
    return {"error": body}


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                exc.code,
                exc.message,
                next_step=exc.next_step,
                details=exc.details,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        issues = [
            {
                "path": ".".join(str(part) for part in item["loc"]),
                "code": item["type"],
                "message": item["msg"],
            }
            for item in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_payload(
                "validation_error",
                "请求字段未通过校验",
                next_step="按 issues 修正请求后重试",
                details={"issues": issues},
            ),
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("database integrity error: %s", exc.orig)
        return JSONResponse(
            status_code=409,
            content=error_payload(
                "data_conflict",
                "数据与现有记录冲突",
                next_step="重新读取最新状态后再提交",
            ),
        )

    @app.exception_handler(DBAPIError)
    async def handle_db_error(_: Request, exc: DBAPIError) -> JSONResponse:
        logger.warning("database error: %s", exc.orig)
        return JSONResponse(
            status_code=409,
            content=error_payload(
                "data_conflict",
                "数据写入未满足业务约束",
                next_step="重新读取最新状态后再提交",
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unexpected API error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=error_payload(
                "internal_error",
                "服务处理失败",
                next_step="稍后重试；若持续失败请联系维护者",
            ),
        )
