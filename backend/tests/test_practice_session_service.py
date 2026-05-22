from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import backend.app.models.llm_run  # noqa: F401
from backend.app.models.auth import AppUser
from backend.app.models.learning import (
    StudyPlan,
    StudyPlanItem,
    StudyPlanStage,
    StudyPlanVersion,
)
from backend.app.models.practice import (
    CodeSnapshot,
    PracticeEvent,
    PracticeSession,
    SubmissionFeedback,
    UserProfileSnapshot,
)
from backend.app.models.problem import Base, Problem


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
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


async def save_python_snapshot(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> int:
    from backend.app.schemas.practice import CodeSnapshotCreate
    from backend.app.services.practice_session_service import save_code_snapshot

    result = await save_code_snapshot(
        db_session,
        user,
        practice_session.id,
        CodeSnapshotCreate(
            language="python3",
            code_text="class Solution:\n    pass\n",
            source="manual_save",
            client_revision=1,
        ),
    )
    return result.id


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

    snapshot_id = await save_python_snapshot(db_session, user, practice_session)

    result = await record_submission_feedback(
        db_session,
        user,
        practice_session.id,
        SubmissionFeedbackCreate(
            code_snapshot_id=snapshot_id,
            result="wa",
            failed_case_text="case 1",
        ),
    )

    assert result.event_id > 0
    await db_session.refresh(practice_session)
    assert practice_session.phase == "analyze_feedback"

    await record_submission_feedback(
        db_session,
        user,
        practice_session.id,
        SubmissionFeedbackCreate(code_snapshot_id=snapshot_id, result="ac"),
    )

    await db_session.refresh(practice_session)
    assert practice_session.phase == "summarize"


@pytest.mark.asyncio
async def test_submission_feedback_without_explicit_snapshot_uses_latest_snapshot(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> None:
    from backend.app.schemas.practice import SubmissionFeedbackCreate
    from backend.app.services.practice_session_service import record_submission_feedback

    snapshot_id = await save_python_snapshot(db_session, user, practice_session)

    result = await record_submission_feedback(
        db_session,
        user,
        practice_session.id,
        SubmissionFeedbackCreate(result="wa"),
    )

    assert result.code_snapshot_id == snapshot_id
    saved_feedback = await db_session.get(SubmissionFeedback, result.id)
    assert saved_feedback is not None
    assert saved_feedback.code_snapshot_id == snapshot_id


@pytest.mark.asyncio
async def test_submission_feedback_without_any_snapshot_is_rejected(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> None:
    from backend.app.schemas.practice import SubmissionFeedbackCreate
    from backend.app.services.practice_session_service import (
        PracticeSessionError,
        record_submission_feedback,
    )

    with pytest.raises(
        PracticeSessionError,
        match="code_snapshot_required_for_submission_feedback",
    ):
        await record_submission_feedback(
            db_session,
            user,
            practice_session.id,
            SubmissionFeedbackCreate(result="wa"),
        )


@pytest.mark.asyncio
async def test_submission_feedback_phase_change_creates_phase_changed_event(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> None:
    from sqlalchemy import select

    from backend.app.schemas.practice import SubmissionFeedbackCreate
    from backend.app.services.practice_session_service import record_submission_feedback

    snapshot_id = await save_python_snapshot(db_session, user, practice_session)

    result = await record_submission_feedback(
        db_session,
        user,
        practice_session.id,
        SubmissionFeedbackCreate(code_snapshot_id=snapshot_id, result="wa"),
    )

    event_result = await db_session.execute(
        select(PracticeEvent).where(
            PracticeEvent.session_id == practice_session.id,
            PracticeEvent.event_type == "phase_changed",
        )
    )
    phase_event = event_result.scalar_one()
    assert phase_event.role == "system"
    assert phase_event.phase == "analyze_feedback"
    assert phase_event.payload_json == {
        "phase_before": "understand_problem",
        "phase_after": "analyze_feedback",
        "reason": "submission_feedback",
        "feedback_id": result.id,
        "result": "wa",
    }


@pytest.mark.asyncio
async def test_profile_snapshot_json_uses_safe_prompt_payload(
    db_session: AsyncSession,
    user: AppUser,
    study_plan_item: StudyPlanItem,
) -> None:
    from backend.app.services.practice_session_service import get_or_create_session_for_plan_item

    snapshot = UserProfileSnapshot(
        user_id=user.id,
        version_number=1,
        source="initial_goal_plan",
        confidence="low",
        overall_level="unknown",
        preferred_training_mode="independent",
        ability_profile_json={},
        skill_profile_json={"strong_skill_tags": [], "weak_skill_tags": []},
        stuck_point_profile_json={"weak_stuck_points": []},
        strategy_json={
            "hint_policy_hint": "safe hint",
            "prompt": "sensitive prompt",
            "nested": {"full_code": "secret code", "safe": "kept"},
        },
        recent_summary_md="recent",
        evidence_summary_json=[
            {
                "source": "summary",
                "summary": "safe evidence",
                "full_solution": "secret solution",
            }
        ],
        created_at=datetime.now(UTC),
    )
    db_session.add(snapshot)
    await db_session.commit()

    session = await get_or_create_session_for_plan_item(
        db_session,
        user,
        study_plan_item.id,
    )

    assert session.profile_snapshot_json["id"] == snapshot.id
    assert "prompt" not in session.profile_snapshot_json["coach_strategy"]
    assert "full_code" not in session.profile_snapshot_json["coach_strategy"]["nested"]
    assert "safe" in session.profile_snapshot_json["coach_strategy"]["nested"]
    assert "full_solution" not in session.profile_snapshot_json["evidence"][0]
