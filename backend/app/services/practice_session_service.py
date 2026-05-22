from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.auth import AppUser
from backend.app.models.learning import StudyPlan, StudyPlanItem, StudyPlanVersion
from backend.app.models.practice import (
    CodeSnapshot,
    PracticeEvent,
    PracticeSession,
    SubmissionFeedback,
)
from backend.app.models.problem import Problem
from backend.app.schemas.practice import (
    CodeSnapshotCreate,
    CodeSnapshotResponse,
    PracticeEventResponse,
    PracticeMessageCreate,
    PracticeMessageResponse,
    PracticeSessionResponse,
    SubmissionFeedbackCreate,
    SubmissionFeedbackResponse,
)
from backend.app.services.profile_service import (
    ensure_initial_profile_snapshot,
    snapshot_payload,
)


logger = logging.getLogger(__name__)

_INITIAL_PHASE = "understand_problem"
_DEFAULT_HINT_LEVEL = "questioning"
_HINT_GEAR_LABELS = {
    0: "questioning",
    1: "direction",
    2: "key_hint",
    3: "reflection",
}
_CONCRETE_SUBMISSION_RESULTS = {"ac", "wa", "tle", "re", "mle", "ce"}


class PracticeSessionError(RuntimeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


async def get_or_create_session_for_plan_item(
    db: AsyncSession,
    user: AppUser,
    plan_item_id: int,
) -> PracticeSession:
    item, version, plan, problem = await _load_plan_item_context(db, user, plan_item_id)
    now = datetime.now(UTC)
    profile_json, profile_snapshot_id = await _current_profile_payload(
        db,
        user_id=user.id,
        plan_id=plan.id,
    )

    practice_session = await _find_existing_session_for_update(
        db,
        user,
        plan.id,
        problem.id,
    )
    created = False
    if practice_session is None:
        practice_session = PracticeSession(
            user_id=user.id,
            study_plan_id=plan.id,
            problem_id=problem.id,
            problem_slug=problem.slug,
            origin_plan_version_id=version.id,
            latest_plan_version_id=version.id,
            latest_plan_item_id=item.id,
            training_mode=item.suggested_mode,
            phase=_INITIAL_PHASE,
            status="active",
            current_hint_level=_DEFAULT_HINT_LEVEL,
            visible_hint_gear=0,
            max_hint_level_used=_DEFAULT_HINT_LEVEL,
            attempt_count=0,
            final_result="",
            profile_snapshot_id=profile_snapshot_id,
            profile_snapshot_json=profile_json,
            started_at=now,
            last_activity_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(practice_session)
        await db.flush()
        created = True
        db.add(
            PracticeEvent(
                session_id=practice_session.id,
                user_id=user.id,
                event_type="session_started",
                role="system",
                phase=practice_session.phase,
                intent=None,
                content_md="",
                payload_json={
                    "study_plan_id": plan.id,
                    "plan_version_id": version.id,
                    "plan_item_id": item.id,
                    "problem_id": problem.id,
                    "problem_slug": problem.slug,
                },
                hint_level=practice_session.current_hint_level,
                visible_hint_gear=practice_session.visible_hint_gear,
                created_at=now,
            )
        )
    else:
        practice_session.problem_slug = problem.slug
        practice_session.training_mode = item.suggested_mode

    _touch_plan_entry(
        practice_session,
        version_id=version.id,
        item_id=item.id,
        profile_snapshot_id=profile_snapshot_id,
        profile_json=profile_json,
        now=now,
    )
    await db.commit()
    await db.refresh(practice_session)
    logger.info(
        "practice_session_plan_entry user_id=%s plan_id=%s item_id=%s "
        "session_id=%s created=%s",
        user.id,
        plan.id,
        item.id,
        practice_session.id,
        created,
    )
    return practice_session


async def get_session_payload(
    db: AsyncSession,
    user: AppUser,
    session_id: int,
) -> PracticeSessionResponse:
    practice_session = await _load_session(db, user, session_id)
    events = await list_session_events(db, user, session_id)
    return _session_response(practice_session, events=events)


async def list_session_events(
    db: AsyncSession,
    user: AppUser,
    session_id: int,
) -> list[PracticeEventResponse]:
    await _load_session(db, user, session_id)
    result = await db.execute(
        select(PracticeEvent)
        .where(
            PracticeEvent.session_id == session_id,
            PracticeEvent.user_id == user.id,
        )
        .order_by(PracticeEvent.created_at, PracticeEvent.id)
    )
    return [_event_response(event) for event in result.scalars().all()]


async def append_user_message(
    db: AsyncSession,
    user: AppUser,
    session_id: int,
    payload: PracticeMessageCreate,
) -> PracticeMessageResponse:
    practice_session = await _load_session_for_update(db, user, session_id)
    now = datetime.now(UTC)
    event = PracticeEvent(
        session_id=practice_session.id,
        user_id=user.id,
        event_type="user_message",
        role="user",
        phase=practice_session.phase,
        intent=payload.intent,
        content_md=payload.content_md,
        payload_json={
            "requested_hint_level": payload.requested_hint_level,
            "content_length": len(payload.content_md),
        },
        hint_level=payload.requested_hint_level,
        visible_hint_gear=practice_session.visible_hint_gear,
        created_at=now,
    )
    db.add(event)
    _touch_session(practice_session, now=now)
    await db.flush()
    await db.commit()
    logger.info(
        "practice_user_message_appended user_id=%s session_id=%s event_id=%s "
        "intent=%s",
        user.id,
        practice_session.id,
        event.id,
        payload.intent,
    )
    # Task 4 只落用户事件，暂不创建真实 llm_run；Task 6 注册教练 run kind 后会替换 run_id 语义。
    return PracticeMessageResponse(
        event_id=event.id,
        run_id=0,
        session_id=practice_session.id,
    )


async def save_code_snapshot(
    db: AsyncSession,
    user: AppUser,
    session_id: int,
    payload: CodeSnapshotCreate,
) -> CodeSnapshotResponse:
    practice_session = await _load_session_for_update(db, user, session_id)
    now = datetime.now(UTC)
    code_hash = hashlib.sha256(payload.code_text.encode("utf-8")).hexdigest()
    event = PracticeEvent(
        session_id=practice_session.id,
        user_id=user.id,
        event_type="code_saved",
        role="user",
        phase=practice_session.phase,
        intent=None,
        content_md="",
        payload_json={
            "language": payload.language,
            "source": payload.source,
            "client_revision": payload.client_revision,
            "code_hash": code_hash,
        },
        hint_level=practice_session.current_hint_level,
        visible_hint_gear=practice_session.visible_hint_gear,
        created_at=now,
    )
    db.add(event)
    await db.flush()
    snapshot = CodeSnapshot(
        session_id=practice_session.id,
        user_id=user.id,
        event_id=event.id,
        language=payload.language,
        code_text=payload.code_text,
        code_hash=code_hash,
        source=payload.source,
        client_revision=payload.client_revision,
        created_at=now,
    )
    db.add(snapshot)
    await db.flush()
    practice_session.latest_code_snapshot_id = snapshot.id
    _touch_session(practice_session, now=now)
    await db.commit()
    logger.info(
        "practice_code_snapshot_saved user_id=%s session_id=%s snapshot_id=%s "
        "event_id=%s source=%s client_revision=%s",
        user.id,
        practice_session.id,
        snapshot.id,
        event.id,
        payload.source,
        payload.client_revision,
    )
    return CodeSnapshotResponse(
        id=snapshot.id,
        language=snapshot.language,
        source=snapshot.source,
        client_revision=snapshot.client_revision,
        code_hash=snapshot.code_hash,
        created_at=snapshot.created_at,
    )


async def record_submission_feedback(
    db: AsyncSession,
    user: AppUser,
    session_id: int,
    payload: SubmissionFeedbackCreate,
) -> SubmissionFeedbackResponse:
    practice_session = await _load_session_for_update(db, user, session_id)
    code_snapshot_id = payload.code_snapshot_id or practice_session.latest_code_snapshot_id
    if code_snapshot_id is None:
        logger.warning(
            "practice_submission_feedback_rejected user_id=%s session_id=%s "
            "reason=code_snapshot_required_for_submission_feedback",
            user.id,
            session_id,
        )
        raise PracticeSessionError("code_snapshot_required_for_submission_feedback")
    await _load_code_snapshot(db, user, practice_session.id, code_snapshot_id)
    now = datetime.now(UTC)
    phase_before = practice_session.phase
    next_phase = _phase_after_submission(payload.result, phase_before)
    phase_changed = next_phase != phase_before
    if phase_changed:
        practice_session.phase = next_phase
    practice_session.attempt_count += 1
    if payload.result in _CONCRETE_SUBMISSION_RESULTS:
        practice_session.final_result = payload.result
    if payload.result == "ac":
        practice_session.status = "summarizing"
    event = PracticeEvent(
        session_id=practice_session.id,
        user_id=user.id,
        event_type="submission_feedback",
        role="user",
        phase=practice_session.phase,
        intent="submit_feedback",
        content_md="",
        payload_json={
            "result": payload.result,
            "code_snapshot_id": code_snapshot_id,
            "runtime_ms": payload.runtime_ms,
            "memory_kb": payload.memory_kb,
            "has_failed_case": bool(payload.failed_case_text),
            "has_error_message": bool(payload.error_message),
        },
        hint_level=practice_session.current_hint_level,
        visible_hint_gear=practice_session.visible_hint_gear,
        created_at=now,
    )
    db.add(event)
    await db.flush()
    feedback = SubmissionFeedback(
        session_id=practice_session.id,
        user_id=user.id,
        event_id=event.id,
        code_snapshot_id=code_snapshot_id,
        result=payload.result,
        runtime_ms=payload.runtime_ms,
        memory_kb=payload.memory_kb,
        failed_case_text=payload.failed_case_text,
        error_message=payload.error_message,
        raw_feedback_json={},
        submitted_at=now,
        created_at=now,
    )
    db.add(feedback)
    await db.flush()
    if phase_changed:
        db.add(
            PracticeEvent(
                session_id=practice_session.id,
                user_id=user.id,
                event_type="phase_changed",
                role="system",
                phase=practice_session.phase,
                intent=None,
                content_md="",
                payload_json={
                    "phase_before": phase_before,
                    "phase_after": practice_session.phase,
                    "reason": "submission_feedback",
                    "feedback_id": feedback.id,
                    "result": payload.result,
                },
                hint_level=practice_session.current_hint_level,
                visible_hint_gear=practice_session.visible_hint_gear,
                created_at=now,
            )
        )
    _touch_session(practice_session, now=now)
    await db.commit()
    logger.info(
        "practice_submission_feedback_recorded user_id=%s session_id=%s "
        "feedback_id=%s event_id=%s result=%s phase=%s",
        user.id,
        practice_session.id,
        feedback.id,
        event.id,
        payload.result,
        practice_session.phase,
    )
    return SubmissionFeedbackResponse(
        id=feedback.id,
        result=cast(Any, feedback.result),
        event_id=event.id,
        code_snapshot_id=feedback.code_snapshot_id,
        created_at=feedback.created_at,
    )


async def _load_plan_item_context(
    db: AsyncSession,
    user: AppUser,
    plan_item_id: int,
) -> tuple[StudyPlanItem, StudyPlanVersion, StudyPlan, Problem]:
    result = await db.execute(
        select(StudyPlanItem, StudyPlanVersion, StudyPlan, Problem)
        .join(StudyPlanVersion, StudyPlanVersion.id == StudyPlanItem.version_id)
        .join(StudyPlan, StudyPlan.id == StudyPlanVersion.plan_id)
        .join(Problem, Problem.id == StudyPlanItem.problem_id)
        .where(StudyPlanItem.id == plan_item_id, StudyPlan.user_id == user.id)
    )
    row = result.one_or_none()
    if row is None:
        logger.warning(
            "practice_session_plan_item_rejected user_id=%s item_id=%s "
            "reason=plan_item_not_found",
            user.id,
            plan_item_id,
        )
        raise PracticeSessionError("plan_item_not_found")
    item, version, plan, problem = row
    return item, version, plan, problem


async def _load_session(
    db: AsyncSession,
    user: AppUser,
    session_id: int,
) -> PracticeSession:
    result = await db.execute(
        select(PracticeSession).where(
            PracticeSession.id == session_id,
            PracticeSession.user_id == user.id,
        )
    )
    practice_session = result.scalar_one_or_none()
    if practice_session is None:
        logger.warning(
            "practice_session_rejected user_id=%s session_id=%s reason=session_not_found",
            user.id,
            session_id,
        )
        raise PracticeSessionError("session_not_found")
    return practice_session


async def _load_session_for_update(
    db: AsyncSession,
    user: AppUser,
    session_id: int,
) -> PracticeSession:
    result = await db.execute(
        select(PracticeSession)
        .where(
            PracticeSession.id == session_id,
            PracticeSession.user_id == user.id,
        )
        .with_for_update()
    )
    practice_session = result.scalar_one_or_none()
    if practice_session is None:
        logger.warning(
            "practice_session_rejected user_id=%s session_id=%s reason=session_not_found",
            user.id,
            session_id,
        )
        raise PracticeSessionError("session_not_found")
    return practice_session


async def _find_existing_session_for_update(
    db: AsyncSession,
    user: AppUser,
    study_plan_id: int,
    problem_id: int,
) -> PracticeSession | None:
    result = await db.execute(
        select(PracticeSession)
        .where(
            PracticeSession.user_id == user.id,
            PracticeSession.study_plan_id == study_plan_id,
            PracticeSession.problem_id == problem_id,
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def _load_code_snapshot(
    db: AsyncSession,
    user: AppUser,
    session_id: int,
    snapshot_id: int,
) -> CodeSnapshot:
    result = await db.execute(
        select(CodeSnapshot).where(
            CodeSnapshot.id == snapshot_id,
            CodeSnapshot.session_id == session_id,
            CodeSnapshot.user_id == user.id,
        )
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        logger.warning(
            "practice_submission_feedback_rejected user_id=%s session_id=%s "
            "snapshot_id=%s reason=code_snapshot_not_found",
            user.id,
            session_id,
            snapshot_id,
        )
        raise PracticeSessionError("code_snapshot_not_found")
    return snapshot


async def _current_profile_payload(
    db: AsyncSession,
    *,
    user_id: int,
    plan_id: int,
) -> tuple[dict[str, Any], int | None]:
    snapshot = await ensure_initial_profile_snapshot(db, user_id, plan_id)
    profile = snapshot_payload(snapshot)
    payload = profile.to_prompt_payload()
    payload["id"] = profile.id
    return payload, snapshot.id


def _touch_plan_entry(
    practice_session: PracticeSession,
    *,
    version_id: int,
    item_id: int,
    profile_snapshot_id: int | None,
    profile_json: dict[str, Any],
    now: datetime,
) -> None:
    practice_session.latest_plan_version_id = version_id
    practice_session.latest_plan_item_id = item_id
    practice_session.profile_snapshot_id = profile_snapshot_id
    practice_session.profile_snapshot_json = profile_json
    _touch_session(practice_session, now=now)


def _touch_session(practice_session: PracticeSession, *, now: datetime) -> None:
    practice_session.last_activity_at = now
    practice_session.updated_at = now


def _phase_after_submission(result: str, current_phase: str) -> str:
    if result == "ac":
        return "summarize"
    if result in _CONCRETE_SUBMISSION_RESULTS:
        return "analyze_feedback"
    return current_phase


def _event_response(event: PracticeEvent) -> PracticeEventResponse:
    return PracticeEventResponse.model_validate(
        {
            "id": event.id,
            "event_type": event.event_type,
            "role": event.role,
            "phase": event.phase,
            "intent": event.intent,
            "content_md": event.content_md,
            "payload": event.payload_json,
            "hint_level": event.hint_level,
            "visible_hint_gear": _hint_gear_label(event.visible_hint_gear),
            "created_at": event.created_at,
        }
    )


def _session_response(
    practice_session: PracticeSession,
    *,
    events: list[PracticeEventResponse] | None = None,
) -> PracticeSessionResponse:
    return PracticeSessionResponse.model_validate(
        {
            "id": practice_session.id,
            "study_plan_id": practice_session.study_plan_id,
            "problem_id": practice_session.problem_id,
            "problem_slug": practice_session.problem_slug,
            "latest_plan_version_id": practice_session.latest_plan_version_id or 0,
            "latest_plan_item_id": practice_session.latest_plan_item_id or 0,
            "training_mode": practice_session.training_mode,
            "phase": practice_session.phase,
            "status": practice_session.status,
            "current_hint_level": practice_session.current_hint_level,
            "visible_hint_gear": _hint_gear_label(practice_session.visible_hint_gear),
            "max_hint_level_used": practice_session.max_hint_level_used or None,
            "attempt_count": practice_session.attempt_count,
            "final_result": practice_session.final_result or None,
            "profile_snapshot": practice_session.profile_snapshot_json,
            "events": events or [],
            "created_at": practice_session.created_at,
            "updated_at": practice_session.updated_at,
        }
    )


def _hint_gear_label(value: int | None) -> str:
    return _HINT_GEAR_LABELS.get(value or 0, _DEFAULT_HINT_LEVEL)
