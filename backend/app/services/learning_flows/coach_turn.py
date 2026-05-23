from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.llm_run import LlmRun
from backend.app.models.practice import (
    CoachTurn,
    CodeSnapshot,
    PracticeEvent,
    PracticeSession,
    SubmissionFeedback,
)
from backend.app.services.coach_guard import guard_transition
from backend.app.services.code_attempts import (
    extract_code_from_message,
    persist_review_code_attempt,
    quality_from_decision,
)
from backend.app.services.learning_flows.goal_plan import LearningFlowError
from backend.app.services.llm_providers.base import LlmProvider
from backend.app.services.llm_run_events import LlmRunEvent
from backend.app.services.llm_run_service import (
    LlmRunError,
    ensure_llm_run_mutable,
)


PROMPT_VERSION = "coach-turn-v2-structured"
SAFE_REPLY = "我已经记录你的输入。先说明你的暴力解法、你准备维护的关键状态，以及你认为必须覆盖的边界用例。"
COACH_REPLY_INSTRUCTIONS = (
    "默认语言语境：简体中文。你是 Agentic Coding Learning Coach 的单题 AI 教练，"
    "必须根据当前题目训练上下文、用户画像、训练阶段、提示档位和用户本轮输入生成下一步教练回复。"
    "不要机械重复固定流程；如果用户已经给出清晰思路，可以快进到不变量、代码或提交阶段。"
    "低提示档位下不要泄露完整可提交答案。只输出 JSON 对象，不要输出解释性前后缀。"
    "JSON 字段必须包含：phase_after、diagnosed_stuck_point、next_action、reply_md、"
    "should_reveal_solution。phase_after 只能使用允许状态；reply_md 必须是面向用户的简体中文。"
    "当 phase_after 为 review_code 且用户本轮提供代码时，可以额外返回 code_quality_status "
    "和 code_quality_comment。code_quality_status 只能是 pending、needs_fix 或 ready_to_submit。"
)
COACH_PHASES = {
    "understand_problem",
    "propose_bruteforce",
    "optimize_solution",
    "define_invariant",
    "write_code",
    "review_code",
    "submit_to_leetcode",
    "analyze_feedback",
    "summarize",
}
COACH_EVENT_TRIGGERS = {
    "describe_idea",
    "stuck",
    "request_hint",
    "code_review",
    "submit_feedback",
    "request_summary",
    "unknown",
}

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
    extracted_code = (
        extract_code_from_message(user_event.content_md)
        if user_event is not None
        else None
    )
    code_snapshot = await _load_latest_code_snapshot(
        session,
        user_id=user_id,
        practice_session=practice_session,
    )
    has_feedback = await _has_submission_feedback(
        session,
        user_id=user_id,
        session_id=practice_session.id,
    )
    trigger_context = _trigger_context(
        payload,
        practice_session,
        user_event=user_event,
        has_submission_feedback=has_feedback,
        force_summary=run.kind == "coach_summary",
    )

    logger.info(
        "coach turn flow started run_id=%s user_id=%s session_id=%s phase=%s "
        "proposed_phase=%s model=%s",
        run.id,
        user_id,
        practice_session.id,
        practice_session.phase,
        trigger_context["proposed_phase"],
        model_name,
    )
    await _publish_progress(
        publish,
        run_id=run.id,
        stage="coach_turn",
        message="正在生成教练回复",
    )
    coach_decision = await _coach_decision(
        session,
        user_id=user_id,
        run=run,
        provider=provider,
        model_name=model_name,
        practice_session=practice_session,
        user_event=user_event,
        code_snapshot=code_snapshot,
        has_feedback=has_feedback,
        trigger_context=trigger_context,
    )
    decision = guard_transition(
        phase_before=practice_session.phase,
        proposed_phase_after=coach_decision["phase_after"],
        has_code=practice_session.latest_code_snapshot_id is not None
        or extracted_code is not None,
        has_submission_feedback=has_feedback,
        hint_level=practice_session.current_hint_level,
        should_reveal_solution=bool(coach_decision["should_reveal_solution"]),
    )
    reply_md = _reply_after_guard(coach_decision, decision_reason=decision.reason)
    await publish(LlmRunEvent("delta", {"run_id": run.id, "text": reply_md}))

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
        content_md=reply_md,
        payload_json={
            "prompt_version": PROMPT_VERSION,
            "trigger": trigger_context["trigger"],
            "next_action": coach_decision["next_action"],
            "guard_reason": decision.reason,
            "guard_accepted": decision.accepted,
            "generation_mode": coach_decision["generation_mode"],
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
        diagnosed_stuck_point=coach_decision["diagnosed_stuck_point"],
        user_intent=_user_intent(user_event),
        next_action=coach_decision["next_action"],
        hint_level_before=practice_session.current_hint_level,
        hint_level_after=decision.hint_level_after,
        visible_hint_gear=practice_session.visible_hint_gear,
        should_reveal_solution=bool(coach_decision["should_reveal_solution"]),
        transition_reason=decision.reason,
        response_json={
            "content_md": reply_md,
            "model_phase_after": coach_decision["phase_after"],
            "generation_mode": coach_decision["generation_mode"],
        },
        # 只保存安全画像快照和结构化上下文，不把完整用户输入或完整代码复制进 turn。
        context_snapshot_json=_context_snapshot(practice_session, has_feedback=has_feedback),
        created_at=now,
    )
    session.add(coach_turn)
    code_attempt_snapshot_id: int | None = None
    if (
        decision.accepted
        and decision.phase_after == "review_code"
        and user_event is not None
        and extracted_code is not None
    ):
        quality_status, quality_comment = quality_from_decision(coach_decision)
        snapshot = await persist_review_code_attempt(
            session,
            user_id=user_id,
            practice_session=practice_session,
            user_event=user_event,
            extracted_code=extracted_code,
            quality_status=quality_status,
            quality_comment=quality_comment,
            client_revision=practice_session.attempt_count + 1,
            now=now,
        )
        code_attempt_snapshot_id = snapshot.id
    coach_turn.response_json = {
        **coach_turn.response_json,
        "code_attempt_snapshot_id": code_attempt_snapshot_id,
    }
    if decision.accepted:
        practice_session.phase = decision.phase_after
        practice_session.current_hint_level = decision.hint_level_after
    practice_session.last_activity_at = now
    practice_session.updated_at = now
    await session.flush()
    await _ensure_run_mutable(session, run)
    # 教练回复与会话状态必须和 run 终态在同一事务提交；这里只更新内存对象，
    # 避免中途 commit 释放 practice_session 行锁后产生并发教练回合。
    run.display_text_md = reply_md

    result = _result_payload(
        practice_session,
        coach_turn=coach_turn,
        assistant_event=assistant_event,
        reply_md=reply_md,
        decision_accepted=decision.accepted,
        guard_reason=decision.reason,
        code_attempt_snapshot_id=code_attempt_snapshot_id,
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
            PracticeEvent.event_type == "user_message",
        )
    )
    user_event = result.scalar_one_or_none()
    if user_event is None:
        raise LearningFlowError("practice_session_not_found")
    return user_event


