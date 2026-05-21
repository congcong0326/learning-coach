from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core.config import settings
from backend.app.models.auth import AppUser
from backend.app.models.llm_run import LlmRun
from backend.app.services.credential_crypto import (
    CredentialEncryptionError,
    decrypt_api_key,
)
from backend.app.services.learning_flows.goal_plan import (
    LearningFlowError,
    run_goal_plan_generate,
)
from backend.app.services.llm_credential_service import (
    LlmCredentialError,
    select_llm_credential_for_user,
)
from backend.app.services.llm_providers.openai_responses import OpenAIResponsesProvider
from backend.app.services.llm_run_events import LlmRunEvent, event_hub
from backend.app.services.llm_run_service import (
    LlmRunError,
    fail_llm_run,
    mark_llm_run_running,
    succeed_llm_run,
)


logger = logging.getLogger(__name__)

ERROR_MESSAGES = {
    "goal_draft_not_found": "目标校准草稿不存在或无权访问",
    "llm_credential_unavailable": "没有可用的模型资产，请检查 API 设置",
    "credential_decryption_failed": "模型资产解密失败，请重新保存 API key",
    "credential_encryption_key_missing": "模型资产加密配置缺失",
    "credential_encryption_key_invalid": "模型资产加密配置无效",
    "llm_provider_error": "模型生成失败",
    "plan_json_invalid": "模型返回的计划格式无效",
    "plan_validation_failed": "计划生成结果未通过题库校验",
    "run_kind_unsupported": "当前生成类型暂未接入",
    "run_status_conflict": "本次生成已结束或已取消",
}


async def _load_run_and_user(
    session: AsyncSession,
    run_id: int,
    user_id: int,
) -> tuple[LlmRun, AppUser]:
    run_result = await session.execute(
        select(LlmRun).where(LlmRun.id == run_id, LlmRun.user_id == user_id)
    )
    run = run_result.scalar_one()
    user_result = await session.execute(select(AppUser).where(AppUser.id == user_id))
    user = user_result.scalar_one()
    return run, user


def _message_for_error(error_code: str) -> str:
    return ERROR_MESSAGES.get(error_code, "模型生成失败")


def _error_code_from_exception(exc: Exception) -> str:
    if isinstance(exc, LearningFlowError):
        return exc.code
    if isinstance(exc, (LlmRunError, LlmCredentialError)):
        return exc.detail
    if isinstance(exc, CredentialEncryptionError):
        return str(exc) or "credential_decryption_failed"
    return "llm_provider_error"


def _is_status_conflict(exc: Exception) -> bool:
    return _error_code_from_exception(exc) == "run_status_conflict"


async def _publish_error(run_id: int, *, error_code: str) -> None:
    await event_hub.publish(
        run_id,
        LlmRunEvent(
            "error",
            {
                "run_id": run_id,
                "error_code": error_code,
                "message": _message_for_error(error_code),
            },
        ),
    )


async def _publish_done(run_id: int) -> None:
    await event_hub.publish(run_id, LlmRunEvent("done", {"run_id": run_id}))


async def _safe_rollback(session: AsyncSession, *, run_id: int, user_id: int) -> None:
    try:
        await session.rollback()
    except Exception as exc:
        logger.warning(
            "llm run rollback failed user_id=%s run_id=%s error_type=%s",
            user_id,
            run_id,
            type(exc).__name__,
        )


async def _refresh_run_if_possible(session: AsyncSession, run: LlmRun) -> None:
    try:
        await session.refresh(run)
    except Exception:
        # 测试替身或跨事务取消可能无法刷新；后续仍可根据内存态做保守收尾。
        return


