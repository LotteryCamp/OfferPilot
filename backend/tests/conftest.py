"""Integration test fixtures for the Alpha business API."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.clock import Clock
from backend.config import Settings
from backend.main import create_app
from backend.security import hash_password

USER_ID = UUID("00000000-0000-7000-8000-000000000001")
WORKSPACE_ID = UUID("00000000-0000-7000-8000-000000000002")
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo" + "-password-2026"

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
            TRUNCATE core.login_throttle, core.user_session, core.model_transfer_consent,
                     core.fact, core.agent_run,
                     core.matter_source, core.task,
                     core.candidate_plan_decision,
                     core.candidate_plan_item_source, core.candidate_plan_item,
                     core.candidate_plan, core.requirement_self_check,
                     core.requirement, ops.evidence, ops.snapshot, ops.source,
                     core.matter, core.workspace, core.app_user
            CASCADE
            """
        )
        connection.execute(
            """
            INSERT INTO core.app_user
                (id, email, display_name, password_hash, account_type, status)
            VALUES (%s, %s, '演示用户', %s, 'applicant', 'active')
            """,
            (USER_ID, DEMO_EMAIL, hash_password(DEMO_PASSWORD)),
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
def app(
    database_urls: tuple[str, str], admin: psycopg.Connection, clock: MutableClock
) -> FastAPI:
    app_url, _ = database_urls
    settings = Settings(
        database_url=app_url,
        demo_timezone="Asia/Shanghai",
    )
    return create_app(settings, clock=clock)


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        login_client(test_client)
        yield test_client


@pytest.fixture()
def login():
    return login_client


def login_client(
    test_client: TestClient,
    *,
    email: str = DEMO_EMAIL,
    password: str = DEMO_PASSWORD,
    remember: bool = False,
) -> None:
    response = test_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "remember": remember},
    )
    assert response.status_code == 200, response.text
