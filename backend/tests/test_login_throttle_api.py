"""Integration tests for login rate limiting and temporary lockout."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from backend.config import Settings
from backend.main import create_app
from backend.services.login_throttle import ip_bucket_key

DEFAULT_SETTINGS = Settings(database_url="")
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-password-2026"
WRONG_PASSWORD = "wrong-password"
LOGIN_PATH = "/api/v1/auth/login"
IP_LIMIT = DEFAULT_SETTINGS.login_ip_limit
IP_WINDOW = timedelta(seconds=DEFAULT_SETTINGS.login_ip_window_seconds)
EMAIL_LIMIT = DEFAULT_SETTINGS.login_email_limit
LOCK_DURATION = timedelta(seconds=DEFAULT_SETTINGS.login_lock_seconds)


def test_ip_rate_limit_blocks_one_address(
    app: FastAPI,
    admin: psycopg.Connection,
    clock,
) -> None:
    with TestClient(app, client=("203.0.113.10", 50000)) as limited:
        for index in range(IP_LIMIT):
            response = _login(
                limited,
                f"unknown-{index}@example.com",
                WRONG_PASSWORD,
            )
            assert response.status_code == 401, response.text

        blocked = _login(limited, "unknown-final@example.com", WRONG_PASSWORD)
        assert blocked.status_code == 429, blocked.text
        assert blocked.json()["error"]["code"] == "too_many_login_attempts"
        assert int(blocked.headers["retry-after"]) > 0

    with TestClient(app, client=("203.0.113.11", 50000)) as other:
        allowed = _login(other, DEMO_EMAIL, DEMO_PASSWORD)
        assert allowed.status_code == 200, allowed.text

    clock.value += IP_WINDOW + timedelta(seconds=1)
    with TestClient(app, client=("203.0.113.10", 50000)) as recovered:
        allowed = _login(recovered, DEMO_EMAIL, DEMO_PASSWORD)
        assert allowed.status_code == 200, allowed.text


def test_email_lockout_blocks_all_addresses(
    app: FastAPI,
    admin: psycopg.Connection,
    clock,
) -> None:
    for index in range(EMAIL_LIMIT):
        with TestClient(app, client=(f"198.51.100.{index + 10}", 50000)) as client:
            response = _login(client, DEMO_EMAIL, WRONG_PASSWORD)
            if index < EMAIL_LIMIT - 1:
                assert response.status_code == 401, response.text
            else:
                assert response.status_code == 429, response.text
                assert response.json()["error"]["code"] == "too_many_login_attempts"
                assert int(response.headers["retry-after"]) == int(
                    LOCK_DURATION.total_seconds()
                )

    with TestClient(app, client=("198.51.100.50", 50000)) as locked:
        response = _login(locked, DEMO_EMAIL, DEMO_PASSWORD)
        assert response.status_code == 429, response.text

    clock.value += LOCK_DURATION + timedelta(seconds=1)
    with TestClient(app, client=("198.51.100.51", 50000)) as recovered:
        response = _login(recovered, DEMO_EMAIL, DEMO_PASSWORD)
        assert response.status_code == 200, response.text


def test_nonexistent_email_gets_same_lockout(
    app: FastAPI,
    admin: psycopg.Connection,
    clock,
) -> None:
    email = "missing@example.com"
    for index in range(EMAIL_LIMIT - 1):
        with TestClient(app, client=(f"198.51.100.{index + 60}", 50000)) as client:
            response = _login(client, email, WRONG_PASSWORD)
            assert response.status_code == 401, response.text
            assert response.json()["error"]["code"] == "invalid_credentials"

    with TestClient(app, client=("198.51.100.70", 50000)) as client:
        response = _login(client, email, WRONG_PASSWORD)
        assert response.status_code == 429, response.text
        assert response.json()["error"]["code"] == "too_many_login_attempts"


def test_successful_login_clears_email_failures(
    app: FastAPI,
    admin: psycopg.Connection,
    clock,
) -> None:
    for index in range(EMAIL_LIMIT - 1):
        with TestClient(app, client=(f"198.51.100.{index + 80}", 50000)) as client:
            response = _login(client, DEMO_EMAIL, WRONG_PASSWORD)
            assert response.status_code == 401, response.text

    with TestClient(app, client=("198.51.100.90", 50000)) as client:
        response = _login(client, DEMO_EMAIL, DEMO_PASSWORD)
        assert response.status_code == 200, response.text

    for index in range(EMAIL_LIMIT - 1):
        with TestClient(app, client=(f"198.51.100.{index + 100}", 50000)) as client:
            response = _login(client, DEMO_EMAIL, WRONG_PASSWORD)
            assert response.status_code == 401, response.text

    with TestClient(app, client=("198.51.100.110", 50000)) as client:
        response = _login(client, DEMO_EMAIL, WRONG_PASSWORD)
        assert response.status_code == 429, response.text


def test_forwarded_for_trust_boundary(
    app: FastAPI,
    admin: psycopg.Connection,
) -> None:
    wrapped = ProxyHeadersMiddleware(cast(Any, app), trusted_hosts="127.0.0.1")

    with TestClient(cast(Any, wrapped), client=("127.0.0.1", 50000)) as trusted:
        response = trusted.post(
            LOGIN_PATH,
            json={"email": DEMO_EMAIL, "password": WRONG_PASSWORD},
            headers={"X-Forwarded-For": "203.0.113.77"},
        )
        assert response.status_code == 401, response.text

    assert _bucket_keys(admin) == ["ip:203.0.113.77"]

    admin.execute("TRUNCATE core.login_throttle")

    with TestClient(cast(Any, wrapped), client=("198.51.100.99", 50000)) as untrusted:
        response = untrusted.post(
            LOGIN_PATH,
            json={"email": DEMO_EMAIL, "password": WRONG_PASSWORD},
            headers={"X-Forwarded-For": "203.0.113.77"},
        )
        assert response.status_code == 401, response.text

    assert _bucket_keys(admin) == ["ip:198.51.100.99"]


def test_custom_thresholds_take_effect(
    database_urls: tuple[str, str],
    admin: psycopg.Connection,
    clock,
) -> None:
    app_url, _ = database_urls
    custom_app = create_app(
        Settings(
            database_url=app_url,
            demo_timezone="Asia/Shanghai",
            login_ip_limit=2,
            login_email_limit=2,
            login_lock_seconds=60,
        ),
        clock=clock,
    )

    with TestClient(custom_app, client=("203.0.113.20", 50000)) as limited:
        first = _login(limited, "ip-first@example.com", WRONG_PASSWORD)
        second = _login(limited, "ip-second@example.com", WRONG_PASSWORD)
        blocked = _login(limited, "ip-third@example.com", WRONG_PASSWORD)
        assert first.status_code == 401, first.text
        assert second.status_code == 401, second.text
        assert blocked.status_code == 429, blocked.text

    for index in range(2):
        with TestClient(
            custom_app, client=(f"198.51.100.{index + 140}", 50000)
        ) as client:
            response = _login(client, DEMO_EMAIL, WRONG_PASSWORD)
            if index == 0:
                assert response.status_code == 401, response.text
            else:
                assert response.status_code == 429, response.text
                assert int(response.headers["retry-after"]) == 60

    with TestClient(custom_app, client=("198.51.100.142", 50000)) as locked:
        response = _login(locked, DEMO_EMAIL, DEMO_PASSWORD)
        assert response.status_code == 429, response.text

    clock.value += timedelta(seconds=61)
    with TestClient(custom_app, client=("198.51.100.143", 50000)) as recovered:
        response = _login(recovered, DEMO_EMAIL, DEMO_PASSWORD)
        assert response.status_code == 200, response.text


def test_zero_limits_disable_throttling(
    database_urls: tuple[str, str],
    admin: psycopg.Connection,
    clock,
) -> None:
    app_url, _ = database_urls
    disabled_app = create_app(
        Settings(
            database_url=app_url,
            demo_timezone="Asia/Shanghai",
            login_ip_limit=0,
            login_email_limit=0,
        ),
        clock=clock,
    )

    with TestClient(disabled_app, client=("203.0.113.30", 50000)) as client:
        for _ in range(IP_LIMIT + 1):
            response = _login(client, "disabled@example.com", WRONG_PASSWORD)
            assert response.status_code == 401, response.text

    assert admin.execute("SELECT count(*) FROM core.login_throttle").fetchone() == (0,)


def test_ip_bucket_key_normalizes_networks() -> None:
    assert ip_bucket_key("203.0.113.7") == "ip:203.0.113.7"
    assert ip_bucket_key("::ffff:203.0.113.7") == "ip:203.0.113.7"
    assert ip_bucket_key("2001:db8:1:2::1") == "ip:2001:db8:1:2::/64"
    assert ip_bucket_key("2001:db8:1:2::ffff") == "ip:2001:db8:1:2::/64"
    assert ip_bucket_key(None) is None
    assert ip_bucket_key("testclient") is None


def _login(client: TestClient, email: str, password: str):
    return client.post(LOGIN_PATH, json={"email": email, "password": password})


def _bucket_keys(admin: psycopg.Connection) -> list[str]:
    return [
        row[0]
        for row in admin.execute(
            "SELECT bucket_key FROM core.login_throttle"
            " WHERE bucket_key LIKE 'ip:%' ORDER BY bucket_key"
        ).fetchall()
    ]