async def _publish_conflict_terminal(
    session: AsyncSession,
    run: LlmRun,
    *,
    run_id: int,
    user_id: int,
) -> None:
    await _safe_rollback(session, run_id=run_id, user_id=user_id)
    await _refresh_run_if_possible(session, run)
    if run.status == "canceled" or getattr(run, "cancel_requested", False):
        await event_hub.publish(run_id, LlmRunEvent("canceled", {"run_id": run_id}))
        logger.info("llm run conflict resolved as canceled user_id=%s run_id=%s", user_id, run_id)
    else:
        logger.info("llm run conflict resolved as done user_id=%s run_id=%s", user_id, run_id)
    await _publish_done(run_id)


async def _fail_and_publish(
    session: AsyncSession,
    run: LlmRun,
    *,
    run_id: int,
    user_id: int,
    error_code: str,
) -> None:
    await _safe_rollback(session, run_id=run_id, user_id=user_id)
    try:
        await fail_llm_run(
            session,
            run,
            error_code=error_code,
            error_message=_message_for_error(error_code),
        )
    except LlmRunError as exc:
        if exc.detail == "run_status_conflict":
            await _publish_conflict_terminal(session, run, run_id=run_id, user_id=user_id)
            return
        logger.warning(
            "llm run fail transition failed user_id=%s run_id=%s error_type=%s error_code=%s",
            user_id,
            run_id,
            type(exc).__name__,
            error_code,
        )
    await _publish_error(run_id, error_code=error_code)
    await _publish_done(run_id)


async def execute_llm_run(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: int,
    user_id: int,
) -> None:
    async with session_factory() as session:
        try:
            run, user = await _load_run_and_user(session, run_id, user_id)
        except Exception as exc:
            logger.error(
                "llm run load failed user_id=%s run_id=%s error_type=%s",
                user_id,
                run_id,
                type(exc).__name__,
            )
            await _publish_error(run_id, error_code="llm_provider_error")
            await _publish_done(run_id)
            return

        try:
            await event_hub.publish(
                run_id,
                LlmRunEvent("started", {"run_id": run_id, "kind": run.kind}),
            )
            await event_hub.publish(
                run_id,
                LlmRunEvent(
                    "progress",
                    {
                        "run_id": run_id,
                        "stage": "selecting_credential",
                        "message": "正在选择模型资产",
                    },
                ),
            )
            credential = await select_llm_credential_for_user(session, user)
            api_key = decrypt_api_key(
                credential.api_key_ciphertext,
                settings.credential_encryption_key,
            )
            await mark_llm_run_running(
                session,
                run,
                stage="selecting_credential",
                llm_credential_id=credential.id,
                model_name=credential.model_name,
            )
            provider = OpenAIResponsesProvider(
                api_key=api_key,
                base_url=credential.base_url,
            )

            if run.kind != "goal_plan_generate":
                await _fail_and_publish(
                    session,
                    run,
                    run_id=run_id,
                    user_id=user_id,
                    error_code="run_kind_unsupported",
                )
                return

            result = await run_goal_plan_generate(
                session,
                user_id=user_id,
                run=run,
                provider=provider,
                model_name=credential.model_name,
                publish=lambda event: event_hub.publish(run_id, event),
            )
            await succeed_llm_run(
                session,
                run,
                result=result,
                display_text_md=run.display_text_md,
            )
            # 正式结果只能在终态提交成功后发布，避免前端确认未提交或已取消的草稿。
            await event_hub.publish(
                run_id,
                LlmRunEvent(
                    "result",
                    {"run_id": run_id, "status": "succeeded", "result": result},
                ),
            )
            await _publish_done(run_id)
        except Exception as exc:
            error_code = _error_code_from_exception(exc)
            if _is_status_conflict(exc):
                await _publish_conflict_terminal(session, run, run_id=run_id, user_id=user_id)
                return
            logger.warning(
                "llm run execution failed user_id=%s run_id=%s error_type=%s error_code=%s",
                user_id,
                run_id,
                type(exc).__name__,
                error_code,
            )
            await _fail_and_publish(
                session,
                run,
                run_id=run_id,
                user_id=user_id,
                error_code=error_code,
            )
