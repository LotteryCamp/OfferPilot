"""Runtime configuration administration."""

from __future__ import annotations

import logging
from typing import Any

from backend.errors import ApiError
from backend.runtime_config import (
    ConfigFileError,
    ConfigFileNotConfigured,
    RuntimeConfig,
)
from backend.schemas import AdminSettingsUpdate

logger = logging.getLogger(__name__)


def settings_payload(config: RuntimeConfig) -> dict[str, Any]:
    """Serialize the active settings with secrets withheld."""
    settings = config.current()
    return {
        "config_file": str(config.path) if config.path is not None else None,
        "writable": config.writable,
        "settings": {
            "timezone": settings.timezone,
            "model": {
                "provider": settings.model_provider,
                "name": settings.model_name,
                "api_url": settings.model_api_url,
                "api_key_configured": bool(settings.model_api_key.strip()),
                "timeout_seconds": settings.model_timeout_seconds,
            },
            "auth": {
                "session_ttl_seconds": settings.session_ttl_seconds,
                "remember_session_ttl_seconds": settings.remember_session_ttl_seconds,
                "cookie_secure": settings.cookie_secure,
                "login_ip_window_seconds": settings.login_ip_window_seconds,
                "login_ip_limit": settings.login_ip_limit,
                "login_email_window_seconds": settings.login_email_window_seconds,
                "login_email_limit": settings.login_email_limit,
                "login_lock_seconds": settings.login_lock_seconds,
            },
        },
    }


def update_settings(
    config: RuntimeConfig,
    body: AdminSettingsUpdate,
) -> dict[str, Any]:
    """Apply a partial settings update and return the new payload."""
    patch = body.model_dump(exclude_unset=True, exclude_none=True)
    try:
        config.update(patch)
    except ConfigFileNotConfigured as exc:
        raise ApiError(
            409,
            "config_file_not_configured",
            "未启用运行配置文件",
            next_step="设置 OFFERPILOT_CONFIG_FILE 后重启服务",
        ) from exc
    except ConfigFileError as exc:
        raise ApiError(
            422,
            "validation_error",
            "配置未通过校验",
            next_step="按 issues 修正后重试",
            details={"issues": exc.issues},
        ) from exc
    except OSError as exc:
        logger.warning("运行配置写盘失败：%s", exc)
        raise ApiError(
            500,
            "config_write_failed",
            "运行配置写盘失败",
            next_step="检查配置文件所在目录的权限后重试",
        ) from exc
    return settings_payload(config)
