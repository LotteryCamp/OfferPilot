"""Model transfer consent persistence and lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.errors import ApiError
from backend.services.common import iso, require_matter, transaction, uuid_text
from backend.tables import model_transfer_consent
from backend.transfer import (
    TRANSFER_DATA_HANDLING,
    TRANSFER_FIELD_CATEGORIES,
    TRANSFER_PURPOSES,
)


def get_consent(
    session: Session, settings: Settings, matter_id: UUID
) -> dict[str, Any]:
    with transaction(session, settings):
        matter_row = require_matter(session, settings, matter_id)
        active = _load_active(session, settings, matter_id)
        return {
            "required": bool(matter_row["scope_attrs"]),
            "disclosure": _disclosure(settings),
            "consent": _serialize(active) if active is not None else None,
        }


def grant_consent(
    session: Session,
    settings: Settings,
    matter_id: UUID,
    *,
    now: datetime,
) -> dict[str, Any]:
    with transaction(session, settings):
        require_matter(session, settings, matter_id, for_update=True)
        active = _load_active(session, settings, matter_id, for_update=True)
        if active is not None:
            return {"consent": _serialize(active), "created": False}

        version_no = _next_version(session, settings, matter_id)
        consent_id = uuid4()
        session.execute(
            insert(model_transfer_consent).values(
                id=consent_id,
                workspace_id=settings.demo_workspace_id,
                owner_id=settings.demo_user_id,
                matter_id=matter_id,
                provider=settings.model_provider,
                purposes=list(TRANSFER_PURPOSES),
                field_categories=list(TRANSFER_FIELD_CATEGORIES),
                consent_status="active",
                version_no=version_no,
                created_at=now,
                revoked_at=None,
            )
        )
        session.flush()
        created = _load_by_id(session, settings, matter_id, consent_id)
        assert created is not None
        return {"consent": _serialize(created), "created": True}


def revoke_consent(
    session: Session,
    settings: Settings,
    matter_id: UUID,
    consent_id: UUID,
    *,
    now: datetime,
) -> dict[str, Any]:
    with transaction(session, settings):
        require_matter(session, settings, matter_id, for_update=True)
        row = (
            session.execute(
                select(model_transfer_consent)
                .where(
                    model_transfer_consent.c.id == consent_id,
                    model_transfer_consent.c.owner_id == settings.demo_user_id,
                    model_transfer_consent.c.matter_id == matter_id,
                )
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if row is None:
            raise ApiError(
                404,
                "transfer_consent_not_found",
                "未找到当前事项的模型传输同意",
                next_step="刷新授权状态后重试",
            )
        if row["consent_status"] == "revoked":
            return {"consent": _serialize(row), "revoked": False}

        session.execute(
            update(model_transfer_consent)
            .where(model_transfer_consent.c.id == consent_id)
            .values(consent_status="revoked", revoked_at=now)
        )
        revoked = _load_by_id(session, settings, matter_id, consent_id)
        assert revoked is not None
        return {"consent": _serialize(revoked), "revoked": True}


def _load_active(
    session: Session,
    settings: Settings,
    matter_id: UUID,
    *,
    for_update: bool = False,
) -> Mapping[str, Any] | None:
    statement = (
        select(model_transfer_consent)
        .where(
            model_transfer_consent.c.owner_id == settings.demo_user_id,
            model_transfer_consent.c.matter_id == matter_id,
            model_transfer_consent.c.consent_status == "active",
        )
        .order_by(model_transfer_consent.c.version_no.desc())
        .limit(1)
    )
    if for_update:
        statement = statement.with_for_update()
    return session.execute(statement).mappings().first()


def _load_by_id(
    session: Session,
    settings: Settings,
    matter_id: UUID,
    consent_id: UUID,
) -> Mapping[str, Any] | None:
    return (
        session.execute(
            select(model_transfer_consent).where(
                model_transfer_consent.c.id == consent_id,
                model_transfer_consent.c.owner_id == settings.demo_user_id,
                model_transfer_consent.c.matter_id == matter_id,
            )
        )
        .mappings()
        .first()
    )


def _next_version(session: Session, settings: Settings, matter_id: UUID) -> int:
    current = session.execute(
        select(func.coalesce(func.max(model_transfer_consent.c.version_no), 0)).where(
            model_transfer_consent.c.owner_id == settings.demo_user_id,
            model_transfer_consent.c.matter_id == matter_id,
        )
    ).scalar_one()
    return int(current) + 1


def _disclosure(settings: Settings) -> dict[str, Any]:
    return {
        "provider": settings.model_provider,
        "model": settings.model_name or None,
        "purposes": list(TRANSFER_PURPOSES),
        "field_categories": list(TRANSFER_FIELD_CATEGORIES),
        "data_handling": TRANSFER_DATA_HANDLING,
    }


def _serialize(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "consent_id": uuid_text(row["id"]),
        "matter_id": uuid_text(row["matter_id"]),
        "provider": row["provider"],
        "purposes": list(row["purposes"]),
        "field_categories": list(row["field_categories"]),
        "status": row["consent_status"],
        "version_no": row["version_no"],
        "created_at": iso(row["created_at"]),
        "revoked_at": iso(row["revoked_at"]),
    }
