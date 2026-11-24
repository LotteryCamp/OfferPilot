"""Tests for environment-backed settings."""

from __future__ import annotations

import pytest

from backend.config import Settings

THROTTLE_ENV = (
    "OFFERPILOT_LOGIN_IP_WINDOW_SECONDS",
    "OFFERPILOT_LOGIN_IP_LIMIT",
    "OFFERPILOT_LOGIN_EMAIL_WINDOW_SECONDS",
    "OFFERPILOT_LOGIN_EMAIL_LIMIT",
    "OFFERPILOT_LOGIN_LOCK_SECONDS",
)


def test_login_throttle_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _prepare_env(monkeypatch)
    settings = Settings.from_env()
    assert settings.login_ip_window_seconds == 300
    assert settings.login_ip_limit == 60
    assert settings.login_email_window_seconds == 900
    assert settings.login_email_limit == 5
    assert settings.login_lock_seconds == 900


def test_login_throttle_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_env(monkeypatch)
    monkeypatch.setenv("OFFERPILOT_LOGIN_IP_WINDOW_SECONDS", "120")
    monkeypatch.setenv("OFFERPILOT_LOGIN_IP_LIMIT", "0")
    monkeypatch.setenv("OFFERPILOT_LOGIN_EMAIL_WINDOW_SECONDS", "600")
    monkeypatch.setenv("OFFERPILOT_LOGIN_EMAIL_LIMIT", "3")
    monkeypatch.setenv("OFFERPILOT_LOGIN_LOCK_SECONDS", "60")
    settings = Settings.from_env()
    assert settings.login_ip_window_seconds == 120
    assert settings.login_ip_limit == 0
    assert settings.login_email_window_seconds == 600
    assert settings.login_email_limit == 3
    assert settings.login_lock_seconds == 60


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("OFFERPILOT_LOGIN_IP_WINDOW_SECONDS", "0", "must be a positive integer"),
        ("OFFERPILOT_LOGIN_IP_LIMIT", "-1", "must be a non-negative integer"),
        ("OFFERPILOT_LOGIN_EMAIL_WINDOW_SECONDS", "0", "must be a positive integer"),
        ("OFFERPILOT_LOGIN_EMAIL_LIMIT", "-1", "must be a non-negative integer"),
        ("OFFERPILOT_LOGIN_LOCK_SECONDS", "0", "must be a positive integer"),
    ],
)
def test_login_throttle_validation(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    message: str,
) -> None:
    _prepare_env(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match=message):
        Settings.from_env()


def _prepare_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFFERPILOT_DATABASE_URL", "postgresql://unused")
    for name in THROTTLE_ENV:
        monkeypatch.delenv(name, raising=False)
