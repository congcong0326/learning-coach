from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

import backend.app.models.llm_run  # noqa: F401
from backend.app.api.auth import current_user_dependency
from backend.app.db.session import get_session
from backend.app.main import app
from backend.app.models.auth import AppUser
from backend.app.models.learning import (
    StudyPlan,
    StudyPlanItem,
    StudyPlanStage,
    StudyPlanVersion,
)
from backend.app.models.practice import UserProfileSnapshot  # noqa: F401
from backend.app.models.problem import Base, Problem


@pytest_asyncio.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def app_user(session_factory: async_sessionmaker[AsyncSession]) -> AppUser:
    now = datetime.now(UTC)
    unique = uuid4().hex
    user = AppUser(
        username=f"user-{unique}",
        email=f"user-{unique}@example.com",
        password_hash="hash",
        display_name="learner",
        status="active",
        created_at=now,
        updated_at=now,
    )
    async with session_factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def study_plan_item(
    session_factory: async_sessionmaker[AsyncSession],
    app_user: AppUser,
) -> StudyPlanItem:
    now = datetime.now(UTC)
    unique = uuid4().hex
    problem = Problem(
        frontend_id=f"practice-api-{unique}",
        slug=f"two-sum-{unique}",
        title="Two Sum",
        translated_title="两数之和",
        difficulty="Easy",
        statement_md="# statement",
        metadata_json={"topic_tags": [{"slug": "array", "name": "Array"}]},
        leetcode_url="https://leetcode.cn/problems/two-sum/",
        is_paid_only=False,
        created_at=now,
        updated_at=now,
    )
    plan = StudyPlan(
        user_id=app_user.id,
        title="学习计划",
        status="active",
        active_version_number=1,
        created_at=now,
        updated_at=now,
    )
    async with session_factory() as session:
        session.add_all([problem, plan])
        await session.flush()
        version = StudyPlanVersion(
            plan_id=plan.id,
            version_number=1,
            status="active",
            target_snapshot_json={"goal_type": "interview_sprint"},
            generation_summary_md="按当前目标生成的训练计划",
            adjustment_summary_md="",
            validation_report_json={"valid": True},
            repair_log_json=[],
            created_at=now,
            activated_at=now,
        )
        session.add(version)
        await session.flush()
        stage = StudyPlanStage(
            version_id=version.id,
            stage_index=0,
            title="基础巩固",
            objective_md="巩固高频基础模式",
            focus_tags_json=["array"],
            assessment_criteria_json=["能解释核心思路"],
            status="not_started",
            created_at=now,
            updated_at=now,
        )
        session.add(stage)
        await session.flush()
        item = StudyPlanItem(
            version_id=version.id,
            stage_id=stage.id,
            problem_id=problem.id,
            problem_slug=problem.slug,
            skill_tags_json=["array"],
            difficulty=problem.difficulty,
            suggested_mode="guided",
            recommendation_reason="练习哈希表补数",
            status="pending",
            order_index=0,
            locked=False,
            created_at=now,
            updated_at=now,
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
    return item


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def authenticated_client(
    session_factory: async_sessionmaker[AsyncSession],
    app_user: AppUser,
) -> Generator[TestClient, None, None]:
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[current_user_dependency] = lambda: app_user
    app.dependency_overrides[get_session] = override_get_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_plan_item_entry_requires_login(client, study_plan_item):
    response = client.post(f"/api/study-plan/items/{study_plan_item.id}/practice-session")

    assert response.status_code in {401, 403}


def test_plan_item_entry_returns_session(authenticated_client, study_plan_item):
    response = authenticated_client.post(
        f"/api/study-plan/items/{study_plan_item.id}/practice-session"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] > 0
    assert body["latest_plan_item_id"] == study_plan_item.id
