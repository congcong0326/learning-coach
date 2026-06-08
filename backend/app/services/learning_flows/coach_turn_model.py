from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.llm_run import LlmRun
from backend.app.models.practice import (
    CodeSnapshot,
    PracticeEvent,
    PracticeSession,
    SubmissionFeedback,
)
from backend.app.services.code_attempts import ExtractedCode
from backend.app.services.learning_flows.coach_turn_context import coach_input_context
from backend.app.services.learning_flows.coach_turn_policy import (
    COACH_REPLY_INSTRUCTIONS,
    fallback_coach_decision,
    parse_coach_json,
)
from backend.app.services.learning_flows.goal_plan import LearningFlowError
from backend.app.services.llm_providers.base import LlmProvider


logger = logging.getLogger(__name__)


async def coach_decision(
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
    chat_feedback_context: dict[str, Any] | None,
    has_feedback: bool,
    target_code_language: dict[str, str] | None,
    trigger_context: dict[str, str],
    rag_context: dict[str, Any],
) -> dict[str, Any]:
    fallback = fallback_coach_decision(trigger_context)
    if run.kind != "coach_turn" or not model_name:
        return fallback

    raw_parts: list[str] = []
    final_text = ""
    try:
        async for chunk in provider.stream_text(
            model=model_name,
            instructions=COACH_REPLY_INSTRUCTIONS,
            input_text=json.dumps(
                coach_input_context(
                    practice_session,
                    user_event=user_event,
                    code_snapshot=code_snapshot,
                    extracted_code=extracted_code,
                    latest_submission_feedback=latest_submission_feedback,
                    chat_feedback_context=chat_feedback_context,
                    has_feedback=has_feedback,
                    target_code_language=target_code_language,
                    trigger_context=trigger_context,
                    rag_context=rag_context,
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
        return parse_coach_json(final_text)
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
