from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.llm_run import LlmRun
from backend.app.models.practice import (
    CoachTurn,
    PracticeEvent,
    PracticeSession,
    SubmissionFeedback,
)
from backend.app.services.coach_guard import guard_transition
from backend.app.services.learning_flows.goal_plan import LearningFlowError
from backend.app.services.llm_providers.base import LlmProvider
from backend.app.services.llm_run_events import LlmRunEvent
from backend.app.services.llm_run_service import (
    LlmRunError,
    ensure_llm_run_mutable,
    update_llm_run_display_text,
)


PROMPT_VERSION = "coach-turn-v1-deterministic"
SAFE_REPLY = "我已经记录你的输入。先说明你的暴力解法、你准备维护的关键状态，以及你认为必须覆盖的边界用例。"

logger = logging.getLogger(__name__)


class CoachTurnHandler:
    async def execute(self, context: Any) -> dict[str, Any]:
        return await run_coach_turn(
            context.session,
            user_id=context.user_id,
            run=context.run,
            provider=context.provider,
            model_name=context.model_name,
            publish=context.publish,
        )


async def run_coach_turn(
    session: AsyncSession,
    *,
    user_id: int,
    run: LlmRun,
    provider: LlmProvider,
    model_name: str,
    publish: Callable[[LlmRunEvent], Awaitable[None]],
) -> dict[str, Any]:
    del provider
    await _ensure_run_mutable(session, run)
    payload = _payload_for_run(run)
    practice_session = await _load_practice_session(
        session,
        user_id=user_id,
        run=run,
        payload=payload,
    )
    user_event = await _load_user_event(
        session,
        user_id=user_id,
        session_id=practice_session.id,
        payload=payload,
        required=run.kind == "coach_turn",
    )
    has_feedback = await _has_submission_feedback(
        session,
        user_id=user_id,
        session_id=practice_session.id,
    )
    trigger_context = _trigger_context(
        payload,
        practice_session,
        has_submission_feedback=has_feedback,
        force_summary=run.kind == "coach_summary",
    )
    decision = guard_transition(
        phase_before=practice_session.phase,
        proposed_phase_after=trigger_context["proposed_phase"],
        has_code=practice_session.latest_code_snapshot_id is not None,
        has_submission_feedback=has_feedback,
        hint_level=practice_session.current_hint_level,
        should_reveal_solution=False,
    )

    logger.info(
        "coach turn flow started run_id=%s user_id=%s session_id=%s phase=%s "
        "proposed_phase=%s accepted=%s model=%s",
        run.id,
        user_id,
        practice_session.id,
        practice_session.phase,
        trigger_context["proposed_phase"],
        decision.accepted,
        model_name,
    )
    await _publish_progress(
        publish,
        run_id=run.id,
        stage="coach_turn",
        message="正在生成教练回复",
    )
    await publish(LlmRunEvent("delta", {"run_id": run.id, "text": SAFE_REPLY}))
    await _update_display_text(session, run, SAFE_REPLY)

    now = datetime.now(UTC)
    phase_before = practice_session.phase
    assistant_event = PracticeEvent(
        session_id=practice_session.id,
        user_id=user_id,
        llm_run_id=run.id,
        event_type="assistant_message",
        role="assistant",
        phase=decision.phase_after,
        intent=None,
        content_md=SAFE_REPLY,
        payload_json={
            "prompt_version": PROMPT_VERSION,
            "trigger": trigger_context["trigger"],
            "next_action": trigger_context["next_action"],
            "guard_reason": decision.reason,
            "guard_accepted": decision.accepted,
        },
        hint_level=decision.hint_level_after,
        visible_hint_gear=practice_session.visible_hint_gear,
        created_at=now,
    )
    session.add(assistant_event)
    await session.flush()
    coach_turn = CoachTurn(
        session_id=practice_session.id,
        user_id=user_id,
        llm_run_id=run.id,
        user_event_id=user_event.id if user_event is not None else None,
        assistant_event_id=assistant_event.id,
        prompt_version=PROMPT_VERSION,
        model_name=model_name,
        phase_before=phase_before,
        phase_after=decision.phase_after,
        training_mode=practice_session.training_mode,
        diagnosed_stuck_point=trigger_context["diagnosed_stuck_point"],
        user_intent=_user_intent(user_event),
        next_action=trigger_context["next_action"],
        hint_level_before=practice_session.current_hint_level,
        hint_level_after=decision.hint_level_after,
        visible_hint_gear=practice_session.visible_hint_gear,
        should_reveal_solution=False,
        transition_reason=decision.reason,
        response_json={"content_md": SAFE_REPLY},
        # 只保存安全画像快照和结构化上下文，不把完整用户输入或完整代码复制进 turn。
        context_snapshot_json=_context_snapshot(practice_session, has_feedback=has_feedback),
        created_at=now,
    )
    session.add(coach_turn)
    if decision.accepted:
        practice_session.phase = decision.phase_after
        practice_session.current_hint_level = decision.hint_level_after
    practice_session.last_activity_at = now
    practice_session.updated_at = now
    await session.flush()
    await _ensure_run_mutable(session, run)

    result = _result_payload(
        practice_session,
        coach_turn=coach_turn,
        assistant_event=assistant_event,
        decision_accepted=decision.accepted,
        guard_reason=decision.reason,
    )
    logger.info(
        "coach turn flow completed run_id=%s user_id=%s session_id=%s "
        "coach_turn_id=%s phase_before=%s phase_after=%s",
        run.id,
        user_id,
        practice_session.id,
        coach_turn.id,
        phase_before,
        decision.phase_after,
    )
    return result


