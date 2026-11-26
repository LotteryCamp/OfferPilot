"""Administrator runtime configuration routes."""

from __future__ import annotations

from fastapi import APIRouter

from backend.routers.deps import AdminUserDep, RuntimeConfigDep
from backend.schemas import AdminSettingsUpdate
from backend.services import admin_settings as admin_settings_service

router = APIRouter(prefix="/admin/settings", tags=["admin settings"])


@router.get("")
def read_admin_settings(config: RuntimeConfigDep, admin: AdminUserDep) -> dict:
    del admin
    return admin_settings_service.settings_payload(config)


@router.patch("")
def update_admin_settings(
    body: AdminSettingsUpdate,
    config: RuntimeConfigDep,
    admin: AdminUserDep,
) -> dict:
    del admin
    return admin_settings_service.update_settings(config, body)
