"""Model transfer consent routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from backend.routers.deps import ClockDep, SessionDep, SettingsDep
from backend.services import consents as consent_service

router = APIRouter(
    prefix="/matters/{matter_id}/model-transfer-consents",
    tags=["model transfer consents"],
)


@router.get("")
def get_consent(
    matter_id: UUID,
    session: SessionDep,
    settings: SettingsDep,
) -> dict:
    return consent_service.get_consent(session, settings, matter_id)


@router.post("")
def grant_consent(
    matter_id: UUID,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> dict:
    return consent_service.grant_consent(
        session,
        settings,
        matter_id,
        now=clock.now(),
    )


@router.delete("/{consent_id}")
def revoke_consent(
    matter_id: UUID,
    consent_id: UUID,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> dict:
    return consent_service.revoke_consent(
        session,
        settings,
        matter_id,
        consent_id,
        now=clock.now(),
    )
