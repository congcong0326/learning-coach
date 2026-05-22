from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.auth import current_user_dependency
from backend.app.core.config import settings
from backend.app.db.session import async_session_factory, get_session
from backend.app.models.auth import AppUser
from backend.app.models.llm_run import LlmRun
from backend.app.schemas.llm_run import (
    LlmRunCancelResponse,
    LlmRunCreateRequest,
    LlmRunCreateResponse,
    LlmRunStatusResponse,
)
from backend.app.services.llm_orchestrator import execute_llm_run
from backend.app.services.llm_run_events import LlmRunEvent, encode_sse, event_hub
from backend.app.services.llm_run_registry import related_from_payload
from backend.app.services.llm_run_service import (
    LlmRunError,
    cancel_llm_run,
    create_llm_run,
    get_llm_run_for_user,
)
from backend.app.services.auth_service import get_current_user_from_token


logger = logging.getLogger(__name__)
# 这里只声明 LLM Run 子路由；main.py 会再统一加上 /api 前缀，
# 因此前端实际访问路径是 /api/llm-runs。
router = APIRouter(prefix="/llm-runs", tags=["llm-runs"])


def _http_error(exc: LlmRunError) -> HTTPException:
    status = 400
    if exc.detail == "run_not_found":
        status = 404
    if exc.detail == "run_status_conflict":
        status = 409
    return HTTPException(status_code=status, detail=exc.detail)


def _datetime_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _status_payload(run: LlmRun) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "kind": run.kind,
        "status": run.status,
        "stage": run.stage,
        "display_text_md": run.display_text_md,
        "result": run.result_json,
        "error_code": run.error_code or None,
        "error_message": run.error_message or None,
        "can_retry": run.status in {"failed", "canceled"},
        "created_at": run.created_at.isoformat(),
        "started_at": _datetime_text(run.started_at),
        "finished_at": _datetime_text(run.finished_at),
    }


