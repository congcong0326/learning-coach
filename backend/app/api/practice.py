from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.auth import current_user_dependency
from backend.app.db.session import get_session
from backend.app.models.auth import AppUser
from backend.app.schemas.llm_run import LlmRunCreateResponse
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
from backend.app.services.practice_session_service import (
    PracticeSessionError,
    append_user_message,
    get_or_create_session_for_plan_item,
    get_session_payload,
    list_session_events,
    record_submission_feedback,
    save_code_snapshot,
)
from backend.app.services.llm_run_service import LlmRunError, create_llm_run


logger = logging.getLogger(__name__)
router = APIRouter(tags=["practice"])


def _http_error(exc: PracticeSessionError) -> HTTPException:
    status = 400
    if "not_found" in exc.detail:
        status = 404
    if exc.detail == "code_snapshot_required_for_submission_feedback":
        status = 409
    return HTTPException(status_code=status, detail=exc.detail)


def _llm_http_error(exc: LlmRunError) -> HTTPException:
    status = 400
    if exc.detail == "run_not_found":
        status = 404
    if exc.detail == "run_status_conflict":
        status = 409
    return HTTPException(status_code=status, detail=exc.detail)


# 路由层只做鉴权、DB session 注入和错误码翻译；训练状态迁移、画像快照和事件落库
# 由 service 层统一维护，避免 API 层重复业务状态机。
@router.post(
    "/study-plan/items/{item_id}/practice-session",
    response_model=PracticeSessionResponse,
)
async def create_practice_session_from_plan_item_route(
    item_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> PracticeSessionResponse:
    try:
        practice_session = await get_or_create_session_for_plan_item(session, user, item_id)
        return await get_session_payload(session, user, practice_session.id)
    except PracticeSessionError as exc:
        raise _http_error(exc) from exc


@router.get(
    "/practice-sessions/{session_id}",
    response_model=PracticeSessionResponse,
)
async def practice_session_detail_route(
    session_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> PracticeSessionResponse:
    try:
        return await get_session_payload(session, user, session_id)
    except PracticeSessionError as exc:
        raise _http_error(exc) from exc


@router.get(
    "/practice-sessions/{session_id}/events",
    response_model=list[PracticeEventResponse],
)
async def practice_session_events_route(
    session_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> list[PracticeEventResponse]:
    try:
        return await list_session_events(session, user, session_id)
    except PracticeSessionError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/practice-sessions/{session_id}/messages",
    response_model=PracticeMessageResponse,
)
async def append_practice_message_route(
    session_id: int,
    payload: PracticeMessageCreate,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> PracticeMessageResponse:
    try:
        return await append_user_message(session, user, session_id, payload)
    except PracticeSessionError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/practice-sessions/{session_id}/code-snapshots",
    response_model=CodeSnapshotResponse,
)
async def save_code_snapshot_route(
    session_id: int,
    payload: CodeSnapshotCreate,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> CodeSnapshotResponse:
    try:
        return await save_code_snapshot(session, user, session_id, payload)
    except PracticeSessionError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/practice-sessions/{session_id}/submission-feedback",
    response_model=SubmissionFeedbackResponse,
)
async def record_submission_feedback_route(
    session_id: int,
    payload: SubmissionFeedbackCreate,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> SubmissionFeedbackResponse:
    try:
        return await record_submission_feedback(session, user, session_id, payload)
    except PracticeSessionError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/practice-sessions/{session_id}/summary",
    response_model=LlmRunCreateResponse,
)
async def generate_practice_summary_route(
    session_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        await get_session_payload(session, user, session_id)
    except PracticeSessionError as exc:
        raise _http_error(exc) from exc
    try:
        run = await create_llm_run(
            session,
            user,
            kind="coach_summary",
            payload={"session_id": session_id, "trigger": "request_summary"},
            related_type="practice_session",
            related_id=session_id,
        )
    except LlmRunError as exc:
        raise _llm_http_error(exc) from exc
    logger.info(
        "practice_summary_run_created user_id=%s session_id=%s run_id=%s",
        user.id,
        session_id,
        run.id,
    )
    return {
        "run_id": run.id,
        "kind": run.kind,
        "status": run.status,
        "stage": run.stage,
        "stream_url": f"/api/llm-runs/{run.id}/stream",
    }
