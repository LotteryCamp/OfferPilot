"""Tests for the hot-reloadable runtime configuration file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from backend.config import Settings
from backend.runtime_config import (
    ConfigFileError,
    ConfigFileNotConfigured,
    RuntimeConfig,
)


def _base(**overrides: Any) -> Settings:
    return Settings(database_url="postgresql://unused", **overrides)


def test_file_overrides_environment(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "model:\n"
        "  name: file-model\n"
        "  timeout_seconds: 240\n"
        "auth:\n"
        "  login_email_limit: 3\n"
        "  cookie_secure: true\n"
        "timezone: Asia/Shanghai\n",
        encoding="utf-8",
    )
    config = RuntimeConfig(
        _base(
            model_name="env-model",
            model_timeout_seconds=180.0,
            login_email_limit=5,
            timezone="UTC",
        ),
        path,
    )

    settings = config.current()
    assert settings.model_name == "file-model"
    assert settings.model_timeout_seconds == 240.0
    assert settings.login_email_limit == 3
    assert settings.cookie_secure is True
    assert settings.timezone == "Asia/Shanghai"
    assert settings.model_provider == "OpenAI 兼容模型服务"


def test_missing_file_uses_environment_settings(tmp_path: Path) -> None:
    path = tmp_path / "missing.yaml"
    base = _base(model_name="env-model")

    config = RuntimeConfig(base, path)

    assert config.current() is base
    assert config.writable is True


def test_runtime_config_without_file_is_not_writable() -> None:
    config = RuntimeConfig(_base())

    assert config.writable is False
    with pytest.raises(ConfigFileNotConfigured):
        config.update({"timezone": "UTC"})


@pytest.mark.parametrize(
    ("content", "path"),
    [
        ("database_url: postgresql://elsewhere\n", "database_url"),
        ("host: 0.0.0.0\n", "host"),
        ("model:\n  timeout_seconds: 0\n", "model.timeout_seconds"),
        ("auth:\n  login_ip_limit: -1\n", "auth.login_ip_limit"),
        ("timezone: Mars/Base\n", "timezone"),
    ],
)
def test_invalid_startup_configuration(tmp_path: Path, content: str, path: str) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(content, encoding="utf-8")

    with pytest.raises(ConfigFileError) as error:
        RuntimeConfig(_base(), config_path)

    assert any(issue["path"] == path for issue in error.value.issues)


def test_invalid_yaml_fails_startup(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("model: [\n", encoding="utf-8")

    with pytest.raises(ConfigFileError) as error:
        RuntimeConfig(_base(), config_path)

    assert error.value.issues[0]["code"] == "yaml_error"


def test_file_change_is_reloaded(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("model:\n  name: first\n", encoding="utf-8")
    config = RuntimeConfig(_base(), config_path, refresh_interval_seconds=0)

    assert config.current().model_name == "first"

    config_path.write_text("model:\n  name: second-name\n", encoding="utf-8")
    config.refresh_if_changed()

    assert config.current().model_name == "second-name"


def test_invalid_file_change_keeps_previous_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("model:\n  name: valid\n", encoding="utf-8")
    config = RuntimeConfig(_base(), config_path, refresh_interval_seconds=0)

    config_path.write_text("model:\n  timeout_seconds: 0\n", encoding="utf-8")
    config.refresh_if_changed()

    assert config.current().model_name == "valid"


def test_removed_file_keeps_previous_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("model:\n  name: kept\n", encoding="utf-8")
    config = RuntimeConfig(_base(), config_path, refresh_interval_seconds=0)

    config_path.unlink()
    config.refresh_if_changed()

    assert config.current().model_name == "kept"


def test_update_writes_file_and_applies_immediately(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "model:\n  name: old-model\n  api_key: file-secret\n",
        encoding="utf-8",
    )
    config = RuntimeConfig(
        _base(model_name="env-model", model_api_key="env-secret"),
        config_path,
    )

    config.update(
        {
            "model": {"name": "page-model", "api_key": ""},
            "auth": {"cookie_secure": True},
            "timezone": "Asia/Shanghai",
        }
    )

    settings = config.current()
    assert settings.model_name == "page-model"
    assert settings.model_api_key == "env-secret"
    assert settings.cookie_secure is True
    assert settings.timezone == "Asia/Shanghai"

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw["model"]["name"] == "page-model"
    assert "api_key" not in raw["model"]
    assert raw["auth"]["cookie_secure"] is True
    assert raw["timezone"] == "Asia/Shanghai"


def test_update_rejects_unsupported_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("", encoding="utf-8")
    config = RuntimeConfig(_base(), config_path)

    with pytest.raises(ConfigFileError) as error:
        config.update({"database_url": "postgresql://elsewhere"})

    assert error.value.issues[0]["path"] == "database_url"


def test_update_rejects_invalid_values(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("", encoding="utf-8")
    config = RuntimeConfig(_base(), config_path)

    with pytest.raises(ConfigFileError) as error:
        config.update({"auth": {"login_lock_seconds": 0}})

    assert error.value.issues[0]["path"] == "auth.login_lock_seconds"
    assert config.current().login_lock_seconds == 900
    assert config_path.read_text(encoding="utf-8") == ""
