from __future__ import annotations

import re
import logging
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.coach_loop import CoachLoopState
from backend.app.models.learning import StudyPlan, StudyPlanVersion
from backend.app.models.llm_run import LlmRun
from backend.app.models.practice import (
    CodeSnapshot,
    PracticeEvent,
    PracticeSession,
    SubmissionFeedback,
)
from backend.app.models.problem import Problem
from backend.app.services.code_attempts import ExtractedCode
from backend.app.services.learning_flows.coach_turn_policy import (
    CHAT_FEEDBACK_TEXT_MAX_LENGTH,
    COACH_PHASES,
    TARGET_CODE_LANGUAGE_LABELS,
    USER_MESSAGE_TEXT_MAX_LENGTH,
    chat_feedback_result,
    user_intent,
)
from backend.app.services.learning_flows.goal_plan import LearningFlowError


logger = logging.getLogger(__name__)


async def load_practice_session(
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


def payload_for_run(run: LlmRun) -> dict[str, Any]:
    if not isinstance(run.input_json, dict):
        raise LearningFlowError("coach_output_invalid")
    return run.input_json


async def load_user_event(
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


async def load_latest_code_snapshot(
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


async def has_submission_feedback(
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


async def load_latest_submission_feedback(
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


async def target_code_language_context(
    session: AsyncSession,
    *,
    user_id: int,
    practice_session: PracticeSession,
) -> dict[str, str] | None:
    version_id = (
        practice_session.latest_plan_version_id
        or practice_session.origin_plan_version_id
    )
    if version_id is None:
        return None
    result = await session.execute(
        select(StudyPlanVersion.target_snapshot_json)
        .join(StudyPlan, StudyPlan.id == StudyPlanVersion.plan_id)
        .where(
            StudyPlanVersion.id == version_id,
            StudyPlan.id == practice_session.study_plan_id,
            StudyPlan.user_id == user_id,
        )
    )
    target_snapshot = result.scalar_one_or_none()
    if not isinstance(target_snapshot, dict):
        return None
    language = target_snapshot.get("preferred_language")
    if not isinstance(language, str) or language not in TARGET_CODE_LANGUAGE_LABELS:
        return None
    # 目标训练语言来自学习计划，不来自用户自由输入；模型只能消费规范化枚举和展示标签。
    return {
        "value": language,
        "label": TARGET_CODE_LANGUAGE_LABELS[language],
        "source": "study_plan_target_snapshot",
    }


async def problem_tags_context(
    session: AsyncSession,
    *,
    problem_id: int,
) -> list[str]:
    result = await session.execute(
        select(Problem.metadata_json).where(Problem.id == problem_id)
    )
    metadata = result.scalar_one_or_none()
    if not isinstance(metadata, dict):
        return []
    tags = metadata.get("topic_tags")
    if not isinstance(tags, list):
        return []
    normalized: list[str] = []
    for item in tags:
        if not isinstance(item, dict):
            continue
        slug = item.get("slug")
        if isinstance(slug, str) and slug:
            normalized.append(slug)
    return normalized


def coach_input_context(
    practice_session: PracticeSession,
    *,
    user_event: PracticeEvent | None,
    code_snapshot: CodeSnapshot | None,
    extracted_code: ExtractedCode | None,
    latest_submission_feedback: SubmissionFeedback | None,
    chat_feedback_context: dict[str, Any] | None,
    has_feedback: bool,
    target_code_language: dict[str, str] | None,
    trigger_context: dict[str, str],
) -> dict[str, Any]:
    latest_code: dict[str, Any] | None = None
    if code_snapshot is not None:
        latest_code = {
            **(latest_code_attempt_context(code_snapshot) or {}),
            "code_text": code_snapshot.code_text,
        }
    user_submitted_code: dict[str, Any] | None = None
    if extracted_code is not None:
        user_submitted_code = {
            "language": extracted_code.language,
            "code_text": extracted_code.code_text,
        }
    feedback_context = submission_feedback_context(
        latest_submission_feedback,
        chat_feedback_context,
    )
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
            "target_code_language": target_code_language,
        },
        "profile_snapshot": practice_session.profile_snapshot_json,
        "trigger_context": trigger_context,
        "user_message": {
            "intent": user_intent(user_event),
            "content_md": user_message_content_context(
                user_event,
                chat_feedback_context=chat_feedback_context,
            ),
            "hint_level": user_event.hint_level if user_event is not None else None,
        },
        "user_submitted_code": user_submitted_code,
        "latest_code": latest_code,
        "latest_submission_feedback": feedback_context,
        "output_contract": {
            "phase_after": "one allowed phase",
            "diagnosed_stuck_point": "short stable snake_case string",
            "next_action": "short stable snake_case string",
            "reply_md": "简体中文教练回复；如包含代码示例，使用 session.target_code_language",
            "should_reveal_solution": "boolean",
            "code_quality_status": "optional pending | needs_fix | ready_to_submit when reviewing code",
            "code_quality_comment": "optional short Chinese review summary",
        },
    }


def coach_loop_state(
    practice_session: PracticeSession,
    *,
    user_id: int,
    run: LlmRun,
    code_snapshot: CodeSnapshot | None,
    latest_submission_feedback: SubmissionFeedback | None,
    chat_feedback_context: dict[str, Any] | None,
    problem_tags: list[str],
    user_query_summary: str,
) -> CoachLoopState:
    thread_id = ensure_thread_id(practice_session)
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
        "problem_tags": problem_tags,
        "phase": practice_session.phase,
        "hint_level": practice_session.current_hint_level,
        "profile_summary": profile_summary[:1200],
        "recent_events": [],
        "latest_code_attempt": latest_code_attempt_context(code_snapshot),
        "latest_submission_feedback": submission_feedback_context(
            latest_submission_feedback,
            chat_feedback_context,
        ),
        "run": {
            "id": run.id,
            "kind": run.kind,
            "related_type": run.related_type,
            "related_id": run.related_id,
        },
        "user_query_summary": user_query_summary,
        "trace": [],
        "error_summary": "",
    }


def user_query_summary(
    *,
    user_event: PracticeEvent | None,
    extracted_code: ExtractedCode | None,
    latest_submission_feedback: SubmissionFeedback | None,
    chat_feedback_context: dict[str, Any] | None,
    trigger_context: dict[str, str],
) -> str:
    if chat_feedback_context is not None:
        return f"chat_submission_feedback result={chat_feedback_context.get('result')}"
    if latest_submission_feedback is not None:
        return f"submission_feedback result={latest_submission_feedback.result}"
    if extracted_code is not None:
        return (
            f"user_code_attempt language={extracted_code.language} "
            f"line_count={len(extracted_code.code_text.splitlines())}"
        )
    if user_event is not None:
        content = strip_code_blocks(user_event.content_md)
        return f"{trigger_context['trigger']}: {content[:240]}"
    return f"trigger={trigger_context['trigger']}"


def strip_code_blocks(value: str) -> str:
    stripped = re.sub(r"```.*?```", " ", value, flags=re.DOTALL)
    return " ".join(stripped.split())


def ensure_thread_id(practice_session: PracticeSession) -> str:
    if practice_session.thread_id:
        return practice_session.thread_id
    practice_session.thread_id = f"practice-session-{practice_session.id}"
    return practice_session.thread_id


def latest_code_attempt_context(
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


def chat_feedback_context(
    user_event: PracticeEvent | None,
    *,
    code_snapshot: CodeSnapshot | None,
) -> dict[str, Any] | None:
    if user_event is None or user_event.event_type != "user_message":
        return None
    content = user_event.content_md.strip()
    if not content:
        return None
    normalized = content.lower()
    result = chat_feedback_result(normalized)
    if result is None:
        return None
    clipped = content[:CHAT_FEEDBACK_TEXT_MAX_LENGTH]
    return {
        "source": "chat_extracted",
        "result": result,
        "code_snapshot_id": code_snapshot.id if code_snapshot is not None else None,
        "failed_case_text": clipped,
        "error_message": clipped,
        "note_md": "",
    }


def user_message_content_context(
    user_event: PracticeEvent | None,
    *,
    chat_feedback_context: dict[str, Any] | None,
) -> str:
    if user_event is None:
        return ""
    if chat_feedback_context is not None:
        failed_case_text = chat_feedback_context.get("failed_case_text")
        return failed_case_text if isinstance(failed_case_text, str) else ""
    return user_event.content_md[:USER_MESSAGE_TEXT_MAX_LENGTH]


def submission_feedback_context(
    feedback: SubmissionFeedback | None,
    chat_feedback_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if feedback is None:
        return chat_feedback_context
    raw_feedback = feedback.raw_feedback_json
    note_md = ""
    if isinstance(raw_feedback, dict) and isinstance(raw_feedback.get("note_md"), str):
        note_md = raw_feedback["note_md"]
    return {
        "source": feedback.source,
        "result": feedback.result,
        "code_snapshot_id": feedback.code_snapshot_id,
        "failed_case_text": feedback.failed_case_text[:CHAT_FEEDBACK_TEXT_MAX_LENGTH],
        "error_message": feedback.error_message[:CHAT_FEEDBACK_TEXT_MAX_LENGTH],
        "note_md": note_md[:CHAT_FEEDBACK_TEXT_MAX_LENGTH],
    }


def context_snapshot(
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
