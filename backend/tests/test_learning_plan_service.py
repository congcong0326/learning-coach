from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import backend.app.models.llm_run  # noqa: F401
from backend.app.models.auth import AppUser
from backend.app.models.learning import (
    GoalCalibrationDraft,
    PlanChangeLog,
    ProfilePlanEnrichmentDraft,
    StudyPlan,
    StudyPlanItem,
    StudyPlanStage,
    StudyPlanVersion,
)
from backend.app.models.practice import PracticeEvent, PracticeSession
from backend.app.models.problem import Base, Problem
from backend.app.schemas.learning import (
    FollowupAnswer,
    GoalCalibrationInput,
    PlanAdjustmentRequest,
    ProfilePlanEnrichmentDraftResponse,
    ProfilePlanEnrichmentRequest,
    StudyPlanResponse,
)
from backend.app.services.learning_plan_llm import PROMPT_VERSION
from backend.app.services.study_plan_service import (
    StudyPlanError,
    activate_plan_version,
    activate_plan,
    answer_goal_followup,
    clone_adjusted_version,
    confirm_plan_draft,
    create_adjustment_draft,
    generate_goal_plan_draft,
    get_active_plan_version,
    get_current_study_plan_payload,
    list_study_plans,
    reorder_stage_items,
    start_goal_calibration,
    study_plan_payload,
    update_plan_item_status,
)


def test_learning_tables_are_registered_in_metadata() -> None:
    table_names = {
        GoalCalibrationDraft.__tablename__,
        StudyPlan.__tablename__,
        StudyPlanVersion.__tablename__,
        StudyPlanStage.__tablename__,
        StudyPlanItem.__tablename__,
        PlanChangeLog.__tablename__,
        ProfilePlanEnrichmentDraft.__tablename__,
    }

    assert table_names == {
        "goal_calibration_draft",
        "study_plan",
        "study_plan_version",
        "study_plan_stage",
        "study_plan_item",
        "plan_change_log",
        "profile_plan_enrichment_draft",
    }


def test_profile_plan_enrichment_draft_has_auditable_context_fields() -> None:
    columns = ProfilePlanEnrichmentDraft.__table__.columns

    assert "user_id" in columns
    assert "study_plan_id" in columns
    assert "study_plan_version_id" in columns
    assert "profile_snapshot_id" in columns
    assert "llm_run_id" in columns
    assert "status" in columns
    assert "user_intent_md" in columns
    assert "item_count" in columns
    assert "difficulty_preference" in columns
    assert "context_summary_json" in columns
    assert "candidate_problem_ids_json" in columns
    assert "model_output_json" in columns
    assert "validation_report_json" in columns
    assert "confirmed_item_ids_json" in columns
    assert "error_summary" in columns
    assert "confirmed_at" in columns


def test_profile_plan_enrichment_request_accepts_supported_item_counts() -> None:
    for item_count in [2, 3, 5]:
        payload = ProfilePlanEnrichmentRequest(item_count=cast(Any, item_count))

        assert payload.item_count == item_count


def test_profile_plan_enrichment_request_rejects_unsupported_item_count() -> None:
    with pytest.raises(ValidationError):
        ProfilePlanEnrichmentRequest(item_count=cast(Any, 4))


def test_profile_plan_enrichment_response_rejects_unsupported_item_count() -> None:
    now = datetime.now(UTC)

    with pytest.raises(ValidationError):
        ProfilePlanEnrichmentDraftResponse(
            draft_id=1,
            status="generated",
            plan_id=1,
            plan_version_id=1,
            profile_snapshot_id=None,
            user_intent_md="",
            item_count=cast(Any, 4),
            difficulty_preference="keep_current",
            items=[],
            created_at=now,
            updated_at=now,
        )


def test_confirmed_version_fk_is_named_and_deferred() -> None:
    foreign_keys = list(GoalCalibrationDraft.__table__.foreign_keys)
    confirmed_version_fk = next(
        fk for fk in foreign_keys if fk.parent.name == "confirmed_version_id"
    )

    assert confirmed_version_fk.constraint is not None
    assert confirmed_version_fk.constraint.name == "fk_goal_draft_confirmed_version"
    assert confirmed_version_fk.constraint.use_alter is True


def test_confirmed_plan_and_version_are_linked_by_composite_fk() -> None:
    draft_table = cast(Table, GoalCalibrationDraft.__table__)
    version_table = cast(Table, StudyPlanVersion.__table__)
    draft_constraints = {
        constraint.name: constraint
        for constraint in draft_table.foreign_key_constraints
    }
    confirmed_version_fk = draft_constraints["fk_goal_draft_confirmed_version"]

    assert confirmed_version_fk.use_alter is True
    assert [element.parent.name for element in confirmed_version_fk.elements] == [
        "confirmed_version_id",
        "confirmed_plan_id",
    ]
    assert [element.column.name for element in confirmed_version_fk.elements] == [
        "id",
        "plan_id",
    ]

    version_unique_constraints = {
        constraint.name for constraint in version_table.constraints
    }
    assert "uq_study_plan_version_id_plan" in version_unique_constraints

    draft_constraint_names = {
        constraint.name for constraint in draft_table.constraints
    }
    assert "ck_goal_draft_confirmed_pair" in draft_constraint_names


