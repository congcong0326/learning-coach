from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
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
    ProfileDelta,
    SessionSummary,
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
    study_plan_item: StudyPlanItem,
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
    await db_session.refresh(study_plan_item)
    assert study_plan_item.status == "in_progress"


@pytest.mark.asyncio
async def test_user_message_locks_session_before_touching_activity(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.schemas.practice import PracticeMessageCreate
    from backend.app.services import practice_session_service

    calls: list[int] = []
    original = practice_session_service._load_session_for_update

    async def tracking_load_session_for_update(
        session: AsyncSession,
        selected_user: AppUser,
        session_id: int,
    ) -> PracticeSession:
        calls.append(session_id)
        return await original(session, selected_user, session_id)

    monkeypatch.setattr(
        practice_session_service,
        "_load_session_for_update",
        tracking_load_session_for_update,
    )

    await practice_session_service.append_user_message(
        db_session,
        user,
        practice_session.id,
        PracticeMessageCreate(intent="describe_idea", content_md="我先讲暴力解法。"),
    )

    assert calls == [practice_session.id]


@pytest.mark.asyncio
async def test_existing_plan_problem_reentry_locks_session_before_touching_plan_entry(
    db_session: AsyncSession,
    user: AppUser,
    study_plan_item: StudyPlanItem,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.services import practice_session_service

    first = await practice_session_service.get_or_create_session_for_plan_item(
        db_session,
        user,
        study_plan_item.id,
    )
    calls: list[tuple[int, int, int]] = []

    async def tracking_find_existing_session_for_update(
        session: AsyncSession,
        selected_user: AppUser,
        study_plan_id: int,
        problem_id: int,
    ) -> PracticeSession | None:
        calls.append((selected_user.id, study_plan_id, problem_id))
        return await practice_session_service._load_session_for_update(
            session,
            selected_user,
            first.id,
        )

    monkeypatch.setattr(
        practice_session_service,
        "_find_existing_session_for_update",
        tracking_find_existing_session_for_update,
        raising=False,
    )

    second = await practice_session_service.get_or_create_session_for_plan_item(
        db_session,
        user,
        study_plan_item.id,
    )

    assert second.id == first.id
    assert calls == [(user.id, first.study_plan_id, first.problem_id)]


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
async def test_session_payload_includes_code_attempts(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> None:
    from backend.app.services.practice_session_service import get_session_payload

    snapshot_id = await save_python_snapshot(db_session, user, practice_session)
    result = await db_session.execute(
        select(PracticeEvent).where(
            PracticeEvent.session_id == practice_session.id,
            PracticeEvent.event_type == "code_saved",
        )
    )
    event = result.scalar_one()
    event.payload_json = {
        **event.payload_json,
        "snapshot_id": snapshot_id,
        "quality_status": "ready_to_submit",
        "quality_comment": "哈希表维护正确，可以去 LeetCode 尝试提交。",
    }
    await db_session.commit()

    payload = await get_session_payload(db_session, user, practice_session.id)

    assert len(payload.code_attempts) == 1
    attempt = payload.code_attempts[0]
    assert attempt.snapshot_id == snapshot_id
    assert attempt.language == "python3"
    assert attempt.source == "manual_save"
    assert attempt.quality_status == "ready_to_submit"
    assert attempt.quality_comment == "哈希表维护正确，可以去 LeetCode 尝试提交。"
    assert attempt.code_preview == "class Solution:\n    pass"


@pytest.mark.asyncio
async def test_session_payload_includes_full_code_attempt_text(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> None:
    from backend.app.schemas.practice import CodeSnapshotCreate
    from backend.app.services.practice_session_service import (
        get_session_payload,
        save_code_snapshot,
    )

    long_code = (
        "class Solution:\n"
        "    def twoSum(self, nums, target):\n"
        "        seen = {}\n"
        + "\n".join(f"        # preserve full submitted code line {index}" for index in range(80))
        + "\n        return []\n"
    )
    result = await save_code_snapshot(
        db_session,
        user,
        practice_session.id,
        CodeSnapshotCreate(
            language="python3",
            code_text=long_code,
            source="manual_save",
            client_revision=2,
        ),
    )

    payload = await get_session_payload(db_session, user, practice_session.id)

    attempt = next(
        code_attempt
        for code_attempt in payload.code_attempts
        if code_attempt.snapshot_id == result.id
    )
    assert attempt.code_text == long_code
    assert "preserve full submitted code line 79" in attempt.code_text
    assert "preserve full submitted code line 79" not in attempt.code_preview


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
async def test_session_payload_includes_submission_feedback_history(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> None:
    from backend.app.schemas.practice import SubmissionFeedbackCreate
    from backend.app.services.practice_session_service import (
        get_session_payload,
        record_submission_feedback,
    )

    snapshot_id = await save_python_snapshot(db_session, user, practice_session)

    await record_submission_feedback(
        db_session,
        user,
        practice_session.id,
        SubmissionFeedbackCreate(
            code_snapshot_id=snapshot_id,
            result="wa",
            failed_case_text="nums = [3,3], target = 6",
            error_message="expected [0,1], got []",
            note_md="我怀疑是哈希表更新顺序。",
        ),
    )

    payload = await get_session_payload(db_session, user, practice_session.id)

    assert len(payload.submission_feedbacks) == 1
    feedback = payload.submission_feedbacks[0]
    assert feedback.result == "wa"
    assert feedback.failed_case_text == "nums = [3,3], target = 6"
    assert feedback.error_message == "expected [0,1], got []"
    assert feedback.note_md == "我怀疑是哈希表更新顺序。"


@pytest.mark.asyncio
async def test_ac_submission_feedback_without_code_snapshot_is_allowed(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
    study_plan_item: StudyPlanItem,
) -> None:
    from backend.app.schemas.practice import SubmissionFeedbackCreate
    from backend.app.services.practice_session_service import record_submission_feedback

    result = await record_submission_feedback(
        db_session,
        user,
        practice_session.id,
        SubmissionFeedbackCreate(result="ac"),
    )

    await db_session.refresh(practice_session)
    assert result.result == "ac"
    assert result.code_snapshot_id is None
    assert practice_session.final_result == "ac"
    assert practice_session.phase == "summarize"
    assert practice_session.status == "summarizing"
    await db_session.refresh(study_plan_item)
    assert study_plan_item.status == "completed"


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


@pytest.mark.asyncio
async def test_session_summary_profile_update_creates_summary_delta_and_snapshot(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> None:
    from backend.app.services.profile_service import (
        persist_session_summary_profile_update,
    )

    previous_snapshot_id = practice_session.profile_snapshot_id

    result = await persist_session_summary_profile_update(
        db_session,
        user_id=user.id,
        session_id=practice_session.id,
    )

    summary = await db_session.get(SessionSummary, result.summary_id)
    delta = await db_session.get(ProfileDelta, result.delta_id)
    snapshot = await db_session.get(UserProfileSnapshot, result.next_snapshot_id)

    assert summary is not None
    assert delta is not None
    assert snapshot is not None
    assert result.accepted is True
    assert summary.session_id == practice_session.id
    assert summary.profile_update_suggestion_json == delta.patch_json
    assert delta.status == "accepted"
    assert delta.previous_snapshot_id == previous_snapshot_id
    assert delta.next_snapshot_id == snapshot.id
    assert snapshot.version_number == 2
    assert snapshot.created_from_summary_id == summary.id
    assert delta.evidence_json[0]["source"] == "session_summary"
    assert delta.evidence_json[0]["summary_id"] == summary.id


@pytest.mark.asyncio
async def test_session_summary_contains_required_training_facts(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> None:
    from backend.app.schemas.practice import SubmissionFeedbackCreate
    from backend.app.services.practice_session_service import record_submission_feedback
    from backend.app.services.profile_service import (
        persist_session_summary_profile_update,
    )

    snapshot_id = await save_python_snapshot(db_session, user, practice_session)
    await record_submission_feedback(
        db_session,
        user,
        practice_session.id,
        SubmissionFeedbackCreate(
            code_snapshot_id=snapshot_id,
            result="wa",
            failed_case_text="[3,3], target=6",
            error_message="expected [0,1]",
            note_md="怀疑重复元素边界没有处理好。",
        ),
    )
    await record_submission_feedback(
        db_session,
        user,
        practice_session.id,
        SubmissionFeedbackCreate(
            code_snapshot_id=snapshot_id,
            result="ac",
        ),
    )

    result = await persist_session_summary_profile_update(
        db_session,
        user_id=user.id,
        session_id=practice_session.id,
    )
    summary = await db_session.get(SessionSummary, result.summary_id)

    assert summary is not None
    assert summary.final_submission_result == "ac"
    assert "wa" in summary.error_types_json
    assert summary.review_summary_md
    assert summary.invariant_summary_md
    assert summary.complexity_analysis_json["status"] == "needs_user_confirmation"
    assert summary.profile_signals_json["evidence"]
    assert summary.next_recommendation_json["reason"]
    assert summary.next_recommendation_json["first_question_hint"]
    assert "class Solution" not in str(summary.profile_signals_json)


@pytest.mark.asyncio
async def test_practice_dashboard_returns_completed_stuck_hint_and_profile(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> None:
    from backend.app.schemas.practice import SubmissionFeedbackCreate
    from backend.app.services.practice_session_service import (
        get_practice_dashboard,
        record_submission_feedback,
    )
    from backend.app.services.profile_service import (
        persist_session_summary_profile_update,
    )

    snapshot_id = await save_python_snapshot(db_session, user, practice_session)
    practice_session.max_hint_level_used = "key_hint"
    await db_session.commit()
    await record_submission_feedback(
        db_session,
        user,
        practice_session.id,
        SubmissionFeedbackCreate(
            code_snapshot_id=snapshot_id,
            result="wa",
            failed_case_text="[3,3], target=6",
        ),
    )
    await record_submission_feedback(
        db_session,
        user,
        practice_session.id,
        SubmissionFeedbackCreate(code_snapshot_id=snapshot_id, result="ac"),
    )
    await persist_session_summary_profile_update(
        db_session,
        user_id=user.id,
        session_id=practice_session.id,
    )

    dashboard = await get_practice_dashboard(db_session, user)

    assert dashboard.completed_problem_count == 1
    assert dashboard.common_stuck_points[0]["stuck_point"] == "submission_wa"
    assert dashboard.highest_hint_level == "key_hint"
    assert dashboard.average_hint_gear == 2
    assert dashboard.recent_profile_summary


@pytest.mark.asyncio
async def test_session_review_returns_summary_profile_and_recommendation(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> None:
    from backend.app.services.practice_session_service import get_session_review
    from backend.app.services.profile_service import (
        persist_session_summary_profile_update,
    )

    practice_session.final_result = "ac"
    practice_session.phase = "summarize"
    practice_session.attempt_count = 2
    await db_session.commit()
    summary_result = await persist_session_summary_profile_update(
        db_session,
        user_id=user.id,
        session_id=practice_session.id,
    )

    review = await get_session_review(db_session, user, practice_session.id)

    assert review.session_id == practice_session.id
    assert review.summary_id == summary_result.summary_id
    assert review.final_result == "ac"
    assert "summarize" in review.phases_visited
    assert review.next_recommendation["review_focus"]
    assert review.profile_delta["status"] == "accepted"


@pytest.mark.asyncio
async def test_session_summary_profile_update_updates_one_summary_per_session(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> None:
    from backend.app.services.profile_service import (
        persist_session_summary_profile_update,
    )

    first = await persist_session_summary_profile_update(
        db_session,
        user_id=user.id,
        session_id=practice_session.id,
    )
    practice_session.final_result = "ac"
    second = await persist_session_summary_profile_update(
        db_session,
        user_id=user.id,
        session_id=practice_session.id,
    )

    summaries = (
        await db_session.execute(
            select(SessionSummary).where(SessionSummary.session_id == practice_session.id)
        )
    ).scalars().all()

    assert len(summaries) == 1
    assert first.summary_id == second.summary_id
    assert summaries[0].final_submission_result == "ac"


@pytest.mark.asyncio
async def test_session_summary_profile_update_rejects_delta_without_evidence(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> None:
    from backend.app.services.profile_service import (
        persist_session_summary_profile_update,
    )

    result = await persist_session_summary_profile_update(
        db_session,
        user_id=user.id,
        session_id=practice_session.id,
        summary_payload={"evidence_json": []},
    )

    delta = await db_session.get(ProfileDelta, result.delta_id)

    assert result.accepted is False
    assert result.next_snapshot_id is None
    assert delta is not None
    assert delta.status == "rejected"
    assert delta.next_snapshot_id is None
    assert delta.rejection_reason == "profile_delta_missing_evidence"


@pytest.mark.asyncio
async def test_session_summary_profile_update_sanitizes_explicit_delta_evidence(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> None:
    from backend.app.services.profile_service import (
        persist_session_summary_profile_update,
    )

    result = await persist_session_summary_profile_update(
        db_session,
        user_id=user.id,
        session_id=practice_session.id,
        summary_payload={
            "evidence_json": [
                {
                    "source": "session_summary",
                    "summary": "保留安全复盘证据",
                    "session_id": practice_session.id,
                    "code_text": "完整代码不应进入画像证据",
                    "raw_chat": "完整聊天不应进入画像证据",
                }
            ]
        },
    )

    delta = await db_session.get(ProfileDelta, result.delta_id)

    assert delta is not None
    assert delta.evidence_json == [
        {
            "session_id": practice_session.id,
            "source": "session_summary",
            "summary": "保留安全复盘证据",
        }
    ]
    assert "完整代码" not in str(delta.evidence_json)
    assert "完整聊天" not in str(delta.evidence_json)