async def _load_practice_session(
    session: AsyncSession,
    *,
    user_id: int,
    run: LlmRun,
    payload: dict[str, Any],
) -> PracticeSession:
    session_id = run.related_id
    if session_id is None:
        session_id = payload.get("session_id")
    if not isinstance(session_id, int) or isinstance(session_id, bool):
        raise LearningFlowError("practice_session_not_found")
    result = await session.execute(
        select(PracticeSession)
        .where(PracticeSession.id == session_id, PracticeSession.user_id == user_id)
        .with_for_update()
    )
    practice_session = result.scalar_one_or_none()
    if practice_session is None:
        logger.warning(
            "coach turn session missing run_id=%s user_id=%s session_id=%s",
            run.id,
            user_id,
            session_id,
        )
        raise LearningFlowError("practice_session_not_found")
    return practice_session


def _payload_for_run(run: LlmRun) -> dict[str, Any]:
    if not isinstance(run.input_json, dict):
        raise LearningFlowError("coach_output_invalid")
    return run.input_json


async def _load_user_event(
    session: AsyncSession,
    *,
    user_id: int,
    session_id: int,
    payload: dict[str, Any],
    required: bool,
) -> PracticeEvent | None:
    event_id = payload.get("user_event_id")
    if event_id is None and not required:
        return None
    if not isinstance(event_id, int) or isinstance(event_id, bool):
        raise LearningFlowError("coach_output_invalid")
    result = await session.execute(
        select(PracticeEvent).where(
            PracticeEvent.id == event_id,
            PracticeEvent.session_id == session_id,
            PracticeEvent.user_id == user_id,
            PracticeEvent.role == "user",
        )
    )
    user_event = result.scalar_one_or_none()
    if user_event is None:
        raise LearningFlowError("practice_session_not_found")
    return user_event


async def _has_submission_feedback(
    session: AsyncSession,
    *,
    user_id: int,
    session_id: int,
) -> bool:
    result = await session.execute(
        select(
            exists().where(
                SubmissionFeedback.session_id == session_id,
                SubmissionFeedback.user_id == user_id,
            )
        )
    )
    return bool(result.scalar())


