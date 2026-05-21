from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.learning import GoalCalibrationDraft
from backend.app.models.llm_run import LlmRun
from backend.app.services.learning_flows.goal_plan import LearningFlowError, PROMPT_VERSION
from backend.app.services.llm_providers.base import LlmProvider
from backend.app.services.llm_run_events import LlmRunEvent
from backend.app.services.llm_run_service import (
    LlmRunError,
    ensure_llm_run_mutable,
    update_llm_run_display_text,
)


FOLLOWUP_INSTRUCTIONS = (
    "默认语言语境：简体中文。你是目标校准教练。根据用户的原始目标校准信息，"
    "判断是否还需要提出 1 个关键追问。信息足够时只输出 null；需要追问时只输出 "
    'JSON 对象，格式为 {"question_id": "q1", "question": "问题文本"}。'
    "question 必须使用简体中文。不要输出解释性前后缀。"
)
MAX_FOLLOWUPS = 3

logger = logging.getLogger(__name__)


async def run_goal_followup(
    session: AsyncSession,
    *,
    user_id: int,
    run: LlmRun,
    provider: LlmProvider,
    model_name: str,
    publish: Callable[[LlmRunEvent], Awaitable[None]],
) -> dict[str, Any]:
    await _ensure_run_mutable(session, run)
    payload = run.input_json if isinstance(run.input_json, dict) else {}
    logger.info(
        "goal followup flow started run_id=%s user_id=%s model=%s",
        run.id,
        user_id,
        model_name,
    )
    await _publish_progress(
        publish,
        run_id=run.id,
        stage="calibrating_goal",
        message="正在校准训练目标",
    )

    display_parts: list[str] = []
    final_text = ""
    try:
        async for chunk in provider.stream_text(
            model=model_name,
            instructions=FOLLOWUP_INSTRUCTIONS,
            input_text=json.dumps(
                {"payload": payload, "history": []},
                ensure_ascii=False,
            ),
        ):
            if chunk.text_delta:
                display_parts.append(chunk.text_delta)
                await publish(
                    LlmRunEvent("delta", {"run_id": run.id, "text": chunk.text_delta})
                )
                await _update_display_text(session, run, "".join(display_parts))
            if chunk.final_text:
                final_text = chunk.final_text
    except LearningFlowError:
        raise
    except Exception as exc:
        logger.warning(
            "goal followup flow provider failed run_id=%s user_id=%s error_type=%s",
            run.id,
            user_id,
            type(exc).__name__,
        )
        raise LearningFlowError("llm_provider_error") from None

    await _ensure_run_mutable(session, run)
    question = _parse_followup_json(final_text)
    history = [question] if question is not None else []
    status = "asking_followup" if question is not None else "collecting_input"
    now = datetime.now(UTC)
    draft = GoalCalibrationDraft(
        user_id=user_id,
        input_json=payload,
        followup_messages_json=history,
        draft_goal_json={},
        draft_plan_json={},
        validation_report_json={},
        repair_log_json=[],
        prompt_version=PROMPT_VERSION,
        model_name=model_name,
        status=status,
        error_message="",
        created_at=now,
        updated_at=now,
    )
    session.add(draft)
    await session.flush()

    # 首次目标校准的 run 创建时还没有 draft_id；成功事务提交前先建立关联，
    # 由 orchestrator 负责最终 succeed commit 和 result 事件。
    await _ensure_run_mutable(session, run)
    run.related_type = "goal_calibration_draft"
    run.related_id = draft.id
    await session.flush()
    await _ensure_run_mutable(session, run)

    result = _goal_calibration_start_response(draft)
    logger.info(
        "goal followup flow completed run_id=%s user_id=%s draft_id=%s "
        "status=%s has_followup=%s remaining_followups=%s",
        run.id,
        user_id,
        draft.id,
        draft.status,
        question is not None,
        result["remaining_followups"],
    )
    return result


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


def _parse_followup_json(final_text: str) -> dict[str, Any] | None:
    text = final_text.strip()
    if text == "null":
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LearningFlowError("followup_json_invalid") from exc
    if not isinstance(parsed, dict):
        raise LearningFlowError("followup_json_invalid")
    question_id = parsed.get("question_id")
    question = parsed.get("question")
    if not isinstance(question_id, str) or not question_id:
        raise LearningFlowError("followup_json_invalid")
    if not isinstance(question, str) or not question:
        raise LearningFlowError("followup_json_invalid")
    return {
        "role": "assistant",
        "question_id": question_id,
        "question": question,
    }


def _followup_question_count(history: list[dict[str, Any]]) -> int:
    return sum(1 for item in history if item.get("role") == "assistant")


def _goal_calibration_start_response(draft: GoalCalibrationDraft) -> dict[str, Any]:
    history = draft.followup_messages_json if isinstance(draft.followup_messages_json, list) else []
    last_message = history[-1] if history else {}
    last_question = (
        last_message
        if draft.status == "asking_followup" and last_message.get("role") == "assistant"
        else {}
    )
    question_count = _followup_question_count(history)
    return {
        "draft_id": draft.id,
        "status": draft.status,
        "followup_question": last_question.get("question"),
        "followup_question_id": last_question.get("question_id"),
        "remaining_followups": (
            max(0, MAX_FOLLOWUPS - question_count)
            if draft.status == "asking_followup"
            else 0
        ),
    }


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
