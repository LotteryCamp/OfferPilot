"""Check the effective model configuration without a network request."""

import math
import sys
from pathlib import Path

from backend.config import Settings
from backend.runtime_config import RuntimeConfig


def main() -> int:
    """Report configuration problems without printing configured credentials."""
    try:
        base = Settings.from_model_env()
        path = Path(base.config_file) if base.config_file else None
        settings = RuntimeConfig(base, path).current()
    except (OSError, RuntimeError, ValueError):
        print(
            "CONFIG_ERROR: 无法加载配置，请检查环境变量和运行时 YAML 文件。",
            file=sys.stderr,
        )
        return 1

    problems = [
        f"缺少 {name}"
        for name, value in (
            ("OFFERPILOT_MODEL_API_URL", settings.model_api_url),
            ("OFFERPILOT_MODEL_NAME", settings.model_name),
            ("OFFERPILOT_MODEL_API_KEY", settings.model_api_key),
        )
        if not value.strip()
    ]

    timeout = settings.model_timeout_seconds
    if not math.isfinite(timeout) or timeout <= 0:
        problems.append("模型超时须为有限且大于 0 的秒数")

    if problems:
        for problem in problems:
            print(f"CONFIG_ERROR: {problem}", file=sys.stderr)
        return 1

    print(f"模型配置检查通过：超时 {timeout:g} 秒。未发出模型请求。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
