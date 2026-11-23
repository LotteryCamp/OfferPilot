"""Source, snapshot, and requirement routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from backend.routers.deps import ClockDep, CurrentUserDep, SessionDep, SourceReaderDep
from backend.schemas import RequirementBatchCreate, SourceCreate, SourceReadRequest
from backend.services import requirements as requirement_service
from backend.services import sources as source_service

router = APIRouter(prefix="/matters/{matter_id}", tags=["sources"])


@router.post(
    "/sources",
    status_code=status.HTTP_201_CREATED,
)
def register_source(
    matter_id: UUID,
    body: SourceCreate,
    current_user: CurrentUserDep,
    session: SessionDep,
    clock: ClockDep,
) -> dict:
    return source_service.register_source(
        session, current_user, matter_id, body, now=clock.now()
    )


@router.post(
    "/sources/read",
    status_code=status.HTTP_201_CREATED,
)
def read_public_source(
    matter_id: UUID,
    body: SourceReadRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
    clock: ClockDep,
    reader: SourceReaderDep,
) -> dict:
    return source_service.read_and_register_source(
        session,
        current_user,
        matter_id,
        body,
        now=clock.now(),
        reader=reader,
    )


@router.get("/sources")
def list_sources(
    matter_id: UUID, session: SessionDep, current_user: CurrentUserDep
) -> dict:
    return source_service.list_matter_sources(session, current_user, matter_id)


@router.post(
    "/requirements",
    status_code=status.HTTP_201_CREATED,
)
def create_requirements(
    matter_id: UUID,
    body: RequirementBatchCreate,
    current_user: CurrentUserDep,
    session: SessionDep,
    clock: ClockDep,
) -> dict:
    return requirement_service.create_requirements(
        session, current_user, matter_id, body, now=clock.now()
    )
