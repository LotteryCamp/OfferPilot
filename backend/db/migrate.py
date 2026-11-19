"""OfferPilot Alpha 数据库迁移执行器。

用法::

    cd backend
    uv sync
    uv run python db/migrate.py status
    uv run python db/migrate.py migrate
    uv run python db/migrate.py seed
    uv run python db/migrate.py seed --demo

设计约定：

* 迁移文件按文件名排序执行，命名 ``NNNN_snake_case.sql``；只追加，不修改已执行文件。
* 每个文件在独立事务中执行，成功后把版本号与 SHA-256 写入 ``ops.schema_version``。
* 重复执行是幂等的：已记录且校验和一致的文件跳过；校验和不一致直接失败。
* 迁移期间持有会话级 advisory lock，避免两个部署同时执行。
* 种子脚本不写入 schema_version，必须自身幂等（ON CONFLICT）。

依赖由 ``backend/pyproject.toml`` 管理（psycopg）。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import time
from pathlib import Path

try:
    import psycopg
except ImportError:  # pragma: no cover - 运行环境错误
    sys.exit("缺少 psycopg。请在 backend 目录执行 uv sync。")

BASE_DIR = Path(__file__).resolve().parent
MIGRATIONS_DIR = BASE_DIR / "migrations"
SEED_DIR = BASE_DIR / "seed"
LOCK_KEY = "offerpilot:schema_migrations"
MIGRATION_RE = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")

BOOTSTRAP_SQL = """
CREATE SCHEMA IF NOT EXISTS ops;
CREATE TABLE IF NOT EXISTS ops.schema_version (
    version      text PRIMARY KEY,
    checksum     char(64) NOT NULL,
    applied_at   timestamptz NOT NULL DEFAULT now(),
    execution_ms integer NOT NULL DEFAULT 0
);
"""


def sha256(path: Path) -> str:
    """按 LF 归一化后计算校验和，避免 Windows CRLF 检出造成假漂移。"""
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def migration_files(directory: Path) -> list[Path]:
    files = sorted(p for p in directory.glob("*.sql") if p.is_file())
    seen: dict[str, Path] = {}
    for path in files:
        match = MIGRATION_RE.match(path.name)
        if not match:
            raise SystemExit(f"迁移文件名不符合 NNNN_snake_case.sql：{path.name}")
        version = match.group("version")
        if version in seen:
            raise SystemExit(f"迁移版本号重复：{seen[version].name} 与 {path.name}")
        seen[version] = path

    versions = [int(MIGRATION_RE.match(path.name).group("version")) for path in files]
    for expected, actual in enumerate(versions, start=1):
        if actual != expected:
            raise SystemExit(f"迁移编号不连续：期望 {expected:04d}，实际 {actual:04d}")
    return files


def schema_version_exists(conn: psycopg.Connection) -> bool:
    return bool(
        conn.execute("SELECT to_regclass('ops.schema_version') IS NOT NULL").fetchone()[
            0
        ]
    )


def applied_versions(conn: psycopg.Connection) -> dict[str, tuple[str, object]]:
    rows = conn.execute(
        "SELECT version, checksum, applied_at FROM ops.schema_version ORDER BY version"
    ).fetchall()
    return {row[0]: (row[1].strip(), row[2]) for row in rows}


def ensure_bootstrap(conn: psycopg.Connection) -> None:
    conn.execute(BOOTSTRAP_SQL)
    conn.commit()


def cmd_status(conn: psycopg.Connection, directory: Path) -> int:
    files = migration_files(directory)
    applied = applied_versions(conn) if schema_version_exists(conn) else {}
    print(f"数据库：{conn.info.dbname} @ {conn.info.host}:{conn.info.port}")
    print(f"迁移目录：{directory}")
    print(f"{'版本':<8}{'状态':<12}{'校验和':<14}文件名")
    drifted = False
    for path in files:
        version = MIGRATION_RE.match(path.name).group("version")
        digest = sha256(path)
        if version not in applied:
            state = "PENDING"
        elif applied[version][0] != digest:
            state = "CHECKSUM-DIFF"
            drifted = True
        else:
            state = "APPLIED"
        print(f"{version:<8}{state:<12}{digest[:12]:<14}{path.name}")
    unknown = sorted(
        set(applied) - {MIGRATION_RE.match(p.name).group("version") for p in files}
    )
    for version in unknown:
        drifted = True
        print(
            f"{version:<8}{'MISSING-FILE':<12}{applied[version][0][:12]:<14}(数据库有记录)"
        )
    return 1 if drifted else 0


def cmd_migrate(conn: psycopg.Connection, directory: Path, dry_run: bool) -> int:
    files = migration_files(directory)
    if not files:
        print(f"错误：迁移目录为空或不存在：{directory}", file=sys.stderr)
        return 2

    known = {MIGRATION_RE.match(path.name).group("version") for path in files}

    if dry_run:
        applied = applied_versions(conn) if schema_version_exists(conn) else {}
        unknown = sorted(set(applied) - known)
        if unknown:
            print(
                "错误：数据库已应用当前目录中不存在的迁移版本：" + ", ".join(unknown),
                file=sys.stderr,
            )
            return 2
        pending = 0
        for path in files:
            version = MIGRATION_RE.match(path.name).group("version")
            if version in applied:
                continue
            pending += 1
            print(f"待执行 {path.name}")
        print(f"预演完成：{pending} 个迁移待执行。")
        return 0

    ensure_bootstrap(conn)
    conn.execute("SELECT pg_advisory_lock(hashtext(%s))", (LOCK_KEY,))
    conn.commit()
    try:
        applied = applied_versions(conn)
        unknown = sorted(set(applied) - known)
        if unknown:
            print(
                "错误：数据库已应用当前目录中不存在的迁移版本："
                + ", ".join(unknown)
                + "\n请先检出与数据库匹配的代码版本，或补充缺失的迁移文件。",
                file=sys.stderr,
            )
            return 2

        pending = 0
        for path in files:
            version = MIGRATION_RE.match(path.name).group("version")
            digest = sha256(path)
            if version in applied:
                if applied[version][0] != digest:
                    print(
                        f"错误：{path.name} 已执行，但校验和与记录不一致。"
                        f"\n  数据库：{applied[version][0]}"
                        f"\n  文件：  {digest}"
                        "\n已执行的迁移不可修改；请新增一个迁移文件。",
                        file=sys.stderr,
                    )
                    return 2
                print(f"跳过 {path.name}（已应用）")
                continue

            pending += 1
            print(f"执行 {path.name} ...", end="", flush=True)
            started = time.perf_counter()
            try:
                with conn.transaction():
                    conn.execute(path.read_text(encoding="utf-8"))
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    conn.execute(
                        "INSERT INTO ops.schema_version (version, checksum, execution_ms)"
                        " VALUES (%s, %s, %s)",
                        (version, digest, elapsed_ms),
                    )
            except Exception:
                print(" 失败")
                raise
            print(f" 完成（{elapsed_ms} ms）")

        if pending == 0:
            print("数据库已是最新，无迁移需要执行。")
        else:
            print(f"迁移完成：本次执行 {pending} 个。")
        return 0
    finally:
        conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (LOCK_KEY,))
        conn.commit()


def cmd_seed(conn: psycopg.Connection, with_demo: bool) -> int:
    scripts = [SEED_DIR / "0001_reference.sql"]
    if with_demo:
        scripts.append(SEED_DIR / "demo.sql")
    for script in scripts:
        if not script.exists():
            print(f"缺少种子脚本：{script}", file=sys.stderr)
            return 2
        print(f"种子 {script.name} ...", end="", flush=True)
        with conn.transaction():
            conn.execute(script.read_text(encoding="utf-8"))
        print(" 完成")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OfferPilot Alpha 数据库迁移执行器")
    parser.add_argument(
        "--dsn",
        default=os.environ.get("DATABASE_URL"),
        help="PostgreSQL 连接串，默认读取 DATABASE_URL",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=MIGRATIONS_DIR,
        help="迁移目录（默认 backend/db/migrations）",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="执行所有未应用的迁移").add_argument(
        "--dry-run", action="store_true", help="只列出待执行迁移"
    )
    sub.add_parser("status", help="显示迁移状态")
    seed = sub.add_parser("seed", help="写入参考数据")
    seed.add_argument("--demo", action="store_true", help="额外写入演示数据")

    args = parser.parse_args(argv)
    if not args.dsn:
        parser.error("未提供 --dsn，且环境变量 DATABASE_URL 为空")

    with psycopg.connect(args.dsn) as conn:
        conn.execute("SET client_min_messages = warning")
        conn.commit()
        if args.command == "status":
            return cmd_status(conn, args.dir)
        if args.command == "migrate":
            return cmd_migrate(conn, args.dir, args.dry_run)
        if args.command == "seed":
            return cmd_seed(conn, args.demo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
