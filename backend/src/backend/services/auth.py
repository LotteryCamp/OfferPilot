"""Account registration, login, session validation, and password changes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.errors import ApiError
from backend.identity import CurrentUser
from backend.schemas import LoginRequest, PasswordChangeRequest, RegisterRequest
from backend.security import (
    hash_password,
    new_session_token,
    session_token_hash,
    verify_password,
)
from backend.services import login_throttle
from backend.services.common import iso
from backend.tables import app_user, user_session, workspace

SESSION_COOKIE_NAME = "offerpilot_session"


@dataclass(frozen=True, slots=True)
class AuthSession:
    user: dict[str, Any]
    token: str
    expires_at: datetime
    remember: bool


def register_account(
    session: Session,
    settings: Settings,
    body: RegisterRequest,
    *,
    now: datetime,
) -> AuthSession:
    token = new_session_token()
    expires_at = _session_expiry(settings, body_remember=False, now=now)
    with session.begin():
        session.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtext(f"offerpilot:email:{body.email}")
                )
            )
        )
        existing = session.execute(
            select(app_user.c.id).where(app_user.c.email == str(body.email))
        ).first()
        if existing is not None:
            raise ApiError(
                409,
                "email_already_registered",
                "该邮箱已注册",
                next_step="使用已有账户登录，或更换邮箱注册",
            )

        user_id = uuid4()
        workspace_id = uuid4()
        session.execute(
            insert(app_user).values(
                id=user_id,
                email=str(body.email),
                display_name=body.display_name,
                password_hash=hash_password(body.password),
                account_type="applicant",
                status="active",
                created_at=now,
                updated_at=now,
                deleted_at=None,
            )
        )
        session.execute(
            insert(workspace).values(
                id=workspace_id,
                owner_id=user_id,
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            insert(user_session).values(
                id=uuid4(),
                user_id=user_id,
                token_hash=session_token_hash(token),
                remember=False,
                created_at=now,
                expires_at=expires_at,
                revoked_at=None,
            )
        )
        row = _load_account(session, user_id)
    return AuthSession(
        user=_serialize_user(row),
        token=token,
        expires_at=expires_at,
        remember=False,
    )


def login(
    session: Session,
    settings: Settings,
    body: LoginRequest,
    *,
    now: datetime,
    client_ip: str | None = None,
) -> AuthSession:
    ip_key = login_throttle.ip_bucket_key(client_ip)
    email_key = login_throttle.email_bucket_key(str(body.email))
    ip_limit = settings.login_ip_limit
    email_limit = settings.login_email_limit

    if ip_limit > 0 and ip_key is not None:
        with session.begin():
            retry_after = login_throttle.consume_ip_attempt(
                session,
                ip_key,
                now=now,
                window=timedelta(seconds=settings.login_ip_window_seconds),
                limit=ip_limit,
            )
        if retry_after is not None:
            raise login_throttle.too_many_attempts(retry_after)

    if email_limit > 0:
        with session.begin():
            retry_after = login_throttle.email_blocked_for(session, email_key, now=now)
        if retry_after is not None:
            raise login_throttle.too_many_attempts(retry_after)

    auth_session: AuthSession | None = None
    try:
        with session.begin():
            row = (
                session.execute(
                    select(
                        app_user.c.id,
                        app_user.c.email,
                        app_user.c.display_name,
                        app_user.c.password_hash,
                        app_user.c.account_type,
                        app_user.c.status,
                        app_user.c.created_at,
                        app_user.c.updated_at,
                        app_user.c.deleted_at,
                        workspace.c.id.label("workspace_id"),
                    )
                    .join(workspace, workspace.c.owner_id == app_user.c.id)
                    .where(app_user.c.email == str(body.email))
                )
                .mappings()
                .first()
            )
            if (
                row is None
                or row["status"] != "active"
                or row["deleted_at"] is not None
                or not verify_password(body.password, row["password_hash"])
            ):
                raise _InvalidCredentials

            token = new_session_token()
            expires_at = _session_expiry(settings, body_remember=body.remember, now=now)
            session.execute(
                delete(user_session).where(
                    user_session.c.user_id == row["id"],
                    user_session.c.expires_at <= now,
                )
            )
            session.execute(
                insert(user_session).values(
                    id=uuid4(),
                    user_id=row["id"],
                    token_hash=session_token_hash(token),
                    remember=body.remember,
                    created_at=now,
                    expires_at=expires_at,
                    revoked_at=None,
                )
            )
            login_throttle.clear_email(session, email_key)
            auth_session = AuthSession(
                user=_serialize_user(row),
                token=token,
                expires_at=expires_at,
                remember=body.remember,
            )
    except _InvalidCredentials:
        if email_limit > 0:
            with session.begin():
                retry_after = login_throttle.record_email_failure(
                    session,
                    email_key,
                    now=now,
                    window=timedelta(seconds=settings.login_email_window_seconds),
                    limit=email_limit,
                    lock_duration=timedelta(seconds=settings.login_lock_seconds),
                )
            if retry_after is not None:
                raise login_throttle.too_many_attempts(retry_after) from None
        raise _invalid_credentials() from None

    assert auth_session is not None
    return auth_session


def authenticate_session(
    session: Session,
    token: str,
    *,
    now: datetime,
) -> CurrentUser | None:
    row = (
        session.execute(
            select(
                user_session.c.id.label("session_id"),
                user_session.c.expires_at.label("session_expires_at"),
                user_session.c.remember,
                app_user.c.id.label("user_id"),
                app_user.c.email,
                app_user.c.display_name,
                app_user.c.account_type,
                app_user.c.status,
                app_user.c.created_at,
                app_user.c.updated_at,
                app_user.c.deleted_at,
                workspace.c.id.label("workspace_id"),
            )
            .join(app_user, app_user.c.id == user_session.c.user_id)
            .join(workspace, workspace.c.owner_id == app_user.c.id)
            .where(
                user_session.c.token_hash == session_token_hash(token),
                user_session.c.revoked_at.is_(None),
                user_session.c.expires_at > now,
                app_user.c.status == "active",
                app_user.c.deleted_at.is_(None),
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return CurrentUser(
        user_id=row["user_id"],
        workspace_id=row["workspace_id"],
        email=row["email"],
        display_name=row["display_name"],
        account_type=row["account_type"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row["deleted_at"],
        session_id=row["session_id"],
        session_expires_at=row["session_expires_at"],
        remember=row["remember"],
    )


def logout(session: Session, token: str, *, now: datetime) -> None:
    with session.begin():
        session.execute(
            update(user_session)
            .where(
                user_session.c.token_hash == session_token_hash(token),
                user_session.c.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )


def change_password(
    session: Session,
    current_user: CurrentUser,
    body: PasswordChangeRequest,
    *,
    now: datetime,
) -> None:
    with session.begin():
        password_hash = session.execute(
            select(app_user.c.password_hash).where(
                app_user.c.id == current_user.user_id
            )
        ).scalar_one_or_none()
        if password_hash is None or not verify_password(
            body.current_password, password_hash
        ):
            raise ApiError(
                401,
                "invalid_current_password",
                "当前密码不正确",
                next_step="重新输入当前密码",
            )
        session.execute(
            update(app_user)
            .where(app_user.c.id == current_user.user_id)
            .values(password_hash=hash_password(body.new_password), updated_at=now)
        )
        _revoke_all_sessions(session, current_user.user_id, now)


def serialize_current_user(current_user: CurrentUser) -> dict[str, Any]:
    return {
        "id": str(current_user.user_id),
        "email": current_user.email,
        "display_name": current_user.display_name,
        "account_type": current_user.account_type,
        "status": current_user.status,
        "workspace_id": str(current_user.workspace_id),
        "created_at": iso(current_user.created_at),
        "updated_at": iso(current_user.updated_at),
        "deleted_at": iso(current_user.deleted_at),
    }


def session_payload(auth_session: AuthSession) -> dict[str, Any]:
    return {
        "expires_at": iso(auth_session.expires_at),
        "remember": auth_session.remember,
    }


def _invalid_credentials() -> ApiError:
    return ApiError(
        401,
        "invalid_credentials",
        "邮箱或密码错误",
        next_step="核对邮箱和密码后重试",
    )


class _InvalidCredentials(Exception):
    """Internal signal for the failed-credential path."""


def _session_expiry(
    settings: Settings,
    *,
    body_remember: bool,
    now: datetime,
) -> datetime:
    ttl_seconds = (
        settings.remember_session_ttl_seconds
        if body_remember
        else settings.session_ttl_seconds
    )
    return now + timedelta(seconds=ttl_seconds)


def _load_account(session: Session, user_id: UUID) -> Any:
    row = (
        session.execute(
            select(
                app_user.c.id,
                app_user.c.email,
                app_user.c.display_name,
                app_user.c.account_type,
                app_user.c.status,
                app_user.c.created_at,
                app_user.c.updated_at,
                app_user.c.deleted_at,
                workspace.c.id.label("workspace_id"),
            )
            .join(workspace, workspace.c.owner_id == app_user.c.id)
            .where(app_user.c.id == user_id)
        )
        .mappings()
        .one()
    )
    return row


def _serialize_user(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "display_name": row["display_name"],
        "account_type": row["account_type"],
        "status": row["status"],
        "workspace_id": str(row["workspace_id"]),
        "created_at": iso(row["created_at"]),
        "updated_at": iso(row["updated_at"]),
        "deleted_at": iso(row["deleted_at"]),
    }


def _revoke_all_sessions(session: Session, user_id: UUID, now: datetime) -> None:
    session.execute(
        update(user_session)
        .where(
            user_session.c.user_id == user_id,
            user_session.c.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
