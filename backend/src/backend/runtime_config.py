"""Hot-reloadable runtime configuration backed by an optional YAML file."""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from backend.config import Settings

logger = logging.getLogger(__name__)


class ConfigFileError(RuntimeError):
    """Raised when the runtime configuration file is unreadable or invalid."""

    def __init__(
        self, message: str, *, issues: list[dict[str, str]] | None = None
    ) -> None:
        super().__init__(message)
        self.issues = issues or []


class ConfigFileNotConfigured(RuntimeError):
    """Raised when a runtime configuration change requires a configured file."""


class _ConfigSection(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelFileSettings(_ConfigSection):
    provider: str | None = None
    name: str | None = None
    api_url: str | None = None
    api_key: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)


class AuthFileSettings(_ConfigSection):
    session_ttl_seconds: int | None = Field(default=None, gt=0)
    remember_session_ttl_seconds: int | None = Field(default=None, gt=0)
    cookie_secure: bool | None = None
    login_ip_window_seconds: int | None = Field(default=None, gt=0)
    login_ip_limit: int | None = Field(default=None, ge=0)
    login_email_window_seconds: int | None = Field(default=None, gt=0)
    login_email_limit: int | None = Field(default=None, ge=0)
    login_lock_seconds: int | None = Field(default=None, gt=0)


class ConfigFileSettings(_ConfigSection):
    model: ModelFileSettings | None = None
    auth: AuthFileSettings | None = None
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"未知时区：{value}") from exc
        return value


class RuntimeConfig:
    """Own the current immutable settings snapshot and reload it on file change."""

    def __init__(
        self,
        base: Settings,
        path: Path | None = None,
        *,
        refresh_interval_seconds: float = 1.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.path = path
        self.refresh_interval_seconds = refresh_interval_seconds
        self._base = base
        self._settings = base
        self._monotonic = monotonic
        self._lock = threading.RLock()
        self._signature: tuple[int, int] | None = None
        self._last_check = monotonic()
        self._last_error_signature: tuple[int, int] | None = None
        self._missing_logged = False

        if path is not None:
            if path.exists():
                try:
                    self._settings = _apply_overrides(base, _load_file(path))
                except OSError as exc:
                    raise ConfigFileError(f"无法读取运行配置文件：{exc}") from exc
                self._signature = _signature(path)
            else:
                logger.warning(
                    "运行配置文件不存在，使用环境变量配置：%s",
                    path,
                )
                self._missing_logged = True

    def current(self) -> Settings:
        """Return the active settings snapshot."""
        return self._settings

    @property
    def writable(self) -> bool:
        """Report whether the runtime configuration file can be written."""
        if self.path is None:
            return False
        target = self.path if self.path.exists() else self.path.parent
        return os.access(target, os.W_OK)

    def refresh_if_changed(self, *, force: bool = False) -> None:
        """Reload the file when its modification time or size changed."""
        if self.path is None:
            return
        with self._lock:
            now = self._monotonic()
            if not force and now - self._last_check < self.refresh_interval_seconds:
                return
            self._last_check = now
            signature = _signature(self.path)
            if signature is None:
                if not self._missing_logged:
                    logger.error("运行配置文件不可读取，保持当前配置：%s", self.path)
                    self._missing_logged = True
                return
            if signature == self._signature:
                return
            try:
                new_settings = _apply_overrides(self._base, _load_file(self.path))
            except (ConfigFileError, OSError) as exc:
                if signature != self._last_error_signature:
                    logger.error(
                        "运行配置文件校验失败，保持上一份有效配置：%s",
                        exc,
                    )
                    self._last_error_signature = signature
                self._signature = signature
                return
            self._settings = new_settings
            self._signature = signature
            self._last_error_signature = None
            self._missing_logged = False
            logger.info("运行配置已重新加载：%s", self.path)

    def update(self, patch: Mapping[str, Any]) -> Settings:
        """Merge a partial update into the file, then activate it immediately."""
        with self._lock:
            if self.path is None:
                raise ConfigFileNotConfigured("未配置运行配置文件")
            raw = _read_mapping(self.path) if self.path.exists() else {}
            merged = _apply_patch(raw, patch)
            file_settings = _validate_mapping(merged)
            new_settings = _apply_overrides(self._base, file_settings)
            _write_atomic(self.path, merged)
            self._settings = new_settings
            self._signature = _signature(self.path)
            self._last_error_signature = None
            self._missing_logged = False
            return new_settings


def _signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _read_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigFileError(
            "运行配置文件不是合法的 YAML",
            issues=[{"path": "", "code": "yaml_error", "message": str(exc)}],
        ) from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigFileError(
            "运行配置文件顶层必须是映射",
            issues=[
                {
                    "path": "",
                    "code": "mapping_type",
                    "message": "顶层必须是对象",
                }
            ],
        )
    return data


def _validate_mapping(raw: Mapping[str, Any]) -> ConfigFileSettings:
    try:
        return ConfigFileSettings.model_validate(dict(raw))
    except ValidationError as exc:
        raise ConfigFileError(
            "运行配置文件校验失败",
            issues=_format_issues(exc),
        ) from exc


def _load_file(path: Path) -> ConfigFileSettings:
    return _validate_mapping(_read_mapping(path))


def _format_issues(exc: ValidationError) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for item in exc.errors():
        location = ".".join(str(part) for part in item.get("loc", ()))
        issues.append(
            {
                "path": location,
                "code": str(item.get("type", "validation_error")),
                "message": str(item.get("msg", "字段无效")),
            }
        )
    return issues


def _apply_overrides(base: Settings, file_settings: ConfigFileSettings) -> Settings:
    updates: dict[str, Any] = {}
    if file_settings.timezone is not None:
        updates["timezone"] = file_settings.timezone
    model = file_settings.model
    if model is not None:
        if model.provider is not None:
            updates["model_provider"] = model.provider
        if model.name is not None:
            updates["model_name"] = model.name
        if model.api_url is not None:
            updates["model_api_url"] = model.api_url
        if model.api_key is not None:
            updates["model_api_key"] = model.api_key
        if model.timeout_seconds is not None:
            updates["model_timeout_seconds"] = model.timeout_seconds
    auth = file_settings.auth
    if auth is not None:
        for field in (
            "session_ttl_seconds",
            "remember_session_ttl_seconds",
            "cookie_secure",
            "login_ip_window_seconds",
            "login_ip_limit",
            "login_email_window_seconds",
            "login_email_limit",
            "login_lock_seconds",
        ):
            value = getattr(auth, field)
            if value is not None:
                updates[field] = value
    return replace(base, **updates)


def _apply_patch(raw: dict[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    unknown = set(patch) - {"timezone", "model", "auth"}
    if unknown:
        raise ConfigFileError(
            "不支持的运行配置字段",
            issues=[
                {
                    "path": name,
                    "code": "extra_forbidden",
                    "message": "不支持的字段",
                }
                for name in sorted(unknown)
            ],
        )
    for section in ("model", "auth"):
        values = patch.get(section)
        if not isinstance(values, Mapping):
            continue
        existing = raw.get(section)
        target: dict[str, Any] = existing if isinstance(existing, dict) else {}
        raw[section] = target
        for key, value in values.items():
            if key == "api_key" and value == "":
                target.pop(key, None)
            else:
                target[key] = value
    if "timezone" in patch:
        raw["timezone"] = patch["timezone"]
    return raw


def _write_atomic(path: Path, raw: Mapping[str, Any]) -> None:
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(dict(raw), handle, allow_unicode=True, sort_keys=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
