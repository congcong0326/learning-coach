from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.llm_run import LlmRun
from backend.app.models.practice import (
    CoachTurn,
    CodeSnapshot,
    PracticeEvent,
    PracticeSession,
    SessionSummary,
    SubmissionFeedback,
)
from backend.app.prompts import get_prompt
from backend.app.services.learning_flows.coach_turn import run_coach_turn
from backend.app.services.llm_providers.base import LlmProvider
from backend.app.services.llm_run_events import LlmRunEvent
from backend.app.services.profile_service import persist_session_summary_profile_update


logger = logging.getLogger(__name__)
_COACH_SUMMARY_PROMPT = get_prompt("coach_summary")
COACH_SUMMARY_PROMPT_VERSION = _COACH_SUMMARY_PROMPT.version
COACH_SUMMARY_INSTRUCTIONS = _COACH_SUMMARY_PROMPT.instructions
_MAX_SUMMARY_EVENT_CONTENT = 800
_MAX_SUMMARY_EVENTS = 16
_MAX_CODE_ATTEMPT_PREVIEW = 240
_MAX_SUMMARY_FEEDBACK_TEXT = 800
_REQUIRED_COACH_SUMMARY_HEADINGS = (
    "## 单题复盘",
    "### 你做得好的地方",
    "### 需要补强的地方",
    "### 本题关键思路",
    "### 下次遇到同类题",
    "### 画像更新",
)


async def run_coach_summary(
    session: AsyncSession,
    *,
    user_id: int,
    run: LlmRun,
    provider: LlmProvider,
    model_name: str,
    publish: Callable[[LlmRunEvent], Awaitable[None]],
) -> dict[str, Any]:
    result = await run_coach_turn(
        session,
        user_id=user_id,
        run=run,
        provider=provider,
        model_name=model_name,
        publish=publish,
    )
    summary_result = await persist_session_summary_profile_update(
        session,
        user_id=user_id,
        session_id=result["session_id"],
    )
    summary = await session.get(SessionSummary, summary_result.summary_id)
    if summary is not None:
        reply_md = await _generate_summary_reply(
            session,
            user_id=user_id,
            run=run,
            provider=provider,
            model_name=model_name,
            summary=summary,
        )
        assistant_event = await session.get(PracticeEvent, result["assistant_event_id"])
        coach_turn = await session.get(CoachTurn, result["coach_turn_id"])
        if assistant_event is not None:
            assistant_event.content_md = reply_md
        if coach_turn is not None:
            coach_turn.response_json = {
                **coach_turn.response_json,
                "content_md": reply_md,
            }
        run.display_text_md = reply_md
        result["reply_md"] = reply_md
        await session.flush()
    result.update(
        {
            "summary_status": "completed",
            "summary_id": summary_result.summary_id,
            "profile_delta_id": summary_result.delta_id,
            "profile_delta_status": (
                "accepted" if summary_result.accepted else "rejected"
            ),
            "profile_snapshot_id": summary_result.next_snapshot_id,
            "profile_rejection_reason": summary_result.rejection_reason,
        }
    )
    return result


async def _generate_summary_reply(
    session: AsyncSession,
    *,
    user_id: int,
    run: LlmRun,
    provider: LlmProvider,
    model_name: str,
    summary: SessionSummary,
) -> str:
    fallback = _summary_reply_markdown(summary)
    if not model_name:
        return fallback
    input_context = await _summary_input_context(
        session,
        user_id=user_id,
        summary=summary,
    )
    raw_parts: list[str] = []
    final_text = ""
    try:
        async for chunk in provider.stream_text(
            model=model_name,
            instructions=COACH_SUMMARY_INSTRUCTIONS,
            input_text=json.dumps(input_context, ensure_ascii=False),
        ):
            if chunk.text_delta:
                raw_parts.append(chunk.text_delta)
            if chunk.final_text:
                final_text = chunk.final_text
    except Exception as exc:
        logger.warning(
            "coach summary provider failed run_id=%s user_id=%s session_id=%s error_type=%s fallback=true",
            run.id,
            user_id,
            summary.session_id,
            type(exc).__name__,
        )
        return fallback
    if not final_text:
        final_text = "".join(raw_parts)
    reply_md = final_text.strip()
    if not _looks_like_coach_summary(reply_md):
        logger.warning(
            "coach summary output invalid run_id=%s user_id=%s session_id=%s fallback=true",
            run.id,
            user_id,
            summary.session_id,
        )
        return fallback
    return reply_md


