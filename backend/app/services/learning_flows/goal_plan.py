from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.learning import GoalCalibrationDraft
from backend.app.models.llm_run import LlmRun
from backend.app.prompts import get_prompt
from backend.app.services.learning_plan_validator import validate_and_repair_plan_draft
from backend.app.services.llm_providers.base import LlmProvider
from backend.app.services.llm_run_events import LlmRunEvent
from backend.app.services.llm_run_service import (
    LlmRunError,
    ensure_llm_run_mutable,
    update_llm_run_display_text,
)


_PLAN_DRAFT_PROMPT = get_prompt("goal_plan_draft")
_REPAIR_PLAN_PROMPT = get_prompt("goal_plan_repair")
PROMPT_VERSION = _PLAN_DRAFT_PROMPT.version
PLAN_DRAFT_INSTRUCTIONS = _PLAN_DRAFT_PROMPT.instructions
REPAIR_PLAN_INSTRUCTIONS = _REPAIR_PLAN_PROMPT.instructions
PLAN_STREAM_DISPLAY_MESSAGES = (
    "模型正在生成计划草稿...\n",
    "正在组织阶段目标和训练重点...\n",
    "正在整理推荐题单与训练理由...\n",
    "正在准备交给后端校验题库...\n",
)
PLAN_STREAM_DISPLAY_THRESHOLDS = (1, 180, 420, 900)

logger = logging.getLogger(__name__)


class LearningFlowError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _count_plan_items(plan: dict[str, Any]) -> tuple[int, int]:
    stages = _list_of_dicts(plan.get("stages", []))
    return len(stages), sum(len(_list_of_dicts(stage.get("items", []))) for stage in stages)


def _format_issues(report: dict[str, Any]) -> str:
    issues = report.get("issues", [])
    if isinstance(issues, list):
        return ",".join(str(issue) for issue in issues) or "none"
    return str(issues) if issues else "none"


async def _draft_for_run(
    session: AsyncSession,
    *,
    user_id: int,
    run: LlmRun,
) -> GoalCalibrationDraft:
    result = await session.execute(
        select(GoalCalibrationDraft).where(
            GoalCalibrationDraft.id == run.related_id,
            GoalCalibrationDraft.user_id == user_id,
        )
    )
    draft = result.scalar_one_or_none()
    if draft is None:
        logger.warning(
            "goal plan flow draft missing run_id=%s user_id=%s related_id=%s",
            run.id,
            user_id,
            run.related_id,
        )
        raise LearningFlowError("goal_draft_not_found")
    return draft


async def _publish_progress(
    publish: Callable[[LlmRunEvent], Awaitable[None]],
    *,
    run_id: int,
    stage: str,
    message: str,
) -> None:
    await publish(
        LlmRunEvent(
            "progress",
            {
                "run_id": run_id,
                "stage": stage,
                "message": message,
            },
        )
    )


async def _publish_display_delta(
    session: AsyncSession,
    *,
    run: LlmRun,
    publish: Callable[[LlmRunEvent], Awaitable[None]],
    display_parts: list[str],
    text: str,
) -> None:
    display_parts.append(text)
    await publish(LlmRunEvent("delta", {"run_id": run.id, "text": text}))
    await _update_display_text(session, run, "".join(display_parts))


