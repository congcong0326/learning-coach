from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.problem import Problem


logger = logging.getLogger(__name__)


class ValidationIssue(str, Enum):
    """稳定的校验问题码，会写入 validation report 和 repair log。"""

    EMPTY_PROBLEM_LIBRARY = "empty_problem_library"
    EMPTY_PLAN_STAGES = "empty_plan_stages"
    EMPTY_STAGE_ITEMS = "empty_stage_items"
    EMPTY_PLAN_ITEMS = "empty_plan_items"
    PROBLEM_NOT_FOUND = "problem_not_found"
    PAID_ONLY_PROBLEM = "paid_only_problem"
    DUPLICATE_PROBLEM = "duplicate_problem"
    INVALID_SUGGESTED_MODE = "invalid_suggested_mode"


TRAINING_MODE_ALIASES = {
    "independent_first": "independent",
    "interviewer_style": "mock_interview",
}
TRAINING_MODES = {"guided", "independent", "mock_interview"}


def normalise_suggested_mode(value: Any) -> str:
    if not isinstance(value, str):
        return "guided"
    normalized = value.strip().lower().replace("-", "_")
    if normalized in TRAINING_MODES:
        return normalized
    return TRAINING_MODE_ALIASES.get(normalized, "guided")


def _problem_tags(problem: Problem) -> set[str]:
    metadata = problem.metadata_json if isinstance(problem.metadata_json, dict) else {}
    topic_tags = metadata.get("topic_tags", [])
    if not isinstance(topic_tags, list):
        return set()
    return {
        item.get("slug", "")
        for item in topic_tags
        if isinstance(item, dict) and item.get("slug")
    }


async def _load_problems(session: AsyncSession) -> list[Problem]:
    result = await session.execute(
        select(Problem).order_by(Problem.difficulty.asc(), Problem.frontend_id.asc())
    )
    return list(result.scalars().all())


def _candidate_for_tags(
    candidates: list[Problem],
    wanted_tags: list[str],
    unavailable: set[str],
) -> Problem | None:
    # 优先选择标签匹配的免费题；如果没有匹配项，再退到第一道可用免费题，
    # 这样空草稿或无效草稿也能被修成可训练的最小计划。
    wanted = set(wanted_tags)
    for candidate in candidates:
        if candidate.slug in unavailable:
            continue
        if wanted and wanted.intersection(_problem_tags(candidate)):
            return candidate
    for candidate in candidates:
        if candidate.slug not in unavailable:
            return candidate
    return None


def _skill_tags(problem: Problem) -> list[str]:
    metadata = problem.metadata_json if isinstance(problem.metadata_json, dict) else {}
    topic_tags = metadata.get("topic_tags", [])
    if not isinstance(topic_tags, list):
        return []
    return [
        tag.get("slug", "")
        for tag in topic_tags
        if isinstance(tag, dict) and tag.get("slug")
    ]


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _list_of_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _append_issue(issues: list[str], issue: ValidationIssue) -> None:
    if issue.value not in issues:
        issues.append(issue.value)


def _problem_display_title(problem: Problem) -> str:
    return problem.translated_title or problem.title


def _item_from_problem(
    problem: Problem,
    original: dict[str, Any],
    order_index: int,
) -> dict[str, Any]:
    return {
        **original,
        "problem_slug": problem.slug,
        "title": _problem_display_title(problem),
        "difficulty": problem.difficulty,
        "skill_tags": _skill_tags(problem),
        "suggested_mode": normalise_suggested_mode(original.get("suggested_mode")),
        "order_index": order_index,
    }


def _fallback_item_payload(problem: Problem, stage: dict[str, Any]) -> dict[str, Any]:
    focus_tags = _list_of_strings(stage.get("focus_tags", []))
    return {
        "problem_slug": problem.slug,
        "title": _problem_display_title(problem),
        "difficulty": problem.difficulty,
        "skill_tags": focus_tags or _skill_tags(problem),
        "suggested_mode": "guided",
        "recommendation_reason": "根据阶段重点从本地题库自动补位。",
    }


