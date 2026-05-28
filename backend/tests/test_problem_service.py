from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.models.problem import Base, Problem
from backend.app.services.problem_service import list_problems


@pytest_asyncio.fixture
async def problem_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def problem(frontend_id: str) -> Problem:
    now = datetime.now(UTC)
    return Problem(
        frontend_id=frontend_id,
        slug=f"problem-{frontend_id}",
        title=f"Problem {frontend_id}",
        translated_title=f"题目 {frontend_id}",
        difficulty="Easy",
        statement_md="# statement",
        metadata_json={"topic_tags": []},
        leetcode_url=f"https://leetcode.cn/problems/problem-{frontend_id}/",
        is_paid_only=False,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_list_problems_sorts_frontend_id_naturally_before_pagination(
    problem_session_factory,
) -> None:
    async with problem_session_factory() as session:
        session.add_all([problem("1"), problem("10"), problem("2")])
        await session.commit()

        first_page = await list_problems(session, page=1, page_size=2)
        second_page = await list_problems(session, page=2, page_size=2)

    assert [item["frontend_id"] for item in first_page["items"]] == ["1", "2"]
    assert [item["frontend_id"] for item in second_page["items"]] == ["10"]
