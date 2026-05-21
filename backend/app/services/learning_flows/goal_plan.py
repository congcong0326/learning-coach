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
from backend.app.services.learning_plan_validator import validate_and_repair_plan_draft
from backend.app.services.llm_providers.base import LlmProvider
from backend.app.services.llm_run_events import LlmRunEvent


PROMPT_VERSION = "goal-plan-v3-streaming"
PLAN_DRAFT_INSTRUCTIONS = (
    "默认语言语境：简体中文。根据用户目标、追问历史和训练偏好生成阶段化学习计划。"
    "只输出 JSON，且 stages 至少包含 1 个阶段，每个阶段 items 至少包含 1 道题。"
    "面向用户展示的 title、objective_md、assessment_criteria、recommendation_reason "
    "必须使用简体中文；problem_slug、difficulty、suggested_mode、skill_tags 等机器字段保持英文或枚举值。"
    "正式题单会由后端本地题库校验和修复，不要输出解释性前后缀。"
)
REPAIR_PLAN_INSTRUCTIONS = (
    "默认语言语境：简体中文。根据 validation_report 修复学习计划。"
    "若报告包含空阶段、空题目、缺失题目、付费题或重复题，必须补充或替换为可训练题目。"
    "只输出符合学习计划结构的 JSON。"
)

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

    display_parts: list[str] = []
    final_text = ""
    # 模型输出只能作为草稿来源，正式计划必须经过本地题库校验后才能持久化。
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
            display_parts.append(chunk.text_delta)
            await publish(
                LlmRunEvent("delta", {"run_id": run.id, "text": chunk.text_delta})
            )
        if chunk.final_text:
            final_text = chunk.final_text

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
    if not report.get("valid"):
        draft.status = "failed"
        draft.validation_report_json = report
        draft.repair_log_json = repair_log
        draft.error_message = "plan_validation_failed"
        draft.updated_at = datetime.now(UTC)
        run.status = "failed"
        run.stage = "validation_failed"
        run.error_code = "plan_validation_failed"
        run.error_message = "plan_validation_failed"
        run.updated_at = datetime.now(UTC)
        run.finished_at = datetime.now(UTC)
        await session.commit()
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
    run.display_text_md = "".join(display_parts)
    run.result_json = result
    run.status = "succeeded"
    run.stage = "completed"
    run.model_name = model_name
    run.updated_at = datetime.now(UTC)
    run.finished_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(draft)
    await publish(
        LlmRunEvent(
            "result",
            {"run_id": run.id, "status": "succeeded", "result": result},
        )
    )
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
