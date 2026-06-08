from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.coach_graph import CoachGraph
from backend.app.models.llm_run import LlmRun
from backend.app.models.practice import CoachTurn, PracticeEvent
from backend.app.rag.retrieval import RetrievalService
from backend.app.services.coach_guard import guard_transition
from backend.app.services.code_attempts import (
    extract_code_from_message,
    persist_review_code_attempt,
    quality_from_decision,
)
from backend.app.services.learning_flows.coach_turn_context import (
    chat_feedback_context as _build_chat_feedback_context,
    coach_graph_state as _build_coach_graph_state,
    coach_input_context,
    context_snapshot,
    ensure_thread_id,
    latest_code_attempt_context,
    load_latest_code_snapshot,
    load_latest_submission_feedback,
    load_practice_session,
    load_user_event,
    payload_for_run,
    problem_tags_context,
    rag_context_for_prompt,
    rag_query_summary,
    selected_rag_chunk_ids,
    submission_feedback_context,
    target_code_language_context,
)
from backend.app.services.learning_flows.coach_turn_model import (
    coach_decision as _generate_coach_decision,
)
from backend.app.services.learning_flows.coach_turn_policy import (
    PROMPT_VERSION,
    chat_feedback_result,
    fallback_coach_decision,
    hint_level_after_turn,
    hint_level_index,
    max_hint_level,
    parse_coach_json,
    reply_after_guard,
    should_persist_code_attempt,
    strip_json_fence,
    trigger_context as _build_trigger_context,
    user_intent,
)
from backend.app.services.learning_flows.coach_turn_trace import (
    append_coach_turn_traces,
)
from backend.app.services.learning_flows.goal_plan import LearningFlowError
from backend.app.services.llm_providers.base import LlmProvider
from backend.app.services.llm_run_events import LlmRunEvent
from backend.app.services.llm_run_service import (
    LlmRunError,
    ensure_llm_run_mutable,
)


logger = logging.getLogger(__name__)

# 兼容既有测试和潜在内部导入；实际实现已移动到职责更明确的小模块。
_chat_feedback_result = chat_feedback_result
_coach_graph_state = _build_coach_graph_state
_coach_input_context = coach_input_context
_context_snapshot = context_snapshot
_ensure_thread_id = ensure_thread_id
_fallback_coach_decision = fallback_coach_decision
_hint_level_after_turn = hint_level_after_turn
_hint_level_index = hint_level_index
_latest_code_attempt_context = latest_code_attempt_context
_load_latest_code_snapshot = load_latest_code_snapshot
_load_latest_submission_feedback = load_latest_submission_feedback
_load_practice_session = load_practice_session
_load_user_event = load_user_event
_max_hint_level = max_hint_level
_parse_coach_json = parse_coach_json
_payload_for_run = payload_for_run
_problem_tags_context = problem_tags_context
_rag_context_for_prompt = rag_context_for_prompt
_rag_query_summary = rag_query_summary
_reply_after_guard = reply_after_guard
_selected_rag_chunk_ids = selected_rag_chunk_ids
_should_persist_code_attempt = should_persist_code_attempt
_strip_json_fence = strip_json_fence
_submission_feedback_context = submission_feedback_context
_target_code_language_context = target_code_language_context
_trigger_context = _build_trigger_context
_user_intent = user_intent

__all__ = [
    "CoachTurnHandler",
    "PROMPT_VERSION",
    "_chat_feedback_result",
    "_parse_coach_json",
    "run_coach_turn",
]


