"""Tests for the local model configuration check."""

from pathlib import Path

import pytest
from backend.model_check import main


@pytest.fixture(autouse=True)
def clean_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "OFFERPILOT_DATABASE_URL",
        "DATABASE_URL",
        "OFFERPILOT_CONFIG_FILE",
        "OFFERPILOT_MODEL_API_URL",
        "OFFERPILOT_MODEL_NAME",
        "OFFERPILOT_MODEL_API_KEY",
        "OFFERPILOT_MODEL_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_missing_model_configuration_is_reported(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main() == 1
    output = capsys.readouterr()

    assert not output.out
    for name in ("API_URL", "NAME", "API_KEY"):
        assert f"CONFIG_ERROR: 缺少 OFFERPILOT_MODEL_{name}" in output.err


def test_environment_configuration_works_without_database(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OFFERPILOT_MODEL_API_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OFFERPILOT_MODEL_NAME", "local-check-model")
    monkeypatch.setenv("OFFERPILOT_MODEL_API_KEY", "env-test-credential")

    assert main() == 0
    output = capsys.readouterr()

    assert "180 秒" in output.out
    assert "未发出模型请求" in output.out
    assert not output.err
    assert "env-test-credential" not in output.out


def test_yaml_completes_configuration_and_overrides_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "model:\n"
        "  api_url: https://example.invalid/v1\n"
        "  name: local-check-model\n"
        "  api_key: yaml-test-credential\n"
        "  timeout_seconds: 12.5\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OFFERPILOT_CONFIG_FILE", str(path))
    monkeypatch.setenv("OFFERPILOT_MODEL_TIMEOUT_SECONDS", "99")

    assert main() == 0
    output = capsys.readouterr()

    assert "12.5 秒" in output.out
    assert not output.err
    assert "yaml-test-credential" not in output.out


@pytest.mark.parametrize("timeout", ["nan", "inf"])
def test_non_finite_timeout_is_rejected(
    timeout: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OFFERPILOT_MODEL_API_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OFFERPILOT_MODEL_NAME", "local-check-model")
    monkeypatch.setenv("OFFERPILOT_MODEL_API_KEY", "env-test-credential")
    monkeypatch.setenv("OFFERPILOT_MODEL_TIMEOUT_SECONDS", timeout)

    assert main() == 1
    output = capsys.readouterr()

    assert not output.out
    assert "CONFIG_ERROR: 模型超时须为有限且大于 0 的秒数" in output.err
    assert "env-test-credential" not in output.err


def test_invalid_yaml_does_not_print_config_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "model:\n  api_key: yaml-test-credential\n  timeout_seconds: [\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OFFERPILOT_CONFIG_FILE", str(path))

    assert main() == 1
    output = capsys.readouterr()

    assert not output.out
    assert "CONFIG_ERROR: 无法加载配置" in output.err
    assert "yaml-test-credential" not in output.err
