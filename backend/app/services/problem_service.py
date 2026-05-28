from __future__ import annotations

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.problem import Problem, ProblemCategory, ProblemCategoryItem


def _tags(problem: Problem) -> list[dict]:
    return problem.metadata_json.get("topic_tags", [])


def _category_payload(items: list[ProblemCategoryItem]) -> list[dict]:
    return [
        {
            "slug": item.category.slug,
            "name": item.category.name,
            "description": item.category.description,
        }
        for item in items
    ]


def _problem_payload(problem: Problem) -> dict:
    return {
        "id": problem.id,
        "frontend_id": problem.frontend_id,
        "slug": problem.slug,
        "title": problem.title,
        "translated_title": problem.translated_title,
        "difficulty": problem.difficulty,
        "tags": _tags(problem),
        "categories": _category_payload(problem.category_items),
    }


def _base_query() -> Select[tuple[Problem]]:
    return select(Problem).options(
        selectinload(Problem.category_items).selectinload(
            ProblemCategoryItem.category
        )
    )


def _has_tag(problem: Problem, tag: str) -> bool:
    return any(item.get("slug") == tag for item in _tags(problem))


def _frontend_id_sort_key(problem: Problem) -> tuple[int, int, str]:
    frontend_id = problem.frontend_id.strip()
    if frontend_id.isdigit():
        return (0, int(frontend_id), frontend_id)
    return (1, 0, frontend_id)


def _sort_problems(problems: list[Problem], sort: str) -> list[Problem]:
    if sort == "title":
        return sorted(
            problems,
            key=lambda problem: (
                problem.title.casefold(),
                _frontend_id_sort_key(problem),
            ),
        )
    if sort == "difficulty":
        difficulty_order = {"Easy": 0, "Medium": 1, "Hard": 2}
        return sorted(
            problems,
            key=lambda problem: (
                difficulty_order.get(problem.difficulty, 99),
                _frontend_id_sort_key(problem),
            ),
        )

    # LeetCode 题号在数据库中以字符串保存，分页前必须按数值语义排序。
    return sorted(problems, key=_frontend_id_sort_key)


async def list_problems(
    session: AsyncSession,
    *,
    keyword: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    category: str | None = None,
    sort: str = "frontend_id",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    query = _base_query()
    if keyword:
        pattern = f"%{keyword}%"
        query = query.where(
            or_(
                Problem.title.ilike(pattern),
                Problem.translated_title.ilike(pattern),
                Problem.slug.ilike(pattern),
            )
        )
    if difficulty:
        query = query.where(Problem.difficulty == difficulty)
    if category:
        query = query.join(ProblemCategoryItem).join(ProblemCategory).where(
            ProblemCategory.slug == category
        )

    result = await session.execute(query)
    problems = list(result.scalars().unique().all())
    if tag:
        problems = [problem for problem in problems if _has_tag(problem, tag)]
    problems = _sort_problems(problems, sort)

    total = len(problems)
    offset = (page - 1) * page_size
    return {
        "items": [_problem_payload(problem) for problem in problems[offset : offset + page_size]],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_problem_detail(session: AsyncSession, slug: str) -> dict | None:
    result = await session.execute(_base_query().where(Problem.slug == slug))
    problem = result.scalar_one_or_none()
    if problem is None:
        return None

    payload = _problem_payload(problem)
    payload.update(
        {
            "statement_md": problem.statement_md,
            "leetcode_url": problem.leetcode_url,
            "sample_test_case": problem.metadata_json.get("sample_test_case", ""),
            "python3_snippet": problem.metadata_json.get("python3_snippet", ""),
        }
    )
    return payload


async def list_problem_categories(session: AsyncSession) -> dict:
    result = await session.execute(select(ProblemCategory).order_by(ProblemCategory.name))
    categories = result.scalars().all()
    return {
        "items": [
            {
                "slug": category.slug,
                "name": category.name,
                "description": category.description,
            }
            for category in categories
        ]
    }
