from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.auth import AppUser
from backend.app.models.llm_run import LlmRun


logger = logging.getLogger(__name__)
TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}


class LlmRunError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


async def _update_mutable_run(
    session: AsyncSession,
    run: LlmRun,
    values: dict[str, Any],
) -> LlmRun:
    result = await session.execute(
        update(LlmRun)
        .where(
            LlmRun.id == run.id,
            LlmRun.status.not_in(TERMINAL_STATUSES),
            LlmRun.cancel_requested.is_(False),
        )
        .values(**values),
    )
    if getattr(result, "rowcount", 0) != 1:
        await session.rollback()
        raise LlmRunError("run_status_conflict")
    await session.commit()
    await session.refresh(run)
    return run


async def create_llm_run(
    session: AsyncSession,
    user: AppUser,
    *,
    kind: str,
    payload: dict[str, Any] | None = None,
    related_type: str = "",
    related_id: int | None = None,
) -> LlmRun:
    # run 创建阶段只保存“要做什么”和输入快照；status、stage、result、错误信息等
    # 由 LlmRun 模型默认值兜底，后续执行器再推进状态机。
    run = LlmRun(
        user_id=user.id,
        kind=kind,
        # 数据库列要求 JSON 非空；没有入参时统一落成空对象，避免后续 flow 处理 None 分支。
        input_json=payload or {},
        related_type=related_type,
        related_id=related_id,
    )
    session.add(run)
    await session.commit()
    # commit 后刷新一次，拿到数据库生成的 id、created_at 和默认状态，供 API 返回 stream_url。
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
    now = datetime.now(UTC)
    values: dict[str, Any] = {
        "status": "running",
        "stage": stage,
        "started_at": run.started_at or now,
        "updated_at": now,
    }
    if llm_credential_id is not None:
        values["llm_credential_id"] = llm_credential_id
    if model_name:
        values["model_name"] = model_name
    await _update_mutable_run(session, run, values)
    logger.info("llm run stage user_id=%s run_id=%s stage=%s", run.user_id, run.id, stage)
    return run


async def update_llm_run_stage(
    session: AsyncSession,
    run: LlmRun,
    *,
    stage: str,
    display_text_md: str | None = None,
) -> LlmRun:
    values: dict[str, Any] = {
        "stage": stage,
        "updated_at": datetime.now(UTC),
    }
    if display_text_md is not None:
        values["display_text_md"] = display_text_md
    await _update_mutable_run(session, run, values)
    logger.info("llm run stage user_id=%s run_id=%s stage=%s", run.user_id, run.id, stage)
    return run


async def ensure_llm_run_mutable(session: AsyncSession, run: LlmRun) -> LlmRun:
    await session.refresh(run)
    if run.status in TERMINAL_STATUSES or run.cancel_requested:
        raise LlmRunError("run_status_conflict")
    return run


async def update_llm_run_display_text(
    session: AsyncSession,
    run: LlmRun,
    *,
    display_text_md: str,
) -> LlmRun:
    await _update_mutable_run(
        session,
        run,
        {
            "display_text_md": display_text_md,
            "updated_at": datetime.now(UTC),
        },
    )
    logger.info(
        "llm run display updated user_id=%s run_id=%s text_length=%s",
        run.user_id,
        run.id,
        len(display_text_md),
    )
    return run


async def cancel_llm_run(session: AsyncSession, user: AppUser, run_id: int) -> LlmRun:
    run = await get_llm_run_for_user(session, user, run_id)
    now = datetime.now(UTC)
    result = await session.execute(
        update(LlmRun)
        .where(
            LlmRun.id == run.id,
            LlmRun.user_id == user.id,
            LlmRun.status.not_in(TERMINAL_STATUSES),
            LlmRun.cancel_requested.is_(False),
        )
        .values(
            cancel_requested=True,
            status="canceled",
            stage="canceled",
            finished_at=now,
            updated_at=now,
        ),
    )
    if getattr(result, "rowcount", 0) != 1:
        await session.rollback()
        raise LlmRunError("run_status_conflict")
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
    now = datetime.now(UTC)
    await _update_mutable_run(
        session,
        run,
        {
            "status": "succeeded",
            "stage": "completed",
            "result_json": result,
            "display_text_md": display_text_md,
            "finished_at": now,
            "updated_at": now,
        },
    )
    logger.info("llm run completed user_id=%s run_id=%s status=%s", run.user_id, run.id, run.status)
    return run


async def fail_llm_run(
    session: AsyncSession,
    run: LlmRun,
    *,
    error_code: str,
    error_message: str,
) -> LlmRun:
    now = datetime.now(UTC)
    await _update_mutable_run(
        session,
        run,
        {
            "status": "failed",
            "stage": "failed",
            "error_code": error_code,
            "error_message": error_message,
            "finished_at": now,
            "updated_at": now,
        },
    )
    logger.warning(
        "llm run failed user_id=%s run_id=%s error_code=%s stage=%s",
        run.user_id,
        run.id,
        error_code,
        run.stage,
    )
    return run
