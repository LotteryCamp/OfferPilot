"""Matter routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from backend.routers.deps import ClockDep, SessionDep, SettingsDep
from backend.schemas import MatterCreate
from backend.services import matters as matter_service

router = APIRouter(prefix="/matters", tags=["matters"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_matter(
    body: MatterCreate,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> dict:
    return {
        "matter": matter_service.create_matter(session, settings, body, now=clock.now())
    }


@router.get("")
def list_matters(session: SessionDep, settings: SettingsDep) -> dict:
    return {"matters": matter_service.list_matters(session, settings)}


@router.get("/{matter_id}")
def get_matter(matter_id: UUID, session: SessionDep, settings: SettingsDep) -> dict:
    return {"matter": matter_service.get_matter(session, settings, matter_id)}
