"""Shared service helpers for serialization, identity, and transactions."""

from __future__ import annotations

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.db import workspace_transaction
from backend.errors import ApiError
from backend.tables import matter, workspace


@contextmanager
def transaction(session: Session, settings: Settings) -> Generator[None, None, None]:
    with workspace_transaction(session, settings.demo_workspace_id):
        _ensure_demo_identity(session, settings)
        yield


def _ensure_demo_identity(session: Session, settings: Settings) -> None:
    row = session.execute(
        select(workspace.c.id).where(
            workspace.c.id == settings.demo_workspace_id,
            workspace.c.owner_id == settings.demo_user_id,
        )
    ).first()
    if row is None:
        raise ApiError(
            500,
            "demo_identity_missing",
            "演示用户或工作区不存在",
            next_step="先执行数据库种子脚本，或检查 OFFERPILOT_DEMO_USER_ID 与 OFFERPILOT_DEMO_WORKSPACE_ID",
        )


def require_matter(
    session: Session,
    settings: Settings,
    matter_id: UUID,
    *,
    for_update: bool = False,
) -> Mapping[str, Any]:
    statement = select(matter).where(
        matter.c.id == matter_id,
        matter.c.workspace_id == settings.demo_workspace_id,
    )
    if for_update:
        statement = statement.with_for_update()
    row = session.execute(statement).mappings().first()
    if row is None:
        raise ApiError(
            404,
            "matter_not_found",
            "未找到当前工作区中的事项",
            next_step="刷新事项列表后重试",
        )
    return row


def iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return value.isoformat()


def uuid_text(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


def decimal_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def json_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    return None


def serialize_matter_overview(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": uuid_text(row["id"]),
        "workspace_id": uuid_text(row["workspace_id"]),
        "type_code": row["type_code"],
        "type_name": row["type_name"],
        "goal": row["goal"],
        "status": row["status"],
        "scope_year": row["scope_year"],
        "scope_attrs": row["scope_attrs"],
        "archived_at": iso(row["archived_at"]),
        "created_at": iso(row["created_at"]),
        "updated_at": iso(row["updated_at"]),
        "tasks": {
            "total": row["task_total"],
            "done": row["task_done"],
            "open": row["task_open"],
        },
        "latest_plan": (
            {
                "id": uuid_text(row["latest_plan_id"]),
                "status": row["latest_plan_status"],
                "version_no": row["latest_plan_version"],
            }
            if row["latest_plan_id"] is not None
            else None
        ),
    }


def serialize_task_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": uuid_text(row["id"]),
        "matter_id": uuid_text(row["matter_id"]),
        "plan_id": uuid_text(row["plan_id"]),
        "plan_item_id": uuid_text(row["plan_item_id"]),
        "title": row["title"],
        "status": row["status"],
        "due_at": iso(row["due_at"]),
        "official_deadline_date": iso(row["official_deadline_date"]),
        "official_deadline_at": iso(row["official_deadline_at"]),
        "suggested_date": iso(row["suggested_date"]),
        "depends_on": [str(value) for value in (row["depends_on"] or [])],
        "completion_evidence": row["completion_evidence"],
        "created_at": iso(row["created_at"]),
        "updated_at": iso(row["updated_at"]),
    }
