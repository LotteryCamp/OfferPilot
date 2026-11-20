"""Matter creation and read services."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.errors import ApiError
from backend.schemas import MatterCreate
from backend.services import plans as plan_service
from backend.services.common import (
    require_matter,
    serialize_matter_overview,
    transaction,
)
from backend.tables import matter, matter_type, template_version, v_matter_overview


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

        template_row = session.execute(
            select(template_version.c.id)
            .where(
                template_version.c.type_code == body.type_code,
                template_version.c.status == "published",
            )
            .order_by(
                template_version.c.published_at.desc().nulls_last(),
                template_version.c.created_at.desc(),
            )
            .limit(1)
        ).scalar_one_or_none()
        if template_row is None:
            raise ApiError(
                409,
                "template_version_missing",
                "事项类型没有已发布的模板版本",
                next_step="检查模板版本数据后重试",
            )

        matter_id = uuid4()
        session.execute(
            insert(matter).values(
                id=matter_id,
                workspace_id=settings.demo_workspace_id,
                type_code=body.type_code,
                template_version_id=template_row,
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
        rows = (
            session.execute(
                select(v_matter_overview)
                .where(v_matter_overview.c.workspace_id == settings.demo_workspace_id)
                .order_by(v_matter_overview.c.updated_at.desc())
            )
            .mappings()
            .all()
        )
        latest_plan_ids = {
            row["latest_plan_id"] for row in rows if row["latest_plan_id"] is not None
        }
        states = plan_service.basis_states_for_plan_ids(
            session, settings, latest_plan_ids
        )
        return [_serialize_with_plan_state(row, states) for row in rows]


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
    latest_plan_id = row["latest_plan_id"]
    states = plan_service.basis_states_for_plan_ids(
        session,
        settings,
        {latest_plan_id} if latest_plan_id is not None else set(),
    )
    return _serialize_with_plan_state(row, states)


def _serialize_with_plan_state(
    row: dict,
    states: dict,
) -> dict:
    latest_plan_id = row["latest_plan_id"]
    basis_status, stale_facts = states.get(latest_plan_id, ("not_applicable", []))
    return serialize_matter_overview(
        row,
        basis_status=basis_status,
        stale_facts=stale_facts,
    )
