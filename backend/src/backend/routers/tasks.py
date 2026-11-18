"""Task routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from backend.routers.deps import SessionDep, SettingsDep
from backend.services import tasks as task_service

router = APIRouter(prefix="/matters/{matter_id}", tags=["tasks"])


@router.get("/tasks")
def list_tasks(matter_id: UUID, session: SessionDep, settings: SettingsDep) -> dict:
    return task_service.list_tasks(session, settings, matter_id)
