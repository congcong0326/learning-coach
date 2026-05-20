from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.models.auth import AppUser, AuthSession, LlmCredential


class AuthError(RuntimeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class CreatedSession:
    record: AuthSession
    token: str


_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError, TypeError):
        return False


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_session(db: AsyncSession, user: AppUser) -> CreatedSession:
    now = datetime.now(UTC)
    token = secrets.token_urlsafe(32)
    record = AuthSession(
        user_id=user.id,
        session_token_hash=session_token_hash(token),
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
        created_at=now,
        last_seen_at=now,
    )
    db.add(record)
    await db.flush()
    return CreatedSession(record=record, token=token)


async def register_user(
    db: AsyncSession,
    *,
    username: str,
    email: str,
    password: str,
) -> tuple[AppUser, CreatedSession]:
    normalized_email = email.strip().lower()
    normalized_username = username.strip()
    if "@" not in normalized_email:
        raise AuthError("invalid_email")

    existing = await db.execute(
        select(AppUser).where(
            or_(
                AppUser.username == normalized_username,
                AppUser.email == normalized_email,
            )
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise AuthError("user_already_exists")

    now = datetime.now(UTC)
    user = AppUser(
        username=normalized_username,
        email=normalized_email,
        password_hash=hash_password(password),
        display_name=normalized_username,
        status="active",
        created_at=now,
        updated_at=now,
        last_login_at=now,
    )
    db.add(user)
    await db.flush()
    created_session = await create_session(db, user)
    await db.commit()
    await db.refresh(user)
    return user, created_session


async def login_user(
    db: AsyncSession,
    *,
    login: str,
    password: str,
) -> tuple[AppUser, CreatedSession]:
    normalized_login = login.strip()
    result = await db.execute(
        select(AppUser).where(
            or_(
                AppUser.username == normalized_login,
                AppUser.email == normalized_login.lower(),
            )
        )
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("invalid_credentials")
    if user.status != "active":
        raise AuthError("user_disabled")

    user.last_login_at = datetime.now(UTC)
    created_session = await create_session(db, user)
    await db.commit()
    await db.refresh(user)
    return user, created_session


async def logout_token(db: AsyncSession, token: str | None) -> None:
    if not token:
        return
    result = await db.execute(
        select(AuthSession).where(
            AuthSession.session_token_hash == session_token_hash(token)
        )
    )
    record = result.scalar_one_or_none()
    if record is not None:
        record.revoked_at = datetime.now(UTC)
        await db.commit()


async def get_current_user_from_token(
    db: AsyncSession,
    token: str | None,
) -> AppUser | None:
    if not token:
        return None
    now = datetime.now(UTC)
    result = await db.execute(
        select(AuthSession)
        .options(selectinload(AuthSession.user))
        .join(AuthSession.user)
        .where(
            AuthSession.session_token_hash == session_token_hash(token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
            AppUser.status == "active",
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        return None
    record.last_seen_at = now
    await db.commit()
    return record.user


async def has_default_llm_credential(db: AsyncSession, user: AppUser) -> bool:
    result = await db.execute(
        select(LlmCredential.id).where(
            LlmCredential.user_id == user.id,
            LlmCredential.is_preferred.is_(True),
            LlmCredential.is_enabled.is_(True),
        ).limit(1)
    )
    return result.scalars().first() is not None
