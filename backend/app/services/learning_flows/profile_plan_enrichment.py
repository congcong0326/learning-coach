from __future__ import annotations

import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.auth import AppUser
from backend.app.models.llm_run import LlmRun
from backend.app.prompts import get_prompt
from backend.app.schemas.learning import ProfilePlanEnrichmentRequest
from backend.app.services.learning_flows.goal_plan import LearningFlowError
from backend.app.services.llm_providers.base import LlmProvider
from backend.app.services.llm_run_events import LlmRunEvent
from backend.app.services.profile_plan_enrichment import (
    MAX_REPAIR_ATTEMPTS,
    build_enrichment_context,
    draft_response,
    persist_generated_draft,
    validate_model_output,
)
from backend.app.services.study_plan_service import StudyPlanError


logger = logging.getLogger(__name__)
PROMPT = get_prompt("profile_plan_enrichment")


class ProfilePlanEnrichmentHandler:
    async def execute(self, context: Any) -> dict[str, Any]:
        return await run_profile_plan_enrichment(
            context.session,
            user_id=context.user_id,
            run=context.run,
            provider=context.provider,
            model_name=context.model_name,
            publish=context.publish,
        )


async def run_profile_plan_enrichment(
    session: AsyncSession,
    *,
    user_id: int,
    run: LlmRun,
    provider: LlmProvider,
    model_name: str,
    publish: Callable[[LlmRunEvent], Awaitable[None] | None],
) -> dict[str, Any]:
    payload = _payload(run)
    plan_id = payload.get("plan_id")
    if not isinstance(plan_id, int) or isinstance(plan_id, bool):
        raise LearningFlowError("active_study_plan_not_found")
    try:
        request = ProfilePlanEnrichmentRequest.model_validate(payload)
    except ValidationError:
        raise LearningFlowError("profile_plan_enrichment_invalid") from None
    user = await session.get(AppUser, user_id)
    if user is None:
        raise LearningFlowError("active_study_plan_not_found")

    logger.info(
        "profile_plan_enrichment_flow_started user_id=%s run_id=%s plan_id=%s model=%s",
        user_id,
        run.id,
        plan_id,
        model_name,
    )
    await _progress(publish, run.id, "building_context", "正在整理画像、计划和训练事实")
    try:
        context = await build_enrichment_context(session, user, plan_id, request)
    except StudyPlanError as exc:
        raise LearningFlowError(exc.detail) from None
    await _progress(publish, run.id, "calling_model", "正在调用大模型生成补强题预览")
    model_output = await _model_output(provider, model_name=model_name, context=context)
    report, normalized_items = validate_model_output(model_output, context)
    for _attempt in range(MAX_REPAIR_ATTEMPTS):
        if report.get("valid"):
            break
        await _progress(publish, run.id, "repairing_output", "正在修复补强题结构")
        model_output, report, normalized_items = await _repair_output(
            provider,
            model_name=model_name,
            context=context,
            model_output=model_output,
            report=report,
        )
    if not report.get("valid"):
        logger.warning(
            "profile_plan_enrichment_flow_validation_failed user_id=%s run_id=%s plan_id=%s issue_count=%s",
            user_id,
            run.id,
            plan_id,
            len(report.get("issues", [])) if isinstance(report.get("issues"), list) else 0,
        )
        raise LearningFlowError("profile_plan_enrichment_invalid")

    await _progress(publish, run.id, "saving_draft", "正在保存补强题预览")
    draft = await persist_generated_draft(
        session,
        user=user,
        plan_id=plan_id,
        version_id=int(context["current_plan"]["version_id"]),
        profile_snapshot_id=_profile_snapshot_id(context),
        llm_run_id=run.id,
        payload=request,
        context=context,
        model_output=model_output,
        validation_report=report,
        normalized_items=normalized_items,
    )
    run.display_text_md = str(model_output.get("overall_reason_md") or "")
    response = draft_response(draft).model_dump(mode="json")
    await session.flush()
    logger.info(
        "profile_plan_enrichment_flow_completed user_id=%s run_id=%s plan_id=%s draft_id=%s item_count=%s",
        user_id,
        run.id,
        plan_id,
        draft.id,
        len(response.get("items", [])),
    )
    return response


def _payload(run: LlmRun) -> dict[str, Any]:
    if not isinstance(run.input_json, dict):
        raise LearningFlowError("profile_plan_enrichment_invalid")
    return run.input_json


async def _progress(
    publish: Callable[[LlmRunEvent], Awaitable[None] | None],
    run_id: int,
    stage: str,
    message: str,
) -> None:
    await _publish(
        publish,
        LlmRunEvent("progress", {"run_id": run_id, "stage": stage, "message": message}),
    )


async def _publish(
    publish: Callable[[LlmRunEvent], Awaitable[None] | None],
    event: LlmRunEvent,
) -> None:
    result = publish(event)
    if inspect.isawaitable(result):
        await result


async def _model_output(
    provider: LlmProvider,
    *,
    model_name: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    raw_parts: list[str] = []
    final_text = ""
    try:
        async for chunk in provider.stream_text(
            model=model_name,
            instructions=PROMPT.instructions,
            input_text=json.dumps(context, ensure_ascii=False),
        ):
            if chunk.text_delta:
                raw_parts.append(chunk.text_delta)
            if chunk.final_text:
                final_text = chunk.final_text
    except LearningFlowError:
        raise
    except Exception as exc:
        logger.warning(
            "profile_plan_enrichment_provider_failed error_type=%s",
            type(exc).__name__,
        )
        raise LearningFlowError("llm_provider_error") from None

    text = final_text or "".join(raw_parts)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LearningFlowError("profile_plan_enrichment_invalid") from exc
    if not isinstance(data, dict):
        raise LearningFlowError("profile_plan_enrichment_invalid")
    return data


async def _repair_output(
    provider: LlmProvider,
    *,
    model_name: str,
    context: dict[str, Any],
    model_output: dict[str, Any],
    report: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    # repair 只允许模型修复结构和候选题选择，不重新扩大上下文或绕过本地校验。
    repair_context = {
        "original_context": context,
        "invalid_output": model_output,
        "validation_report": report,
        "repair_instruction": "只修复 JSON，使题目来自 candidate_problems，并满足 validation_report。",
    }
    repaired = await _model_output(provider, model_name=model_name, context=repair_context)
    repaired_report, repaired_items = validate_model_output(repaired, context)
    return repaired, repaired_report, repaired_items


def _profile_snapshot_id(context: dict[str, Any]) -> int | None:
    profile_snapshot = context.get("profile_snapshot")
    if not isinstance(profile_snapshot, dict):
        return None
    value = profile_snapshot.get("id")
    return value if isinstance(value, int) and not isinstance(value, bool) else None
