"""Registration, login, session, and password routes."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from backend.config import Settings
from backend.routers.deps import ClockDep, CurrentUserDep, SessionDep, SettingsDep
from backend.schemas import LoginRequest, PasswordChangeRequest, RegisterRequest
from backend.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterRequest,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> dict:
    auth_session = auth_service.register_account(
        session,
        settings,
        body,
        now=clock.now(),
    )
    _set_session_cookie(response, auth_session, settings)
    return {
        "user": auth_session.user,
        "session": auth_service.session_payload(auth_session),
    }


@router.post("/login")
def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> dict:
    auth_session = auth_service.login(
        session,
        settings,
        body,
        now=clock.now(),
        client_ip=request.client.host if request.client else None,
    )
    _set_session_cookie(response, auth_session, settings)
    return {
        "user": auth_session.user,
        "session": auth_service.session_payload(auth_session),
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> Response:
    token = request.cookies.get(auth_service.SESSION_COOKIE_NAME)
    if token:
        auth_service.logout(session, token, now=clock.now())
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_session_cookie(response, settings)
    return response


@router.get("/me")
def get_current_account(current_user: CurrentUserDep) -> dict:
    return {
        "user": auth_service.serialize_current_user(current_user),
        "session": {
            "expires_at": current_user.session_expires_at.isoformat(),
            "remember": current_user.remember,
        },
    }


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: PasswordChangeRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> Response:
    auth_service.change_password(
        session,
        current_user,
        body,
        now=clock.now(),
    )
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_session_cookie(response, settings)
    return response


def _set_session_cookie(
    response: Response,
    auth_session: auth_service.AuthSession,
    settings: Settings,
) -> None:
    response.set_cookie(
        key=auth_service.SESSION_COOKIE_NAME,
        value=auth_session.token,
        max_age=(
            settings.remember_session_ttl_seconds if auth_session.remember else None
        ),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=auth_service.SESSION_COOKIE_NAME,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
