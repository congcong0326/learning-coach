from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.models.auth import AppUser
from backend.app.models.llm_run import LlmRun
from backend.app.models.problem import Base
from backend.app.services.llm_run_service import (
    LlmRunError,
    cancel_llm_run,
    create_llm_run,
    fail_llm_run,
    get_llm_run_for_user,
    mark_llm_run_running,
    succeed_llm_run,
    update_llm_run_display_text,
)


@pytest_asyncio.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def create_user(session: AsyncSession) -> AppUser:
    now = datetime.now(UTC)
    unique = uuid4().hex
    user = AppUser(
        username=f"user-{unique}",
        email=f"user-{unique}@example.com",
        password_hash="hash",
        display_name="Learner",
        status="active",
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def cancel_run_from_second_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[AsyncSession, AppUser, LlmRun]:
    session_a = session_factory()
    user = await create_user(session_a)
    run = await create_llm_run(session_a, user, kind="goal_plan_generate")

    async with session_factory() as session_b:
        user_b = await session_b.get(AppUser, user.id)
        assert user_b is not None
        await cancel_llm_run(session_b, user_b, run.id)

    return session_a, user, run


@pytest.mark.asyncio
async def test_create_and_fetch_llm_run(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        run = await create_llm_run(
            session,
            user,
            kind="goal_plan_generate",
            payload={"draft_id": 9},
            related_type="goal_calibration_draft",
            related_id=9,
        )

        fetched = await get_llm_run_for_user(session, user, run.id)

        assert fetched.id == run.id
        assert fetched.status == "pending"
        assert fetched.stage == "queued"
        assert fetched.input_json == {"draft_id": 9}


@pytest.mark.asyncio
async def test_status_transitions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        run = await create_llm_run(session, user, kind="goal_plan_generate")

        await mark_llm_run_running(session, run, stage="selecting_credential")
        await succeed_llm_run(
            session,
            run,
            result={"draft_id": 12},
            display_text_md="计划生成完成",
        )

        fetched = await get_llm_run_for_user(session, user, run.id)
        assert fetched.status == "succeeded"
        assert fetched.stage == "completed"
        assert fetched.result_json == {"draft_id": 12}
        assert fetched.finished_at is not None


@pytest.mark.asyncio
async def test_cancel_terminal_run_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        run = await create_llm_run(session, user, kind="goal_plan_generate")
        await fail_llm_run(
            session,
            run,
            error_code="llm_provider_error",
            error_message="模型请求失败",
        )

        with pytest.raises(LlmRunError, match="run_status_conflict"):
            await cancel_llm_run(session, user, run.id)


@pytest.mark.asyncio
async def test_cancelled_run_cannot_be_succeeded(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        run = await create_llm_run(session, user, kind="goal_plan_generate")
        user_id = user.id
        run_id = run.id

        await cancel_llm_run(session, user, run.id)

        with pytest.raises(LlmRunError, match="run_status_conflict"):
            await succeed_llm_run(
                session,
                run,
                result={"draft_id": 12},
                display_text_md="计划生成完成",
            )

        refreshed_user = await session.get(AppUser, user_id)
        assert refreshed_user is not None
        fetched = await get_llm_run_for_user(session, refreshed_user, run_id)
        assert fetched.status == "canceled"
        assert fetched.stage == "canceled"


@pytest.mark.asyncio
async def test_other_user_cannot_fetch_or_cancel_run(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        owner = await create_user(session)
        other_user = await create_user(session)
        run = await create_llm_run(session, owner, kind="goal_plan_generate")

        with pytest.raises(LlmRunError, match="run_not_found"):
            await get_llm_run_for_user(session, other_user, run.id)

        with pytest.raises(LlmRunError, match="run_not_found"):
            await cancel_llm_run(session, other_user, run.id)


@pytest.mark.asyncio
async def test_stale_run_cannot_succeed_after_cancel(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_a, user, run = await cancel_run_from_second_session(session_factory)
    user_id = user.id
    run_id = run.id
    async with session_a:
        with pytest.raises(LlmRunError, match="run_status_conflict"):
            await succeed_llm_run(
                session_a,
                run,
                result={"draft_id": 12},
                display_text_md="计划生成完成",
            )

        refreshed_user = await session_a.get(AppUser, user_id)
        assert refreshed_user is not None
        fetched = await get_llm_run_for_user(session_a, refreshed_user, run_id)
        assert fetched.status == "canceled"


@pytest.mark.asyncio
async def test_stale_run_cannot_fail_after_cancel(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_a, user, run = await cancel_run_from_second_session(session_factory)
    user_id = user.id
    run_id = run.id
    async with session_a:
        with pytest.raises(LlmRunError, match="run_status_conflict"):
            await fail_llm_run(
                session_a,
                run,
                error_code="llm_provider_error",
                error_message="模型请求失败",
            )

        refreshed_user = await session_a.get(AppUser, user_id)
        assert refreshed_user is not None
        fetched = await get_llm_run_for_user(session_a, refreshed_user, run_id)
        assert fetched.status == "canceled"


@pytest.mark.asyncio
async def test_stale_run_cannot_mark_running_after_cancel(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_a, user, run = await cancel_run_from_second_session(session_factory)
    user_id = user.id
    run_id = run.id
    async with session_a:
        with pytest.raises(LlmRunError, match="run_status_conflict"):
            await mark_llm_run_running(session_a, run, stage="selecting_credential")

        refreshed_user = await session_a.get(AppUser, user_id)
        assert refreshed_user is not None
        fetched = await get_llm_run_for_user(session_a, refreshed_user, run_id)
        assert fetched.status == "canceled"


@pytest.mark.asyncio
async def test_stale_run_cannot_update_display_text_after_cancel(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_a, user, run = await cancel_run_from_second_session(session_factory)
    user_id = user.id
    run_id = run.id
    async with session_a:
        with pytest.raises(LlmRunError, match="run_status_conflict"):
            await update_llm_run_display_text(
                session_a,
                run,
                display_text_md="计划生成中",
            )

        refreshed_user = await session_a.get(AppUser, user_id)
        assert refreshed_user is not None
        fetched = await get_llm_run_for_user(session_a, refreshed_user, run_id)
        assert fetched.status == "canceled"
        assert fetched.display_text_md == ""