async def _load_latest_code_snapshot(
    session: AsyncSession,
    *,
    user_id: int,
    practice_session: PracticeSession,
) -> CodeSnapshot | None:
    snapshot_id = practice_session.latest_code_snapshot_id
    if snapshot_id is None:
        return None
    result = await session.execute(
        select(CodeSnapshot).where(
            CodeSnapshot.id == snapshot_id,
            CodeSnapshot.session_id == practice_session.id,
            CodeSnapshot.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


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


async def _coach_decision(
    session: AsyncSession,
    *,
    user_id: int,
    run: LlmRun,
    provider: LlmProvider,
    model_name: str,
    practice_session: PracticeSession,
    user_event: PracticeEvent | None,
    code_snapshot: CodeSnapshot | None,
    has_feedback: bool,
    trigger_context: dict[str, str],
) -> dict[str, Any]:
    fallback = _fallback_coach_decision(trigger_context)
    if run.kind != "coach_turn" or not model_name:
        return fallback

    raw_parts: list[str] = []
    final_text = ""
    try:
        async for chunk in provider.stream_text(
            model=model_name,
            instructions=COACH_REPLY_INSTRUCTIONS,
            input_text=json.dumps(
                _coach_input_context(
                    practice_session,
                    user_event=user_event,
                    code_snapshot=code_snapshot,
                    has_feedback=has_feedback,
                    trigger_context=trigger_context,
                ),
                ensure_ascii=False,
            ),
        ):
            if chunk.text_delta:
                raw_parts.append(chunk.text_delta)
            if chunk.final_text:
                final_text = chunk.final_text
    except Exception as exc:
        logger.warning(
            "coach turn provider failed run_id=%s user_id=%s session_id=%s "
            "error_type=%s fallback=true",
            run.id,
            user_id,
            practice_session.id,
            type(exc).__name__,
        )
        return fallback

    if not final_text:
        final_text = "".join(raw_parts)
    try:
        return _parse_coach_json(final_text)
    except LearningFlowError as exc:
        logger.warning(
            "coach turn model output invalid run_id=%s user_id=%s session_id=%s "
            "error_code=%s fallback=true",
            run.id,
            user_id,
            practice_session.id,
            exc.code,
        )
        return fallback


def _coach_input_context(
    practice_session: PracticeSession,
    *,
    user_event: PracticeEvent | None,
    code_snapshot: CodeSnapshot | None,
    has_feedback: bool,
    trigger_context: dict[str, str],
) -> dict[str, Any]:
    latest_code: dict[str, Any] | None = None
    if code_snapshot is not None:
        latest_code = {
            "language": code_snapshot.language,
            "source": code_snapshot.source,
            "client_revision": code_snapshot.client_revision,
            "code_text": code_snapshot.code_text,
        }
    return {
        "allowed_phases": sorted(COACH_PHASES),
        "session": {
            "session_id": practice_session.id,
            "problem_slug": practice_session.problem_slug,
            "phase": practice_session.phase,
            "training_mode": practice_session.training_mode,
            "status": practice_session.status,
            "current_hint_level": practice_session.current_hint_level,
            "visible_hint_gear": practice_session.visible_hint_gear,
            "has_code": practice_session.latest_code_snapshot_id is not None,
            "has_submission_feedback": has_feedback,
        },
        "profile_snapshot": practice_session.profile_snapshot_json,
        "trigger_context": trigger_context,
        "user_message": {
            "intent": _user_intent(user_event),
            "content_md": user_event.content_md if user_event is not None else "",
            "hint_level": user_event.hint_level if user_event is not None else None,
        },
        "latest_code": latest_code,
        "output_contract": {
            "phase_after": "one allowed phase",
            "diagnosed_stuck_point": "short stable snake_case string",
            "next_action": "short stable snake_case string",
            "reply_md": "简体中文教练回复",
            "should_reveal_solution": "boolean",
            "code_quality_status": "optional pending | needs_fix | ready_to_submit when reviewing code",
            "code_quality_comment": "optional short Chinese review summary",
        },
    }


def _parse_coach_json(final_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(_strip_json_fence(final_text))
    except json.JSONDecodeError as exc:
        raise LearningFlowError("coach_output_invalid") from exc
    if not isinstance(parsed, dict):
        raise LearningFlowError("coach_output_invalid")
    phase_after = parsed.get("phase_after")
    diagnosed_stuck_point = parsed.get("diagnosed_stuck_point")
    next_action = parsed.get("next_action")
    reply_md = parsed.get("reply_md")
    should_reveal_solution = parsed.get("should_reveal_solution")
    code_quality_status = parsed.get("code_quality_status")
    code_quality_comment = parsed.get("code_quality_comment")
    if not isinstance(phase_after, str) or phase_after not in COACH_PHASES:
        raise LearningFlowError("coach_output_invalid")
    if not isinstance(diagnosed_stuck_point, str) or not diagnosed_stuck_point.strip():
        raise LearningFlowError("coach_output_invalid")
    if not isinstance(next_action, str) or not next_action.strip():
        raise LearningFlowError("coach_output_invalid")
    if not isinstance(reply_md, str) or not reply_md.strip():
        raise LearningFlowError("coach_output_invalid")
    if not isinstance(should_reveal_solution, bool):
        raise LearningFlowError("coach_output_invalid")
    if code_quality_status is not None:
        if not isinstance(code_quality_status, str) or code_quality_status not in {
            "pending",
            "needs_fix",
            "ready_to_submit",
        }:
            raise LearningFlowError("coach_output_invalid")
    if code_quality_comment is not None and not isinstance(code_quality_comment, str):
        raise LearningFlowError("coach_output_invalid")
    return {
        "phase_after": phase_after,
        "diagnosed_stuck_point": diagnosed_stuck_point.strip(),
        "next_action": next_action.strip(),
        "reply_md": reply_md.strip(),
        "should_reveal_solution": should_reveal_solution,
        "code_quality_status": code_quality_status,
        "code_quality_comment": code_quality_comment.strip()
        if isinstance(code_quality_comment, str)
        else "",
        "generation_mode": "llm",
    }


def _strip_json_fence(final_text: str) -> str:
    text = final_text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def _fallback_coach_decision(trigger_context: dict[str, str]) -> dict[str, Any]:
    return {
        "phase_after": trigger_context["proposed_phase"],
        "diagnosed_stuck_point": trigger_context["diagnosed_stuck_point"],
        "next_action": trigger_context["next_action"],
        "reply_md": SAFE_REPLY,
        "should_reveal_solution": False,
        "generation_mode": "fallback",
    }


def _reply_after_guard(
    coach_decision: dict[str, Any],
    *,
    decision_reason: str,
) -> str:
    if decision_reason == "hint_level_prevents_solution_reveal":
        return SAFE_REPLY
    return str(coach_decision["reply_md"])


def _trigger_context(
    payload: dict[str, Any],
    practice_session: PracticeSession,
    *,
    user_event: PracticeEvent | None,
    has_submission_feedback: bool,
    force_summary: bool,
) -> dict[str, str]:
    payload_trigger = payload.get("trigger")
    if payload_trigger is not None and not isinstance(payload_trigger, str):
        raise LearningFlowError("coach_output_invalid")

    if force_summary:
        if payload_trigger is not None and payload_trigger != "request_summary":
            raise LearningFlowError("coach_output_invalid")
        trigger = "request_summary"
    else:
        if user_event is None:
            raise LearningFlowError("coach_output_invalid")
        event_trigger = user_event.intent or "unknown"
        if payload_trigger is not None and payload_trigger != event_trigger:
            raise LearningFlowError("coach_output_invalid")
        trigger = event_trigger

    if trigger not in COACH_EVENT_TRIGGERS:
        raise LearningFlowError("coach_output_invalid")

    if trigger == "request_summary" or practice_session.final_result == "ac" or practice_session.status == "summarizing":
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
    if trigger == "stuck":
        return {
            "trigger": trigger,
            "proposed_phase": practice_session.phase,
            "next_action": "diagnose_stuck_point",
            "diagnosed_stuck_point": "user_reported_stuck",
        }
    if trigger == "describe_idea":
        proposed_phase = "analyze_feedback" if has_submission_feedback else practice_session.phase
        return {
            "trigger": trigger,
            "proposed_phase": proposed_phase,
            "next_action": "ask_bruteforce_state_and_edges",
            "diagnosed_stuck_point": "bruteforce_state_unclear",
        }
    return {
        "trigger": trigger,
        "proposed_phase": practice_session.phase,
        "next_action": "ask_clarifying_question",
        "diagnosed_stuck_point": "intent_unclear",
    }


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
    reply_md: str,
    decision_accepted: bool,
    guard_reason: str,
    code_attempt_snapshot_id: int | None,
) -> dict[str, Any]:
    return {
        "session_id": practice_session.id,
        "coach_turn_id": coach_turn.id,
        "assistant_event_id": assistant_event.id,
        "code_attempt_snapshot_id": code_attempt_snapshot_id,
        "reply_md": reply_md,
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
