from __future__ import annotations

from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.problem import Problem


class ValidationIssue(str, Enum):
    EMPTY_PROBLEM_LIBRARY = "empty_problem_library"
    PROBLEM_NOT_FOUND = "problem_not_found"
    PAID_ONLY_PROBLEM = "paid_only_problem"
    DUPLICATE_PROBLEM = "duplicate_problem"


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


def _item_from_problem(
    problem: Problem,
    original: dict[str, Any],
    order_index: int,
) -> dict[str, Any]:
    return {
        **original,
        "problem_slug": problem.slug,
        "title": problem.title,
        "difficulty": problem.difficulty,
        "skill_tags": _skill_tags(problem),
        "order_index": order_index,
    }


async def validate_and_repair_plan_draft(
    session: AsyncSession,
    draft: dict[str, Any],
    *,
    locked_problem_slugs: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    problems = await _load_problems(session)
    candidates = [problem for problem in problems if not problem.is_paid_only]
    if not problems:
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
    locked = locked_problem_slugs or set()
    repaired = {**draft, "stages": []}

    for stage in _list_of_dicts(draft.get("stages", [])):
        repaired_stage = {**stage, "items": []}
        for order_index, item in enumerate(_list_of_dicts(stage.get("items", [])), start=1):
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
                replacement = _candidate_for_tags(
                    candidates,
                    _list_of_strings(item.get("skill_tags", [])),
                    used | locked,
                )
                if replacement is None:
                    _append_issue(issues, ValidationIssue.EMPTY_PROBLEM_LIBRARY)
                    continue
                repair_log.append(
                    {
                        "reason": reason,
                        "original_problem_slug": slug,
                        "replacement_problem_slug": replacement.slug,
                    }
                )
                problem = replacement

            used.add(problem.slug)
            repaired_stage["items"].append(
                _item_from_problem(problem, item, order_index)
            )
        repaired["stages"].append(repaired_stage)

    item_count = sum(len(stage.get("items", [])) for stage in repaired["stages"])
    report = {
        "valid": not issues and item_count > 0,
        "issues": issues,
        "item_count": item_count,
    }
    return repaired, report, repair_log
