from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.db.session import get_session
from backend.app.models.auth import AppUser
from backend.app.schemas.auth import (
    AuthUserEnvelope,
    CurrentUserResponse,
    LoginRequest,
    RegisterRequest,
)
from backend.app.services.auth_service import (
    AuthError,
    get_current_user_from_token,
    login_user,
    logout_token,
    register_user,
)


router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_hours * 60 * 60,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name)


def _user_envelope(user: AppUser) -> dict:
    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
        }
    }


async def current_user_dependency(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AppUser:
    user = await get_current_user_from_token(
        session,
        request.cookies.get(settings.session_cookie_name),
    )
    if user is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    return user


@router.post("/register", response_model=AuthUserEnvelope)
async def register(
    payload: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        user, created_session = await register_user(
            session,
            username=payload.username,
            email=payload.email,
            password=payload.password,
        )
    except AuthError as exc:
        status_code = 409 if exc.detail == "user_already_exists" else 422
        raise HTTPException(status_code=status_code, detail=exc.detail) from exc
    _set_session_cookie(response, created_session.token)
    return _user_envelope(user)


@router.post("/login", response_model=AuthUserEnvelope)
async def login(
    payload: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        user, created_session = await login_user(
            session,
            login=payload.login,
            password=payload.password,
        )
    except AuthError as exc:
        status_code = 403 if exc.detail == "user_disabled" else 401
        raise HTTPException(status_code=status_code, detail=exc.detail) from exc
    _set_session_cookie(response, created_session.token)
    return _user_envelope(user)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await logout_token(
        session,
        request.cookies.get(settings.session_cookie_name),
    )
    _clear_session_cookie(response)
    return {"status": "ok"}


@router.get("/me", response_model=CurrentUserResponse)
async def me(
    user: AppUser = Depends(current_user_dependency),
) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
    }
