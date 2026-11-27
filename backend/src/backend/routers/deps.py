"""FastAPI dependencies shared by the routers."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from backend.clock import Clock
from backend.config import Settings
from backend.db import get_session
from backend.errors import ApiError
from backend.identity import CurrentUser
from backend.runtime_config import RuntimeConfig
from backend.services import auth as auth_service
from backend.services.sources import SourceReader, read_public_html

SessionDep = Annotated[Session, Depends(get_session)]


def get_settings(request: Request) -> Settings:
    return request.app.state.runtime_config.current()


def get_runtime_config(request: Request) -> RuntimeConfig:
    return request.app.state.runtime_config


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


SettingsDep = Annotated[Settings, Depends(get_settings)]
RuntimeConfigDep = Annotated[RuntimeConfig, Depends(get_runtime_config)]
ClockDep = Annotated[Clock, Depends(get_clock)]


def get_current_user(request: Request) -> CurrentUser:
    token = request.cookies.get(auth_service.SESSION_COOKIE_NAME)
    if not token:
        raise _authentication_required()
    with request.app.state.session_factory() as session:
        current_user = auth_service.authenticate_session(
            session,
            token,
            now=request.app.state.clock.now(),
        )
    if current_user is None:
        raise _authentication_required()
    return current_user


def require_admin(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    if not current_user.is_admin:
        raise ApiError(
            403,
            "admin_required",
            "需要管理员权限",
            next_step="使用管理员账户登录后重试",
        )
    return current_user


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
AdminUserDep = Annotated[CurrentUser, Depends(require_admin)]


def _authentication_required() -> ApiError:
    return ApiError(
        401,
        "authentication_required",
        "需要登录后访问",
        next_step="登录后重试",
    )


def idempotency_key(
    value: Annotated[str, Header(alias="Idempotency-Key")],
) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ApiError(
            400,
            "invalid_idempotency_key",
            "Idempotency-Key 必须是 UUID",
            next_step="为本次操作生成一个 UUID 并重试",
        ) from exc


IdempotencyKeyDep = Annotated[UUID, Depends(idempotency_key)]


def get_source_reader() -> SourceReader:
    return read_public_html


SourceReaderDep = Annotated[SourceReader, Depends(get_source_reader)]