def _stream_headers() -> dict[str, str]:
    return {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _observe_llm_task(run_id: int, task: asyncio.Task[None]) -> None:
    event_hub.clear_task(run_id)
    try:
        exception = task.exception()
    except asyncio.CancelledError:
        return
    if exception is not None:
        logger.error(
            "llm run task failed run_id=%s error_type=%s",
            run_id,
            type(exception).__name__,
        )


def _terminal_stream_events(
    *,
    run_id: int,
    status: str,
    result: dict[str, Any],
    error_code: str,
    error_message: str,
) -> list[LlmRunEvent]:
    if status == "succeeded":
        events = [LlmRunEvent("result", {"run_id": run_id, "result": result})]
    elif status == "failed":
        events = [
            LlmRunEvent(
                "error",
                {"run_id": run_id, "error_code": error_code, "message": error_message},
            ),
        ]
    elif status == "canceled":
        events = [LlmRunEvent("canceled", {"run_id": run_id})]
    else:
        events = []
    events.append(LlmRunEvent("done", {"run_id": run_id}))
    return events


async def _finite_event_stream(events: list[LlmRunEvent]) -> AsyncIterator[str]:
    for event in events:
        yield encode_sse(event)


@router.post("", response_model=LlmRunCreateResponse)
async def create_llm_run_route(
    payload: LlmRunCreateRequest,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    # 创建 run 阶段只落库排队任务，不直接调用模型。
    # 真正的 LLM 执行会在前端随后连接 stream_url 时启动，便于支持 SSE、取消和刷新恢复。
    related_type, related_id = related_from_payload(payload.kind, payload.payload)
    try:
        run = await create_llm_run(
            session,
            user,
            kind=payload.kind,
            payload=payload.payload,
            related_type=related_type,
            related_id=related_id,
        )
    except LlmRunError as exc:
        raise _http_error(exc) from exc
    # stream_url 是前端下一步要打开的 SSE 地址；run_id 是后续查状态、取消和接收事件的稳定句柄。
    return {
        "run_id": run.id,
        "kind": run.kind,
        "status": run.status,
        "stage": run.stage,
        "stream_url": f"/api/llm-runs/{run.id}/stream",
    }


@router.get("/{run_id}", response_model=LlmRunStatusResponse)
async def llm_run_status_route(
    run_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        run = await get_llm_run_for_user(session, user, run_id)
    except LlmRunError as exc:
        raise _http_error(exc) from exc
    return _status_payload(run)


@router.post("/{run_id}/cancel", response_model=LlmRunCancelResponse)
async def cancel_llm_run_route(
    run_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        run = await cancel_llm_run(session, user, run_id)
    except LlmRunError as exc:
        raise _http_error(exc) from exc
    await event_hub.publish(run.id, LlmRunEvent("canceled", {"run_id": run.id}))
    await event_hub.publish(run.id, LlmRunEvent("done", {"run_id": run.id}))
    return {"run_id": run.id, "status": run.status, "cancel_requested": run.cancel_requested}


@router.get("/{run_id}/stream")
async def stream_llm_run_route(
    run_id: int,
    request: Request,
) -> StreamingResponse:
    # SSE 连接没有走普通 Depends 注入，这里手动用 HttpOnly cookie 还原当前用户，
    # 再用 run_id + user_id 校验这个 run 是否属于当前登录用户。
    async with async_session_factory() as session:
        user = await get_current_user_from_token(
            session,
            request.cookies.get(settings.session_cookie_name),
        )
        if user is None:
            raise HTTPException(status_code=401, detail="not_authenticated")
        try:
            run = await get_llm_run_for_user(session, user, run_id)
        except LlmRunError as exc:
            raise _http_error(exc) from exc

        status = run.status
        user_id = user.id
        result = run.result_json
        error_code = run.error_code
        error_message = run.error_message

    # 如果 run 已经结束，stream 不再启动后台任务，而是把 DB 里的终态结果有限回放给前端。
    # 这让页面刷新后仍能通过同一个 stream_url 拿到 result/error/canceled + done。
    if status in {"succeeded", "failed", "canceled"}:
        events = _terminal_stream_events(
            run_id=run_id,
            status=status,
            result=result,
            error_code=error_code,
            error_message=error_message,
        )
        return StreamingResponse(
            _finite_event_stream(events),
            media_type="text/event-stream",
            headers=_stream_headers(),
        )

    async def stream_events() -> AsyncIterator[str]:
        # 先订阅内存事件 hub，再启动 pending run，避免后台任务太快发布 started/result 时丢事件。
        subscription = event_hub.subscribe(run_id)

        async def next_event() -> LlmRunEvent:
            return await anext(subscription)

        first_event_task: asyncio.Task[LlmRunEvent] = asyncio.create_task(next_event())
        try:
            await asyncio.sleep(0)
            # stream 是 pending run 的实际启动点：POST /api/llm-runs 只负责落库排队，
            # 第一次打开 stream 时才创建后台任务调用 orchestrator 执行 LLM flow。
            # has_task 用来避免同一个单进程内重复打开 stream 时重复启动同一个 run。
            if status == "pending" and not event_hub.has_task(run_id):
                task = asyncio.create_task(execute_llm_run(async_session_factory, run_id, user_id))
                task.add_done_callback(lambda done_task: _observe_llm_task(run_id, done_task))
                event_hub.set_task(run_id, task)
                logger.info("llm run stream started task user_id=%s run_id=%s", user_id, run_id)

            try:
                event = await first_event_task
            except StopAsyncIteration:
                return
            # StreamingResponse 会把这里 yield 出来的文本按 text/event-stream 推给浏览器 EventSource。
            # 事件序列通常是 started/progress/delta/result/done，失败或取消时走 error/canceled/done。
            yield encode_sse(event)
            async for event in subscription:
                yield encode_sse(event)
        finally:
            if not first_event_task.done():
                first_event_task.cancel()
            await subscription.aclose()

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers=_stream_headers(),
    )
