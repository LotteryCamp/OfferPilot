"""Password hashing and opaque session token helpers."""

from __future__ import annotations

import hashlib
import secrets

from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError

_PASSWORD_HASH = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _PASSWORD_HASH.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _PASSWORD_HASH.verify(password, password_hash)
    except PwdlibError:
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
