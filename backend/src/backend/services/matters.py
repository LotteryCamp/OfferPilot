"""Matter creation and read services."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.errors import ApiError
from backend.schemas import MatterCreate
from backend.services.common import (
    require_matter,
    serialize_matter_overview,
    transaction,
)
from backend.tables import matter, matter_type, v_matter_overview


def create_matter(
    session: Session,
    settings: Settings,
    body: MatterCreate,
    *,
    now: datetime,
) -> dict:
    with transaction(session, settings):
        type_row = session.execute(
            select(matter_type.c.id).where(
                matter_type.c.type_code == body.type_code,
                matter_type.c.enabled.is_(True),
            )
        ).first()
        if type_row is None:
            raise ApiError(
                422,
                "unknown_matter_type",
                "事项类型不存在或未启用",
                next_step="检查 type_code 后重试",
            )

        matter_id = uuid4()
        session.execute(
            insert(matter).values(
                id=matter_id,
                workspace_id=settings.demo_workspace_id,
                type_code=body.type_code,
                template_version_id=None,
                goal=body.goal,
                status="draft",
                scope_year=body.scope_year,
                scope_attrs=body.scope_attrs,
                created_at=now,
                updated_at=now,
            )
        )
        return _read_overview(session, settings, matter_id)


def list_matters(session: Session, settings: Settings) -> list[dict]:
    with transaction(session, settings):
        rows = session.execute(
            select(v_matter_overview)
            .where(v_matter_overview.c.workspace_id == settings.demo_workspace_id)
            .order_by(v_matter_overview.c.updated_at.desc())
        ).mappings()
        return [serialize_matter_overview(row) for row in rows]


def get_matter(session: Session, settings: Settings, matter_id: UUID) -> dict:
    with transaction(session, settings):
        require_matter(session, settings, matter_id)
        return _read_overview(session, settings, matter_id)


def _read_overview(session: Session, settings: Settings, matter_id: UUID) -> dict:
    row = (
        session.execute(
            select(v_matter_overview).where(
                v_matter_overview.c.id == matter_id,
                v_matter_overview.c.workspace_id == settings.demo_workspace_id,
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise ApiError(
            404,
            "matter_not_found",
            "未找到当前工作区中的事项",
            next_step="刷新事项列表后重试",
        )
    return serialize_matter_overview(row)
