"""Administrator account management."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, insert, or_, select, update
from sqlalchemy.orm import Session

from backend.errors import ApiError
from backend.identity import CurrentUser
from backend.schemas import (
    AdminPasswordReset,
    AdminUserRoleUpdate,
    AdminUserStatusUpdate,
)
from backend.security import hash_password
from backend.services import login_throttle
from backend.services.common import iso
from backend.tables import app_user, user_session, workspace


def create_admin_account(
    session: Session,
    *,
    email: str,
    display_name: str,
    password: str,
    now: datetime,
) -> dict[str, Any]:
    with session.begin():
        session.execute(
            select(
                func.pg_advisory_xact_lock(func.hashtext(f"offerpilot:email:{email}"))
            )
        )
        existing = session.execute(
            select(app_user.c.id).where(app_user.c.email == email)
        ).first()
        if existing is not None:
            raise ApiError(
                409,
                "email_already_registered",
                "该邮箱已注册",
                next_step="使用其他邮箱创建管理员",
            )

        user_id = uuid4()
        workspace_id = uuid4()
        session.execute(
            insert(app_user).values(
                id=user_id,
                email=email,
                display_name=display_name,
                password_hash=hash_password(password),
                account_type="admin",
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
        return _serialize_user(_load_account(session, user_id))


def list_users(
    session: Session,
    *,
    search: str | None,
    status: str | None,
    account_type: str | None,
    include_deleted: bool,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    filters = []
    if search is not None and search.strip():
        pattern = f"%{_escape_like(search.strip())}%"
        filters.append(
            or_(
                app_user.c.email.ilike(pattern, escape="\\"),
                app_user.c.display_name.ilike(pattern, escape="\\"),
            )
        )
    if status is not None:
        filters.append(app_user.c.status == status)
    if account_type is not None:
        filters.append(app_user.c.account_type == account_type)
    if not include_deleted:
        filters.append(app_user.c.deleted_at.is_(None))

    with session.begin():
        total = session.execute(
            select(func.count())
            .select_from(app_user)
            .join(workspace, workspace.c.owner_id == app_user.c.id)
            .where(*filters)
        ).scalar_one()
        rows = (
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
                .where(*filters)
                .order_by(app_user.c.created_at.desc(), app_user.c.id)
                .limit(limit)
                .offset(offset)
            )
            .mappings()
            .all()
        )
    return {
        "users": [_serialize_user(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def update_status(
    session: Session,
    actor: CurrentUser,
    user_id: UUID,
    body: AdminUserStatusUpdate,
    *,
    now: datetime,
) -> dict[str, Any]:
    with session.begin():
        _lock_admin_membership(session)
        target = _require_account(session, user_id, for_update=True)
        _require_not_deleted(target)
        if user_id == actor.user_id and body.status != target["status"]:
            raise _self_administration_forbidden()
        if target["status"] == body.status:
            return _serialize_user(target)
        if (
            body.status == "disabled"
            and target["account_type"] == "admin"
            and target["status"] == "active"
        ):
            _require_other_active_admin(session, user_id)
        session.execute(
            update(app_user)
            .where(app_user.c.id == user_id)
            .values(status=body.status, updated_at=now)
        )
        if body.status == "disabled":
            _revoke_all_sessions(session, user_id, now)
        else:
            login_throttle.clear_email_for(session, target["email"])
        return _serialize_user(_load_account(session, user_id))


def update_role(
    session: Session,
    actor: CurrentUser,
    user_id: UUID,
    body: AdminUserRoleUpdate,
    *,
    now: datetime,
) -> dict[str, Any]:
    with session.begin():
        _lock_admin_membership(session)
        target = _require_account(session, user_id, for_update=True)
        _require_not_deleted(target)
        if user_id == actor.user_id and body.account_type != target["account_type"]:
            raise _self_administration_forbidden()
        if target["account_type"] == body.account_type:
            return _serialize_user(target)
        if target["account_type"] == "admin" and target["status"] == "active":
            _require_other_active_admin(session, user_id)
        session.execute(
            update(app_user)
            .where(app_user.c.id == user_id)
            .values(account_type=body.account_type, updated_at=now)
        )
        return _serialize_user(_load_account(session, user_id))


def reset_password(
    session: Session,
    actor: CurrentUser,
    user_id: UUID,
    body: AdminPasswordReset,
    *,
    now: datetime,
) -> dict[str, Any]:
    with session.begin():
        target = _require_account(session, user_id, for_update=True)
        _require_not_deleted(target)
        if user_id == actor.user_id:
            raise _self_administration_forbidden()
        session.execute(
            update(app_user)
            .where(app_user.c.id == user_id)
            .values(password_hash=hash_password(body.new_password), updated_at=now)
        )
        _revoke_all_sessions(session, user_id, now)
        login_throttle.clear_email_for(session, target["email"])
        return _serialize_user(_load_account(session, user_id))


def delete_user(
    session: Session,
    actor: CurrentUser,
    user_id: UUID,
    *,
    now: datetime,
) -> None:
    with session.begin():
        _lock_admin_membership(session)
        target = _require_account(session, user_id, for_update=True)
        if target["deleted_at"] is not None:
            return
        if user_id == actor.user_id:
            raise _self_administration_forbidden()
        if target["account_type"] == "admin" and target["status"] == "active":
            _require_other_active_admin(session, user_id)
        session.execute(
            update(app_user)
            .where(app_user.c.id == user_id)
            .values(status="disabled", deleted_at=now, updated_at=now)
        )
        _revoke_all_sessions(session, user_id, now)


def _require_account(session: Session, user_id: UUID, *, for_update: bool) -> Any:
    statement = (
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
    if for_update:
        statement = statement.with_for_update(of=app_user)
    row = session.execute(statement).mappings().first()
    if row is None:
        raise ApiError(
            404,
            "user_not_found",
            "未找到账户",
            next_step="刷新用户列表后重试",
        )
    return row


def _load_account(session: Session, user_id: UUID) -> Any:
    return _require_account(session, user_id, for_update=False)


def _require_not_deleted(target: Any) -> None:
    if target["deleted_at"] is not None:
        raise ApiError(
            409,
            "account_deleted",
            "账户已删除",
            next_step="刷新用户列表后选择其他账户",
        )


def _require_other_active_admin(session: Session, excluded_user_id: UUID) -> None:
    active_admins = session.execute(
        select(func.count())
        .select_from(app_user)
        .where(
            app_user.c.id != excluded_user_id,
            app_user.c.account_type == "admin",
            app_user.c.status == "active",
            app_user.c.deleted_at.is_(None),
        )
    ).scalar_one()
    if active_admins < 1:
        raise ApiError(
            409,
            "last_admin_required",
            "系统必须保留至少一个有效管理员",
            next_step="先授予其他账户管理员身份，再修改当前管理员",
        )


def _lock_admin_membership(session: Session) -> None:
    session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext("offerpilot:admin-membership")))
    )


def _revoke_all_sessions(session: Session, user_id: UUID, now: datetime) -> None:
    session.execute(
        update(user_session)
        .where(
            user_session.c.user_id == user_id,
            user_session.c.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )


def _self_administration_forbidden() -> ApiError:
    return ApiError(
        409,
        "self_administration_forbidden",
        "不能通过管理员接口修改自己的账户",
        next_step="使用个人账户接口完成该操作",
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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
