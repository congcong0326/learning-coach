from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.models.auth import AppUser
from backend.app.models.learning import GoalCalibrationDraft
from backend.app.models.llm_run import LlmRun
from backend.app.models.problem import Base, Problem
from backend.app.services.learning_flows.goal_plan import (
    LearningFlowError,
    PROMPT_VERSION,
    run_goal_plan_generate,
)
from backend.app.services.llm_providers.base import ProviderChunk
from backend.app.services.llm_run_events import LlmRunEvent
from backend.app.services.llm_run_service import cancel_llm_run


class FakePlanProvider:
    def __init__(self, final_payload: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, str]] = []
        self.final_payload = final_payload or {
            "title": "面试冲刺计划",
            "target_snapshot": {"goal_type": "interview_sprint"},
            "generation_summary_md": "按三个阶段训练。",
            "stages": [
                {
                    "title": "数组基础",
                    "objective_md": "巩固基础题型。",
                    "focus_tags": ["array"],
                    "assessment_criteria": ["能讲清思路"],
                    "items": [
                        {
                            "problem_slug": "two-sum",
                            "difficulty": "Easy",
                            "skill_tags": ["array"],
                            "suggested_mode": "guided",
                            "recommendation_reason": "训练哈希表入门",
                        }
                    ],
                }
            ],
        }

    async def stream_text(
        self,
        *,
        model: str,
        instructions: str,
        input_text: str,
    ) -> AsyncGenerator[ProviderChunk, None]:
        self.calls.append(
            {"model": model, "instructions": instructions, "input_text": input_text}
        )
        yield ProviderChunk(text_delta="我会按三个阶段生成计划。")
        yield ProviderChunk(
            final_text=json.dumps(self.final_payload, ensure_ascii=False)
        )


class FailingProvider:
    async def stream_text(
        self,
        *,
        model: str,
        instructions: str,
        input_text: str,
    ) -> AsyncGenerator[ProviderChunk, None]:
        raise RuntimeError("secret provider details")
        yield ProviderChunk(text_delta="unreachable")


class CancelingProvider(FakePlanProvider):
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        user_id: int,
        run_id: int,
    ) -> None:
        super().__init__()
        self.session_factory = session_factory
        self.user_id = user_id
        self.run_id = run_id

    async def stream_text(
        self,
        *,
        model: str,
        instructions: str,
        input_text: str,
    ) -> AsyncGenerator[ProviderChunk, None]:
        yield ProviderChunk(text_delta="我会按三个阶段生成计划。")
        async with self.session_factory() as session:
            user = await session.get(AppUser, self.user_id)
            assert user is not None
            await cancel_llm_run(session, user, self.run_id)
        yield ProviderChunk(
            final_text=json.dumps(self.final_payload, ensure_ascii=False)
        )


@pytest_asyncio.fixture
async def session_factory() -> AsyncGenerator[
    async_sessionmaker[AsyncSession],
    None,
]:
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
    await session.flush()
    return user


async def create_draft_run(
    session: AsyncSession,
    user: AppUser,
    *,
    with_problem: bool = True,
) -> tuple[GoalCalibrationDraft, LlmRun]:
    now = datetime.now(UTC)
    if with_problem:
        session.add(
            Problem(
                frontend_id=f"1-{uuid4().hex}",
                slug="two-sum",
                title="Two Sum",
                translated_title="两数之和",
                difficulty="Easy",
                statement_md="# Two Sum",
                metadata_json={"topic_tags": [{"slug": "array", "name": "Array"}]},
                leetcode_url="https://leetcode.cn/problems/two-sum/",
                is_paid_only=False,
                created_at=now,
                updated_at=now,
            )
        )
    draft = GoalCalibrationDraft(
        user_id=user.id,
        input_json={"goal_type": "interview_sprint"},
        followup_messages_json=[],
        draft_goal_json={},
        draft_plan_json={},
        validation_report_json={},
        repair_log_json=[],
        status="collecting_input",
        created_at=now,
        updated_at=now,
    )
    session.add(draft)
    await session.flush()
    run = LlmRun(
        user_id=user.id,
        kind="goal_plan_generate",
        related_type="goal_calibration_draft",
        related_id=draft.id,
    )
    session.add(run)
    await session.commit()
    await session.refresh(draft)
    await session.refresh(run)
    return draft, run


@pytest.mark.asyncio
async def test_goal_plan_generate_flow_updates_draft_without_final_result_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        draft, run = await create_draft_run(session, user)
        provider = FakePlanProvider()
        events: list[LlmRunEvent] = []

        async def publish(event: LlmRunEvent) -> None:
            events.append(event)

        result = await run_goal_plan_generate(
            session,
            user_id=user.id,
            run=run,
            provider=provider,
            model_name="gpt-test",
            publish=publish,
        )

        await session.refresh(draft)
        assert provider.calls[0]["model"] == "gpt-test"
        assert "默认语言语境：简体中文" in provider.calls[0]["instructions"]
        assert result == {
            "draft_id": draft.id,
            "status": "ready_for_review",
            "stage_count": 1,
            "item_count": 1,
        }
        assert draft.status == "ready_for_review"
        assert draft.prompt_version == PROMPT_VERSION
        assert draft.model_name == "gpt-test"
        assert draft.draft_goal_json == {"goal_type": "interview_sprint"}
        assert draft.draft_plan_json["stages"][0]["items"][0]["problem_slug"] == "two-sum"
        assert draft.validation_report_json["valid"] is True
        await session.refresh(run)
        assert run.status == "pending"
        assert run.result_json == {}
        assert run.display_text_md == "我会按三个阶段生成计划。"
        assert [event.name for event in events] == [
            "progress",
            "delta",
            "progress",
        ]
        assert all(event.name != "result" for event in events)


