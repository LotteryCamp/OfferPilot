"""Authenticated request identity shared by services and routers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """The authenticated account and its personal workspace."""

    user_id: UUID
    workspace_id: UUID
    email: str
    display_name: str
    account_type: str
    status: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    session_id: UUID
    session_expires_at: datetime
    remember: bool

    @property
    def is_admin(self) -> bool:
        return self.account_type == "admin"
