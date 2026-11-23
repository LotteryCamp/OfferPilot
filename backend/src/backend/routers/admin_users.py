"""Administrator user-management routes."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, status

from backend.routers.deps import AdminUserDep, ClockDep, SessionDep
from backend.schemas import (
    AdminPasswordReset,
    AdminUserRoleUpdate,
    AdminUserStatusUpdate,
)
from backend.services import admin_users as admin_user_service

router = APIRouter(prefix="/admin/users", tags=["admin users"])


@router.get("")
def list_users(
    session: SessionDep,
    admin: AdminUserDep,
    search: Annotated[str | None, Query(max_length=160)] = None,
    status_filter: Annotated[
        Literal["pending", "active", "disabled"] | None,
        Query(alias="status"),
    ] = None,
    account_type: Annotated[
        Literal["applicant", "admin"] | None,
        Query(),
    ] = None,
    include_deleted: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    del admin
    return admin_user_service.list_users(
        session,
        search=search,
        status=status_filter,
        account_type=account_type,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
    )


@router.patch("/{user_id}/status")
def update_user_status(
    user_id: UUID,
    body: AdminUserStatusUpdate,
    session: SessionDep,
    admin: AdminUserDep,
    clock: ClockDep,
) -> dict:
    return {
        "user": admin_user_service.update_status(
            session,
            admin,
            user_id,
            body,
            now=clock.now(),
        )
    }


@router.patch("/{user_id}/role")
def update_user_role(
    user_id: UUID,
    body: AdminUserRoleUpdate,
    session: SessionDep,
    admin: AdminUserDep,
    clock: ClockDep,
) -> dict:
    return {
        "user": admin_user_service.update_role(
            session,
            admin,
            user_id,
            body,
            now=clock.now(),
        )
    }


@router.post("/{user_id}/password-reset")
def reset_user_password(
    user_id: UUID,
    body: AdminPasswordReset,
    session: SessionDep,
    admin: AdminUserDep,
    clock: ClockDep,
) -> dict:
    return {
        "user": admin_user_service.reset_password(
            session,
            admin,
            user_id,
            body,
            now=clock.now(),
        )
    }


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: UUID,
    session: SessionDep,
    admin: AdminUserDep,
    clock: ClockDep,
) -> None:
    admin_user_service.delete_user(
        session,
        admin,
        user_id,
        now=clock.now(),
    )
