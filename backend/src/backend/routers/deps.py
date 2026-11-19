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
from backend.services.sources import SourceReader, read_public_html

SessionDep = Annotated[Session, Depends(get_session)]


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


SettingsDep = Annotated[Settings, Depends(get_settings)]
ClockDep = Annotated[Clock, Depends(get_clock)]


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