async def _summary_input_context(
    session: AsyncSession,
    *,
    user_id: int,
    summary: SessionSummary,
) -> dict[str, Any]:
    practice_session = await _summary_practice_session(
        session,
        user_id=user_id,
        session_id=summary.session_id,
    )
    # 复盘 Prompt 只接收摘要化证据，避免把完整聊天、完整代码或敏感失败细节交给模型。
    return {
        "session": _summary_session_context(practice_session, summary),
        "profile_snapshot": (
            practice_session.profile_snapshot_json if practice_session is not None else {}
        ),
        "summary": {
            "summary_id": summary.id,
            "result": summary.result,
            "final_submission_result": summary.final_submission_result,
            "training_mode": summary.training_mode,
            "phases_visited": summary.phases_visited_json,
            "main_stuck_points": summary.main_stuck_points_json,
            "error_types": summary.error_types_json,
            "max_hint_level_used": summary.max_hint_level_used,
            "attempt_count": summary.attempt_count,
            "complexity_analysis": summary.complexity_analysis_json,
            "invariant_summary_md": _truncate(summary.invariant_summary_md, 800),
            "review_summary_md": _truncate(summary.review_summary_md, 800),
            "profile_signals": summary.profile_signals_json,
            "next_recommendation": summary.next_recommendation_json,
        },
        "events": await _summary_event_context(
            session,
            user_id=user_id,
            session_id=summary.session_id,
        ),
        "code_attempts": await _summary_code_context(
            session,
            user_id=user_id,
            session_id=summary.session_id,
        ),
        "submission_feedbacks": await _summary_feedback_context(
            session,
            user_id=user_id,
            session_id=summary.session_id,
        ),
        "ac_fact": {
            "is_ac": summary.final_submission_result in {"ac", "accepted"},
            "final_submission_result": summary.final_submission_result,
            "attempt_count": summary.attempt_count,
        },
    }