@pytest.mark.asyncio
async def test_goal_plan_generate_raises_stable_error_when_draft_missing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        run = LlmRun(
            user_id=user.id,
            kind="goal_plan_generate",
            related_type="goal_calibration_draft",
            related_id=404,
        )
        session.add(run)
        await session.commit()
        events: list[LlmRunEvent] = []

        async def publish(event: LlmRunEvent) -> None:
            events.append(event)

        with pytest.raises(LearningFlowError) as exc_info:
            await run_goal_plan_generate(
                session,
                user_id=user.id,
                run=run,
                provider=FakePlanProvider(),
                model_name="gpt-test",
                publish=publish,
            )

        assert exc_info.value.code == "goal_draft_not_found"
        assert events == []


@pytest.mark.asyncio
async def test_goal_plan_generate_stores_failure_report_without_formal_plan(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        draft, run = await create_draft_run(session, user, with_problem=False)
        events: list[LlmRunEvent] = []

        async def publish(event: LlmRunEvent) -> None:
            events.append(event)

        with pytest.raises(LearningFlowError) as exc_info:
            await run_goal_plan_generate(
                session,
                user_id=user.id,
                run=run,
                provider=FakePlanProvider(),
                model_name="gpt-test",
                publish=publish,
            )

        await session.refresh(draft)
        assert exc_info.value.code == "plan_validation_failed"
        assert draft.status == "failed"
        assert draft.draft_plan_json == {}
        assert draft.validation_report_json == {
            "valid": False,
            "issues": ["empty_problem_library"],
            "item_count": 0,
        }
        assert draft.error_message == "plan_validation_failed"
        await session.refresh(run)
        assert run.status == "pending"
        assert run.error_code == ""
        assert run.result_json == {}
        assert run.display_text_md == "我会按三个阶段生成计划。"
        assert [event.name for event in events] == ["progress", "delta", "progress"]


@pytest.mark.asyncio
async def test_goal_plan_generate_wraps_provider_failure_without_terminal_run(
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        _draft, run = await create_draft_run(session, user)
        events: list[LlmRunEvent] = []

        async def publish(event: LlmRunEvent) -> None:
            events.append(event)

        with pytest.raises(LearningFlowError) as exc_info:
            await run_goal_plan_generate(
                session,
                user_id=user.id,
                run=run,
                provider=FailingProvider(),
                model_name="gpt-test",
                publish=publish,
            )

        assert exc_info.value.code == "llm_provider_error"
        assert exc_info.value.__cause__ is None
        assert "secret provider details" not in caplog.text
        await session.refresh(run)
        assert run.status == "pending"
        assert run.error_code == ""
        assert run.result_json == {}
        assert [event.name for event in events] == ["progress"]


@pytest.mark.asyncio
async def test_goal_plan_generate_stops_when_run_is_canceled_mid_stream(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        draft, run = await create_draft_run(session, user)
        events: list[LlmRunEvent] = []

        async def publish(event: LlmRunEvent) -> None:
            events.append(event)

        with pytest.raises(LearningFlowError) as exc_info:
            await run_goal_plan_generate(
                session,
                user_id=user.id,
                run=run,
                provider=CancelingProvider(
                    session_factory=session_factory,
                    user_id=user.id,
                    run_id=run.id,
                ),
                model_name="gpt-test",
                publish=publish,
            )

        assert exc_info.value.code == "run_status_conflict"
        await session.refresh(draft)
        assert draft.status == "collecting_input"
        assert draft.draft_plan_json == {}
        await session.refresh(run)
        assert run.status == "canceled"
        assert run.result_json == {}
        assert [event.name for event in events] == ["progress", "delta"]


@pytest.mark.asyncio
async def test_goal_plan_generate_does_not_commit_formal_draft_before_run_success(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        draft, run = await create_draft_run(session, user)
        events: list[LlmRunEvent] = []

        async def publish(event: LlmRunEvent) -> None:
            events.append(event)

        await run_goal_plan_generate(
            session,
            user_id=user.id,
            run=run,
            provider=FakePlanProvider(),
            model_name="gpt-test",
            publish=publish,
        )
        assert draft.status == "ready_for_review"

        await session.rollback()

        await session.refresh(draft)
        assert draft.status == "collecting_input"
        assert draft.draft_plan_json == {}
        await session.refresh(run)
        assert run.status == "pending"
        assert run.result_json == {}
        assert run.display_text_md == "我会按三个阶段生成计划。"
        assert all(event.name != "result" for event in events)