class CoachTurnHandler:
    """LLM Run 的教练回合适配器。

    该类只负责把 registry 传入的通用执行上下文转换为 `run_coach_turn`
    所需参数；教练策略、上下文加载、模型调用和持久化都由下游模块处理。
    """

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
    """执行单轮 AI 教练：加载上下文、调用模型、守卫状态迁移并持久化结果。"""
    # 入口先确认 run 仍可写，并锁定训练会话；后续回复、阶段迁移和 run 终态要在同一事务完成。
    await _ensure_run_mutable(session, run)
    payload = payload_for_run(run)
    practice_session = await load_practice_session(
        session,
        user_id=user_id,
        run=run,
        payload=payload,
    )
    # coach_summary 是系统触发的复盘 run，可能没有用户消息；普通 coach_turn 必须绑定本轮用户事件。
    user_event = await load_user_event(
        session,
        user_id=user_id,
        session_id=practice_session.id,
        payload=payload,
        required=run.kind == "coach_turn",
    )
    # 用户消息里的代码块、最近代码快照和提交反馈共同决定本轮是否进入 review 或反馈分析。
    extracted_code = (
        extract_code_from_message(user_event.content_md)
        if user_event is not None
        else None
    )
    code_snapshot = await load_latest_code_snapshot(
        session,
        user_id=user_id,
        practice_session=practice_session,
    )
    latest_submission_feedback = await load_latest_submission_feedback(
        session,
        user_id=user_id,
        session_id=practice_session.id,
    )
    # 用户直接在聊天里粘贴 WA/TLE/RE 等平台结果时，也按提交反馈处理，避免强制走单独表单。
    chat_feedback = _build_chat_feedback_context(
        user_event,
        code_snapshot=code_snapshot,
    )
    if chat_feedback is not None:
        logger.info(
            "coach turn chat feedback detected run_id=%s user_id=%s session_id=%s "
            "result=%s code_snapshot_id=%s",
            run.id,
            user_id,
            practice_session.id,
            chat_feedback["result"],
            chat_feedback["code_snapshot_id"],
        )
    has_feedback = latest_submission_feedback is not None or chat_feedback is not None
    target_code_language = await target_code_language_context(
        session,
        user_id=user_id,
        practice_session=practice_session,
    )
    # 触发器是本轮教练决策的路由信号；它会影响目标阶段、RAG query 摘要和兜底回复。
    trigger = _build_trigger_context(
        payload,
        practice_session,
        user_event=user_event,
        has_submission_feedback=has_feedback,
        force_summary=run.kind == "coach_summary",
        extracted_code=extracted_code,
        chat_feedback_context=chat_feedback,
    )
    problem_tags = await problem_tags_context(
        session,
        problem_id=practice_session.problem_id,
    )
    # CoachGraph 负责整理图状态、RAG 检索和节点 trace；RAG 只能增强教练判断，不能绕过状态守卫。
    graph_state = await CoachGraph(
        retrieval_service=RetrievalService(session),
    ).run_turn(
        _build_coach_graph_state(
            practice_session,
            user_id=user_id,
            run=run,
            code_snapshot=code_snapshot,
            latest_submission_feedback=latest_submission_feedback,
            chat_feedback_context=chat_feedback,
            problem_tags=problem_tags,
            user_query_summary=rag_query_summary(
                user_event=user_event,
                extracted_code=extracted_code,
                latest_submission_feedback=latest_submission_feedback,
                chat_feedback_context=chat_feedback,
                trigger_context=trigger,
            ),
        )
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
        trigger["proposed_phase"],
        model_name,
    )
    await _publish_progress(
        publish,
        run_id=run.id,
        stage="calling_model",
        message="正在调用大模型",
    )
    # LLM 只产出诊断、回复草稿和建议阶段；最终能否跳转由下面的 coach_guard 统一裁决。
    coach_decision = await _generate_coach_decision(
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
        chat_feedback_context=chat_feedback,
        has_feedback=has_feedback,
        target_code_language=target_code_language,
        trigger_context=trigger,
        rag_context=graph_state["retrieval_context"],
    )
    await _publish_progress(
        publish,
        run_id=run.id,
        stage="guarding_transition",
        message="正在校验教练阶段",
    )
    # 提示档位先按用户行为推进，再进入阶段守卫，防止低提示档位泄题或无证据快进。
    hint_level_after_policy = hint_level_after_turn(
        practice_session.current_hint_level,
        trigger=trigger["trigger"],
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
    # 用户看到的是 guard 处理后的安全回复；模型建议不合法时会被回退到当前训练边界内。
    reply_md = reply_after_guard(coach_decision, decision_reason=decision.reason)
    await publish(LlmRunEvent("delta", {"run_id": run.id, "text": reply_md}))
    await _publish_progress(
        publish,
        run_id=run.id,
        stage="saving_reply",
        message="正在保存教练回复",
    )

    now = datetime.now(UTC)
    phase_before = practice_session.phase
    # assistant_event 写入聊天时间线；CoachTurn 写入可审计的结构化回合记录，二者通过同一个 run 串联。
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
            "trigger": trigger["trigger"],
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
        user_intent=user_intent(user_event),
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
        context_snapshot_json=context_snapshot(
            practice_session,
            has_feedback=has_feedback,
            rag_context=graph_state["retrieval_context"],
        ),
        created_at=now,
    )
    session.add(coach_turn)
    code_attempt_snapshot_id: int | None = None
    # 只有进入 review_code 或模型已建议去 LeetCode 提交时，才把本轮代码沉淀为尝试记录。
    if (
        user_event is not None
        and extracted_code is not None
        and should_persist_code_attempt(
            decision_phase_after=decision.phase_after,
            decision_accepted=decision.accepted,
            model_phase_after=coach_decision["phase_after"],
        )
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
    # 只有守卫接受时才推进 session 状态；被拒绝的模型跳转会保留原因，但不污染训练阶段。
    if decision.accepted:
        practice_session.phase = decision.phase_after
        practice_session.current_hint_level = decision.hint_level_after
        practice_session.visible_hint_gear = hint_level_index(decision.hint_level_after)
        practice_session.max_hint_level_used = max_hint_level(
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
    await append_coach_turn_traces(
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


def _result_payload(
    practice_session: Any,
    *,
    coach_turn: CoachTurn,
    assistant_event: PracticeEvent,
    reply_md: str,
    decision_accepted: bool,
    guard_reason: str,
    code_attempt_snapshot_id: int | None,
    graph_state: Any,
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
