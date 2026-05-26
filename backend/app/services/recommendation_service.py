from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.learning import StudyPlanItem, StudyPlanStage
from backend.app.models.practice import PracticeSession
from backend.app.models.problem import Problem


_DIFFICULTY_RANK = {"Easy": 1, "Medium": 2, "Hard": 3}
_WEAK_POINT_TAGS = {
    "edge_case_missing": {"边界", "正确性"},
    "submission_wa": {"边界", "正确性"},
    "wa": {"边界", "正确性"},
    "tle": {"复杂度", "时间复杂度"},
    "submission_tle": {"复杂度", "时间复杂度"},
    "mle": {"空间复杂度"},
    "submission_mle": {"空间复杂度"},
    "re": {"运行错误", "越界"},
    "submission_re": {"运行错误", "越界"},
    "ce": {"语法", "编译"},
    "submission_ce": {"语法", "编译"},
    "user_reported_stuck": {"思路"},
}


async def recommend_next_plan_item_for_session(
    session: AsyncSession,
    practice_session: PracticeSession,
    summary: Any,
) -> dict[str, Any]:
    if practice_session.latest_plan_version_id is None:
        return _fallback_recommendation(summary)
    result = await session.execute(
        select(StudyPlanItem, StudyPlanStage, Problem)
        .join(StudyPlanStage, StudyPlanStage.id == StudyPlanItem.stage_id)
        .join(Problem, Problem.id == StudyPlanItem.problem_id)
        .where(StudyPlanItem.version_id == practice_session.latest_plan_version_id)
        .order_by(StudyPlanStage.stage_index, StudyPlanItem.order_index)
    )
    items: list[dict[str, Any]] = []
    for item, stage, problem in result.all():
        items.append(
            {
                "item_id": item.id,
                "problem_id": item.problem_id,
                "problem_slug": item.problem_slug,
                "problem_title": problem.translated_title or problem.title,
                "stage_index": stage.stage_index,
                "order_index": item.order_index,
                "difficulty": item.difficulty,
                "skill_tags": item.skill_tags_json,
                "status": item.status,
                "recommendation_reason": item.recommendation_reason,
            }
        )
    plan_payload = {
        "current_item_id": practice_session.latest_plan_item_id,
        "current_stage_index": _current_stage_index(items, practice_session.latest_plan_item_id),
        "current_difficulty": _current_difficulty(items, practice_session.latest_plan_item_id),
        "items": items,
    }
    return recommend_next_plan_item(plan_payload, summary)


def recommend_next_plan_item(
    plan_payload: dict[str, Any],
    summary: Any,
) -> dict[str, Any]:
    weak_terms = _weak_terms(summary)
    candidates = [
        item
        for item in _list_value(plan_payload.get("items"))
        if _is_candidate(item, current_item_id=plan_payload.get("current_item_id"))
    ]
    if not candidates:
        return _fallback_recommendation(summary)

    current_stage = _int_value(plan_payload.get("current_stage_index"), default=0)
    current_difficulty = str(plan_payload.get("current_difficulty") or "Easy")

    # 规则推荐只使用计划元数据和安全复盘标签，避免把完整聊天或代码带入长期画像。
    ranked = sorted(
        candidates,
        key=lambda item: (
            -_score_item(
                item,
                weak_terms=weak_terms,
                current_stage=current_stage,
                current_difficulty=current_difficulty,
            ),
            _int_value(item.get("stage_index"), default=999),
            _int_value(item.get("order_index"), default=999),
        ),
    )
    selected = ranked[0]
    focus = _focus_label(weak_terms)
    problem_title = str(selected.get("problem_title") or selected.get("problem_slug") or "下一题")
    problem_slug = str(selected.get("problem_slug") or "")
    return {
        "item_id": _int_value(selected.get("item_id"), default=0),
        "problem_id": _int_value(selected.get("problem_id"), default=0),
        "problem_slug": problem_slug,
        "problem_title": problem_title,
        "difficulty": str(selected.get("difficulty") or ""),
        "skill_tags": _string_list(selected.get("skill_tags")),
        "reason": _recommendation_reason(problem_title, weak_terms=weak_terms),
        "first_question_hint": _first_question_hint(focus),
        "review_focus": _review_focus(focus),
        "preferred_hint_level": "questioning",
    }


def _is_candidate(item: Any, *, current_item_id: Any) -> bool:
    if not isinstance(item, dict):
        return False
    status = str(item.get("status") or "pending")
    if status not in {"pending", "in_progress"}:
        return False
    if item.get("item_id") == current_item_id:
        return False
    return True


