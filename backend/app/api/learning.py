from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.auth import current_user_dependency
from backend.app.db.session import get_session
from backend.app.models.auth import AppUser
from backend.app.schemas.learning import (
    ConfirmPlanRequest,
    FollowupAnswer,
    GoalCalibrationInput,
    GoalCalibrationStartResponse,
    PlanAdjustmentRequest,
    PlanDraftResponse,
    PlanItemReorderRequest,
    PlanItemStatusUpdateRequest,
    StudyPlanListResponse,
    StudyPlanResponse,
)
from backend.app.services.study_plan_service import StudyPlanError


router = APIRouter(tags=["learning"])


def _http_error(exc: StudyPlanError) -> HTTPException:
    status = 404 if "not_found" in exc.detail else 400
    if exc.detail in {"llm_credential_unavailable", "empty_problem_library"}:
        status = 409
    return HTTPException(status_code=status, detail=exc.detail)


@router.post("/goal-calibration", response_model=GoalCalibrationStartResponse)
async def start_goal_calibration_route(
    payload: GoalCalibrationInput,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        from backend.app.services.study_plan_service import start_goal_calibration

        return await start_goal_calibration(session, user, payload)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/goal-calibration/{draft_id}/followup",
    response_model=GoalCalibrationStartResponse,
)
async def answer_followup_route(
    draft_id: int,
    payload: FollowupAnswer,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        from backend.app.services.study_plan_service import answer_goal_followup

        return await answer_goal_followup(session, user, draft_id, payload)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.post("/goal-calibration/{draft_id}/generate", response_model=PlanDraftResponse)
async def generate_plan_draft_route(
    draft_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        from backend.app.services.study_plan_service import generate_goal_plan_draft

        return await generate_goal_plan_draft(session, user, draft_id)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.post("/study-plans/confirm", response_model=StudyPlanResponse)
async def confirm_plan_route(
    payload: ConfirmPlanRequest,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        from backend.app.services.study_plan_service import (
            confirm_plan_draft,
            study_plan_payload,
        )

        plan = await confirm_plan_draft(session, user, payload.draft_id)
        return await study_plan_payload(session, user, plan.id)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.get("/study-plan/current", response_model=StudyPlanResponse)
async def current_plan_route(
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        from backend.app.services.study_plan_service import get_current_study_plan_payload

        return await get_current_study_plan_payload(session, user)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.get("/study-plans", response_model=StudyPlanListResponse)
async def study_plan_list_route(
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    from backend.app.services.study_plan_service import list_study_plan_payloads

    return await list_study_plan_payloads(session, user)


@router.post("/study-plans/{plan_id}/activate", response_model=StudyPlanResponse)
async def activate_plan_route(
    plan_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        from backend.app.services.study_plan_service import (
            activate_plan,
            study_plan_payload,
        )

        plan = await activate_plan(session, user, plan_id)
        return await study_plan_payload(session, user, plan.id)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.get(
    "/study-plans/{plan_id}/versions/{version_id}",
    response_model=StudyPlanResponse,
)
async def plan_version_route(
    plan_id: int,
    version_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        from backend.app.services.study_plan_service import study_plan_payload

        return await study_plan_payload(session, user, plan_id, version_id=version_id)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.post("/study-plans/{plan_id}/adjustments", response_model=PlanDraftResponse)
async def create_adjustment_route(
    plan_id: int,
    payload: PlanAdjustmentRequest,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        from backend.app.services.study_plan_service import create_adjustment_draft

        return await create_adjustment_draft(session, user, plan_id, payload)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/study-plans/{plan_id}/versions/{version_id}/activate",
    response_model=StudyPlanResponse,
)
async def activate_version_route(
    plan_id: int,
    version_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        from backend.app.services.study_plan_service import (
            activate_plan_version,
            study_plan_payload,
        )

        await activate_plan_version(session, user, plan_id, version_id)
        return await study_plan_payload(session, user, plan_id)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.patch("/study-plan/items/{item_id}", response_model=StudyPlanResponse)
async def update_item_status_route(
    item_id: int,
    payload: PlanItemStatusUpdateRequest,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        from backend.app.services.study_plan_service import (
            study_plan_payload,
            update_plan_item_status,
        )

        plan_id = await update_plan_item_status(session, user, item_id, payload.status)
        return await study_plan_payload(session, user, plan_id)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.post("/study-plan/stages/{stage_id}/reorder", response_model=StudyPlanResponse)
async def reorder_stage_route(
    stage_id: int,
    payload: PlanItemReorderRequest,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        from backend.app.services.study_plan_service import (
            reorder_stage_items,
            study_plan_payload,
        )

        plan_id = await reorder_stage_items(session, user, stage_id, payload.item_ids)
        return await study_plan_payload(session, user, plan_id)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc
