from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker

import backend.app.models.trace  # noqa: F401
from backend.app.models.problem import Base


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_trace_service_writes_node_summary_without_full_user_input(
    db_session: AsyncSession,
) -> None:
    from backend.app.services.agent_trace_service import append_agent_trace

    trace = await append_agent_trace(
        db_session,
        session_id="1",
        thread_id="practice-session-1",
        problem_slug="two-sum",
        node_name="guard_transition",
        phase="review_code",
        hint_level="questioning",
        input_summary={"content_md": "x" * 2000},
        output_summary={"reason": "accepted"},
    )

    assert trace.node_name == "guard_transition"
    assert trace.hint_level == 0
    assert trace.tool_calls is not None
    assert trace.tool_calls["input_summary"]["content_md"].endswith("...")
    assert "x" * 1000 not in trace.tool_calls["input_summary"]["content_md"]
    assert trace.tool_calls["output_summary"] == {"reason": "accepted"}


@pytest.mark.asyncio
async def test_list_agent_traces_returns_recent_rows(
    db_session: AsyncSession,
) -> None:
    from backend.app.services.agent_trace_service import (
        append_agent_trace,
        list_agent_traces,
    )

    await append_agent_trace(
        db_session,
        session_id="1",
        thread_id="practice-session-1",
        node_name="load_training_context",
        output_summary={"status": "ok"},
    )
    await append_agent_trace(
        db_session,
        session_id="1",
        thread_id="practice-session-1",
        node_name="guard_transition",
        output_summary={"reason": "accepted"},
    )

    rows = await list_agent_traces(db_session, session_id="1")

    assert [row.node_name for row in rows] == [
        "load_training_context",
        "guard_transition",
    ]


@pytest.mark.asyncio
async def test_trace_service_records_error_summary(
    db_session: AsyncSession,
) -> None:
    from backend.app.services.agent_trace_service import append_agent_trace

    trace = await append_agent_trace(
        db_session,
        session_id="1",
        thread_id="practice-session-1",
        node_name="generate_coach_reply",
        output_summary={"status": "failed"},
        error_summary="provider timeout with sensitive raw prompt " + "x" * 2000,
    )

    assert trace.tool_calls is not None
    assert trace.tool_calls["error_summary"].endswith("...")
    assert "x" * 1000 not in trace.tool_calls["error_summary"]
