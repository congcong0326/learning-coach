from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import backend.app.models.llm_run  # noqa: F401
from backend.app.models.auth import AppUser
from backend.app.models.learning import (
    StudyPlan,
    StudyPlanItem,
    StudyPlanStage,
    StudyPlanVersion,
)
from backend.app.models.practice import CodeSnapshot, PracticeSession
from backend.app.models.problem import Base, Problem


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> AppUser:
    now = datetime.now(UTC)
    unique = uuid4().hex
    app_user = AppUser(
        username=f"user-{unique}",
        email=f"user-{unique}@example.com",
        password_hash="hash",
        display_name="learner",
        status="active",
        created_at=now,
        updated_at=now,
    )
    db_session.add(app_user)
    await db_session.commit()
    await db_session.refresh(app_user)
    return app_user


@pytest_asyncio.fixture
async def study_plan_item(
    db_session: AsyncSession,
    user: AppUser,
) -> StudyPlanItem:
    now = datetime.now(UTC)
    problem = Problem(
        frontend_id="1",
        slug="two-sum",
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
        user_id=user.id,
        title="学习计划",
        status="active",
        active_version_number=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([problem, plan])
    await db_session.flush()

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
    db_session.add(version)
    await db_session.flush()

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
    db_session.add(stage)
    await db_session.flush()

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
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


@pytest_asyncio.fixture
async def practice_session(
    db_session: AsyncSession,
    user: AppUser,
    study_plan_item: StudyPlanItem,
) -> PracticeSession:
    from backend.app.services.practice_session_service import get_or_create_session_for_plan_item

    return await get_or_create_session_for_plan_item(db_session, user, study_plan_item.id)


@pytest.mark.asyncio
async def test_same_plan_problem_reuses_practice_session(
    db_session: AsyncSession,
    user: AppUser,
    study_plan_item: StudyPlanItem,
) -> None:
    from backend.app.services.practice_session_service import get_or_create_session_for_plan_item

    first = await get_or_create_session_for_plan_item(db_session, user, study_plan_item.id)
    second = await get_or_create_session_for_plan_item(db_session, user, study_plan_item.id)

    assert first.id == second.id


@pytest.mark.asyncio
async def test_user_message_creates_practice_event(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> None:
    from backend.app.schemas.practice import PracticeMessageCreate
    from backend.app.services.practice_session_service import append_user_message

    result = await append_user_message(
        db_session,
        user,
        practice_session.id,
        PracticeMessageCreate(intent="describe_idea", content_md="我先讲暴力解法。"),
    )

    assert result.event_id > 0
    assert result.session_id == practice_session.id
    assert result.run_id == 0


@pytest.mark.asyncio
async def test_code_snapshot_hash_is_sha256(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> None:
    from hashlib import sha256

    from backend.app.schemas.practice import CodeSnapshotCreate
    from backend.app.services.practice_session_service import save_code_snapshot

    code_text = "class Solution:\n    pass\n"
    result = await save_code_snapshot(
        db_session,
        user,
        practice_session.id,
        CodeSnapshotCreate(
            language="python3",
            code_text=code_text,
            source="manual_save",
            client_revision=1,
        ),
    )

    assert result.code_hash == sha256(code_text.encode("utf-8")).hexdigest()
    saved = await db_session.get(CodeSnapshot, result.id)
    assert saved is not None
    assert saved.session_id == practice_session.id


@pytest.mark.asyncio
async def test_submission_feedback_updates_session_phase(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> None:
    from backend.app.schemas.practice import SubmissionFeedbackCreate
    from backend.app.services.practice_session_service import record_submission_feedback

    result = await record_submission_feedback(
        db_session,
        user,
        practice_session.id,
        SubmissionFeedbackCreate(result="wa", failed_case_text="case 1"),
    )

    assert result.event_id > 0
    await db_session.refresh(practice_session)
    assert practice_session.phase == "analyze_feedback"

    await record_submission_feedback(
        db_session,
        user,
        practice_session.id,
        SubmissionFeedbackCreate(result="ac"),
    )

    await db_session.refresh(practice_session)
    assert practice_session.phase == "summarize"
