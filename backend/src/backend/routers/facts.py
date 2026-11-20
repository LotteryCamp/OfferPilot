"""Personal fact routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from backend.routers.deps import ClockDep, SessionDep, SettingsDep
from backend.schemas import FactSaveRequest
from backend.services import facts as fact_service

router = APIRouter(prefix="/matters/{matter_id}/facts", tags=["facts"])


@router.put("/{fact_type}")
def save_fact(
    matter_id: UUID,
    fact_type: str,
    body: FactSaveRequest,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> dict:
    return fact_service.save_fact(
        session,
        settings,
        matter_id,
        fact_type,
        body,
        now=clock.now(),
    )


@router.get("")
def list_facts(matter_id: UUID, session: SessionDep, settings: SettingsDep) -> dict:
    return fact_service.list_facts(session, settings, matter_id)


@router.get("/{fact_type}")
def get_fact(
    matter_id: UUID,
    fact_type: str,
    session: SessionDep,
    settings: SettingsDep,
) -> dict:
    return fact_service.get_fact(session, settings, matter_id, fact_type)
