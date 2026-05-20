from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.core.config import settings
from backend.app.models.auth import AppUser, LlmCredential
from backend.app.schemas.llm_credential import (
    LlmCredentialCreateRequest,
    LlmCredentialUpdateRequest,
)
from backend.app.services.llm_credential_service import (
    LLM_CREDENTIAL_FAILURE_THRESHOLD,
    LlmCredentialError,
    create_credential,
    record_llm_credential_failure,
    record_llm_credential_success,
    select_llm_credential_for_user,
    set_default_credential,
    update_credential,
)


@pytest_asyncio.fixture
async def routing_session_factory(monkeypatch):
    monkeypatch.setattr(
        settings,
        "credential_encryption_key",
        Fernet.generate_key().decode(),
    )
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(AppUser.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def make_credential(
    user: AppUser,
    display_name: str,
    *,
    is_enabled: bool = True,
    is_preferred: bool = False,
    is_active: bool = False,
    failure_count: int = 0,
    status: str = "valid",
    last_used_at: datetime | None = None,
) -> LlmCredential:
    now = datetime.now(UTC)
    return LlmCredential(
        user_id=user.id,
        provider="openai",
        display_name=display_name,
        base_url="https://api.openai.com/v1",
        api_mode="responses",
        model_name="gpt-4.1-mini",
        api_key_ciphertext=f"cipher-{display_name}",
        api_key_mask="sk-...test",
        is_default=is_preferred,
        is_enabled=is_enabled,
        is_preferred=is_preferred,
        is_active=is_active,
        failure_count=failure_count,
        status=status,
        last_error="",
        last_used_at=last_used_at,
        created_at=now,
        updated_at=now,
    )


async def create_user_and_credentials(
    session: AsyncSession,
) -> tuple[AppUser, LlmCredential, LlmCredential]:
    now = datetime.now(UTC)
    user = AppUser(
        username="alice",
        email="alice@example.com",
        password_hash="hash",
        display_name="alice",
        status="active",
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    await session.flush()

    active = make_credential(
        user,
        "active",
        is_preferred=True,
        is_active=True,
        failure_count=LLM_CREDENTIAL_FAILURE_THRESHOLD - 1,
        last_used_at=now,
    )
    backup = make_credential(
        user,
        "backup",
        last_used_at=now - timedelta(hours=1),
    )
    session.add_all([active, backup])
    await session.commit()
    await session.refresh(user)
    await session.refresh(active)
    await session.refresh(backup)
    return user, active, backup


async def create_user(session: AsyncSession) -> AppUser:
    now = datetime.now(UTC)
    user = AppUser(
        username="bob",
        email="bob@example.com",
        password_hash="hash",
        display_name="bob",
        status="active",
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def credential_create_request(
    display_name: str,
    *,
    is_default: bool = False,
) -> LlmCredentialCreateRequest:
    return LlmCredentialCreateRequest(
        display_name=display_name,
        provider="openai",
        base_url="https://api.openai.com/v1",
        api_mode="responses",
        model_name="gpt-4.1-mini",
        api_key=f"sk-{display_name}-secret",
        is_default=is_default,
    )


@pytest.mark.asyncio
async def test_create_default_credential_syncs_preferred_and_active_aliases(
    routing_session_factory,
) -> None:
    async with routing_session_factory() as session:
        user = await create_user(session)

        created = await create_credential(
            session,
            user,
            credential_create_request("primary", is_default=True),
        )

        assert created.is_default is True
        assert created.is_preferred is True
        assert created.is_active is True


@pytest.mark.asyncio
async def test_set_default_credential_syncs_preferred_alias_and_clears_others(
    routing_session_factory,
) -> None:
    async with routing_session_factory() as session:
        user, first, second = await create_user_and_credentials(session)

        selected = await set_default_credential(session, user, second.id)

        assert selected.id == second.id
        assert selected.is_default is True
        assert selected.is_preferred is True
        await session.refresh(first)
        assert first.is_default is False
        assert first.is_preferred is False


@pytest.mark.asyncio
async def test_select_keeps_active_credential_while_enabled_below_failure_threshold(
    routing_session_factory,
) -> None:
    async with routing_session_factory() as session:
        user, active, backup = await create_user_and_credentials(session)

        selected = await select_llm_credential_for_user(session, user)

        assert selected.id == active.id
        assert selected.is_active is True
        await session.refresh(backup)
        assert backup.is_active is False


@pytest.mark.asyncio
async def test_select_switches_when_active_reaches_threshold_and_marks_selected_active(
    routing_session_factory,
) -> None:
    async with routing_session_factory() as session:
        user, active, backup = await create_user_and_credentials(session)
        active.failure_count = LLM_CREDENTIAL_FAILURE_THRESHOLD
        await session.commit()

        selected = await select_llm_credential_for_user(session, user)

        assert selected.id == backup.id
        assert selected.is_active is True
        assert selected.last_used_at is not None
        await session.refresh(active)
        assert active.is_active is False


@pytest.mark.asyncio
async def test_select_prefers_enabled_preferred_credential_before_fallback(
    routing_session_factory,
) -> None:
    async with routing_session_factory() as session:
        user, active, fallback = await create_user_and_credentials(session)
        active.failure_count = LLM_CREDENTIAL_FAILURE_THRESHOLD
        active.is_preferred = False
        preferred = make_credential(
            user,
            "preferred",
            is_preferred=True,
            last_used_at=datetime.now(UTC),
        )
        fallback.last_used_at = None
        session.add(preferred)
        await session.commit()
        await session.refresh(preferred)

        selected = await select_llm_credential_for_user(session, user)

        assert selected.id == preferred.id
        assert selected.is_active is True
        await session.refresh(fallback)
        assert fallback.is_active is False


@pytest.mark.asyncio
async def test_select_skips_disabled_credentials_and_raises_when_none_available(
    routing_session_factory,
) -> None:
    async with routing_session_factory() as session:
        user, active, backup = await create_user_and_credentials(session)
        active.is_enabled = False
        backup.is_enabled = False
        await session.commit()

        with pytest.raises(LlmCredentialError) as exc_info:
            await select_llm_credential_for_user(session, user)

        assert "llm_credential_unavailable" in str(exc_info.value)


@pytest.mark.asyncio
async def test_reenabling_preferred_credential_marks_it_active_and_clears_others(
    routing_session_factory,
) -> None:
    async with routing_session_factory() as session:
        user, active, preferred = await create_user_and_credentials(session)
        active.is_preferred = False
        preferred.is_preferred = True
        preferred.is_default = True
        preferred.is_enabled = False
        preferred.is_active = False
        preferred.failure_count = LLM_CREDENTIAL_FAILURE_THRESHOLD - 1
        await session.commit()

        updated = await update_credential(
            session,
            user,
            preferred.id,
            LlmCredentialUpdateRequest(is_enabled=True),
        )

        assert updated.is_active is True
        await session.refresh(active)
        assert active.is_active is False


@pytest.mark.asyncio
async def test_record_success_clears_failure_state(routing_session_factory) -> None:
    async with routing_session_factory() as session:
        _user, active, _backup = await create_user_and_credentials(session)
        active.failure_count = 2
        active.status = "invalid"
        active.last_error = "timeout"
        active.last_used_at = None
        await session.commit()

        updated = await record_llm_credential_success(session, active)

        assert updated.failure_count == 0
        assert updated.status == "valid"
        assert updated.last_error == ""
        assert updated.last_used_at is not None


@pytest.mark.asyncio
async def test_record_failure_updates_error_state_and_clears_active_at_threshold(
    routing_session_factory,
) -> None:
    async with routing_session_factory() as session:
        _user, active, _backup = await create_user_and_credentials(session)
        active.failure_count = LLM_CREDENTIAL_FAILURE_THRESHOLD - 1
        active.is_active = True
        await session.commit()
        error_summary = "x" * 600

        updated = await record_llm_credential_failure(session, active, error_summary)

        assert updated.failure_count == LLM_CREDENTIAL_FAILURE_THRESHOLD
        assert updated.status == "invalid"
        assert updated.last_error == error_summary[:500]
        assert updated.last_used_at is not None
        assert updated.is_active is False
