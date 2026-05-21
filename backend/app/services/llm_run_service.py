from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.auth import AppUser
from backend.app.models.llm_run import LlmRun


logger = logging.getLogger(__name__)
TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}


class LlmRunError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def _ensure_mutable_run(run: LlmRun) -> None:
    if run.status in TERMINAL_STATUSES or run.cancel_requested:
        raise LlmRunError("run_status_conflict")


async def create_llm_run(
    session: AsyncSession,
    user: AppUser,
    *,
    kind: str,
    payload: dict[str, Any] | None = None,
    related_type: str = "",
    related_id: int | None = None,
) -> LlmRun:
    run = LlmRun(
        user_id=user.id,
        kind=kind,
        input_json=payload or {},
        related_type=related_type,
        related_id=related_id,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    logger.info(
        "llm run created user_id=%s run_id=%s kind=%s related_type=%s related_id=%s",
        user.id,
        run.id,
        kind,
        related_type,
        related_id,
    )
    return run


async def get_llm_run_for_user(
    session: AsyncSession,
    user: AppUser,
    run_id: int,
) -> LlmRun:
    result = await session.execute(
        select(LlmRun).where(LlmRun.id == run_id, LlmRun.user_id == user.id),
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise LlmRunError("run_not_found")
    return run


async def mark_llm_run_running(
    session: AsyncSession,
    run: LlmRun,
    *,
    stage: str,
    llm_credential_id: int | None = None,
    model_name: str = "",
) -> LlmRun:
    _ensure_mutable_run(run)
    now = datetime.now(UTC)
    run.status = "running"
    run.stage = stage
    run.started_at = run.started_at or now
    run.updated_at = now
    if llm_credential_id is not None:
        run.llm_credential_id = llm_credential_id
    if model_name:
        run.model_name = model_name
    await session.commit()
    await session.refresh(run)
    logger.info("llm run stage user_id=%s run_id=%s stage=%s", run.user_id, run.id, stage)
    return run


async def update_llm_run_stage(
    session: AsyncSession,
    run: LlmRun,
    *,
    stage: str,
    display_text_md: str | None = None,
) -> LlmRun:
    _ensure_mutable_run(run)
    run.stage = stage
    run.updated_at = datetime.now(UTC)
    if display_text_md is not None:
        run.display_text_md = display_text_md
    await session.commit()
    await session.refresh(run)
    logger.info("llm run stage user_id=%s run_id=%s stage=%s", run.user_id, run.id, stage)
    return run


async def cancel_llm_run(session: AsyncSession, user: AppUser, run_id: int) -> LlmRun:
    run = await get_llm_run_for_user(session, user, run_id)
    if run.status in TERMINAL_STATUSES:
        raise LlmRunError("run_status_conflict")
    run.cancel_requested = True
    run.status = "canceled"
    run.stage = "canceled"
    run.finished_at = datetime.now(UTC)
    run.updated_at = run.finished_at
    await session.commit()
    await session.refresh(run)
    logger.info("llm run canceled user_id=%s run_id=%s stage=%s", user.id, run.id, run.stage)
    return run


async def succeed_llm_run(
    session: AsyncSession,
    run: LlmRun,
    *,
    result: dict[str, Any],
    display_text_md: str,
) -> LlmRun:
    await session.refresh(run)
    _ensure_mutable_run(run)
    run.status = "succeeded"
    run.stage = "completed"
    run.result_json = result
    run.display_text_md = display_text_md
    run.finished_at = datetime.now(UTC)
    run.updated_at = run.finished_at
    await session.commit()
    await session.refresh(run)
    logger.info("llm run completed user_id=%s run_id=%s status=%s", run.user_id, run.id, run.status)
    return run


async def fail_llm_run(
    session: AsyncSession,
    run: LlmRun,
    *,
    error_code: str,
    error_message: str,
) -> LlmRun:
    await session.refresh(run)
    _ensure_mutable_run(run)
    run.status = "failed"
    run.stage = "failed"
    run.error_code = error_code
    run.error_message = error_message
    run.finished_at = datetime.now(UTC)
    run.updated_at = run.finished_at
    await session.commit()
    await session.refresh(run)
    logger.warning(
        "llm run failed user_id=%s run_id=%s error_code=%s stage=%s",
        run.user_id,
        run.id,
        error_code,
        run.stage,
    )
    return run
