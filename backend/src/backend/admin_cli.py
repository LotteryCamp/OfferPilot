"""Command-line bootstrap for the first administrator account."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime

from pydantic import ValidationError

from backend.config import Settings
from backend.db import build_engine, build_session_factory
from backend.errors import ApiError
from backend.schemas import RegisterRequest
from backend.services import admin_users as admin_user_service

ADMIN_PASSWORD_ENV = "OFFERPILOT_ADMIN_PASSWORD"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="offerpilot-admin")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser(
        "create",
        help="创建有效管理员及其个人工作区",
    )
    create_parser.add_argument("--email", required=True)
    create_parser.add_argument("--display-name", required=True)
    args = parser.parse_args(argv)

    if args.command != "create":
        parser.error("unknown command")

    password = os.environ.get(ADMIN_PASSWORD_ENV, "")
    if not password:
        print(f"{ADMIN_PASSWORD_ENV} 必须设置为管理员初始密码", file=sys.stderr)
        raise SystemExit(2)
    try:
        account = RegisterRequest(
            email=args.email,
            display_name=args.display_name,
            password=password,
        )
    except ValidationError as exc:
        issues = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        print(f"管理员账户参数不合法: {issues}", file=sys.stderr)
        raise SystemExit(2) from exc

    settings = Settings.from_env()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    try:
        with session_factory() as session:
            user = admin_user_service.create_admin_account(
                session,
                email=str(account.email),
                display_name=account.display_name,
                password=account.password,
                now=datetime.now(UTC),
            )
    except ApiError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        engine.dispose()

    print(f"已创建管理员 {user['email']} ({user['id']})")


if __name__ == "__main__":
    main()
