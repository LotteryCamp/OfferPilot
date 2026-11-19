"""Integration test fixtures for the Alpha business API."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.clock import Clock
from backend.config import Settings
from backend.main import create_app

USER_ID = UUID("00000000-0000-7000-8000-000000000001")
WORKSPACE_ID = UUID("00000000-0000-7000-8000-000000000002")

TEST_DATABASE_URL = os.environ.get("OFFERPILOT_TEST_DATABASE_URL")
TEST_ADMIN_DATABASE_URL = os.environ.get("OFFERPILOT_TEST_ADMIN_DATABASE_URL")


class MutableClock(Clock):
    def __init__(self, value: datetime) -> None:
        self.value = value.astimezone(UTC)

    def now(self) -> datetime:
        return self.value


@pytest.fixture(scope="session")
def database_urls() -> tuple[str, str]:
    if not TEST_DATABASE_URL or not TEST_ADMIN_DATABASE_URL:
        pytest.skip(
            "set OFFERPILOT_TEST_DATABASE_URL and "
            "OFFERPILOT_TEST_ADMIN_DATABASE_URL to run integration tests"
        )
    return TEST_DATABASE_URL, TEST_ADMIN_DATABASE_URL


@pytest.fixture()
def admin(database_urls: tuple[str, str]) -> Iterator[psycopg.Connection]:
    _, admin_url = database_urls
    connection = psycopg.connect(admin_url, autocommit=True)
    try:
        connection.execute(
            """
            TRUNCATE core.task, core.candidate_plan_decision,
                     core.candidate_plan_item_source, core.candidate_plan_item,
                     core.candidate_plan, core.requirement, ops.evidence,
                     ops.snapshot, ops.source, core.matter, core.workspace,
                     core.app_user
            CASCADE
            """
        )
        connection.execute(
            """
            INSERT INTO core.app_user
                (id, email, display_name, password_hash, account_type, status)
            VALUES (%s, 'demo@offerpilot.local', '演示用户',
                    '!alpha-demo-no-login', 'applicant', 'active')
            """,
            (USER_ID,),
        )
        connection.execute(
            "INSERT INTO core.workspace (id, owner_id) VALUES (%s, %s)",
            (WORKSPACE_ID, USER_ID),
        )
        connection.execute(
            """
            INSERT INTO core.matter_type (type_code, name, built_in, enabled)
            VALUES ('pre_recommend', '推免', true, true)
            ON CONFLICT (type_code) DO UPDATE
                SET name = EXCLUDED.name, built_in = true
            """
        )
        yield connection
    finally:
        connection.close()


@pytest.fixture()
def clock() -> MutableClock:
    return MutableClock(datetime(2026, 9, 9, 9, 0, tzinfo=UTC))


@pytest.fixture()
def client(
    database_urls: tuple[str, str], admin: psycopg.Connection, clock: MutableClock
) -> Iterator[TestClient]:
    app_url, _ = database_urls
    settings = Settings(
        database_url=app_url,
        demo_user_id=USER_ID,
        demo_workspace_id=WORKSPACE_ID,
        demo_timezone="Asia/Shanghai",
    )
    app = create_app(settings, clock=clock)
    with TestClient(app) as test_client:
        yield test_client