def test_default_empty_learning_columns_have_server_defaults() -> None:
    columns = [
        GoalCalibrationDraft.__table__.c.followup_messages_json,
        GoalCalibrationDraft.__table__.c.draft_goal_json,
        GoalCalibrationDraft.__table__.c.draft_plan_json,
        GoalCalibrationDraft.__table__.c.validation_report_json,
        GoalCalibrationDraft.__table__.c.repair_log_json,
        GoalCalibrationDraft.__table__.c.prompt_version,
        GoalCalibrationDraft.__table__.c.model_name,
        GoalCalibrationDraft.__table__.c.error_message,
        StudyPlanVersion.__table__.c.generation_summary_md,
        StudyPlanVersion.__table__.c.adjustment_summary_md,
        StudyPlanVersion.__table__.c.validation_report_json,
        StudyPlanVersion.__table__.c.repair_log_json,
        StudyPlanStage.__table__.c.focus_tags_json,
        StudyPlanStage.__table__.c.assessment_criteria_json,
        StudyPlanItem.__table__.c.skill_tags_json,
        PlanChangeLog.__table__.c.detail_json,
        PlanChangeLog.__table__.c.reason_md,
    ]

    assert all(column.server_default is not None for column in columns)


def test_study_plan_item_stage_fk_includes_version_guard() -> None:
    item_table = cast(Table, StudyPlanItem.__table__)
    stage_table = cast(Table, StudyPlanStage.__table__)
    constraints = {
        constraint.name: constraint for constraint in item_table.foreign_key_constraints
    }
    stage_version_fk = constraints["fk_study_plan_item_stage_version"]

    assert [element.parent.name for element in stage_version_fk.elements] == [
        "stage_id",
        "version_id",
    ]
    assert [element.column.name for element in stage_version_fk.elements] == [
        "id",
        "version_id",
    ]

    stage_unique_constraints = {
        constraint.name for constraint in stage_table.constraints
    }
    assert "uq_study_plan_stage_id_version" in stage_unique_constraints

def test_goal_calibration_accepts_supported_languages() -> None:
    for language in ["c", "go", "python3", "javascript", "java"]:
        payload = GoalCalibrationInput(
            goal_type="interview_sprint",
            target_timeline="one_to_three_months",
            weekly_days=4,
            session_minutes=60,
            current_level="medium_partial",
            preferred_language=cast(Any, language),
            self_reported_weaknesses=["pattern", "edge_case"],
            extra_notes="3 months until interview",
            training_preference="independent_first",
        )
        assert payload.preferred_language == language


def test_goal_calibration_rejects_unsupported_language() -> None:
    with pytest.raises(ValidationError):
        GoalCalibrationInput(
            goal_type="interview_sprint",
            target_timeline="one_to_three_months",
            weekly_days=4,
            session_minutes=60,
            current_level="medium_partial",
            preferred_language=cast(Any, "ruby"),
            self_reported_weaknesses=[],
            training_preference="guided",
        )


@pytest_asyncio.fixture
async def learning_session_factory() -> AsyncGenerator[
    async_sessionmaker[AsyncSession],
    None,
]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def problem(slug: str, *, difficulty: str = "Easy") -> Problem:
    now = datetime.now(UTC)
    return Problem(
        frontend_id=slug,
        slug=slug,
        title=slug.replace("-", " ").title(),
        translated_title=slug,
        difficulty=difficulty,
        statement_md="# statement",
        metadata_json={
            "topic_tags": [
                {"slug": "array", "name": "Array", "translated_name": "数组"}
            ]
        },
        leetcode_url=f"https://leetcode.cn/problems/{slug}/",
        is_paid_only=False,
        created_at=now,
        updated_at=now,
    )


async def create_learning_user(session: AsyncSession) -> AppUser:
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
    session.add(user)
    await session.flush()
    session.add(problem("two-sum"))
    session.add(problem("valid-parentheses", difficulty="Medium"))
    session.add(problem("merge-intervals", difficulty="Medium"))
    session.add(problem("binary-search", difficulty="Easy"))
    session.add(problem("climbing-stairs", difficulty="Easy"))
    await session.commit()
    await session.refresh(user)
    return user


def draft_plan_json(title: str = "学习计划") -> dict[str, Any]:
    return {
        "title": title,
        "generation_summary_md": "按当前目标生成的训练计划",
        "stages": [
            {
                "title": "基础巩固",
                "objective_md": "巩固高频基础模式",
                "focus_tags": ["array", "stack"],
                "assessment_criteria": ["能解释核心思路"],
                "items": [
                    {
                        "problem_slug": "two-sum",
                        "skill_tags": ["array"],
                        "suggested_mode": "guided",
                        "recommendation_reason": "练习哈希表补数",
                    },
                    {
                        "problem_slug": "valid-parentheses",
                        "skill_tags": ["stack"],
                        "suggested_mode": "independent",
                        "recommendation_reason": "练习栈匹配",
                    },
                ],
            }
        ],
    }


def duplicate_plan_json() -> dict[str, Any]:
    plan = draft_plan_json("重复计划")
    plan["stages"][0]["items"].append(
        {
            "problem_slug": "two-sum",
            "skill_tags": ["array"],
            "suggested_mode": "guided",
            "recommendation_reason": "重复题目",
        }
    )
    return plan


