from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.coach_graph import CoachGraph, CoachGraphState
from backend.app.models.llm_run import LlmRun
from backend.app.models.practice import (
    CoachTurn,
    CodeSnapshot,
    PracticeEvent,
    PracticeSession,
    SubmissionFeedback,
)
from backend.app.services.coach_guard import guard_transition
from backend.app.services.agent_trace_service import append_agent_trace
from backend.app.services.code_attempts import (
    ExtractedCode,
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
SUMMARY_SAFE_REPLY = (
    "LeetCode AC 已记录。下面进入单题复盘：我会围绕本题最终结果、"
    "关键思路、主要卡点、提示使用和下一步训练建议做沉淀。"
)
DIAGNOSED_STUCK_POINT_MAX_LENGTH = 120
NEXT_ACTION_MAX_LENGTH = 60
COACH_REPLY_INSTRUCTIONS = (
    "默认语言语境：简体中文。你是 Agentic Coding Learning Coach 的单题 AI 教练，"
    "必须根据当前题目训练上下文、用户画像、训练阶段、提示档位和用户本轮输入生成下一步教练回复。"
    "不要机械重复固定流程；如果用户已经给出清晰思路，可以快进到不变量、代码或提交阶段。"
    "低提示档位下不要泄露完整可提交答案。只输出 JSON 对象，不要输出解释性前后缀。"
    "JSON 字段必须包含：phase_after、diagnosed_stuck_point、next_action、reply_md、"
    "should_reveal_solution。phase_after 只能使用允许状态；reply_md 必须是面向用户的简体中文。"
    "如果 user_submitted_code 非空，优先判断本轮是否应进入 review_code，并且只基于其中的代码内容做代码质量判断。"
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
HINT_LEVEL_ORDER = ["questioning", "direction", "key_hint", "reflection"]
HINT_LEVEL_INDEX = {level: index for index, level in enumerate(HINT_LEVEL_ORDER)}

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
    latest_submission_feedback = await _load_latest_submission_feedback(
        session,
        user_id=user_id,
        session_id=practice_session.id,
    )
    has_feedback = latest_submission_feedback is not None
    graph_state = await CoachGraph().run_turn(
        _coach_graph_state(
            practice_session,
            user_id=user_id,
            run=run,
            code_snapshot=code_snapshot,
            latest_submission_feedback=latest_submission_feedback,
        )
    )
    trigger_context = _trigger_context(
        payload,
        practice_session,
        user_event=user_event,
        has_submission_feedback=has_feedback,
        force_summary=run.kind == "coach_summary",
        extracted_code=extracted_code,
    )
    await _publish_progress(
        publish,
        run_id=run.id,
        stage="loading_context",
        message="正在准备训练上下文",
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
        stage="calling_model",
        message="正在调用大模型",
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
        extracted_code=extracted_code,
        latest_submission_feedback=latest_submission_feedback,
        has_feedback=has_feedback,
        trigger_context=trigger_context,
    )
    await _publish_progress(
        publish,
        run_id=run.id,
        stage="guarding_transition",
        message="正在校验教练阶段",
    )
    hint_level_after_policy = _hint_level_after_turn(
        practice_session.current_hint_level,
        trigger=trigger_context["trigger"],
        proposed_phase_after=coach_decision["phase_after"],
    )
    decision = guard_transition(
        phase_before=practice_session.phase,
        proposed_phase_after=coach_decision["phase_after"],
        has_code=practice_session.latest_code_snapshot_id is not None
        or extracted_code is not None,
        has_submission_feedback=has_feedback,
        has_terminal_result=practice_session.final_result == "ac",
        hint_level=hint_level_after_policy,
        should_reveal_solution=bool(coach_decision["should_reveal_solution"]),
    )
    reply_md = _reply_after_guard(coach_decision, decision_reason=decision.reason)
    await publish(LlmRunEvent("delta", {"run_id": run.id, "text": reply_md}))
    await _publish_progress(
        publish,
        run_id=run.id,
        stage="saving_reply",
        message="正在保存教练回复",
    )

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
        practice_session.visible_hint_gear = _hint_level_index(decision.hint_level_after)
        practice_session.max_hint_level_used = _max_hint_level(
            practice_session.max_hint_level_used,
            decision.hint_level_after,
        )
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
        graph_state=graph_state,
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
    await _append_coach_turn_traces(
        session,
        practice_session=practice_session,
        run=run,
        graph_state=graph_state,
        coach_decision=coach_decision,
        decision_accepted=decision.accepted,
        guard_reason=decision.reason,
        reply_md=reply_md,
        model_name=model_name,
        phase_before=phase_before,
    )
    return result


async def _append_coach_turn_traces(
    session: AsyncSession,
    *,
    practice_session: PracticeSession,
    run: LlmRun,
    graph_state: CoachGraphState,
    coach_decision: dict[str, Any],
    decision_accepted: bool,
    guard_reason: str,
    reply_md: str,
    model_name: str,
    phase_before: str,
) -> None:
    common: dict[str, Any] = {
        "session_id": practice_session.id,
        "thread_id": graph_state["thread_id"],
        "problem_slug": practice_session.problem_slug,
        "prompt_version": PROMPT_VERSION,
        "model_name": model_name,
    }
    await append_agent_trace(
        session,
        **common,
        node_name="llm_run_started",
        phase=phase_before,
        hint_level=practice_session.current_hint_level,
        input_summary={"run_id": run.id, "kind": run.kind},
        output_summary={"status": "started"},
    )
    for item in graph_state["trace"]:
        node_name = str(item.get("node") or "")
        if node_name == "guard_transition":
            continue
        output_summary: dict[str, Any] = {"status": "completed"}
        if node_name == "retrieve_supporting_context":
            output_summary = {
                "retrieval_status": graph_state["retrieval_context"].get("status"),
                "rag_deferred": True,
            }
        await append_agent_trace(
            session,
            **common,
            node_name=node_name,
            phase=str(item.get("phase") or practice_session.phase),
            hint_level=item.get("hint_level"),
            input_summary={"run_id": run.id},
            output_summary=output_summary,
        )
    await append_agent_trace(
        session,
        **common,
        node_name="guard_transition",
        phase=phase_before,
        hint_level=practice_session.current_hint_level,
        input_summary={
            "model_phase_after": coach_decision["phase_after"],
            "should_reveal_solution": coach_decision["should_reveal_solution"],
        },
        output_summary={
            "guard_accepted": decision_accepted,
            "guard_reason": guard_reason,
            "phase_after": practice_session.phase,
        },
        stuck_point=coach_decision["diagnosed_stuck_point"],
        should_reveal_solution=bool(coach_decision["should_reveal_solution"]),
    )
    await append_agent_trace(
        session,
        **common,
        node_name="final_reply",
        phase=practice_session.phase,
        hint_level=practice_session.current_hint_level,
        input_summary={"reply_length": len(reply_md)},
        output_summary={"reply_preview": reply_md[:240]},
        stuck_point=coach_decision["diagnosed_stuck_point"],
        should_reveal_solution=bool(coach_decision["should_reveal_solution"]),
    )
    await append_agent_trace(
        session,
        **common,
        node_name="llm_run_completed",
        phase=practice_session.phase,
        hint_level=practice_session.current_hint_level,
        input_summary={"run_id": run.id, "kind": run.kind},
        output_summary={"status": "completed"},
        error_summary=str(coach_decision.get("error_summary") or ""),
    )


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
            PracticeEvent.event_type.in_(("user_message", "submission_feedback")),
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


async def _load_latest_submission_feedback(
    session: AsyncSession,
    *,
    user_id: int,
    session_id: int,
) -> SubmissionFeedback | None:
    result = await session.execute(
        select(SubmissionFeedback)
        .where(
            SubmissionFeedback.session_id == session_id,
            SubmissionFeedback.user_id == user_id,
        )
        .order_by(
            SubmissionFeedback.submitted_at.desc(),
            SubmissionFeedback.id.desc(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


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
    extracted_code: ExtractedCode | None,
    latest_submission_feedback: SubmissionFeedback | None,
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
                    extracted_code=extracted_code,
                    latest_submission_feedback=latest_submission_feedback,
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
        return {
            **fallback,
            "error_summary": f"provider_failed:{type(exc).__name__}",
        }

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
        return {**fallback, "error_summary": exc.code}


def _coach_input_context(
    practice_session: PracticeSession,
    *,
    user_event: PracticeEvent | None,
    code_snapshot: CodeSnapshot | None,
    extracted_code: ExtractedCode | None,
    latest_submission_feedback: SubmissionFeedback | None,
    has_feedback: bool,
    trigger_context: dict[str, str],
) -> dict[str, Any]:
    latest_code: dict[str, Any] | None = None
    if code_snapshot is not None:
        latest_code = {
            **(_latest_code_attempt_context(code_snapshot) or {}),
            "code_text": code_snapshot.code_text,
        }
    user_submitted_code: dict[str, Any] | None = None
    if extracted_code is not None:
        user_submitted_code = {
            "language": extracted_code.language,
            "code_text": extracted_code.code_text,
        }
    feedback_context = _submission_feedback_context(latest_submission_feedback)
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
        "user_submitted_code": user_submitted_code,
        "latest_code": latest_code,
        "latest_submission_feedback": feedback_context,
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


def _coach_graph_state(
    practice_session: PracticeSession,
    *,
    user_id: int,
    run: LlmRun,
    code_snapshot: CodeSnapshot | None,
    latest_submission_feedback: SubmissionFeedback | None,
) -> CoachGraphState:
    thread_id = _ensure_thread_id(practice_session)
    profile_snapshot = practice_session.profile_snapshot_json
    profile_summary = ""
    if isinstance(profile_snapshot, dict):
        profile_summary = str(profile_snapshot.get("recent_summary") or "")
    return {
        "user_id": user_id,
        "session_id": practice_session.id,
        "thread_id": thread_id,
        "study_plan_id": practice_session.study_plan_id,
        "latest_plan_version_id": practice_session.latest_plan_version_id,
        "latest_plan_item_id": practice_session.latest_plan_item_id,
        "problem_id": practice_session.problem_id,
        "problem_slug": practice_session.problem_slug,
        "phase": practice_session.phase,
        "hint_level": practice_session.current_hint_level,
        "profile_summary": profile_summary[:1200],
        "recent_events": [],
        "latest_code_attempt": _latest_code_attempt_context(code_snapshot),
        "latest_submission_feedback": _submission_feedback_context(
            latest_submission_feedback
        ),
        "run": {
            "id": run.id,
            "kind": run.kind,
            "related_type": run.related_type,
            "related_id": run.related_id,
        },
        "trace": [],
        "error_summary": "",
        "retrieval_context": {"status": "not_loaded", "chunks": []},
    }


def _ensure_thread_id(practice_session: PracticeSession) -> str:
    if practice_session.thread_id:
        return practice_session.thread_id
    practice_session.thread_id = f"practice-session-{practice_session.id}"
    return practice_session.thread_id


def _latest_code_attempt_context(
    code_snapshot: CodeSnapshot | None,
) -> dict[str, Any] | None:
    if code_snapshot is None:
        return None
    return {
        "snapshot_id": code_snapshot.id,
        "language": code_snapshot.language,
        "source": code_snapshot.source,
        "client_revision": code_snapshot.client_revision,
    }


def _submission_feedback_context(
    feedback: SubmissionFeedback | None,
) -> dict[str, Any] | None:
    if feedback is None:
        return None
    raw_feedback = feedback.raw_feedback_json
    note_md = ""
    if isinstance(raw_feedback, dict) and isinstance(raw_feedback.get("note_md"), str):
        note_md = raw_feedback["note_md"]
    return {
        "result": feedback.result,
        "code_snapshot_id": feedback.code_snapshot_id,
        "failed_case_text": feedback.failed_case_text[:1200],
        "error_message": feedback.error_message[:1200],
        "note_md": note_md[:1200],
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
    diagnosed_stuck_point = diagnosed_stuck_point.strip()
    next_action = next_action.strip()
    if len(diagnosed_stuck_point) > DIAGNOSED_STUCK_POINT_MAX_LENGTH:
        raise LearningFlowError("coach_output_invalid")
    if len(next_action) > NEXT_ACTION_MAX_LENGTH:
        raise LearningFlowError("coach_output_invalid")
    return {
        "phase_after": phase_after,
        "diagnosed_stuck_point": diagnosed_stuck_point,
        "next_action": next_action,
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
    # 复盘 run 允许不依赖模型资产执行，兜底文案必须保持复盘语境，
    # 不能复用普通教练回合的前置追问。
    reply_md = (
        SUMMARY_SAFE_REPLY
        if trigger_context["trigger"] == "request_summary"
        or trigger_context["next_action"] == "summarize_session"
        else SAFE_REPLY
    )
    return {
        "phase_after": trigger_context["proposed_phase"],
        "diagnosed_stuck_point": trigger_context["diagnosed_stuck_point"],
        "next_action": trigger_context["next_action"],
        "reply_md": reply_md,
        "should_reveal_solution": False,
        "generation_mode": "fallback",
        "error_summary": "",
    }


def _reply_after_guard(
    coach_decision: dict[str, Any],
    *,
    decision_reason: str,
) -> str:
    if decision_reason == "hint_level_prevents_solution_reveal":
        return SAFE_REPLY
    return str(coach_decision["reply_md"])


def _hint_level_after_turn(
    current_hint_level: str,
    *,
    trigger: str,
    proposed_phase_after: str,
) -> str:
    if proposed_phase_after == "summarize" or trigger == "request_summary":
        return "reflection"
    current_index = HINT_LEVEL_INDEX.get(current_hint_level, 0)
    if trigger == "request_hint":
        return HINT_LEVEL_ORDER[min(current_index + 1, HINT_LEVEL_INDEX["key_hint"])]
    if trigger in {"describe_idea", "code_review", "submit_feedback"} and current_index > 0:
        return HINT_LEVEL_ORDER[current_index - 1]
    return current_hint_level if current_hint_level in HINT_LEVEL_INDEX else "questioning"


def _hint_level_index(hint_level: str) -> int:
    return HINT_LEVEL_INDEX.get(hint_level, 0)


def _max_hint_level(current: str, candidate: str) -> str:
    current_index = HINT_LEVEL_INDEX.get(current, 0)
    candidate_index = HINT_LEVEL_INDEX.get(candidate, 0)
    return HINT_LEVEL_ORDER[max(current_index, candidate_index)]


def _trigger_context(
    payload: dict[str, Any],
    practice_session: PracticeSession,
    *,
    user_event: PracticeEvent | None,
    has_submission_feedback: bool,
    force_summary: bool,
    extracted_code: ExtractedCode | None,
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
    if trigger in {"unknown", "describe_idea"} and extracted_code is not None:
        return {
            "trigger": trigger,
            "proposed_phase": "review_code",
            "next_action": "review_code",
            "diagnosed_stuck_point": "code_review_candidate",
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
    graph_state: CoachGraphState,
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
        "graph": {
            "thread_id": graph_state["thread_id"],
            "retrieval_context": graph_state["retrieval_context"],
            "node_trace": graph_state["trace"],
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
