"""Application configuration for the OfferPilot business API."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings for the business API."""

    database_url: str
    api_prefix: str = "/api/v1"
    timezone: str = "Asia/Shanghai"
    model_provider: str = "OpenAI 兼容模型服务"
    model_name: str = ""
    model_api_url: str = ""
    model_api_key: str = ""
    model_timeout_seconds: float = 180.0
    session_ttl_seconds: int = 43_200
    remember_session_ttl_seconds: int = 2_592_000
    cookie_secure: bool = False
    login_ip_window_seconds: int = 300
    login_ip_limit: int = 60
    login_email_window_seconds: int = 900
    login_email_limit: int = 5
    login_lock_seconds: int = 900
    config_file: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        database_url = os.environ.get("OFFERPILOT_DATABASE_URL") or os.environ.get(
            "DATABASE_URL"
        )
        if not database_url:
            raise RuntimeError("OFFERPILOT_DATABASE_URL or DATABASE_URL must be set")
        return cls(
            database_url=database_url,
            timezone=os.environ.get("OFFERPILOT_TIMEZONE", "Asia/Shanghai"),
            model_provider=os.environ.get(
                "OFFERPILOT_MODEL_PROVIDER", "OpenAI 兼容模型服务"
            ),
            model_name=os.environ.get("OFFERPILOT_MODEL_NAME", ""),
            model_api_url=os.environ.get("OFFERPILOT_MODEL_API_URL", ""),
            model_api_key=os.environ.get("OFFERPILOT_MODEL_API_KEY", ""),
            model_timeout_seconds=_positive_float_env(
                "OFFERPILOT_MODEL_TIMEOUT_SECONDS", 180.0
            ),
            session_ttl_seconds=_int_env("OFFERPILOT_SESSION_TTL_SECONDS", 43_200),
            remember_session_ttl_seconds=_int_env(
                "OFFERPILOT_REMEMBER_SESSION_TTL_SECONDS", 2_592_000
            ),
            cookie_secure=_bool_env("OFFERPILOT_COOKIE_SECURE", False),
            login_ip_window_seconds=_int_env("OFFERPILOT_LOGIN_IP_WINDOW_SECONDS", 300),
            login_ip_limit=_non_negative_int_env("OFFERPILOT_LOGIN_IP_LIMIT", 60),
            login_email_window_seconds=_int_env(
                "OFFERPILOT_LOGIN_EMAIL_WINDOW_SECONDS", 900
            ),
            login_email_limit=_non_negative_int_env("OFFERPILOT_LOGIN_EMAIL_LIMIT", 5),
            login_lock_seconds=_int_env("OFFERPILOT_LOGIN_LOCK_SECONDS", 900),
            config_file=_optional_str_env("OFFERPILOT_CONFIG_FILE"),
        )


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = int(raw.strip())
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


def _non_negative_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = int(raw.strip())
    if value < 0:
        raise RuntimeError(f"{name} must be a non-negative integer")
    return value


def _positive_float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip())
    except ValueError:
        raise RuntimeError(f"{name} must be a number") from None
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive number")
    return value


def _optional_str_env(name: str) -> str | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    return raw.strip()


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean")
