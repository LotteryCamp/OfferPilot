"""Login attempt throttling and temporary account lockout.

Counters are kept in PostgreSQL so multiple API processes share the same
window. Bucket keys contain a normalized IP prefix or a SHA-256 email digest;
raw emails are not stored in the throttle table.
"""

from __future__ import annotations

import hashlib
import ipaddress
import math
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.errors import ApiError
from backend.tables import login_throttle


def ip_bucket_key(client_ip: str | None) -> str | None:
    """Return the rate-limit bucket for a client address.

    IPv6 clients are grouped by /64 so rotating addresses inside one prefix
    does not create fresh buckets. Non-IP peer values are ignored.
    """

    if not client_ip:
        return None
    try:
        address = ipaddress.ip_address(client_ip)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address):
        mapped = address.ipv4_mapped
        if mapped is not None:
            return f"ip:{mapped}"
        network = ipaddress.ip_network(f"{address}/64", strict=False)
        return f"ip:{network}"
    return f"ip:{address}"


def email_bucket_key(email: str) -> str:
    normalized = email.strip().lower()
    return "email:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def consume_ip_attempt(
    session: Session,
    bucket_key: str,
    *,
    now: datetime,
    window: timedelta,
    limit: int,
) -> int | None:
    """Count one login request for the IP bucket.

    Returns the number of seconds to wait when the fixed window is exhausted.
    """

    row = _increment(session, bucket_key, now=now, window=window)
    if row.attempts <= limit:
        return None
    return _retry_after(row.window_start + window, now)


def email_blocked_for(
    session: Session,
    bucket_key: str,
    *,
    now: datetime,
) -> int | None:
    blocked_until = session.execute(
        select(login_throttle.c.blocked_until).where(
            login_throttle.c.bucket_key == bucket_key
        )
    ).scalar_one_or_none()
    if blocked_until is None:
        return None
    return _retry_after(blocked_until, now)


def record_email_failure(
    session: Session,
    bucket_key: str,
    *,
    now: datetime,
    window: timedelta,
    limit: int,
    lock_duration: timedelta,
) -> int | None:
    """Count one failed credential check and start a lock at the threshold."""

    row = _increment(session, bucket_key, now=now, window=window)
    existing_retry = (
        _retry_after(row.blocked_until, now) if row.blocked_until is not None else None
    )
    if existing_retry is not None:
        return existing_retry
    if row.attempts < limit:
        return None
    blocked_until = now + lock_duration
    session.execute(
        update(login_throttle)
        .where(login_throttle.c.bucket_key == bucket_key)
        .values(blocked_until=blocked_until, updated_at=now)
    )
    return _retry_after(blocked_until, now)


def clear_email(session: Session, bucket_key: str) -> None:
    session.execute(
        delete(login_throttle).where(login_throttle.c.bucket_key == bucket_key)
    )


def clear_email_for(session: Session, email: str) -> None:
    clear_email(session, email_bucket_key(email))


def too_many_attempts(retry_after: int) -> ApiError:
    return ApiError(
        429,
        "too_many_login_attempts",
        "登录尝试过于频繁",
        next_step="等待后重试",
        headers={"Retry-After": str(retry_after)},
    )


def _increment(
    session: Session,
    bucket_key: str,
    *,
    now: datetime,
    window: timedelta,
) -> Any:
    cutoff = now - window
    statement = (
        pg_insert(login_throttle)
        .values(
            bucket_key=bucket_key,
            window_start=now,
            attempts=1,
            blocked_until=None,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=[login_throttle.c.bucket_key],
            set_={
                "attempts": case(
                    (login_throttle.c.window_start <= cutoff, 1),
                    else_=login_throttle.c.attempts + 1,
                ),
                "window_start": case(
                    (login_throttle.c.window_start <= cutoff, now),
                    else_=login_throttle.c.window_start,
                ),
                "updated_at": now,
            },
        )
        .returning(
            login_throttle.c.attempts,
            login_throttle.c.window_start,
            login_throttle.c.blocked_until,
        )
    )
    return session.execute(statement).one()


def _retry_after(deadline: datetime, now: datetime) -> int | None:
    if deadline <= now:
        return None
    return max(1, math.ceil((deadline - now).total_seconds()))