async def _summary_practice_session(
    session: AsyncSession,
    *,
    user_id: int,
    session_id: int,
) -> PracticeSession | None:
    result = await session.execute(
        select(PracticeSession).where(
            PracticeSession.id == session_id,
            PracticeSession.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


def _summary_session_context(
    practice_session: PracticeSession | None,
    summary: SessionSummary,
) -> dict[str, Any]:
    if practice_session is None:
        return {
            "session_id": summary.session_id,
            "problem_id": summary.problem_id,
            "problem_slug": "",
            "training_mode": summary.training_mode,
            "phase": "",
            "status": "",
        }
    return {
        "session_id": practice_session.id,
        "problem_id": practice_session.problem_id,
        "problem_slug": practice_session.problem_slug,
        "training_mode": practice_session.training_mode,
        "phase": practice_session.phase,
        "status": practice_session.status,
        "current_hint_level": practice_session.current_hint_level,
        "visible_hint_gear": practice_session.visible_hint_gear,
        "max_hint_level_used": practice_session.max_hint_level_used,
        "final_result": practice_session.final_result,
    }


async def _summary_event_context(
    session: AsyncSession,
    *,
    user_id: int,
    session_id: int,
) -> list[dict[str, Any]]:
    result = await session.execute(
        select(PracticeEvent)
        .where(
            PracticeEvent.session_id == session_id,
            PracticeEvent.user_id == user_id,
            PracticeEvent.event_type.in_(("user_message", "assistant_message")),
        )
        .order_by(PracticeEvent.created_at.asc(), PracticeEvent.id.asc())
        .limit(_MAX_SUMMARY_EVENTS)
    )
    return [
        {
            "event_id": event.id,
            "event_type": event.event_type,
            "role": event.role,
            "phase": event.phase,
            "intent": event.intent,
            "hint_level": event.hint_level,
            "content_md": _truncate(event.content_md, _MAX_SUMMARY_EVENT_CONTENT),
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        for event in result.scalars()
    ]


async def _summary_code_context(
    session: AsyncSession,
    *,
    user_id: int,
    session_id: int,
) -> list[dict[str, Any]]:
    result = await session.execute(
        select(CodeSnapshot)
        .where(
            CodeSnapshot.session_id == session_id,
            CodeSnapshot.user_id == user_id,
        )
        .order_by(CodeSnapshot.created_at.asc(), CodeSnapshot.id.asc())
    )
    return [
        {
            "snapshot_id": snapshot.id,
            "event_id": snapshot.event_id,
            "language": snapshot.language,
            "source": snapshot.source,
            "client_revision": snapshot.client_revision,
            "code_preview": _truncate(
                snapshot.code_text,
                _MAX_CODE_ATTEMPT_PREVIEW,
            ),
            "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        }
        for snapshot in result.scalars()
    ]


async def _summary_feedback_context(
    session: AsyncSession,
    *,
    user_id: int,
    session_id: int,
) -> list[dict[str, Any]]:
    result = await session.execute(
        select(SubmissionFeedback)
        .where(
            SubmissionFeedback.session_id == session_id,
            SubmissionFeedback.user_id == user_id,
        )
        .order_by(SubmissionFeedback.created_at.asc(), SubmissionFeedback.id.asc())
    )
    return [_feedback_item_context(feedback) for feedback in result.scalars()]


def _feedback_item_context(feedback: SubmissionFeedback) -> dict[str, Any]:
    raw_feedback = (
        feedback.raw_feedback_json if isinstance(feedback.raw_feedback_json, dict) else {}
    )
    note_md = raw_feedback.get("note_md")
    return {
        "feedback_id": feedback.id,
        "event_id": feedback.event_id,
        "code_snapshot_id": feedback.code_snapshot_id,
        "source": feedback.source,
        "result": feedback.result,
        "runtime_ms": feedback.runtime_ms,
        "memory_kb": feedback.memory_kb,
        "failed_case_text": _truncate(
            feedback.failed_case_text,
            _MAX_SUMMARY_FEEDBACK_TEXT,
        ),
        "error_message": _truncate(
            feedback.error_message,
            _MAX_SUMMARY_FEEDBACK_TEXT,
        ),
        "note_md": _truncate(
            note_md if isinstance(note_md, str) else "",
            _MAX_SUMMARY_FEEDBACK_TEXT,
        ),
        "raw_status": raw_feedback.get("status"),
        "submitted_at": (
            feedback.submitted_at.isoformat() if feedback.submitted_at else None
        ),
    }


def _looks_like_coach_summary(markdown: str) -> bool:
    if not markdown:
        return False
    return all(heading in markdown for heading in _REQUIRED_COACH_SUMMARY_HEADINGS)


def _truncate(value: str | None, max_length: int) -> str:
    text = (value or "").strip()
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "..."


def _summary_reply_markdown(summary: SessionSummary) -> str:
    final_result = _result_label(summary.final_submission_result)
    phases = _phase_list(summary.phases_visited_json)
    stuck_points = _markdown_list(
        (_stuck_point_label(point) for point in summary.main_stuck_points_json),
        empty_text="本次没有记录明确卡点。",
    )
    error_types = _markdown_list(
        (_result_label(item) for item in summary.error_types_json),
        empty_text="本次没有记录未通过提交错误类型。",
    )
    complexity_text = _truncate(summary.invariant_summary_md, 220)
    if not complexity_text:
        complexity_text = (
            "复盘时可以继续补充核心状态、边界覆盖方式，以及时间和空间复杂度。"
        )
    review_text = _truncate(summary.review_summary_md, 220)
    if not review_text:
        review_text = "本次代码 review 证据较少，后续可以多记录关键分支和边界用例。"

    return "\n\n".join(
        [
            "## 单题复盘",
            (
                "### 你做得好的地方\n"
                f"- 本题最终结果是 {final_result}，说明你已经完成本轮训练闭环。\n"
                f"- 你经历了这些训练阶段：{phases}。"
            ),
            (
                "### 需要补强的地方\n"
                f"{stuck_points}\n"
                f"- 最高提示档位是 {_hint_label(summary.max_hint_level_used)}，"
                "下次可以更早主动说出卡住的位置。"
            ),
            (
                "### 本题关键思路\n"
                f"- {complexity_text}\n"
                f"- 代码和提交反馈线索：{review_text}\n"
                f"{error_types}"
            ),
            (
                "### 下次遇到同类题\n"
                + _next_recommendation(summary)
            ),
            (
                "### 画像更新\n"
                f"- 本题结果={final_result}，最高提示档位={_hint_label(summary.max_hint_level_used)}，"
                f"尝试次数={summary.attempt_count}。"
            ),
        ]
    )


def _result_label(value: str | None) -> str:
    labels = {
        "ac": "AC",
        "accepted": "AC",
        "wa": "WA",
        "tle": "TLE",
        "re": "RE",
        "mle": "MLE",
        "ce": "CE",
        "unknown": "Unknown",
        "not_submitted": "未提交",
    }
    return labels.get((value or "unknown").lower(), value or "Unknown")


def _hint_label(value: str | None) -> str:
    labels = {
        "questioning": "追问档",
        "direction": "方向档",
        "key_hint": "关键提示档",
        "reflection": "复盘档",
    }
    return labels.get(value or "", value or "未记录")


def _phase_list(values: list[str]) -> str:
    if not values:
        return "未记录"
    labels = {
        "understand_problem": "理解题意",
        "propose_bruteforce": "提出暴力解法",
        "optimize_solution": "推导优化方案",
        "define_invariant": "明确关键不变量",
        "write_code": "编写代码",
        "review_code": "代码 review",
        "submit_to_leetcode": "引导 LeetCode 提交",
        "analyze_feedback": "分析提交反馈",
        "summarize": "单题复盘",
    }
    return " -> ".join(labels.get(value, value) for value in values)


def _stuck_point_label(value: str) -> str:
    labels = {
        "user_reported_stuck": "用户主动表达卡住，需要后续继续定位卡点类型。",
        "reflection_requested": "已进入复盘阶段，需要沉淀可迁移经验。",
    }
    return labels.get(value, value)


def _markdown_list(values: Any, *, empty_text: str) -> str:
    items = [str(value).strip() for value in values if str(value).strip()]
    if not items:
        return f"- {empty_text}"
    return "\n".join(f"- {item}" for item in items)


def _next_recommendation(summary: SessionSummary) -> str:
    recommendation = summary.next_recommendation_json
    if not isinstance(recommendation, dict):
        return "- 继续下一题前，先口头复述本题关键状态、边界用例和复杂度。"
    review_focus = recommendation.get("review_focus")
    if not isinstance(review_focus, str) or not review_focus.strip():
        review_focus = "继续下一题前，先口头复述本题关键状态、边界用例和复杂度。"
    return f"- {review_focus.strip()}"


class CoachSummaryHandler:
    async def execute(self, context: Any) -> dict[str, Any]:
        return await run_coach_summary(
            context.session,
            user_id=context.user_id,
            run=context.run,
            provider=context.provider,
            model_name=context.model_name,
            publish=context.publish,
        )
