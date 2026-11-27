"""Integration tests for administrator runtime configuration endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config import MAX_DURATION_SECONDS, Settings
from backend.main import create_app
from backend.security import hash_password

ADMIN_EMAIL = "config-admin@example.com"
ADMIN_PASSWORD = "config-admin" + str(2026) + "!"


def test_applicant_cannot_manage_runtime_settings(client: TestClient) -> None:
    read = client.get("/api/v1/admin/settings")
    assert read.status_code == 403, read.text
    assert read.json()["error"]["code"] == "admin_required"

    update = client.patch("/api/v1/admin/settings", json={"timezone": "UTC"})
    assert update.status_code == 403, update.text
    assert update.json()["error"]["code"] == "admin_required"


def test_admin_reads_and_updates_runtime_settings(
    database_urls: tuple[str, str],
    admin: psycopg.Connection,
    clock: Any,
    tmp_path: Path,
) -> None:
    app_url, _ = database_urls
    config_path = tmp_path / "config.yaml"
    config_path.write_text("model:\n  name: file-model\n", encoding="utf-8")
    app = _build_app(app_url, clock, config_path)
    _create_admin(admin)

    with TestClient(app) as client:
        _login(client)

        payload = client.get("/api/v1/admin/settings")
        assert payload.status_code == 200, payload.text
        data = payload.json()
        assert data["config_file"] == str(config_path)
        assert data["writable"] is True
        assert data["settings"]["model"]["name"] == "file-model"
        assert data["settings"]["model"]["provider"] == "环境服务商"
        assert data["settings"]["model"]["api_key_configured"] is True
        assert "api_key" not in data["settings"]["model"]

        updated = client.patch(
            "/api/v1/admin/settings",
            json={
                "model": {
                    "name": "page-model",
                    "provider": "页面服务商",
                    "timeout_seconds": 240,
                },
                "auth": {"login_email_limit": 9},
                "timezone": "Asia/Shanghai",
            },
        )
        assert updated.status_code == 200, updated.text
        settings = updated.json()["settings"]
        assert settings["model"]["name"] == "page-model"
        assert settings["model"]["provider"] == "页面服务商"
        assert settings["model"]["timeout_seconds"] == 240.0
        assert settings["auth"]["login_email_limit"] == 9
        assert settings["timezone"] == "Asia/Shanghai"

        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert raw["model"]["name"] == "page-model"
        assert raw["model"]["provider"] == "页面服务商"
        assert raw["auth"]["login_email_limit"] == 9
        assert raw["timezone"] == "Asia/Shanghai"

        disclosure = client.get("/api/v1/model-transfer-consent")
        assert disclosure.status_code == 200, disclosure.text
        assert disclosure.json()["disclosure"]["provider"] == "页面服务商"
        assert disclosure.json()["disclosure"]["model"] == "page-model"

        with_key = client.patch(
            "/api/v1/admin/settings",
            json={"model": {"api_key": "page-secret"}},
        )
        assert with_key.status_code == 200, with_key.text
        assert with_key.json()["settings"]["model"]["api_key_configured"] is True
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert raw["model"]["api_key"] == "page-secret"
        assert "page-secret" not in with_key.text

        cleared = client.patch(
            "/api/v1/admin/settings",
            json={"model": {"api_key": ""}},
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["settings"]["model"]["api_key_configured"] is True
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert "api_key" not in raw["model"]


def test_clearing_file_key_without_environment_key_reports_unconfigured(
    database_urls: tuple[str, str],
    admin: psycopg.Connection,
    clock: Any,
    tmp_path: Path,
) -> None:
    app_url, _ = database_urls
    config_path = tmp_path / "config.yaml"
    config_path.write_text("model:\n  api_key: file-secret\n", encoding="utf-8")
    app = _build_app(app_url, clock, config_path, model_api_key="")
    _create_admin(admin)

    with TestClient(app) as client:
        _login(client)
        before = client.get("/api/v1/admin/settings")
        assert before.json()["settings"]["model"]["api_key_configured"] is True

        cleared = client.patch(
            "/api/v1/admin/settings",
            json={"model": {"api_key": ""}},
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["settings"]["model"]["api_key_configured"] is False


def test_whitespace_environment_key_reports_unconfigured(
    database_urls: tuple[str, str],
    admin: psycopg.Connection,
    clock: Any,
    tmp_path: Path,
) -> None:
    app_url, _ = database_urls
    config_path = tmp_path / "config.yaml"
    config_path.write_text("model:\n  name: file-model\n", encoding="utf-8")
    app = _build_app(app_url, clock, config_path, model_api_key="   ")
    _create_admin(admin)

    with TestClient(app) as client:
        _login(client)
        payload = client.get("/api/v1/admin/settings")

        assert payload.status_code == 200, payload.text
        assert payload.json()["settings"]["model"]["api_key_configured"] is False


def test_update_requires_config_file(
    database_urls: tuple[str, str],
    admin: psycopg.Connection,
    clock: Any,
) -> None:
    app_url, _ = database_urls
    app = _build_app(app_url, clock, None)
    _create_admin(admin)

    with TestClient(app) as client:
        _login(client)

        payload = client.get("/api/v1/admin/settings")
        assert payload.status_code == 200, payload.text
        assert payload.json()["config_file"] is None
        assert payload.json()["writable"] is False
        assert payload.json()["settings"]["model"]["name"] == "env-model"

        update = client.patch(
            "/api/v1/admin/settings",
            json={"timezone": "Asia/Shanghai"},
        )
        assert update.status_code == 409, update.text
        assert update.json()["error"]["code"] == "config_file_not_configured"


def test_first_update_creates_missing_file(
    database_urls: tuple[str, str],
    admin: psycopg.Connection,
    clock: Any,
    tmp_path: Path,
) -> None:
    app_url, _ = database_urls
    config_path = tmp_path / "config.yaml"
    app = _build_app(app_url, clock, config_path)
    _create_admin(admin)

    with TestClient(app) as client:
        _login(client)
        assert config_path.exists() is False

        updated = client.patch(
            "/api/v1/admin/settings",
            json={"model": {"name": "created-model"}},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["settings"]["model"]["name"] == "created-model"
        assert config_path.exists()
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert raw["model"]["name"] == "created-model"


@pytest.mark.parametrize(
    ("body", "path"),
    [
        ({"model": {"timeout_seconds": 0}}, "body.model.timeout_seconds"),
        ({"auth": {"login_ip_limit": -1}}, "body.auth.login_ip_limit"),
        (
            {"auth": {"session_ttl_seconds": MAX_DURATION_SECONDS + 1}},
            "body.auth.session_ttl_seconds",
        ),
        ({"model": {"api_key": "   "}}, "model.api_key"),
        ({"timezone": "Mars/Base"}, "timezone"),
        ({"database_url": "postgresql://elsewhere"}, "body.database_url"),
    ],
)
def test_invalid_update_is_rejected_without_writing(
    database_urls: tuple[str, str],
    admin: psycopg.Connection,
    clock: Any,
    tmp_path: Path,
    body: dict[str, Any],
    path: str,
) -> None:
    app_url, _ = database_urls
    config_path = tmp_path / "config.yaml"
    original = "model:\n  name: stable-model\n"
    config_path.write_text(original, encoding="utf-8")
    app = _build_app(app_url, clock, config_path)
    _create_admin(admin)

    with TestClient(app) as client:
        _login(client)

        response = client.patch("/api/v1/admin/settings", json=body)
        assert response.status_code == 422, response.text
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert any(issue["path"] == path for issue in error["details"]["issues"])

        assert config_path.read_text(encoding="utf-8") == original
        assert (
            client.get("/api/v1/admin/settings").json()["settings"]["model"]["name"]
            == "stable-model"
        )


def test_external_file_change_is_reloaded(
    database_urls: tuple[str, str],
    admin: psycopg.Connection,
    clock: Any,
    tmp_path: Path,
) -> None:
    app_url, _ = database_urls
    config_path = tmp_path / "config.yaml"
    config_path.write_text("model:\n  provider: 初始服务商\n", encoding="utf-8")
    app = _build_app(app_url, clock, config_path)
    app.state.runtime_config.refresh_interval_seconds = 0
    _create_admin(admin)

    with TestClient(app) as client:
        _login(client)

        before = client.get("/api/v1/model-transfer-consent")
        assert before.status_code == 200, before.text
        assert before.json()["disclosure"]["provider"] == "初始服务商"

        config_path.write_text(
            "model:\n  provider: 外部修改服务商\n",
            encoding="utf-8",
        )
        after = client.get("/api/v1/model-transfer-consent")
        assert after.json()["disclosure"]["provider"] == "外部修改服务商"

        config_path.write_text("model:\n  timeout_seconds: 0\n", encoding="utf-8")
        kept = client.get("/api/v1/model-transfer-consent")
        assert kept.json()["disclosure"]["provider"] == "外部修改服务商"


def _build_app(
    database_url: str,
    clock: Any,
    config_path: Path | None,
    *,
    model_api_key: str = "env-key",
) -> FastAPI:
    settings = Settings(
        database_url=database_url,
        timezone="UTC",
        model_provider="环境服务商",
        model_name="env-model",
        model_api_url="https://env.example/v1",
        model_api_key=model_api_key,
        config_file=str(config_path) if config_path is not None else None,
    )
    return create_app(settings, clock=clock)


def _create_admin(admin: psycopg.Connection) -> None:
    user_id = uuid4()
    workspace_id = uuid4()
    admin.execute(
        """
        INSERT INTO core.app_user
            (id, email, display_name, password_hash, account_type, status)
        VALUES (%s, %s, '配置管理员', %s, 'admin', 'active')
        """,
        (user_id, ADMIN_EMAIL, hash_password(ADMIN_PASSWORD)),
    )
    admin.execute(
        "INSERT INTO core.workspace (id, owner_id) VALUES (%s, %s)",
        (workspace_id, user_id),
    )


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
