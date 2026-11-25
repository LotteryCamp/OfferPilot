"""Task routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from backend.routers.deps import CurrentUserDep, SessionDep
from backend.services import tasks as task_service

router = APIRouter(prefix="/matters/{matter_id}", tags=["tasks"])


@router.get("/tasks")
def list_tasks(
    matter_id: UUID, session: SessionDep, current_user: CurrentUserDep
) -> dict:
    return task_service.list_tasks(session, current_user, matter_id)