def multi_stage_plan_json(title: str = "多阶段计划") -> dict[str, Any]:
    return {
        "title": title,
        "generation_summary_md": "多阶段训练计划",
        "stages": [
            {
                "title": "基础阶段",
                "objective_md": "先练基础数据结构",
                "focus_tags": ["array", "stack"],
                "assessment_criteria": ["能稳定写出基础题"],
                "items": [
                    {
                        "problem_slug": "two-sum",
                        "skill_tags": ["array"],
                        "suggested_mode": "guided",
                        "recommendation_reason": "练习哈希表",
                    },
                    {
                        "problem_slug": "valid-parentheses",
                        "skill_tags": ["stack"],
                        "suggested_mode": "independent",
                        "recommendation_reason": "练习栈",
                    },
                ],
            },
            {
                "title": "进阶阶段",
                "objective_md": "补充区间和二分",
                "focus_tags": ["interval", "binary-search"],
                "assessment_criteria": ["能识别进阶模式"],
                "items": [
                    {
                        "problem_slug": "merge-intervals",
                        "skill_tags": ["interval"],
                        "suggested_mode": "guided",
                        "recommendation_reason": "练习区间",
                    },
                    {
                        "problem_slug": "binary-search",
                        "skill_tags": ["binary-search"],
                        "suggested_mode": "independent",
                        "recommendation_reason": "练习二分",
                    },
                ],
            },
        ],
    }


def replacement_plan_json() -> dict[str, Any]:
    return {
        "title": "替换计划",
        "generation_summary_md": "替换后的训练计划",
        "stages": [
            {
                "title": "新增阶段",
                "objective_md": "新增动态规划入门",
                "focus_tags": ["dp"],
                "assessment_criteria": ["能解释状态转移"],
                "items": [
                    {
                        "problem_slug": "climbing-stairs",
                        "skill_tags": ["dp"],
                        "suggested_mode": "guided",
                        "recommendation_reason": "补充动态规划",
                    }
                ],
            }
        ],
    }


def adjusted_plan_json() -> dict[str, Any]:
    return {
        "title": "调整计划",
        "generation_summary_md": "调整后的训练计划",
        "stages": [
            {
                "title": "补强区间",
                "objective_md": "补充区间题",
                "focus_tags": ["interval"],
                "assessment_criteria": ["能识别排序合并策略"],
                "items": [
                    {
                        "problem_slug": "merge-intervals",
                        "skill_tags": ["interval"],
                        "suggested_mode": "guided",
                        "recommendation_reason": "补强区间合并",
                    }
                ],
            }
        ],
    }


async def create_ready_draft(
    session: AsyncSession,
    user: AppUser,
    *,
    title: str = "学习计划",
    plan_json: dict[str, Any] | None = None,
) -> GoalCalibrationDraft:
    now = datetime.now(UTC)
    draft = GoalCalibrationDraft(
        user_id=user.id,
        input_json={"goal_type": "interview_sprint"},
        followup_messages_json=[],
        draft_goal_json={"goal_type": "interview_sprint", "weekly_days": 4},
        draft_plan_json=plan_json or draft_plan_json(title),
        validation_report_json={"valid": True},
        repair_log_json=[],
        prompt_version=PROMPT_VERSION,
        model_name="test-model",
        status="ready_for_review",
        error_message="",
        created_at=now,
        updated_at=now,
    )
    session.add(draft)
    await session.commit()
    await session.refresh(draft)
    return draft


def ordered_stages(version: StudyPlanVersion) -> list[StudyPlanStage]:
    return sorted(version.stages, key=lambda stage: stage.stage_index)


def ordered_items(stage: StudyPlanStage) -> list[StudyPlanItem]:
    return sorted(stage.items, key=lambda item: item.order_index)


def item_by_slug(version: StudyPlanVersion, slug: str) -> StudyPlanItem:
    return next(item for item in version.items if item.problem_slug == slug)


