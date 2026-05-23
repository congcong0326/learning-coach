from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.models.auth import AppUser
from backend.app.models.learning import GoalCalibrationDraft
from backend.app.models.llm_run import LlmRun
from backend.app.models.practice import (
    CodeSnapshot,
    CoachTurn,
    PracticeEvent,
    PracticeSession,
    ProfileDelta,
    SessionSummary,
    SubmissionFeedback,
    UserProfileSnapshot,
)
from backend.app.models.problem import Base, Problem
from backend.app.schemas.practice import PracticeEventResponse
from backend.app.services.learning_flows.goal_plan import (
    LearningFlowError,
    PROMPT_VERSION,
    run_goal_plan_generate,
)
from backend.app.services.learning_flows.coach_turn import (
    _parse_coach_json,
    run_coach_turn,
)
from backend.app.services.learning_flows.coach_summary import run_coach_summary
from backend.app.services.learning_flows.goal_calibration import run_goal_followup
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


class JsonChunkPlanProvider(FakePlanProvider):
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
        final_text = json.dumps(self.final_payload, ensure_ascii=False)
        midpoint = max(1, len(final_text) // 2)
        yield ProviderChunk(text_delta=final_text[:midpoint])
        yield ProviderChunk(text_delta=final_text[midpoint:])
        yield ProviderChunk(final_text=final_text)


class FakeFollowupProvider:
    def __init__(self, final_text: str) -> None:
        self.calls: list[dict[str, str]] = []
        self.final_text = final_text

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
        yield ProviderChunk(text_delta="我需要再确认一个问题。")
        yield ProviderChunk(final_text=self.final_text)


class FakeCoachProvider:
    def __init__(self, final_payload: dict[str, Any]) -> None:
        self.calls: list[dict[str, str]] = []
        self.final_payload = final_payload

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
        final_text = json.dumps(self.final_payload, ensure_ascii=False)
        midpoint = max(1, len(final_text) // 2)
        yield ProviderChunk(text_delta=final_text[:midpoint])
        yield ProviderChunk(text_delta=final_text[midpoint:])
        yield ProviderChunk(final_text=final_text)


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


def profile_snapshot_json() -> dict[str, Any]:
    return {
        "id": None,
        "version": "profile-snapshot-v1",
        "source": "initial_goal_plan",
        "confidence": "low",
        "overall_level": "unknown",
        "preferred_training_mode": "guided",
        "weak_stuck_points": [],
        "strong_skill_tags": [],
        "weak_skill_tags": [],
        "recent_summary": "",
        "hint_policy_hint": "",
        "coach_strategy": {},
        "evidence": [],
    }


async def create_practice_session_with_user_event(
    session: AsyncSession,
    user: AppUser,
    *,
    phase: str = "write_code",
    user_intent: str = "code_review",
    content_md: str = "请帮我看一下代码。",
    with_code: bool = False,
) -> tuple[PracticeSession, PracticeEvent, CodeSnapshot | None]:
    now = datetime.now(UTC)
    practice_session = PracticeSession(
        user_id=user.id,
        study_plan_id=100,
        problem_id=200,
        problem_slug="two-sum",
        training_mode="guided",
        phase=phase,
        status="active",
        current_hint_level="questioning",
        visible_hint_gear=0,
        max_hint_level_used="questioning",
        attempt_count=0,
        final_result="",
        profile_snapshot_json=profile_snapshot_json(),
        started_at=now,
        last_activity_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(practice_session)
    await session.flush()
    user_event = PracticeEvent(
        session_id=practice_session.id,
        user_id=user.id,
        event_type="user_message",
        role="user",
        phase=phase,
        intent=user_intent,
        content_md=content_md,
        payload_json={"content_length": len(content_md)},
        hint_level="questioning",
        visible_hint_gear=0,
        created_at=now,
    )
    session.add(user_event)
    await session.flush()
    snapshot: CodeSnapshot | None = None
    if with_code:
        snapshot = CodeSnapshot(
            session_id=practice_session.id,
            user_id=user.id,
            event_id=user_event.id,
            language="python3",
            code_text="def twoSum(nums, target):\n    return []",
            code_hash=uuid4().hex,
            source="before_review",
            client_revision=1,
            created_at=now,
        )
        session.add(snapshot)
        await session.flush()
        practice_session.latest_code_snapshot_id = snapshot.id
    await session.commit()
    await session.refresh(practice_session)
    await session.refresh(user_event)
    if snapshot is not None:
        await session.refresh(snapshot)
    return practice_session, user_event, snapshot


async def create_coach_run(
    session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
    *,
    kind: str = "coach_turn",
    user_event_id: int | None = None,
    trigger: str = "code_review",
) -> LlmRun:
    payload: dict[str, Any] = {
        "session_id": practice_session.id,
        "trigger": trigger,
    }
    if user_event_id is not None:
        payload["user_event_id"] = user_event_id
    run = LlmRun(
        user_id=user.id,
        kind=kind,
        related_type="practice_session",
        related_id=practice_session.id,
        input_json=payload,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


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


async def create_followup_run(session: AsyncSession, user: AppUser) -> LlmRun:
    run = LlmRun(
        user_id=user.id,
        kind="goal_followup",
        input_json={
            "goal_type": "interview_sprint",
            "target_timeline": "within_1_month",
            "weekly_days": 5,
            "session_minutes": 60,
            "current_level": "easy_started",
            "preferred_language": "python3",
            "self_reported_weaknesses": ["interview_expression"],
            "extra_notes": "想准备后端面试",
            "training_preference": "guided",
        },
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def create_followup_answer_run(
    session: AsyncSession,
    user: AppUser,
) -> tuple[GoalCalibrationDraft, LlmRun]:
    now = datetime.now(UTC)
    draft = GoalCalibrationDraft(
        user_id=user.id,
        input_json={
            "goal_type": "interview_sprint",
            "target_timeline": "within_1_month",
            "weekly_days": 5,
            "session_minutes": 60,
            "current_level": "easy_started",
            "preferred_language": "python3",
            "self_reported_weaknesses": ["interview_expression"],
            "extra_notes": "想准备后端面试",
            "training_preference": "guided",
        },
        followup_messages_json=[
            {
                "role": "assistant",
                "question_id": "q1",
                "question": "你的面试时间是？",
            }
        ],
        draft_goal_json={},
        draft_plan_json={},
        validation_report_json={},
        repair_log_json=[],
        status="asking_followup",
        created_at=now,
        updated_at=now,
    )
    session.add(draft)
    await session.flush()
    run = LlmRun(
        user_id=user.id,
        kind="goal_followup",
        related_type="goal_calibration_draft",
        related_id=draft.id,
        input_json={
            "draft_id": draft.id,
            "question_id": "q1",
            "answer": "三周后面试，主要是后端岗位。",
        },
    )
    session.add(run)
    await session.commit()
    await session.refresh(draft)
    await session.refresh(run)
    return draft, run


@pytest.mark.asyncio
async def test_coach_turn_persists_serializable_assistant_event_without_result_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        practice_session, user_event, _snapshot = await create_practice_session_with_user_event(
            session,
            user,
            phase="write_code",
            user_intent="code_review",
            with_code=True,
        )
        run = await create_coach_run(
            session,
            user,
            practice_session,
            user_event_id=user_event.id,
            trigger="code_review",
        )
        events: list[LlmRunEvent] = []

        async def publish(event: LlmRunEvent) -> None:
            events.append(event)

        result = await run_coach_turn(
            session,
            user_id=user.id,
            run=run,
            provider=FakePlanProvider(),
            model_name="gpt-test",
            publish=publish,
        )

        assistant = await session.get(PracticeEvent, result["assistant_event_id"])
        assert assistant is not None
        response = PracticeEventResponse.model_validate(
            {
                "id": assistant.id,
                "event_type": assistant.event_type,
                "role": assistant.role,
                "phase": assistant.phase,
                "intent": assistant.intent,
                "content_md": assistant.content_md,
                "payload": assistant.payload_json,
                "hint_level": assistant.hint_level,
                "visible_hint_gear": "questioning",
                "created_at": assistant.created_at,
            }
        )
        assert response.intent is None
        assert [event.name for event in events] == ["progress", "delta"]


@pytest.mark.asyncio
async def test_coach_turn_uses_model_reply_when_user_already_described_hash_idea(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        idea = (
            "这道题很简单，用 hash 表第一次遍历保存数据，第二次遍历用 "
            "target 减去当前值看 hash 表里面有没有。"
        )
        practice_session, user_event, _snapshot = await create_practice_session_with_user_event(
            session,
            user,
            phase="understand_problem",
            user_intent="describe_idea",
            content_md=idea,
        )
        run = await create_coach_run(
            session,
            user,
            practice_session,
            user_event_id=user_event.id,
            trigger="describe_idea",
        )
        reply = (
            "你已经给出了哈希表方向，不需要回到暴力解法。下一步说清楚哈希表里存的是值还是下标，"
            "以及遍历到当前数时先查还是先写。"
        )
        provider = FakeCoachProvider(
            {
                "phase_after": "define_invariant",
                "diagnosed_stuck_point": "hash_state_needs_precision",
                "next_action": "ask_hash_invariant",
                "reply_md": reply,
                "should_reveal_solution": False,
            }
        )
        events: list[LlmRunEvent] = []

        async def publish(event: LlmRunEvent) -> None:
            events.append(event)

        result = await run_coach_turn(
            session,
            user_id=user.id,
            run=run,
            provider=provider,
            model_name="gpt-test",
            publish=publish,
        )

        assistant = await session.get(PracticeEvent, result["assistant_event_id"])
        coach_turn = await session.get(CoachTurn, result["coach_turn_id"])
        assert assistant is not None
        assert coach_turn is not None
        assert provider.calls[0]["model"] == "gpt-test"
        assert "单题 AI 教练" in provider.calls[0]["instructions"]
        input_context = json.loads(provider.calls[0]["input_text"])
        assert input_context["user_message"]["content_md"] == idea
        assert assistant.content_md == reply
        assert coach_turn.response_json["content_md"] == reply
        assert coach_turn.phase_after == "understand_problem"
        assert coach_turn.diagnosed_stuck_point == "hash_state_needs_precision"
        assert coach_turn.next_action == "ask_hash_invariant"
        assert run.display_text_md == reply
        assert result["guard"]["accepted"] is False
        assert result["guard"]["reason"] == "phase_transition_not_allowed"
        assert events[-1].data["text"] == reply


@pytest.mark.asyncio
async def test_coach_turn_extracts_code_attempt_when_review_code_is_accepted(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from backend.app.models.practice import CodeSnapshot, PracticeEvent

    async with session_factory() as session:
        user = await create_user(session)
        practice_session, user_event, _snapshot = await create_practice_session_with_user_event(
            session,
            user,
            phase="write_code",
            user_intent="code_review",
            content_md=(
                "请 review：\n"
                "```python\n"
                "class Solution:\n"
                "    def twoSum(self, nums, target):\n"
                "        return []\n"
                "```"
            ),
        )
        run = await create_coach_run(
            session,
            user,
            practice_session,
            user_event_id=user_event.id,
            trigger="code_review",
        )

        async def publish(_event: LlmRunEvent) -> None:
            return None

        result = await run_coach_turn(
            session,
            user_id=user.id,
            run=run,
            provider=FakeCoachProvider(
                {
                    "phase_after": "review_code",
                    "diagnosed_stuck_point": "implementation_bug",
                    "next_action": "review_code",
                    "reply_md": "这版代码还没有实现哈希表查找。",
                    "should_reveal_solution": False,
                    "code_quality_status": "needs_fix",
                    "code_quality_comment": "当前代码直接返回空列表，不建议提交。",
                }
            ),
            model_name="gpt-test",
            publish=publish,
        )

        assert result["code_attempt_snapshot_id"] is not None
        snapshot = await session.get(CodeSnapshot, result["code_attempt_snapshot_id"])
        assert snapshot is not None
        assert snapshot.source == "chat_review"
        assert snapshot.language == "python3"
        expected_code = (
            "class Solution:\n"
            "    def twoSum(self, nums, target):\n"
            "        return []"
        )
        assert snapshot.code_text == expected_code
        assert practice_session.latest_code_snapshot_id == snapshot.id

        event_result = await session.execute(
            select(PracticeEvent).where(
                PracticeEvent.session_id == practice_session.id,
                PracticeEvent.event_type == "code_saved",
            )
        )
        code_event = event_result.scalar_one()
        coach_turn = await session.get(CoachTurn, result["coach_turn_id"])
        assert coach_turn is not None
        assert coach_turn.response_json["code_attempt_snapshot_id"] == snapshot.id
        assert code_event.payload_json["quality_status"] == "needs_fix"
        assert code_event.payload_json["quality_comment"] == "当前代码直接返回空列表，不建议提交。"
        assert code_event.payload_json["snapshot_id"] == snapshot.id
        assert expected_code not in json.dumps(coach_turn.response_json, ensure_ascii=False)
        assert expected_code not in json.dumps(
            coach_turn.context_snapshot_json,
            ensure_ascii=False,
        )


@pytest.mark.asyncio
async def test_coach_turn_does_not_extract_code_attempt_outside_review_code(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from backend.app.models.practice import CodeSnapshot

    async with session_factory() as session:
        user = await create_user(session)
        practice_session, user_event, _snapshot = await create_practice_session_with_user_event(
            session,
            user,
            phase="understand_problem",
            user_intent="unknown",
            content_md="我可能会写 for i in range(len(nums))，先讨论思路。",
        )
        run = await create_coach_run(
            session,
            user,
            practice_session,
            user_event_id=user_event.id,
            trigger="unknown",
        )

        async def publish(_event: LlmRunEvent) -> None:
            return None

        await run_coach_turn(
            session,
            user_id=user.id,
            run=run,
            provider=FakeCoachProvider(
                {
                    "phase_after": "understand_problem",
                    "diagnosed_stuck_point": "intent_unclear",
                    "next_action": "ask_clarifying_question",
                    "reply_md": "先说输入输出。",
                    "should_reveal_solution": False,
                }
            ),
            model_name="gpt-test",
            publish=publish,
        )

        result = await session.execute(
            select(CodeSnapshot).where(CodeSnapshot.session_id == practice_session.id)
        )
        assert result.scalars().all() == []


def test_parse_coach_json_rejects_non_string_code_quality_status() -> None:
    with pytest.raises(LearningFlowError) as exc_info:
        _parse_coach_json(
            json.dumps(
                {
                    "phase_after": "review_code",
                    "diagnosed_stuck_point": "implementation_bug",
                    "next_action": "review_code",
                    "reply_md": "这版代码需要修改。",
                    "should_reveal_solution": False,
                    "code_quality_status": [],
                },
                ensure_ascii=False,
            )
        )

    assert exc_info.value.code == "coach_output_invalid"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("next_action", f" {'a' * 61} "),
        ("diagnosed_stuck_point", f" {'a' * 121} "),
    ],
)
def test_parse_coach_json_rejects_overlong_fields(
    field_name: str,
    value: str,
) -> None:
    payload = {
        "phase_after": "review_code",
        "diagnosed_stuck_point": "implementation_bug",
        "next_action": "review_code",
        "reply_md": "这版代码需要修改。",
        "should_reveal_solution": False,
    }
    payload[field_name] = value

    with pytest.raises(LearningFlowError) as exc_info:
        _parse_coach_json(json.dumps(payload, ensure_ascii=False))

    assert exc_info.value.code == "coach_output_invalid"


@pytest.mark.asyncio
async def test_coach_turn_does_not_commit_before_terminal_run_update(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        practice_session, user_event, _snapshot = await create_practice_session_with_user_event(
            session,
            user,
            phase="write_code",
            user_intent="code_review",
            with_code=True,
        )
        run = await create_coach_run(
            session,
            user,
            practice_session,
            user_event_id=user_event.id,
            trigger="code_review",
        )

        async def fail_commit() -> None:
            raise AssertionError("coach turn handler must not commit before orchestrator terminal update")

        monkeypatch.setattr(session, "commit", fail_commit)

        async def publish(_event: LlmRunEvent) -> None:
            return None

        await run_coach_turn(
            session,
            user_id=user.id,
            run=run,
            provider=FakePlanProvider(),
            model_name="gpt-test",
            publish=publish,
        )


@pytest.mark.asyncio
async def test_coach_turn_requires_explicit_user_event_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        practice_session, _user_event, _snapshot = await create_practice_session_with_user_event(
            session,
            user,
        )
        run = await create_coach_run(session, user, practice_session)

        async def publish(_event: LlmRunEvent) -> None:
            return None

        with pytest.raises(LearningFlowError) as exc_info:
            await run_coach_turn(
                session,
                user_id=user.id,
                run=run,
                provider=FakePlanProvider(),
                model_name="gpt-test",
                publish=publish,
            )

        assert exc_info.value.code == "coach_output_invalid"


@pytest.mark.asyncio
async def test_coach_turn_rejects_invalid_user_event_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        practice_session, _user_event, _snapshot = await create_practice_session_with_user_event(
            session,
            user,
        )
        run = await create_coach_run(
            session,
            user,
            practice_session,
            user_event_id=999_999,
            trigger="code_review",
        )

        async def publish(_event: LlmRunEvent) -> None:
            return None

        with pytest.raises(LearningFlowError) as exc_info:
            await run_coach_turn(
                session,
                user_id=user.id,
                run=run,
                provider=FakePlanProvider(),
                model_name="gpt-test",
                publish=publish,
            )

        assert exc_info.value.code == "practice_session_not_found"


@pytest.mark.asyncio
async def test_coach_turn_rejects_trigger_mismatch_with_user_event_intent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        practice_session, user_event, _snapshot = await create_practice_session_with_user_event(
            session,
            user,
            phase="write_code",
            user_intent="request_summary",
            with_code=True,
        )
        run = await create_coach_run(
            session,
            user,
            practice_session,
            user_event_id=user_event.id,
            trigger="code_review",
        )

        async def publish(_event: LlmRunEvent) -> None:
            return None

        with pytest.raises(LearningFlowError) as exc_info:
            await run_coach_turn(
                session,
                user_id=user.id,
                run=run,
                provider=FakePlanProvider(),
                model_name="gpt-test",
                publish=publish,
            )

        assert exc_info.value.code == "coach_output_invalid"


@pytest.mark.asyncio
async def test_coach_turn_code_review_trigger_sets_review_action_and_phase(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        practice_session, user_event, _snapshot = await create_practice_session_with_user_event(
            session,
            user,
            phase="write_code",
            user_intent="code_review",
            with_code=True,
        )
        run = await create_coach_run(
            session,
            user,
            practice_session,
            user_event_id=user_event.id,
            trigger="code_review",
        )

        async def publish(_event: LlmRunEvent) -> None:
            return None

        result = await run_coach_turn(
            session,
            user_id=user.id,
            run=run,
            provider=FakePlanProvider(),
            model_name="gpt-test",
            publish=publish,
        )

        coach_turn = await session.get(CoachTurn, result["coach_turn_id"])
        assert coach_turn is not None
        assert coach_turn.user_event_id == user_event.id
        assert coach_turn.phase_after == "review_code"
        assert coach_turn.next_action == "review_code"
        assert coach_turn.diagnosed_stuck_point == "code_review_requested"


@pytest.mark.asyncio
async def test_coach_summary_does_not_require_user_event_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        practice_session, _user_event, _snapshot = await create_practice_session_with_user_event(
            session,
            user,
            phase="analyze_feedback",
            user_intent="request_summary",
        )
        session.add(
            SubmissionFeedback(
                session_id=practice_session.id,
                user_id=user.id,
                source="leetcode_manual",
                result="accepted",
                runtime_ms=12,
                memory_kb=1024,
                failed_case_text="",
                error_message="",
                raw_feedback_json={"status": "Accepted"},
                submitted_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()
        run = await create_coach_run(
            session,
            user,
            practice_session,
            kind="coach_summary",
            trigger="request_summary",
        )
        events: list[LlmRunEvent] = []

        async def publish(event: LlmRunEvent) -> None:
            events.append(event)

        result = await run_coach_summary(
            session,
            user_id=user.id,
            run=run,
            provider=FakePlanProvider(),
            model_name="gpt-test",
            publish=publish,
        )

        coach_turn = await session.get(CoachTurn, result["coach_turn_id"])
        assert coach_turn is not None
        assert coach_turn.user_event_id is None
        assert coach_turn.phase_after == "summarize"
        assert coach_turn.next_action == "summarize_session"
        assert result["summary_status"] == "completed"
        summary = await session.get(SessionSummary, result["summary_id"])
        delta = await session.get(ProfileDelta, result["profile_delta_id"])
        snapshot = await session.get(UserProfileSnapshot, result["profile_snapshot_id"])
        assert summary is not None
        assert delta is not None
        assert snapshot is not None
        assert delta.status == "accepted"
        assert delta.summary_id == summary.id
        assert snapshot.created_from_summary_id == summary.id
        assert [event.name for event in events] == ["progress", "delta"]


@pytest.mark.asyncio
async def test_goal_followup_flow_creates_draft_from_payload(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        run = await create_followup_run(session, user)
        provider = FakeFollowupProvider(
            json.dumps(
                {"question_id": "q1", "question": "你的面试时间是？"},
                ensure_ascii=False,
            )
        )
        events: list[LlmRunEvent] = []

        async def publish(event: LlmRunEvent) -> None:
            events.append(event)

        result = await run_goal_followup(
            session,
            user_id=user.id,
            run=run,
            provider=provider,
            model_name="gpt-test",
            publish=publish,
        )

        draft = await session.get(GoalCalibrationDraft, result["draft_id"])
        assert draft is not None
        assert draft.user_id == user.id
        assert draft.input_json == run.input_json
        assert draft.status == "asking_followup"
        assert draft.followup_messages_json == [
            {
                "role": "assistant",
                "question_id": "q1",
                "question": "你的面试时间是？",
            }
        ]
        assert result == {
            "draft_id": draft.id,
            "status": "asking_followup",
            "followup_question": "你的面试时间是？",
            "followup_question_id": "q1",
            "remaining_followups": 2,
        }
        assert provider.calls[0]["model"] == "gpt-test"
        assert "目标校准教练" in provider.calls[0]["instructions"]
        assert json.loads(provider.calls[0]["input_text"]) == {
            "payload": run.input_json,
            "history": [],
        }
        await session.refresh(run)
        assert run.status == "pending"
        assert run.related_type == "goal_calibration_draft"
        assert run.related_id == draft.id
        assert run.result_json == {}
        assert run.display_text_md == "正在判断是否需要追问...\n"
        assert [event.name for event in events] == ["progress", "delta"]
        assert events[1].data["text"] == "正在判断是否需要追问...\n"
        assert all(event.name != "result" for event in events)


@pytest.mark.asyncio
async def test_goal_followup_flow_answers_existing_draft_through_run(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        draft, run = await create_followup_answer_run(session, user)
        provider = FakeFollowupProvider("null")
        events: list[LlmRunEvent] = []

        async def publish(event: LlmRunEvent) -> None:
            events.append(event)

        result = await run_goal_followup(
            session,
            user_id=user.id,
            run=run,
            provider=provider,
            model_name="gpt-test",
            publish=publish,
        )

        await session.refresh(draft)
        assert draft.status == "collecting_input"
        assert draft.followup_messages_json == [
            {
                "role": "assistant",
                "question_id": "q1",
                "question": "你的面试时间是？",
            },
            {
                "role": "user",
                "question_id": "q1",
                "answer": "三周后面试，主要是后端岗位。",
            },
        ]
        assert result == {
            "draft_id": draft.id,
            "status": "collecting_input",
            "followup_question": None,
            "followup_question_id": None,
            "remaining_followups": 0,
        }
        assert json.loads(provider.calls[0]["input_text"]) == {
            "payload": draft.input_json,
            "history": draft.followup_messages_json,
        }
        await session.refresh(run)
        assert run.status == "pending"
        assert run.result_json == {}
        assert run.display_text_md == "正在判断是否需要追问...\n"
        assert [event.name for event in events] == ["progress", "delta"]
        assert events[1].data["text"] == "正在判断是否需要追问...\n"
        assert all(event.name != "result" for event in events)


@pytest.mark.asyncio
async def test_goal_followup_flow_collects_input_when_model_returns_null(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        run = await create_followup_run(session, user)
        events: list[LlmRunEvent] = []

        async def publish(event: LlmRunEvent) -> None:
            events.append(event)

        result = await run_goal_followup(
            session,
            user_id=user.id,
            run=run,
            provider=FakeFollowupProvider("null"),
            model_name="gpt-test",
            publish=publish,
        )

        draft = await session.get(GoalCalibrationDraft, result["draft_id"])
        assert draft is not None
        assert draft.status == "collecting_input"
        assert draft.followup_messages_json == []
        assert result == {
            "draft_id": draft.id,
            "status": "collecting_input",
            "followup_question": None,
            "followup_question_id": None,
            "remaining_followups": 0,
        }
        assert [event.name for event in events] == ["progress", "delta"]
        assert events[1].data["text"] == "正在判断是否需要追问...\n"


@pytest.mark.asyncio
async def test_goal_plan_generate_flow_updates_draft_without_final_result_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        draft, run = await create_draft_run(session, user)
        provider = JsonChunkPlanProvider()
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
        assert result["draft_id"] == draft.id
        assert result["status"] == "ready_for_review"
        assert result["target_snapshot"] == {"goal_type": "interview_sprint"}
        assert result["generation_summary_md"] == "按三个阶段训练。"
        assert result["stages"][0]["items"][0]["problem_slug"] == "two-sum"
        assert result["validation_report"] == {
            "valid": True,
            "issues": [],
            "item_count": 1,
        }
        assert result["repair_log"] == []
        assert result["uncertainty_notes"] == []
        assert result["stage_count"] == 1
        assert result["item_count"] == 1
        assert draft.status == "ready_for_review"
        assert draft.prompt_version == PROMPT_VERSION
        assert draft.model_name == "gpt-test"
        assert draft.draft_goal_json == {"goal_type": "interview_sprint"}
        assert draft.draft_plan_json["stages"][0]["items"][0]["problem_slug"] == "two-sum"
        assert draft.validation_report_json["valid"] is True
        await session.refresh(run)
        assert run.status == "pending"
        assert run.result_json == {}
        assert run.display_text_md.startswith("模型正在生成计划草稿...\n")
        assert "problem_slug" not in run.display_text_md
        assert "{" not in run.display_text_md
        assert [event.name for event in events] == [
            "progress",
            "delta",
            "delta",
            "progress",
        ]
        assert events[1].data["text"] == "模型正在生成计划草稿...\n"
        assert "problem_slug" not in str(events[1].data["text"])
        assert "{" not in str(events[1].data["text"])
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
        assert run.display_text_md == "模型正在生成计划草稿...\n"
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
        assert events[1].data["text"] == "模型正在生成计划草稿...\n"


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
        assert run.display_text_md == "模型正在生成计划草稿...\n"
        assert all(event.name != "result" for event in events)