def _parse_plan_json(final_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(final_text)
    except json.JSONDecodeError as exc:
        raise LearningFlowError("plan_json_invalid") from exc
    if not isinstance(parsed, dict):
        raise LearningFlowError("plan_json_invalid")
    return parsed


async def run_goal_plan_generate(
    session: AsyncSession,
    *,
    user_id: int,
    run: LlmRun,
    provider: LlmProvider,
    model_name: str,
    publish: Callable[[LlmRunEvent], Awaitable[None]],
) -> dict[str, Any]:
    draft = await _draft_for_run(session, user_id=user_id, run=run)
    await _ensure_run_mutable(session, run)
    logger.info(
        "goal plan flow started run_id=%s user_id=%s draft_id=%s model=%s",
        run.id,
        user_id,
        draft.id,
        model_name,
    )
    await _publish_progress(
        publish,
        run_id=run.id,
        stage="generating_plan_outline",
        message="正在生成阶段化学习计划",
    )

    raw_parts: list[str] = []
    display_parts: list[str] = []
    display_message_index = 0
    streamed_char_count = 0
    final_text = ""
    # 模型输出只能作为草稿来源，正式计划必须经过本地题库校验后才能持久化。
    try:
        async for chunk in provider.stream_text(
            model=model_name,
            instructions=PLAN_DRAFT_INSTRUCTIONS,
            input_text=json.dumps(
                {
                    "payload": draft.input_json,
                    "history": _list_of_dicts(draft.followup_messages_json),
                },
                ensure_ascii=False,
            ),
        ):
            if chunk.text_delta:
                raw_parts.append(chunk.text_delta)
                streamed_char_count += len(chunk.text_delta)
                while (
                    display_message_index < len(PLAN_STREAM_DISPLAY_MESSAGES)
                    and streamed_char_count
                    >= PLAN_STREAM_DISPLAY_THRESHOLDS[display_message_index]
                ):
                    await _publish_display_delta(
                        session,
                        run=run,
                        publish=publish,
                        display_parts=display_parts,
                        text=PLAN_STREAM_DISPLAY_MESSAGES[display_message_index],
                    )
                    display_message_index += 1
            if chunk.final_text:
                final_text = chunk.final_text
    except LearningFlowError:
        raise
    except Exception as exc:
        logger.warning(
            "goal plan flow provider failed run_id=%s user_id=%s draft_id=%s "
            "error_type=%s",
            run.id,
            user_id,
            draft.id,
            type(exc).__name__,
        )
        raise LearningFlowError("llm_provider_error") from None

    if not final_text:
        final_text = "".join(raw_parts)
    await _ensure_run_mutable(session, run)
    raw_plan = _parse_plan_json(final_text)
    raw_stage_count, raw_item_count = _count_plan_items(raw_plan)
    logger.info(
        "goal plan flow model completed run_id=%s user_id=%s draft_id=%s "
        "stage_count=%s item_count=%s",
        run.id,
        user_id,
        draft.id,
        raw_stage_count,
        raw_item_count,
    )
    await _publish_progress(
        publish,
        run_id=run.id,
        stage="validating_problem_library",
        message="正在校验题库并修复不可用题目",
    )

    repaired, report, repair_log = await validate_and_repair_plan_draft(
        session,
        raw_plan,
    )
    await _ensure_run_mutable(session, run)
    if not report.get("valid"):
        draft.status = "failed"
        draft.validation_report_json = report
        draft.repair_log_json = repair_log
        draft.error_message = "plan_validation_failed"
        draft.updated_at = datetime.now(UTC)
        await session.flush()
        logger.warning(
            "goal plan flow validation failed run_id=%s user_id=%s draft_id=%s "
            "issues=%s item_count=%s repair_log_count=%s",
            run.id,
            user_id,
            draft.id,
            _format_issues(report),
            report.get("item_count", 0),
            len(repair_log),
        )
        raise LearningFlowError("plan_validation_failed")

    stage_count, item_count = _count_plan_items(repaired)
    result = {
        "draft_id": draft.id,
        "status": "ready_for_review",
        "target_snapshot": repaired.get("target_snapshot", draft.input_json),
        "generation_summary_md": str(repaired.get("generation_summary_md", "")),
        "stages": _list_of_dicts(repaired.get("stages", [])),
        "validation_report": report,
        "repair_log": repair_log,
        "uncertainty_notes": [],
        "stage_count": stage_count,
        "item_count": item_count,
    }
    draft.draft_goal_json = repaired.get("target_snapshot", draft.input_json)
    draft.draft_plan_json = repaired
    draft.validation_report_json = report
    draft.repair_log_json = repair_log
    draft.prompt_version = PROMPT_VERSION
    draft.model_name = model_name
    draft.status = "ready_for_review"
    draft.error_message = ""
    draft.updated_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(draft)
    logger.info(
        "goal plan flow completed run_id=%s user_id=%s draft_id=%s "
        "stage_count=%s item_count=%s repair_log_count=%s",
        run.id,
        user_id,
        draft.id,
        stage_count,
        item_count,
        len(repair_log),
    )
    return result


async def _ensure_run_mutable(session: AsyncSession, run: LlmRun) -> None:
    try:
        await ensure_llm_run_mutable(session, run)
    except LlmRunError as exc:
        raise LearningFlowError(exc.detail) from None


async def _update_display_text(
    session: AsyncSession,
    run: LlmRun,
    display_text_md: str,
) -> None:
    try:
        await update_llm_run_display_text(
            session,
            run,
            display_text_md=display_text_md,
        )
    except LlmRunError as exc:
        raise LearningFlowError(exc.detail) from None