def _fallback_stage_payload() -> dict[str, Any]:
    return {
        "title": "当前阶段",
        "objective_md": "先从本地题库中的可训练题目开始，建立当前阶段的练习基线。",
        "focus_tags": [],
        "assessment_criteria": ["完成题目并能复盘核心思路。"],
        "items": [],
    }


def _append_repair_log(
    repair_log: list[dict[str, Any]],
    *,
    reason: ValidationIssue,
    original_problem_slug: str,
    replacement: Problem,
) -> None:
    repair_log.append(
        {
            "reason": reason.value,
            "original_problem_slug": original_problem_slug,
            "replacement_problem_slug": replacement.slug,
        }
    )


def _safe_suggested_mode_value(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    stripped = value.strip()
    if len(stripped) <= 64 and all(
        character.isalnum() or character in "_-" for character in stripped
    ):
        return stripped
    return "invalid"


def _append_suggested_mode_repair_log(
    repair_log: list[dict[str, Any]],
    *,
    problem_slug: str,
    original_suggested_mode: Any,
    replacement_suggested_mode: str,
) -> None:
    repair_log.append(
        {
            "reason": ValidationIssue.INVALID_SUGGESTED_MODE.value,
            "problem_slug": problem_slug,
            "original_suggested_mode": _safe_suggested_mode_value(
                original_suggested_mode
            ),
            "replacement_suggested_mode": replacement_suggested_mode,
        }
    )


def _repair_empty_stage_items(
    stage: dict[str, Any],
    candidates: list[Problem],
    unavailable: set[str],
    repair_log: list[dict[str, Any]],
    reason: ValidationIssue,
) -> tuple[dict[str, Any], Problem | None]:
    replacement = _candidate_for_tags(
        candidates,
        _list_of_strings(stage.get("focus_tags", [])),
        unavailable,
    )
    if replacement is None:
        return stage, None
    repaired_stage = {**stage, "items": [_fallback_item_payload(replacement, stage)]}
    _append_repair_log(
        repair_log,
        reason=reason,
        original_problem_slug="",
        replacement=replacement,
    )
    return repaired_stage, replacement


async def validate_and_repair_plan_draft(
    session: AsyncSession,
    draft: dict[str, Any],
    *,
    locked_problem_slugs: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    # validator 是 LLM 输出进入正式计划前的后端闸门：只允许本地题库中存在、
    # 非 paid only、且未重复的题目进入后续落库流程。
    locked = locked_problem_slugs or set()
    problems = await _load_problems(session)
    candidates = [problem for problem in problems if not problem.is_paid_only]
    if not problems:
        logger.warning("learning plan validation failed reason=empty_problem_library")
        return (
            draft,
            {
                "valid": False,
                "issues": [ValidationIssue.EMPTY_PROBLEM_LIBRARY.value],
                "item_count": 0,
            },
            [],
        )

    by_slug = {problem.slug: problem for problem in problems}
    used: set[str] = set()
    repair_log: list[dict[str, Any]] = []
    issues: list[str] = []
    repaired = {**draft, "stages": []}
    stages = _list_of_dicts(draft.get("stages", []))
    logger.info(
        "learning plan validation started stage_count=%s problem_count=%s "
        "candidate_count=%s locked_problem_count=%s",
        len(stages),
        len(problems),
        len(candidates),
        len(locked),
    )

    if not stages:
        # LLM 偶尔会返回空 stages。这里用本地题库补一个“当前阶段”，
        # 保证用户至少能看到一份可训练的草稿，而不是直接失败。
        fallback_stage, replacement = _repair_empty_stage_items(
            _fallback_stage_payload(),
            candidates,
            used | locked,
            repair_log,
            ValidationIssue.EMPTY_PLAN_STAGES,
        )
        if replacement is None:
            _append_issue(issues, ValidationIssue.EMPTY_PLAN_STAGES)
            logger.warning(
                "learning plan validation found empty stages without fallback"
            )
        else:
            stages = [fallback_stage]
            logger.warning(
                "learning plan validation repaired empty stages replacement_slug=%s",
                replacement.slug,
            )

    for stage in stages:
        repaired_stage = {**stage, "items": []}
        stage_items = _list_of_dicts(stage.get("items", []))
        if not stage_items:
            # 空阶段没有训练价值；按阶段 focus_tags 补位，避免后续确认计划时生成空 stage。
            fallback_stage, replacement = _repair_empty_stage_items(
                stage,
                candidates,
                used | locked,
                repair_log,
                ValidationIssue.EMPTY_STAGE_ITEMS,
            )
            if replacement is None:
                _append_issue(issues, ValidationIssue.EMPTY_STAGE_ITEMS)
                logger.warning(
                    "learning plan validation found empty stage without fallback "
                    "stage_title=%s",
                    stage.get("title", ""),
                )
            else:
                stage_items = _list_of_dicts(fallback_stage.get("items", []))
                logger.warning(
                    "learning plan validation repaired empty stage "
                    "stage_title=%s replacement_slug=%s",
                    stage.get("title", ""),
                    replacement.slug,
                )

        for order_index, item in enumerate(stage_items, start=1):
            slug = item.get("problem_slug", "")
            problem = by_slug.get(slug)
            reason = ""

            if slug in used:
                reason = ValidationIssue.DUPLICATE_PROBLEM.value
                problem = None
            elif problem is None:
                reason = ValidationIssue.PROBLEM_NOT_FOUND.value
            elif problem.is_paid_only:
                reason = ValidationIssue.PAID_ONLY_PROBLEM.value
                problem = None

            if problem is None:
                # 对不存在、付费或重复题做同位替换，repair_log 保留原 slug 和替换原因，
                # 方便前端或排障时解释为什么最终题单和 LLM 原始输出不同。
                replacement = _candidate_for_tags(
                    candidates,
                    _list_of_strings(item.get("skill_tags", [])),
                    used | locked,
                )
                if replacement is None:
                    _append_issue(issues, ValidationIssue.EMPTY_PROBLEM_LIBRARY)
                    logger.warning(
                        "learning plan validation could not replace item "
                        "reason=%s original_slug=%s order_index=%s",
                        reason,
                        slug,
                        order_index,
                    )
                    continue
                _append_repair_log(
                    repair_log,
                    reason=ValidationIssue(reason),
                    original_problem_slug=str(slug),
                    replacement=replacement,
                )
                logger.warning(
                    "learning plan validation replaced item reason=%s "
                    "original_slug=%s replacement_slug=%s order_index=%s",
                    reason,
                    slug,
                    replacement.slug,
                    order_index,
                )
                problem = replacement

            used.add(problem.slug)
            raw_suggested_mode = item.get("suggested_mode")
            suggested_mode = normalise_suggested_mode(raw_suggested_mode)
            if raw_suggested_mode is not None and suggested_mode != raw_suggested_mode:
                _append_suggested_mode_repair_log(
                    repair_log,
                    problem_slug=problem.slug,
                    original_suggested_mode=raw_suggested_mode,
                    replacement_suggested_mode=suggested_mode,
                )
                logger.warning(
                    "learning plan validation normalized suggested mode "
                    "problem_slug=%s order_index=%s original_mode=%s replacement_mode=%s",
                    problem.slug,
                    order_index,
                    _safe_suggested_mode_value(raw_suggested_mode),
                    suggested_mode,
                )
            repaired_stage["items"].append(
                _item_from_problem(problem, item, order_index)
            )
        repaired["stages"].append(repaired_stage)

    item_count = sum(len(stage.get("items", [])) for stage in repaired["stages"])
    if item_count == 0 and not issues:
        _append_issue(issues, ValidationIssue.EMPTY_PLAN_ITEMS)
    report = {
        "valid": not issues and item_count > 0,
        "issues": issues,
        "item_count": item_count,
    }
    log_result = logger.info if report["valid"] else logger.warning
    log_result(
        "learning plan validation completed valid=%s issues=%s item_count=%s "
        "repair_log_count=%s",
        report["valid"],
        ",".join(issues) or "none",
        item_count,
        len(repair_log),
    )
    return repaired, report, repair_log