def _trigger_context(
    payload: dict[str, Any],
    practice_session: PracticeSession,
    *,
    has_submission_feedback: bool,
    force_summary: bool,
) -> dict[str, str]:
    trigger = payload.get("trigger") or ("request_summary" if force_summary else None)
    if not isinstance(trigger, str):
        raise LearningFlowError("coach_output_invalid")
    if (
        force_summary
        or trigger == "request_summary"
        or practice_session.final_result == "ac"
        or practice_session.status == "summarizing"
    ):
        return {
            "trigger": trigger,
            "proposed_phase": "summarize",
            "next_action": "summarize_session",
            "diagnosed_stuck_point": "reflection_requested",
        }
    if trigger == "submit_feedback":
        return {
            "trigger": trigger,
            "proposed_phase": "analyze_feedback",
            "next_action": "analyze_submission_feedback",
            "diagnosed_stuck_point": "submission_feedback_analysis",
        }
    if trigger == "code_review":
        return {
            "trigger": trigger,
            "proposed_phase": "review_code",
            "next_action": "review_code",
            "diagnosed_stuck_point": "code_review_requested",
        }
    if trigger == "request_hint":
        return {
            "trigger": trigger,
            "proposed_phase": practice_session.phase,
            "next_action": "offer_questioning_hint",
            "diagnosed_stuck_point": "needs_hint",
        }
    if trigger == "describe_idea":
        proposed_phase = "analyze_feedback" if has_submission_feedback else practice_session.phase
        return {
            "trigger": trigger,
            "proposed_phase": proposed_phase,
            "next_action": "ask_bruteforce_state_and_edges",
            "diagnosed_stuck_point": "bruteforce_state_unclear",
        }
    raise LearningFlowError("coach_output_invalid")


def _user_intent(user_event: PracticeEvent | None) -> str:
    if user_event is None:
        return ""
    return user_event.intent or ""


def _context_snapshot(
    practice_session: PracticeSession,
    *,
    has_feedback: bool,
) -> dict[str, Any]:
    return {
        "session_id": practice_session.id,
        "problem_id": practice_session.problem_id,
        "problem_slug": practice_session.problem_slug,
        "study_plan_id": practice_session.study_plan_id,
        "phase": practice_session.phase,
        "training_mode": practice_session.training_mode,
        "hint_level": practice_session.current_hint_level,
        "has_code": practice_session.latest_code_snapshot_id is not None,
        "has_submission_feedback": has_feedback,
        "profile_snapshot": practice_session.profile_snapshot_json,
    }


def _result_payload(
    practice_session: PracticeSession,
    *,
    coach_turn: CoachTurn,
    assistant_event: PracticeEvent,
    decision_accepted: bool,
    guard_reason: str,
) -> dict[str, Any]:
    return {
        "session_id": practice_session.id,
        "coach_turn_id": coach_turn.id,
        "assistant_event_id": assistant_event.id,
        "reply_md": SAFE_REPLY,
        "phase_after": coach_turn.phase_after,
        "hint_level_after": coach_turn.hint_level_after,
        "guard": {
            "accepted": decision_accepted,
            "reason": guard_reason,
        },
    }


async def _publish_progress(
    publish: Callable[[LlmRunEvent], Awaitable[None]],
    *,
    run_id: int,
    stage: str,
    message: str,
) -> None:
    await publish(
        LlmRunEvent(
            "progress",
            {
                "run_id": run_id,
                "stage": stage,
                "message": message,
            },
        )
    )


async def _ensure_run_mutable(session: AsyncSession, run: LlmRun) -> None:
    try:
        await ensure_llm_run_mutable(session, run)
    except LlmRunError as exc:
        raise LearningFlowError(exc.detail) from None


async def _update_display_text(
    session: AsyncSession,
    run: LlmRun,
    display_text_md: str,
) -> None:
    try:
        await update_llm_run_display_text(
            session,
            run,
            display_text_md=display_text_md,
        )
    except LlmRunError as exc:
        raise LearningFlowError(exc.detail) from None
