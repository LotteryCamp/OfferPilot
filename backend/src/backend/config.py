"""Application configuration for the Alpha business API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import UUID

DEFAULT_USER_ID = UUID("00000000-0000-7000-8000-000000000001")
DEFAULT_WORKSPACE_ID = UUID("00000000-0000-7000-8000-000000000002")


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings for the single-user Alpha demo."""

    database_url: str
    demo_user_id: UUID = DEFAULT_USER_ID
    demo_workspace_id: UUID = DEFAULT_WORKSPACE_ID
    api_prefix: str = "/api/v1"
    demo_timezone: str = "Asia/Shanghai"

    @classmethod
    def from_env(cls) -> Settings:
        database_url = os.environ.get("OFFERPILOT_DATABASE_URL") or os.environ.get(
            "DATABASE_URL"
        )
        if not database_url:
            raise RuntimeError("OFFERPILOT_DATABASE_URL or DATABASE_URL must be set")
        return cls(
            database_url=database_url,
            demo_user_id=_uuid_env("OFFERPILOT_DEMO_USER_ID", DEFAULT_USER_ID),
            demo_workspace_id=_uuid_env(
                "OFFERPILOT_DEMO_WORKSPACE_ID", DEFAULT_WORKSPACE_ID
            ),
            demo_timezone=os.environ.get("OFFERPILOT_DEMO_TIMEZONE", "Asia/Shanghai"),
        )


def _uuid_env(name: str, default: UUID) -> UUID:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return UUID(raw.strip())
