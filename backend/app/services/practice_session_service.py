from __future__ import annotations

import hashlib
import logging
from collections import Counter
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
    ProfileDelta,
    SessionSummary,
    SubmissionFeedback,
)
from backend.app.models.problem import Problem
from backend.app.schemas.practice import (
    CodeAttemptResponse,
    CodeSnapshotCreate,
    CodeSnapshotResponse,
    PracticeDashboardResponse,
    PracticeEventResponse,
    PracticeMessageCreate,
    PracticeMessageResponse,
    PracticeSessionResponse,
    PracticeSessionReviewResponse,
    SubmissionFeedbackCreate,
    SubmissionFeedbackHistoryResponse,
    SubmissionFeedbackResponse,
)
from backend.app.services.profile_service import (
    ensure_initial_profile_snapshot,
    latest_profile_snapshot,
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
_HINT_LEVEL_GEARS = {value: key for key, value in _HINT_GEAR_LABELS.items()}
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
        practice_session.thread_id = f"practice-session-{practice_session.id}"
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
    code_attempts = await _list_code_attempts(db, user, session_id)
    submission_feedbacks = await _list_submission_feedbacks(db, user, session_id)
    return _session_response(
        practice_session,
        events=events,
        code_attempts=code_attempts,
        submission_feedbacks=submission_feedbacks,
    )


async def get_session_review(
    db: AsyncSession,
    user: AppUser,
    session_id: int,
) -> PracticeSessionReviewResponse:
    practice_session = await _load_session(db, user, session_id)
    result = await db.execute(
        select(SessionSummary)
        .where(
            SessionSummary.session_id == practice_session.id,
            SessionSummary.user_id == user.id,
        )
        .order_by(SessionSummary.updated_at.desc(), SessionSummary.id.desc())
        .limit(1)
    )
    summary = result.scalar_one_or_none()
    if summary is None:
        logger.warning(
            "practice_session_review_rejected user_id=%s session_id=%s reason=summary_not_found",
            user.id,
            session_id,
        )
        raise PracticeSessionError("summary_not_found")
    delta_result = await db.execute(
        select(ProfileDelta)
        .where(
            ProfileDelta.session_id == practice_session.id,
            ProfileDelta.user_id == user.id,
            ProfileDelta.summary_id == summary.id,
        )
        .order_by(ProfileDelta.created_at.desc(), ProfileDelta.id.desc())
        .limit(1)
    )
    delta = delta_result.scalar_one_or_none()
    return _session_review_response(practice_session, summary=summary, delta=delta)


async def get_practice_dashboard(
    db: AsyncSession,
    user: AppUser,
) -> PracticeDashboardResponse:
    session_result = await db.execute(
        select(PracticeSession)
        .where(PracticeSession.user_id == user.id)
        .order_by(PracticeSession.updated_at.desc(), PracticeSession.id.desc())
    )
    practice_sessions = list(session_result.scalars().all())
    summary_result = await db.execute(
        select(SessionSummary)
        .where(SessionSummary.user_id == user.id)
        .order_by(SessionSummary.updated_at.desc(), SessionSummary.id.desc())
    )
    summaries = list(summary_result.scalars().all())
    profile_snapshot = await latest_profile_snapshot(db, user.id)

    completed_problem_ids = {
        practice_session.problem_id
        for practice_session in practice_sessions
        if practice_session.final_result == "ac"
    }
    stuck_counter: Counter[str] = Counter()
    hint_gears: list[int] = []
    highest_gear: int | None = None
    for summary in summaries:
        stuck_counter.update(
            point
            for point in summary.main_stuck_points_json
            if isinstance(point, str) and point.strip()
        )
        gear = _HINT_LEVEL_GEARS.get(summary.max_hint_level_used)
        if gear is not None:
            hint_gears.append(gear)
            highest_gear = gear if highest_gear is None else max(highest_gear, gear)

    average_hint_gear = (
        round(sum(hint_gears) / len(hint_gears), 1) if hint_gears else None
    )
    return PracticeDashboardResponse.model_validate(
        {
            "completed_problem_count": len(completed_problem_ids),
            "common_stuck_points": [
                {"stuck_point": stuck_point, "count": count}
                for stuck_point, count in stuck_counter.most_common(5)
            ],
            "average_hint_gear": average_hint_gear,
            "highest_hint_level": (
                _hint_gear_label(highest_gear) if highest_gear is not None else None
            ),
            "recent_profile_summary": (
                profile_snapshot.recent_summary_md if profile_snapshot is not None else ""
            ),
            "profile_snapshot_id": (
                profile_snapshot.id if profile_snapshot is not None else None
            ),
        }
    )


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
    await _sync_latest_plan_item_status(
        db,
        practice_session,
        status="in_progress",
        now=now,
    )
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
    event.payload_json = {
        **event.payload_json,
        "snapshot_id": snapshot.id,
        "quality_status": "pending",
        "quality_comment": "",
    }
    practice_session.latest_code_snapshot_id = snapshot.id
    _touch_session(practice_session, now=now)
    await _sync_latest_plan_item_status(
        db,
        practice_session,
        status="in_progress",
        now=now,
    )
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
    if code_snapshot_id is None and payload.result != "ac":
        logger.warning(
            "practice_submission_feedback_rejected user_id=%s session_id=%s "
            "reason=code_snapshot_required_for_submission_feedback",
            user.id,
            session_id,
        )
        raise PracticeSessionError("code_snapshot_required_for_submission_feedback")
    if code_snapshot_id is not None:
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
        await _sync_latest_plan_item_status(
            db,
            practice_session,
            status="completed",
            now=now,
        )
    elif payload.result in _CONCRETE_SUBMISSION_RESULTS:
        await _sync_latest_plan_item_status(
            db,
            practice_session,
            status="in_progress",
            now=now,
        )
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
            "has_note": bool(payload.note_md),
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
        raw_feedback_json={"note_md": payload.note_md},
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
        note_md=payload.note_md,
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


async def _sync_latest_plan_item_status(
    db: AsyncSession,
    practice_session: PracticeSession,
    *,
    status: str,
    now: datetime,
) -> None:
    if status not in {"in_progress", "completed"}:
        return
    if practice_session.latest_plan_item_id is None:
        logger.warning(
            "practice_plan_item_status_sync_skipped user_id=%s session_id=%s "
            "reason=missing_latest_plan_item status=%s",
            practice_session.user_id,
            practice_session.id,
            status,
        )
        return
    result = await db.execute(
        select(StudyPlanItem, StudyPlan)
        .join(StudyPlanVersion, StudyPlanVersion.id == StudyPlanItem.version_id)
        .join(StudyPlan, StudyPlan.id == StudyPlanVersion.plan_id)
        .where(
            StudyPlanItem.id == practice_session.latest_plan_item_id,
            StudyPlan.id == practice_session.study_plan_id,
            StudyPlan.user_id == practice_session.user_id,
        )
        .with_for_update()
    )
    row = result.one_or_none()
    if row is None:
        logger.warning(
            "practice_plan_item_status_sync_skipped user_id=%s session_id=%s "
            "item_id=%s status=%s reason=plan_item_not_found",
            practice_session.user_id,
            practice_session.id,
            practice_session.latest_plan_item_id,
            status,
        )
        return
    item, plan = row
    old_status = item.status
    if status == "in_progress":
        if old_status in {"in_progress", "completed", "locked_completed"}:
            return
        if old_status not in {"pending", "skipped"}:
            logger.warning(
                "practice_plan_item_status_sync_skipped user_id=%s plan_id=%s "
                "item_id=%s old_status=%s status=%s reason=unsupported_transition",
                practice_session.user_id,
                plan.id,
                item.id,
                old_status,
                status,
            )
            return
    if status == "completed" and old_status in {"completed", "locked_completed"}:
        return

    # 训练事实只允许把计划题推进到“编码中/已 AC”，不从已 AC 回退，避免复盘后的聊天覆盖完成结果。
    item.status = status
    item.updated_at = now
    plan.updated_at = now
    logger.info(
        "practice_plan_item_status_synced user_id=%s plan_id=%s item_id=%s "
        "session_id=%s old_status=%s status=%s",
        practice_session.user_id,
        plan.id,
        item.id,
        practice_session.id,
        old_status,
        status,
    )


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


async def _list_code_attempts(
    db: AsyncSession,
    user: AppUser,
    session_id: int,
) -> list[CodeAttemptResponse]:
    result = await db.execute(
        select(CodeSnapshot, PracticeEvent)
        .join(
            PracticeEvent,
            PracticeEvent.id == CodeSnapshot.event_id,
        )
        .where(
            CodeSnapshot.session_id == session_id,
            CodeSnapshot.user_id == user.id,
        )
        .order_by(CodeSnapshot.created_at, CodeSnapshot.id)
    )
    return [_code_attempt_response(snapshot, event) for snapshot, event in result.all()]


async def _list_submission_feedbacks(
    db: AsyncSession,
    user: AppUser,
    session_id: int,
) -> list[SubmissionFeedbackHistoryResponse]:
    result = await db.execute(
        select(SubmissionFeedback)
        .where(
            SubmissionFeedback.session_id == session_id,
            SubmissionFeedback.user_id == user.id,
        )
        .order_by(SubmissionFeedback.created_at, SubmissionFeedback.id)
    )
    return [_submission_feedback_response(feedback) for feedback in result.scalars().all()]


def _code_attempt_response(
    snapshot: CodeSnapshot,
    event: PracticeEvent,
) -> CodeAttemptResponse:
    payload = event.payload_json if isinstance(event.payload_json, dict) else {}
    quality_status = payload.get("quality_status")
    if quality_status not in {"pending", "needs_fix", "ready_to_submit"}:
        quality_status = "pending"
    quality_comment = payload.get("quality_comment")
    if not isinstance(quality_comment, str):
        quality_comment = ""
    return CodeAttemptResponse.model_validate(
        {
            "snapshot_id": snapshot.id,
            "event_id": event.id,
            "language": snapshot.language,
            "source": snapshot.source,
            "client_revision": snapshot.client_revision,
            "code_hash": snapshot.code_hash,
            "code_preview": _code_preview(snapshot.code_text),
            "code_text": snapshot.code_text,
            "quality_status": quality_status,
            "quality_comment": quality_comment,
            "created_at": snapshot.created_at,
        }
    )


def _submission_feedback_response(
    feedback: SubmissionFeedback,
) -> SubmissionFeedbackHistoryResponse:
    raw_feedback = feedback.raw_feedback_json
    note_md = ""
    if isinstance(raw_feedback, dict) and isinstance(raw_feedback.get("note_md"), str):
        note_md = raw_feedback["note_md"]
    return SubmissionFeedbackHistoryResponse.model_validate(
        {
            "id": feedback.id,
            "event_id": feedback.event_id,
            "code_snapshot_id": feedback.code_snapshot_id,
            "result": feedback.result,
            "failed_case_text": feedback.failed_case_text,
            "error_message": feedback.error_message,
            "note_md": note_md,
            "runtime_ms": feedback.runtime_ms,
            "memory_kb": feedback.memory_kb,
            "created_at": feedback.created_at,
        }
    )


def _session_review_response(
    practice_session: PracticeSession,
    *,
    summary: SessionSummary,
    delta: ProfileDelta | None,
) -> PracticeSessionReviewResponse:
    profile_delta = {
        "id": delta.id,
        "status": delta.status,
        "previous_snapshot_id": delta.previous_snapshot_id,
        "next_snapshot_id": delta.next_snapshot_id,
        "rejection_reason": delta.rejection_reason,
    } if delta is not None else {}
    return PracticeSessionReviewResponse.model_validate(
        {
            "session_id": practice_session.id,
            "summary_id": summary.id,
            "problem_id": practice_session.problem_id,
            "problem_slug": practice_session.problem_slug,
            "final_result": summary.final_submission_result,
            "training_mode": summary.training_mode,
            "phases_visited": summary.phases_visited_json,
            "main_stuck_points": summary.main_stuck_points_json,
            "error_types": summary.error_types_json,
            "max_hint_level_used": summary.max_hint_level_used or None,
            "attempt_count": summary.attempt_count,
            "complexity_analysis": summary.complexity_analysis_json,
            "core_idea_md": summary.invariant_summary_md,
            "review_summary_md": summary.review_summary_md,
            "profile_signals": summary.profile_signals_json,
            "profile_update_suggestion": summary.profile_update_suggestion_json,
            "profile_delta": profile_delta,
            "next_recommendation": summary.next_recommendation_json,
            "updated_at": summary.updated_at,
        }
    )


def _code_preview(code_text: str) -> str:
    return code_text.strip()[:400]


def _session_response(
    practice_session: PracticeSession,
    *,
    events: list[PracticeEventResponse] | None = None,
    code_attempts: list[CodeAttemptResponse] | None = None,
    submission_feedbacks: list[SubmissionFeedbackHistoryResponse] | None = None,
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
            "code_attempts": code_attempts or [],
            "submission_feedbacks": submission_feedbacks or [],
            "created_at": practice_session.created_at,
            "updated_at": practice_session.updated_at,
        }
    )


def _hint_gear_label(value: int | None) -> str:
    return _HINT_GEAR_LABELS.get(value or 0, _DEFAULT_HINT_LEVEL)
