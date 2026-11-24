"""Integration tests for authentication, sessions, and administrator accounts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from uuid import UUID

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.admin_cli import ADMIN_PASSWORD_ENV
from backend.admin_cli import main as admin_cli_main
from backend.config import Settings

USER_PASSWORD = "user" + str(2026) + "!"
NEW_PASSWORD = "newuser" + str(2026) + "!"
ADMIN_EMAIL = "admin@example.com"
ADMIN_DISPLAY_NAME = "系统管理员"
ADMIN_PASSWORD = "admin" + str(2026) + "!"
EMAIL_LIMIT = Settings(database_url="").login_email_limit


def test_registration_immediately_authenticates(
    app: FastAPI, admin: psycopg.Connection
) -> None:
    with TestClient(app) as user_client:
        user = _register(user_client, "first@example.com", "首位用户")

        assert user["account_type"] == "applicant"
        assert user["status"] == "active"
        assert user["deleted_at"] is None
        assert user["workspace_id"]

        me = user_client.get("/api/v1/auth/me")
        assert me.status_code == 200, me.text
        assert me.json()["user"]["id"] == user["id"]
        assert me.json()["session"]["remember"] is False

        matters = user_client.get("/api/v1/matters")
        assert matters.status_code == 200, matters.text
        assert matters.json()["matters"] == []

        forbidden = user_client.get("/api/v1/admin/users")
        assert forbidden.status_code == 403, forbidden.text
        assert forbidden.json()["error"]["code"] == "admin_required"

        duplicate = user_client.post(
            "/api/v1/auth/register",
            json={
                "email": "FIRST@example.com",
                "display_name": "重复用户",
                "password": USER_PASSWORD,
            },
        )
        assert duplicate.status_code == 409, duplicate.text
        assert duplicate.json()["error"]["code"] == "email_already_registered"

        row = admin.execute(
            "SELECT password_hash, status, account_type"
            " FROM core.app_user WHERE email = %s",
            ("first@example.com",),
        ).fetchone()
        assert row is not None
        assert row[0].startswith("$argon2")
        assert row[0] != USER_PASSWORD
        assert row[1:] == ("active", "applicant")


def test_login_remember_cookie_and_server_session(
    app: FastAPI, admin: psycopg.Connection
) -> None:
    with TestClient(app) as user_client:
        _register(user_client, "session@example.com", "会话用户")
        logged_out = user_client.post("/api/v1/auth/logout")
        assert logged_out.status_code == 204
        assert user_client.get("/api/v1/auth/me").status_code == 401

        normal = user_client.post(
            "/api/v1/auth/login",
            json={
                "email": "session@example.com",
                "password": USER_PASSWORD,
                "remember": False,
            },
        )
        assert normal.status_code == 200, normal.text
        normal_cookie = normal.headers["set-cookie"].lower()
        assert "offerpilot_session=" in normal_cookie
        assert "httponly" in normal_cookie
        assert "samesite=lax" in normal_cookie
        assert "max-age" not in normal_cookie

        session = _latest_session(admin, "session@example.com", remember=False)
        assert session[0] is False
        assert session[1] == timedelta(seconds=43_200)

        assert user_client.post("/api/v1/auth/logout").status_code == 204
        remembered = user_client.post(
            "/api/v1/auth/login",
            json={
                "email": "SESSION@example.com",
                "password": USER_PASSWORD,
                "remember": True,
            },
        )
        assert remembered.status_code == 200, remembered.text
        remembered_cookie = remembered.headers["set-cookie"].lower()
        assert "max-age=2592000" in remembered_cookie
        assert remembered.json()["session"]["remember"] is True

        session = _latest_session(admin, "session@example.com", remember=True)
        assert session[0] is True
        assert session[1] == timedelta(seconds=2_592_000)

        current = user_client.get("/api/v1/auth/me")
        assert current.status_code == 200, current.text
        assert current.json()["session"]["remember"] is True

        wrong = user_client.post(
            "/api/v1/auth/login",
            json={
                "email": "session@example.com",
                "password": "wrong" + "-password",
            },
        )
        assert wrong.status_code == 401
        assert wrong.json()["error"]["code"] == "invalid_credentials"


def test_password_change_revokes_every_session(app: FastAPI) -> None:
    with TestClient(app) as first_client, TestClient(app) as second_client:
        _register(first_client, "password@example.com", "改密用户")
        _login(second_client, "password@example.com", USER_PASSWORD)
        assert second_client.get("/api/v1/auth/me").status_code == 200

        changed = first_client.post(
            "/api/v1/auth/password",
            json={
                "current_password": USER_PASSWORD,
                "new_password": NEW_PASSWORD,
            },
        )
        assert changed.status_code == 204, changed.text
        assert first_client.get("/api/v1/auth/me").status_code == 401
        assert second_client.get("/api/v1/auth/me").status_code == 401

        old_login = first_client.post(
            "/api/v1/auth/login",
            json={"email": "password@example.com", "password": USER_PASSWORD},
        )
        assert old_login.status_code == 401

        new_login = first_client.post(
            "/api/v1/auth/login",
            json={"email": "password@example.com", "password": NEW_PASSWORD},
        )
        assert new_login.status_code == 200, new_login.text

        invalid_current = first_client.post(
            "/api/v1/auth/password",
            json={
                "current_password": USER_PASSWORD,
                "new_password": "another" + "-password",
            },
        )
        assert invalid_current.status_code == 401
        assert invalid_current.json()["error"]["code"] == "invalid_current_password"


def test_profile_update_changes_display_name_without_ending_session(
    app: FastAPI, admin: psycopg.Connection
) -> None:
    with TestClient(app) as user_client:
        _register(user_client, "profile@example.com", "旧名称")

        updated = user_client.patch(
            "/api/v1/auth/me",
            json={"display_name": "  新名称  "},
        )
        assert updated.status_code == 200, updated.text
        body = updated.json()
        assert body["session_revoked"] is False
        assert body["user"]["display_name"] == "新名称"
        assert body["user"]["email"] == "profile@example.com"

        current = user_client.get("/api/v1/auth/me")
        assert current.status_code == 200
        assert current.json()["user"]["display_name"] == "新名称"

        row = admin.execute(
            "SELECT display_name, email FROM core.app_user WHERE email = %s",
            ("profile@example.com",),
        ).fetchone()
        assert row == ("新名称", "profile@example.com")


def test_email_change_requires_password_and_revokes_every_session(
    app: FastAPI,
) -> None:
    with TestClient(app) as first_client, TestClient(app) as second_client:
        _register(first_client, "old-mail@example.com", "改邮箱用户")
        _login(second_client, "old-mail@example.com", USER_PASSWORD)

        missing_password = first_client.patch(
            "/api/v1/auth/me",
            json={"email": "new-mail@example.com"},
        )
        assert missing_password.status_code == 422, missing_password.text
        assert missing_password.json()["error"]["code"] == "validation_error"

        wrong_password = first_client.patch(
            "/api/v1/auth/me",
            json={
                "email": "new-mail@example.com",
                "current_password": "wrong" + "-password",
            },
        )
        assert wrong_password.status_code == 401, wrong_password.text
        assert wrong_password.json()["error"]["code"] == "invalid_current_password"
        assert first_client.get("/api/v1/auth/me").status_code == 200

        changed = first_client.patch(
            "/api/v1/auth/me",
            json={
                "email": " NEW-MAIL@example.com ",
                "display_name": "新邮箱用户",
                "current_password": USER_PASSWORD,
            },
        )
        assert changed.status_code == 200, changed.text
        body = changed.json()
        assert body["session_revoked"] is True
        assert body["user"]["email"] == "new-mail@example.com"
        assert body["user"]["display_name"] == "新邮箱用户"
        assert "max-age=0" in changed.headers["set-cookie"].lower()
        assert first_client.get("/api/v1/auth/me").status_code == 401
        assert second_client.get("/api/v1/auth/me").status_code == 401

        old_login = first_client.post(
            "/api/v1/auth/login",
            json={"email": "old-mail@example.com", "password": USER_PASSWORD},
        )
        assert old_login.status_code == 401

        _login(first_client, "new-mail@example.com", USER_PASSWORD)
        assert first_client.get("/api/v1/auth/me").status_code == 200


def test_email_change_rejects_registered_email(app: FastAPI) -> None:
    with TestClient(app) as user_client, TestClient(app) as other_client:
        _register(user_client, "owner@example.com", "本人")
        _register(other_client, "taken@example.com", "他人")

        response = user_client.patch(
            "/api/v1/auth/me",
            json={
                "email": "TAKEN@example.com",
                "current_password": USER_PASSWORD,
            },
        )
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "email_already_registered"

        current = user_client.get("/api/v1/auth/me")
        assert current.status_code == 200
        assert current.json()["user"]["email"] == "owner@example.com"


def test_profile_update_with_unchanged_email_keeps_session(app: FastAPI) -> None:
    with TestClient(app) as user_client:
        _register(user_client, "same-mail@example.com", "同名用户")

        response = user_client.patch(
            "/api/v1/auth/me",
            json={"email": "SAME-MAIL@example.com"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["session_revoked"] is False
        assert body["user"]["email"] == "same-mail@example.com"
        assert user_client.get("/api/v1/auth/me").status_code == 200


def test_profile_update_validates_request(app: FastAPI) -> None:
    with TestClient(app) as user_client:
        _register(user_client, "invalid-profile@example.com", "校验用户")

        empty = user_client.patch("/api/v1/auth/me", json={})
        assert empty.status_code == 422, empty.text
        assert empty.json()["error"]["code"] == "validation_error"

        blank = user_client.patch(
            "/api/v1/auth/me",
            json={"display_name": "   "},
        )
        assert blank.status_code == 422, blank.text
        assert blank.json()["error"]["code"] == "validation_error"


def test_administrator_account_lifecycle(
    app: FastAPI,
    admin: psycopg.Connection,
    database_urls: tuple[str, str],
    login: Callable[..., None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_url, _ = database_urls
    _create_admin(monkeypatch, app_url)

    with (
        TestClient(app) as applicant_client,
        TestClient(app) as admin_client,
    ):
        applicant = _register(applicant_client, "managed@example.com", "受管用户")
        _login(admin_client, ADMIN_EMAIL, ADMIN_PASSWORD)

        listed = admin_client.get(
            "/api/v1/admin/users",
            params={"search": "managed@example.com"},
        )
        assert listed.status_code == 200, listed.text
        assert listed.json()["total"] == 1
        assert listed.json()["users"][0]["id"] == applicant["id"]

        escaped = admin_client.get(
            "/api/v1/admin/users",
            params={"search": "%"},
        )
        assert escaped.status_code == 200, escaped.text
        assert escaped.json()["total"] == 0

        disabled = admin_client.patch(
            f"/api/v1/admin/users/{applicant['id']}/status",
            json={"status": "disabled"},
        )
        assert disabled.status_code == 200, disabled.text
        assert disabled.json()["user"]["status"] == "disabled"
        assert applicant_client.get("/api/v1/auth/me").status_code == 401

        disabled_login = applicant_client.post(
            "/api/v1/auth/login",
            json={"email": "managed@example.com", "password": USER_PASSWORD},
        )
        assert disabled_login.status_code == 401

        enabled = admin_client.patch(
            f"/api/v1/admin/users/{applicant['id']}/status",
            json={"status": "active"},
        )
        assert enabled.status_code == 200, enabled.text
        _login(applicant_client, "managed@example.com", USER_PASSWORD)
        assert applicant_client.get("/api/v1/admin/users").status_code == 403

        promoted = admin_client.patch(
            f"/api/v1/admin/users/{applicant['id']}/role",
            json={"account_type": "admin"},
        )
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["user"]["account_type"] == "admin"
        assert applicant_client.get("/api/v1/admin/users").status_code == 200

        reset = admin_client.post(
            f"/api/v1/admin/users/{applicant['id']}/password-reset",
            json={"new_password": NEW_PASSWORD},
        )
        assert reset.status_code == 200, reset.text
        assert applicant_client.get("/api/v1/auth/me").status_code == 401
        _login(applicant_client, "managed@example.com", NEW_PASSWORD)

        admin_id = _current_user_id(admin_client)
        for method, path, payload in (
            (
                "patch",
                f"/api/v1/admin/users/{admin_id}/status",
                {"status": "disabled"},
            ),
            (
                "patch",
                f"/api/v1/admin/users/{admin_id}/role",
                {"account_type": "applicant"},
            ),
            (
                "post",
                f"/api/v1/admin/users/{admin_id}/password-reset",
                {"new_password": NEW_PASSWORD},
            ),
            ("delete", f"/api/v1/admin/users/{admin_id}", None),
        ):
            response = admin_client.request(
                method.upper(),
                path,
                json=payload,
            )
            assert response.status_code == 409, response.text
            assert response.json()["error"]["code"] == "self_administration_forbidden"

        deleted = admin_client.delete(f"/api/v1/admin/users/{applicant['id']}")
        assert deleted.status_code == 204, deleted.text
        deleted_login = applicant_client.post(
            "/api/v1/auth/login",
            json={"email": "managed@example.com", "password": NEW_PASSWORD},
        )
        assert deleted_login.status_code == 401

        for method, path, payload in (
            (
                "patch",
                f"/api/v1/admin/users/{applicant['id']}/status",
                {"status": "active"},
            ),
            (
                "patch",
                f"/api/v1/admin/users/{applicant['id']}/role",
                {"account_type": "applicant"},
            ),
            (
                "post",
                f"/api/v1/admin/users/{applicant['id']}/password-reset",
                {"new_password": USER_PASSWORD},
            ),
        ):
            response = admin_client.request(method.upper(), path, json=payload)
            assert response.status_code == 409, response.text
            assert response.json()["error"]["code"] == "account_deleted"

        missing = admin_client.patch(
            "/api/v1/admin/users/00000000-0000-4000-8000-000000000099/status",
            json={"status": "disabled"},
        )
        assert missing.status_code == 404, missing.text
        assert missing.json()["error"]["code"] == "user_not_found"

        with_deleted = admin_client.get(
            "/api/v1/admin/users",
            params={"search": "managed@example.com", "include_deleted": True},
        )
        assert with_deleted.status_code == 200, with_deleted.text
        assert with_deleted.json()["users"][0]["deleted_at"] is not None

    with pytest.raises(SystemExit) as duplicate:
        _create_admin(monkeypatch, app_url)
    assert duplicate.value.code == 1


def test_administrator_password_reset_clears_login_lockout(
    app: FastAPI,
    admin: psycopg.Connection,
    database_urls: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_url, _ = database_urls
    _create_admin(monkeypatch, app_url)

    with TestClient(app, client=("203.0.113.60", 50000)) as applicant_client:
        applicant = _register(applicant_client, "locked@example.com", "锁定用户")

    for index in range(EMAIL_LIMIT):
        with TestClient(app, client=(f"198.51.100.{index + 120}", 50000)) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={
                    "email": "locked@example.com",
                    "password": "wrong" + "-password",
                },
            )
            if index < EMAIL_LIMIT - 1:
                assert response.status_code == 401, response.text
            else:
                assert response.status_code == 429, response.text

    with TestClient(app, client=("198.51.100.130", 50000)) as locked:
        response = locked.post(
            "/api/v1/auth/login",
            json={"email": "locked@example.com", "password": USER_PASSWORD},
        )
        assert response.status_code == 429, response.text

    with TestClient(app, client=("198.51.100.131", 50000)) as admin_client:
        _login(admin_client, ADMIN_EMAIL, ADMIN_PASSWORD)
        reset = admin_client.post(
            f"/api/v1/admin/users/{applicant['id']}/password-reset",
            json={"new_password": NEW_PASSWORD},
        )
        assert reset.status_code == 200, reset.text

    with TestClient(app, client=("198.51.100.132", 50000)) as recovered:
        response = recovered.post(
            "/api/v1/auth/login",
            json={"email": "locked@example.com", "password": NEW_PASSWORD},
        )
        assert response.status_code == 200, response.text


def test_administrator_cannot_read_another_users_private_data(
    app: FastAPI,
    database_urls: tuple[str, str],
    login: Callable[..., None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_url, _ = database_urls
    _create_admin(monkeypatch, app_url)

    with (
        TestClient(app) as applicant_client,
        TestClient(app) as admin_client,
    ):
        _register(applicant_client, "private@example.com", "私有用户")
        matter = applicant_client.post(
            "/api/v1/matters",
            json={
                "goal": "私有事项",
                "type_code": "pre_recommend",
                "scope_year": 2027,
            },
        )
        assert matter.status_code == 201, matter.text
        matter_id = matter.json()["matter"]["id"]

        _login(admin_client, ADMIN_EMAIL, ADMIN_PASSWORD)
        assert admin_client.get("/api/v1/matters").json()["matters"] == []
        hidden = admin_client.get(f"/api/v1/matters/{matter_id}")
        assert hidden.status_code == 404
        assert hidden.json()["error"]["code"] == "matter_not_found"
        users = admin_client.get(
            "/api/v1/admin/users",
            params={"search": "private@example.com"},
        )
        assert users.status_code == 200, users.text
        assert users.json()["total"] == 1


def test_anonymous_requests_are_rejected(app: FastAPI) -> None:
    with TestClient(app) as anonymous:
        for path in ("/api/v1/matters", "/api/v1/auth/me"):
            response = anonymous.get(path)
            assert response.status_code == 401, response.text
            assert response.json()["error"]["code"] == "authentication_required"

        anonymous.cookies.set("offerpilot_session", "not-a-real-token")
        invalid = anonymous.get("/api/v1/matters")
        assert invalid.status_code == 401
        assert invalid.json()["error"]["code"] == "authentication_required"

        anonymous_update = anonymous.patch(
            "/api/v1/auth/me",
            json={"display_name": "匿名用户"},
        )
        assert anonymous_update.status_code == 401
        assert anonymous_update.json()["error"]["code"] == "authentication_required"

        health = anonymous.get("/healthz")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}


def _register(
    client: TestClient,
    email: str,
    display_name: str,
) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "display_name": display_name,
            "password": USER_PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]


def _login(client: TestClient, email: str, password: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text


def _create_admin(monkeypatch: pytest.MonkeyPatch, app_url: str) -> None:
    monkeypatch.setenv("OFFERPILOT_DATABASE_URL", app_url)
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, ADMIN_PASSWORD)
    admin_cli_main(
        [
            "create",
            "--email",
            ADMIN_EMAIL,
            "--display-name",
            ADMIN_DISPLAY_NAME,
        ]
    )


def _latest_session(
    admin: psycopg.Connection,
    email: str,
    *,
    remember: bool,
) -> tuple[bool, timedelta]:
    row = admin.execute(
        """
        SELECT s.remember, s.expires_at - s.created_at
        FROM core.user_session s
        JOIN core.app_user u ON u.id = s.user_id
        WHERE u.email = %s
          AND s.remember = %s
          AND s.revoked_at IS NULL
        ORDER BY s.created_at DESC, s.id DESC
        LIMIT 1
        """,
        (email, remember),
    ).fetchone()
    assert row is not None
    return row[0], row[1]


def _current_user_id(client: TestClient) -> UUID:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200, response.text
    return UUID(response.json()["user"]["id"])
