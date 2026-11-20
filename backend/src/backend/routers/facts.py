"""Personal fact routes."""

from __future__ import annotations

from fastapi import APIRouter

from backend.routers.deps import ClockDep, SessionDep, SettingsDep
from backend.schemas import FactSaveRequest
from backend.services import facts as fact_service

router = APIRouter(prefix="/facts", tags=["facts"])


@router.put("/{fact_type}")
def save_fact(
    fact_type: str,
    body: FactSaveRequest,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> dict:
    return fact_service.save_fact(
        session,
        settings,
        fact_type,
        body,
        now=clock.now(),
    )


@router.get("")
def list_facts(session: SessionDep, settings: SettingsDep) -> dict:
    return fact_service.list_facts(session, settings)


@router.get("/{fact_type}")
def get_fact(
    fact_type: str,
    session: SessionDep,
    settings: SettingsDep,
) -> dict:
    return fact_service.get_fact(session, settings, fact_type)