def _score_item(
    item: dict[str, Any],
    *,
    weak_terms: set[str],
    current_stage: int,
    current_difficulty: str,
) -> int:
    searchable = {
        *(_normalize_term(tag) for tag in _string_list(item.get("skill_tags"))),
        _normalize_term(str(item.get("recommendation_reason") or "")),
        _normalize_term(str(item.get("problem_title") or "")),
        _normalize_term(str(item.get("problem_slug") or "")),
    }
    overlap = sum(1 for term in weak_terms if any(term in value for value in searchable))
    stage_index = _int_value(item.get("stage_index"), default=current_stage)
    difficulty = str(item.get("difficulty") or current_difficulty)
    score = overlap * 100
    if stage_index == current_stage:
        score += 20
    elif stage_index > current_stage:
        score += max(0, 10 - (stage_index - current_stage))
    if _difficulty_step_ok(current_difficulty, difficulty):
        score += 8
    if str(item.get("status") or "") == "in_progress":
        score += 6
    return score


def _weak_terms(summary: Any) -> set[str]:
    terms: set[str] = set()
    for value in _summary_list(summary, "main_stuck_points", "main_stuck_points_json"):
        terms.add(_normalize_term(value))
        terms.update(_WEAK_POINT_TAGS.get(_normalize_term(value), set()))
    for value in _summary_list(summary, "error_types", "error_types_json"):
        terms.add(_normalize_term(value))
        terms.update(_WEAK_POINT_TAGS.get(_normalize_term(value), set()))
    profile_signals = _summary_dict(summary, "profile_signals", "profile_signals_json")
    for value in _string_list(profile_signals.get("weak_skill_tags")):
        terms.add(_normalize_term(value))
    if not terms:
        terms.add("思路")
    return {term for term in terms if term}


def _fallback_recommendation(summary: Any) -> dict[str, Any]:
    focus = _focus_label(_weak_terms(summary))
    return {
        "item_id": None,
        "problem_id": None,
        "problem_slug": "",
        "problem_title": "",
        "difficulty": "",
        "skill_tags": [],
        "reason": f"当前没有可推荐的待训练计划题，先围绕{focus}复盘本题。",
        "first_question_hint": _first_question_hint(focus),
        "review_focus": _review_focus(focus),
        "preferred_hint_level": "questioning",
    }


def _recommendation_reason(problem_title: str, *, weak_terms: set[str]) -> str:
    focus = _focus_label(weak_terms)
    return f"延续本题的{focus}卡点，下一题优先练习 {problem_title}，先补齐可迁移检查点。"


def _first_question_hint(focus: str) -> str:
    if focus == "边界":
        return "先列出至少两个边界或重复元素用例，再说明你准备用什么状态维护候选答案。"
    if focus == "复杂度":
        return "先说出暴力复杂度瓶颈，再说明你打算用什么结构把重复计算降下来。"
    return "先用自己的话说明题目约束、暴力思路和你最担心出错的一步。"


def _review_focus(focus: str) -> str:
    if focus == "边界":
        return "代码 review 优先检查边界用例、重复元素、下标越界和状态更新顺序。"
    if focus == "复杂度":
        return "代码 review 优先检查循环层数、重复扫描和是否满足目标复杂度。"
    if focus == "运行错误":
        return "代码 review 优先检查空值、数组越界、类型转换和异常分支。"
    if focus == "语法":
        return "代码 review 优先检查语言语法、变量名和返回类型。"
    return "代码 review 优先检查关键状态、不变量和失败用例覆盖。"


def _focus_label(weak_terms: set[str]) -> str:
    for focus in ("边界", "复杂度", "运行错误", "语法"):
        if focus in weak_terms or any(focus in term for term in weak_terms):
            return focus
    return "思路"


def _difficulty_step_ok(current: str, candidate: str) -> bool:
    current_rank = _DIFFICULTY_RANK.get(current, 1)
    candidate_rank = _DIFFICULTY_RANK.get(candidate, current_rank)
    return candidate_rank <= current_rank + 1


def _current_stage_index(items: list[dict[str, Any]], current_item_id: int | None) -> int:
    for item in items:
        if item.get("item_id") == current_item_id:
            return _int_value(item.get("stage_index"), default=0)
    return 0


def _current_difficulty(items: list[dict[str, Any]], current_item_id: int | None) -> str:
    for item in items:
        if item.get("item_id") == current_item_id:
            return str(item.get("difficulty") or "Easy")
    return "Easy"


def _summary_list(summary: Any, dict_key: str, attr_name: str) -> list[str]:
    if isinstance(summary, dict):
        return _string_list(summary.get(dict_key) or summary.get(attr_name))
    return _string_list(getattr(summary, attr_name, None))


def _summary_dict(summary: Any, dict_key: str, attr_name: str) -> dict[str, Any]:
    value = summary.get(dict_key) if isinstance(summary, dict) else getattr(summary, attr_name, None)
    if value is None and isinstance(summary, dict):
        value = summary.get(attr_name)
    return value if isinstance(value, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _int_value(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


def _normalize_term(value: str) -> str:
    return value.strip().lower().replace("-", "_")