class FakeGoalCalibrationClient:
    def __init__(self) -> None:
        self.followup_calls = 0

    async def followup_question(
        self,
        payload: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        self.followup_calls += 1
        if self.followup_calls == 1:
            return {"question_id": "q1", "question": "你的面试时间是？"}
        return None

    async def plan_draft(
        self,
        payload: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return draft_plan_json()

    async def repair_plan_draft(
        self,
        payload: dict[str, Any],
        report: dict[str, Any],
        repair_log: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return draft_plan_json()


def goal_input() -> GoalCalibrationInput:
    return GoalCalibrationInput(
        goal_type="interview_sprint",
        target_timeline="one_to_three_months",
        weekly_days=4,
        session_minutes=60,
        current_level="medium_partial",
        preferred_language="python3",
        self_reported_weaknesses=["pattern"],
        extra_notes="",
        training_preference="independent_first",
    )


@pytest.mark.asyncio
async def test_goal_calibration_start_answer_and_generate_persists_draft(
    learning_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeGoalCalibrationClient()
    credential = SimpleNamespace(id=7, model_name="test-model")

    async def fake_client_for_user(
        session: AsyncSession,
        user: AppUser,
    ) -> tuple[FakeGoalCalibrationClient, SimpleNamespace]:
        return client, credential

    async def fake_generate_plan_with_repair(
        session: AsyncSession,
        client: FakeGoalCalibrationClient,
        payload: dict[str, Any],
        history: list[dict[str, Any]],
        *,
        max_repairs: int = 2,
        locked_problem_slugs: set[str] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        return (
            draft_plan_json(),
            {"valid": True, "issues": [], "item_count": 2},
            [{"reason": "problem_not_found", "replacement_problem_slug": "two-sum"}],
        )

    monkeypatch.setattr(
        "backend.app.services.study_plan_service.client_for_user",
        fake_client_for_user,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.app.services.study_plan_service.generate_plan_with_repair",
        fake_generate_plan_with_repair,
        raising=False,
    )

    async with learning_session_factory() as session:
        user = await create_learning_user(session)

        started = await start_goal_calibration(session, user, goal_input())
        answered = await answer_goal_followup(
            session,
            user,
            started["draft_id"],
            FollowupAnswer(question_id="q1", answer="两个月后"),
        )
        generated = await generate_goal_plan_draft(session, user, started["draft_id"])

        saved_draft = await session.get(GoalCalibrationDraft, started["draft_id"])
        assert saved_draft is not None
        assert started["followup_question"] == "你的面试时间是？"
        assert answered["status"] == "collecting_input"
        assert answered["followup_question"] is None
        assert answered["remaining_followups"] == 0
        assert generated["status"] == "ready_for_review"
        assert generated["stages"][0]["items"][0]["problem_slug"] == "two-sum"
        assert saved_draft.status == "ready_for_review"
        assert saved_draft.model_name == "test-model"
        assert saved_draft.repair_log_json


@pytest.mark.asyncio
async def test_goal_plan_generation_logs_validation_failure(
    learning_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    credential = SimpleNamespace(id=7, model_name="test-model")

    async def fake_client_for_user(
        session: AsyncSession,
        user: AppUser,
    ) -> tuple[FakeGoalCalibrationClient, SimpleNamespace]:
        return FakeGoalCalibrationClient(), credential

    async def fake_generate_plan_with_repair(
        session: AsyncSession,
        client: FakeGoalCalibrationClient,
        payload: dict[str, Any],
        history: list[dict[str, Any]],
        *,
        max_repairs: int = 2,
        locked_problem_slugs: set[str] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        return (
            draft_plan_json(),
            {"valid": False, "issues": ["empty_problem_library"], "item_count": 0},
            [],
        )

    monkeypatch.setattr(
        "backend.app.services.study_plan_service.client_for_user",
        fake_client_for_user,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.app.services.study_plan_service.generate_plan_with_repair",
        fake_generate_plan_with_repair,
        raising=False,
    )
    caplog.set_level(logging.WARNING, logger="backend.app.services.study_plan_service")

    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(session, user)
        draft.status = "collecting_input"
        await session.commit()

        with pytest.raises(StudyPlanError, match="empty_problem_library"):
            await generate_goal_plan_draft(session, user, draft.id)

        assert (
            "goal plan draft generation failed validation "
            f"draft_id={draft.id} user_id={user.id} credential_id=7 "
            "model=test-model issues=empty_problem_library item_count=0"
        ) in caplog.text


@pytest.mark.asyncio
async def test_goal_plan_generation_can_retry_failed_draft(
    learning_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential = SimpleNamespace(id=7, model_name="test-model")

    async def fake_client_for_user(
        session: AsyncSession,
        user: AppUser,
    ) -> tuple[FakeGoalCalibrationClient, SimpleNamespace]:
        return FakeGoalCalibrationClient(), credential

    async def fake_generate_plan_with_repair(
        session: AsyncSession,
        client: FakeGoalCalibrationClient,
        payload: dict[str, Any],
        history: list[dict[str, Any]],
        *,
        max_repairs: int = 2,
        locked_problem_slugs: set[str] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        return draft_plan_json(), {"valid": True, "issues": [], "item_count": 2}, []

    monkeypatch.setattr(
        "backend.app.services.study_plan_service.client_for_user",
        fake_client_for_user,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.app.services.study_plan_service.generate_plan_with_repair",
        fake_generate_plan_with_repair,
        raising=False,
    )

    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(session, user)
        draft.status = "failed"
        draft.error_message = "empty_problem_library"
        await session.commit()

        generated = await generate_goal_plan_draft(session, user, draft.id)

        saved_draft = await session.get(GoalCalibrationDraft, draft.id)
        assert saved_draft is not None
        assert generated["status"] == "ready_for_review"
        assert saved_draft.status == "ready_for_review"
        assert saved_draft.error_message == ""


@pytest.mark.asyncio
async def test_goal_plan_generation_returns_existing_ready_draft_without_llm(
    learning_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected_client_for_user(
        session: AsyncSession,
        user: AppUser,
    ) -> tuple[FakeGoalCalibrationClient, SimpleNamespace]:
        raise AssertionError("ready draft should not call LLM")

    monkeypatch.setattr(
        "backend.app.services.study_plan_service.client_for_user",
        unexpected_client_for_user,
        raising=False,
    )

    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(session, user)

        generated = await generate_goal_plan_draft(session, user, draft.id)

        assert generated["status"] == "ready_for_review"
        assert generated["stages"][0]["items"][0]["problem_slug"] == "two-sum"


@pytest.mark.asyncio
async def test_goal_plan_generation_regenerates_stale_ready_draft(
    learning_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential = SimpleNamespace(id=7, model_name="test-model")

    async def fake_client_for_user(
        session: AsyncSession,
        user: AppUser,
    ) -> tuple[FakeGoalCalibrationClient, SimpleNamespace]:
        return FakeGoalCalibrationClient(), credential

    async def fake_generate_plan_with_repair(
        session: AsyncSession,
        client: FakeGoalCalibrationClient,
        payload: dict[str, Any],
        history: list[dict[str, Any]],
        *,
        max_repairs: int = 2,
        locked_problem_slugs: set[str] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        plan = draft_plan_json("中文学习计划")
        return plan, {"valid": True, "issues": [], "item_count": 2}, []

    monkeypatch.setattr(
        "backend.app.services.study_plan_service.client_for_user",
        fake_client_for_user,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.app.services.study_plan_service.generate_plan_with_repair",
        fake_generate_plan_with_repair,
        raising=False,
    )

    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(session, user, title="Old English Plan")
        draft.prompt_version = "goal-plan-v1"
        await session.commit()

        generated = await generate_goal_plan_draft(session, user, draft.id)

        saved_draft = await session.get(GoalCalibrationDraft, draft.id)
        assert saved_draft is not None
        assert generated["generation_summary_md"] == "按当前目标生成的训练计划"
        assert saved_draft.prompt_version == PROMPT_VERSION
        assert saved_draft.draft_plan_json["title"] == "中文学习计划"


@pytest.mark.asyncio
async def test_create_adjustment_draft_and_activate_version_preserves_active_plan_until_confirmed(
    learning_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_client_for_user(
        session: AsyncSession,
        user: AppUser,
    ) -> tuple[FakeGoalCalibrationClient, SimpleNamespace]:
        return FakeGoalCalibrationClient(), SimpleNamespace(id=7, model_name="test-model")

    async def fake_generate_plan_with_repair(
        session: AsyncSession,
        client: FakeGoalCalibrationClient,
        payload: dict[str, Any],
        history: list[dict[str, Any]],
        *,
        max_repairs: int = 2,
        locked_problem_slugs: set[str] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        assert locked_problem_slugs == {"two-sum"}
        return replacement_plan_json(), {"valid": True, "issues": [], "item_count": 1}, []

    monkeypatch.setattr(
        "backend.app.services.study_plan_service.client_for_user",
        fake_client_for_user,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.app.services.study_plan_service.generate_plan_with_repair",
        fake_generate_plan_with_repair,
        raising=False,
    )

    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(session, user, plan_json=multi_stage_plan_json())
        plan = await confirm_plan_draft(session, user, draft.id)
        active_version = await get_active_plan_version(session, user, plan.id)
        item_by_slug(active_version, "two-sum").status = "completed"
        await session.commit()

        adjustment = await create_adjustment_draft(
            session,
            user,
            plan.id,
            PlanAdjustmentRequest(
                reason="strengthen_topic",
                notes="补强动态规划",
                preferred_language=None,
            ),
        )

        await session.refresh(plan)
        draft_version = await session.get(StudyPlanVersion, adjustment["draft_id"])
        assert draft_version is not None
        assert draft_version.status == "draft"
        assert plan.active_version_number == 1
        assert adjustment["stages"][0]["items"][0]["problem_slug"] == "two-sum"

        await activate_plan_version(session, user, plan.id, draft_version.id)

        await session.refresh(plan)
        await session.refresh(active_version)
        await session.refresh(draft_version)
        assert plan.active_version_number == 2
        assert active_version.status == "superseded"
        assert draft_version.status == "active"


@pytest.mark.asyncio
async def test_confirm_draft_creates_unique_active_plan(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        first_draft = await create_ready_draft(session, user, title="第一计划")
        first_plan = await confirm_plan_draft(session, user, first_draft.id)

        second_draft = await create_ready_draft(session, user, title="第二计划")
        second_plan = await confirm_plan_draft(session, user, second_draft.id)

        await session.refresh(first_plan)
        assert first_plan.status == "paused"
        assert second_plan.status == "active"
        assert second_draft.status == "confirmed"
        assert second_draft.confirmed_plan_id == second_plan.id


@pytest.mark.asyncio
async def test_confirm_draft_adds_context_to_duplicate_llm_titles(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        first_draft = await create_ready_draft(session, user, title="面试冲刺计划")
        first_draft.draft_goal_json = {
            "goal_type": "interview_sprint",
            "preferred_language": "python3",
        }
        first_draft.input_json = first_draft.draft_goal_json
        second_draft = await create_ready_draft(session, user, title="面试冲刺计划")
        second_draft.draft_goal_json = first_draft.draft_goal_json
        second_draft.input_json = first_draft.draft_goal_json
        await session.commit()

        first_plan = await confirm_plan_draft(session, user, first_draft.id)
        second_plan = await confirm_plan_draft(session, user, second_draft.id)

        assert first_plan.title.startswith("面试冲刺计划 · 面试冲刺 · Python3 · ")
        assert second_plan.title.startswith("面试冲刺计划 · 面试冲刺 · Python3 · ")
        assert second_plan.title != first_plan.title


@pytest.mark.asyncio
async def test_confirm_draft_returns_existing_plan_when_already_confirmed(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(session, user, title="已确认计划")
        first_plan = await confirm_plan_draft(session, user, draft.id)

        second_plan = await confirm_plan_draft(session, user, draft.id)

        assert second_plan.id == first_plan.id
        assert second_plan.status == "active"


@pytest.mark.asyncio
async def test_adjustment_clone_preserves_completed_items(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(session, user, title="原计划")
        plan = await confirm_plan_draft(session, user, draft.id)
        version = await get_active_plan_version(session, user, plan.id)
        completed_item = item_by_slug(version, "two-sum")
        completed_item.status = "completed"
        completed_item.locked = True
        await session.commit()

        new_version = await clone_adjusted_version(
            session,
            user,
            plan.id,
            adjustment_summary_md="完成题保留，补充数组题",
            draft_plan_json=adjusted_plan_json(),
            validation_report_json={"valid": True},
            repair_log_json=[],
        )

        preserved = item_by_slug(new_version, "two-sum")
        assert preserved.status == "completed"
        assert preserved.locked is True
        assert new_version.version_number == 2
        assert new_version.status == "active"
        assert plan.active_version_number == 2
        assert version.status == "superseded"


@pytest.mark.asyncio
async def test_plan_payload_lists_stages_items_and_current_plan(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(session, user, title="当前计划")
        plan = await confirm_plan_draft(session, user, draft.id)

        payload = await study_plan_payload(session, user, plan.id)
        current = await get_current_study_plan_payload(session, user)
        plans = await list_study_plans(session, user)

        assert payload["title"].startswith("当前计划 · 面试冲刺 · ")
        StudyPlanResponse.model_validate(payload)
        stages = payload["active_version"]["stages"]
        items = stages[0]["items"]
        assert items[0]["frontend_id"] == "two-sum"
        assert current["id"] == plan.id
        assert plans["items"] == [
            {
                "id": plan.id,
                "title": payload["title"],
                "status": "active",
                "active_version_number": 1,
                "created_at": plan.created_at,
                "updated_at": plan.updated_at,
            }
        ]


@pytest.mark.asyncio
async def test_confirm_draft_normalizes_suggested_mode_alias_before_payload(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        plan_json = draft_plan_json("别名计划")
        plan_json["stages"][0]["items"][0]["suggested_mode"] = "independent_first"
        draft = await create_ready_draft(session, user, plan_json=plan_json)

        plan = await confirm_plan_draft(session, user, draft.id)
        payload = await study_plan_payload(session, user, plan.id)

        StudyPlanResponse.model_validate(payload)
        first_item = payload["active_version"]["stages"][0]["items"][0]
        assert first_item["suggested_mode"] == "independent"


@pytest.mark.asyncio
async def test_plan_payload_normalizes_legacy_persisted_suggested_mode_alias(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(session, user, title="旧数据计划")
        plan = await confirm_plan_draft(session, user, draft.id)
        version = await get_active_plan_version(session, user, plan.id)
        item_by_slug(version, "two-sum").suggested_mode = "interviewer_style"
        await session.commit()

        payload = await study_plan_payload(session, user, plan.id)

        StudyPlanResponse.model_validate(payload)
        first_item = payload["active_version"]["stages"][0]["items"][0]
        assert first_item["suggested_mode"] == "mock_interview"


@pytest.mark.asyncio
async def test_plan_payload_projects_practice_progress_into_item_status(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(session, user)
        plan = await confirm_plan_draft(session, user, draft.id)
        version = await get_active_plan_version(session, user, plan.id)
        two_sum = item_by_slug(version, "two-sum")
        valid_parentheses = item_by_slug(version, "valid-parentheses")
        now = datetime.now(UTC)
        ac_session = PracticeSession(
            user_id=user.id,
            study_plan_id=plan.id,
            problem_id=two_sum.problem_id,
            problem_slug=two_sum.problem_slug,
            origin_plan_version_id=version.id,
            latest_plan_version_id=version.id,
            latest_plan_item_id=two_sum.id,
            training_mode=two_sum.suggested_mode,
            phase="summarize",
            status="summarizing",
            current_hint_level="questioning",
            visible_hint_gear=0,
            max_hint_level_used="questioning",
            attempt_count=1,
            final_result="ac",
            profile_snapshot_json={
                "version": "test",
                "source": "mock_from_goal_and_plan",
                "confidence": "low",
                "overall_level": "new",
                "preferred_training_mode": "guided",
            },
            started_at=now,
            last_activity_at=now,
            created_at=now,
            updated_at=now,
        )
        coding_session = PracticeSession(
            user_id=user.id,
            study_plan_id=plan.id,
            problem_id=valid_parentheses.problem_id,
            problem_slug=valid_parentheses.problem_slug,
            origin_plan_version_id=version.id,
            latest_plan_version_id=version.id,
            latest_plan_item_id=valid_parentheses.id,
            training_mode=valid_parentheses.suggested_mode,
            phase="review_code",
            status="active",
            current_hint_level="questioning",
            visible_hint_gear=0,
            max_hint_level_used="questioning",
            attempt_count=0,
            final_result="",
            profile_snapshot_json={
                "version": "test",
                "source": "mock_from_goal_and_plan",
                "confidence": "low",
                "overall_level": "new",
                "preferred_training_mode": "guided",
            },
            started_at=now,
            last_activity_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add_all([ac_session, coding_session])
        await session.flush()
        session.add(
            PracticeEvent(
                session_id=coding_session.id,
                user_id=user.id,
                event_type="user_message",
                role="user",
                phase=coding_session.phase,
                intent="describe_idea",
                content_md="我先写一个栈。",
                payload_json={},
                hint_level="questioning",
                visible_hint_gear=0,
                created_at=now,
            )
        )
        await session.commit()

        payload = await study_plan_payload(session, user, plan.id)
        items = {
            item["problem_slug"]: item
            for stage in payload["active_version"]["stages"]
            for item in stage["items"]
        }

        assert two_sum.status == "pending"
        assert valid_parentheses.status == "pending"
        assert items["two-sum"]["status"] == "completed"
        assert items["valid-parentheses"]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_update_plan_item_status_allows_only_pending_or_skipped_on_active_version(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(session, user)
        plan = await confirm_plan_draft(session, user, draft.id)
        version = await get_active_plan_version(session, user, plan.id)
        item = item_by_slug(version, "two-sum")

        returned_plan_id = await update_plan_item_status(
            session,
            user,
            item.id,
            "skipped",
        )

        assert returned_plan_id == plan.id
        await session.refresh(item)
        assert item.status == "skipped"
        with pytest.raises(StudyPlanError, match="invalid_plan_item_status"):
            await update_plan_item_status(session, user, item.id, "completed")


@pytest.mark.asyncio
async def test_reorder_stage_items_requires_exact_same_item_set(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(session, user)
        plan = await confirm_plan_draft(session, user, draft.id)
        version = await get_active_plan_version(session, user, plan.id)
        stage = ordered_stages(version)[0]
        ordered_ids = [item.id for item in ordered_items(stage)]

        returned_plan_id = await reorder_stage_items(
            session,
            user,
            stage.id,
            list(reversed(ordered_ids)),
        )

        assert returned_plan_id == plan.id
        await session.refresh(stage, attribute_names=["items"])
        assert [item.id for item in ordered_items(stage)] == list(
            reversed(ordered_ids)
        )
        with pytest.raises(StudyPlanError, match="stage_item_set_mismatch"):
            await reorder_stage_items(session, user, stage.id, ordered_ids[:1])


@pytest.mark.asyncio
async def test_activate_plan_pauses_other_active_plans(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        first_draft = await create_ready_draft(session, user, title="第一计划")
        first_plan = await confirm_plan_draft(session, user, first_draft.id)
        second_draft = await create_ready_draft(session, user, title="第二计划")
        second_plan = await confirm_plan_draft(session, user, second_draft.id)

        activated = await activate_plan(session, user, first_plan.id)

        await session.refresh(second_plan)
        assert activated.id == first_plan.id
        assert activated.status == "active"
        assert second_plan.status == "paused"


@pytest.mark.asyncio
async def test_get_current_study_plan_payload_repairs_duplicate_active_plans(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id: int
    first_plan_id: int
    second_plan_id: int
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        first_draft = await create_ready_draft(session, user, title="第一计划")
        first_plan = await confirm_plan_draft(session, user, first_draft.id)
        second_draft = await create_ready_draft(session, user, title="第二计划")
        second_plan = await confirm_plan_draft(session, user, second_draft.id)
        first_plan.status = "active"
        await session.commit()

        payload = await get_current_study_plan_payload(session, user)

        await session.refresh(first_plan)
        await session.refresh(second_plan)
        assert payload["id"] == second_plan.id
        assert first_plan.status == "paused"
        assert second_plan.status == "active"
        user_id = user.id
        first_plan_id = first_plan.id
        second_plan_id = second_plan.id

    async with learning_session_factory() as session:
        result = await session.execute(
            select(StudyPlan.id, StudyPlan.status)
            .where(StudyPlan.user_id == user_id)
            .order_by(StudyPlan.id.asc())
        )
        plan_statuses = {plan_id: status for plan_id, status in result.all()}

        assert plan_statuses[first_plan_id] == "paused"
        assert plan_statuses[second_plan_id] == "active"


@pytest.mark.asyncio
async def test_confirm_draft_rejects_duplicate_plan_items(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(
            session,
            user,
            plan_json=duplicate_plan_json(),
        )

        with pytest.raises(StudyPlanError, match="duplicate_plan_item"):
            await confirm_plan_draft(session, user, draft.id)


@pytest.mark.asyncio
async def test_adjustment_clone_preserves_cross_stage_item_order_and_logs_changes(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(
            session,
            user,
            plan_json=multi_stage_plan_json(),
        )
        plan = await confirm_plan_draft(session, user, draft.id)
        version = await get_active_plan_version(session, user, plan.id)
        item_by_slug(version, "two-sum").status = "completed"
        item_by_slug(version, "valid-parentheses").status = "in_progress"
        item_by_slug(version, "merge-intervals").status = "skipped"
        await session.commit()

        new_version = await clone_adjusted_version(
            session,
            user,
            plan.id,
            adjustment_summary_md="保留已开始题目，替换未开始题目",
            draft_plan_json=replacement_plan_json(),
            validation_report_json={"valid": True},
            repair_log_json=[],
        )

        stages = ordered_stages(new_version)
        assert [[item.problem_slug for item in ordered_items(stage)] for stage in stages] == [
            ["two-sum", "valid-parentheses"],
            ["merge-intervals"],
            ["climbing-stairs"],
        ]
        assert item_by_slug(new_version, "two-sum").status == "completed"
        assert item_by_slug(new_version, "valid-parentheses").status == "in_progress"
        assert item_by_slug(new_version, "merge-intervals").status == "skipped"
        result = await session.execute(
            select(PlanChangeLog.change_type).where(
                PlanChangeLog.version_id == new_version.id
            )
        )
        change_types = sorted(result.scalars().all())
        assert change_types.count("preserved") == 3
        assert "added" in change_types
        assert "removed" in change_types


@pytest.mark.asyncio
async def test_get_active_plan_version_uses_active_version_number_when_statuses_conflict(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first_version_id: int
    second_version_id: int
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(session, user, plan_json=multi_stage_plan_json())
        plan = await confirm_plan_draft(session, user, draft.id)
        first_version = await get_active_plan_version(session, user, plan.id)
        second_version = await clone_adjusted_version(
            session,
            user,
            plan.id,
            adjustment_summary_md="制造多 active 版本状态",
            draft_plan_json=replacement_plan_json(),
            validation_report_json={"valid": True},
            repair_log_json=[],
        )
        first_version.status = "active"
        await session.commit()

        active_version = await get_active_plan_version(session, user, plan.id)

        assert active_version.id == second_version.id
        await session.refresh(first_version)
        assert first_version.status == "superseded"
        first_version_id = first_version.id
        second_version_id = second_version.id

    async with learning_session_factory() as session:
        first_version_record = await session.get(StudyPlanVersion, first_version_id)
        second_version_record = await session.get(StudyPlanVersion, second_version_id)

        assert first_version_record is not None
        assert second_version_record is not None
        assert first_version_record.status == "superseded"
        assert second_version_record.status == "active"


@pytest.mark.asyncio
async def test_current_plan_payload_repairs_duplicate_active_versions(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first_version_id: int
    second_version_id: int
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(session, user, plan_json=multi_stage_plan_json())
        plan = await confirm_plan_draft(session, user, draft.id)
        first_version = await get_active_plan_version(session, user, plan.id)
        second_version = await clone_adjusted_version(
            session,
            user,
            plan.id,
            adjustment_summary_md="制造当前计划读取时的多 active 版本状态",
            draft_plan_json=replacement_plan_json(),
            validation_report_json={"valid": True},
            repair_log_json=[],
        )
        first_version.status = "active"
        await session.commit()

        payload = await get_current_study_plan_payload(session, user)

        assert payload["active_version"]["id"] == second_version.id
        first_version_id = first_version.id
        second_version_id = second_version.id

    async with learning_session_factory() as session:
        first_version_record = await session.get(StudyPlanVersion, first_version_id)
        second_version_record = await session.get(StudyPlanVersion, second_version_id)

        assert first_version_record is not None
        assert second_version_record is not None
        assert first_version_record.status == "superseded"
        assert second_version_record.status == "active"


@pytest.mark.asyncio
async def test_activate_plan_supersedes_other_active_versions(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(session, user, plan_json=multi_stage_plan_json())
        plan = await confirm_plan_draft(session, user, draft.id)
        first_version = await get_active_plan_version(session, user, plan.id)
        second_version = await clone_adjusted_version(
            session,
            user,
            plan.id,
            adjustment_summary_md="制造多 active 版本状态",
            draft_plan_json=replacement_plan_json(),
            validation_report_json={"valid": True},
            repair_log_json=[],
        )
        first_version.status = "active"
        await session.commit()

        await activate_plan(session, user, plan.id)

        await session.refresh(first_version)
        await session.refresh(second_version)
        assert first_version.status == "superseded"
        assert second_version.status == "active"


@pytest.mark.asyncio
async def test_update_plan_item_status_rejects_stale_active_version_item(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(session, user, plan_json=multi_stage_plan_json())
        plan = await confirm_plan_draft(session, user, draft.id)
        first_version = await get_active_plan_version(session, user, plan.id)
        old_item = item_by_slug(first_version, "two-sum")
        await clone_adjusted_version(
            session,
            user,
            plan.id,
            adjustment_summary_md="制造 stale active item",
            draft_plan_json=replacement_plan_json(),
            validation_report_json={"valid": True},
            repair_log_json=[],
        )
        first_version.status = "active"
        await session.commit()

        with pytest.raises(StudyPlanError, match="active_plan_item_not_found"):
            await update_plan_item_status(session, user, old_item.id, "skipped")


@pytest.mark.asyncio
async def test_reorder_stage_items_rejects_stale_active_version_stage(
    learning_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(session, user, plan_json=multi_stage_plan_json())
        plan = await confirm_plan_draft(session, user, draft.id)
        first_version = await get_active_plan_version(session, user, plan.id)
        old_stage = ordered_stages(first_version)[0]
        old_item_ids = [item.id for item in ordered_items(old_stage)]
        await clone_adjusted_version(
            session,
            user,
            plan.id,
            adjustment_summary_md="制造 stale active stage",
            draft_plan_json=replacement_plan_json(),
            validation_report_json={"valid": True},
            repair_log_json=[],
        )
        first_version.status = "active"
        await session.commit()

        with pytest.raises(StudyPlanError, match="active_plan_stage_not_found"):
            await reorder_stage_items(
                session,
                user,
                old_stage.id,
                list(reversed(old_item_ids)),
            )
