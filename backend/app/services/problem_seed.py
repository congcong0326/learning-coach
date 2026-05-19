from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.problem import Problem, ProblemCategory, ProblemCategoryItem


@dataclass(frozen=True)
class SeedImportStats:
    inserted_problems: int = 0
    inserted_categories: int = 0
    inserted_category_items: int = 0


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


async def _problem_by_slug(session: AsyncSession, slug: str) -> Problem | None:
    result = await session.execute(select(Problem).where(Problem.slug == slug))
    return result.scalar_one_or_none()


async def _category_by_slug(
    session: AsyncSession,
    slug: str,
) -> ProblemCategory | None:
    result = await session.execute(
        select(ProblemCategory).where(ProblemCategory.slug == slug)
    )
    return result.scalar_one_or_none()


async def import_problem_seed(seed_dir: Path, session: AsyncSession) -> SeedImportStats:
    if not (seed_dir / "manifest.json").exists():
        raise FileNotFoundError(seed_dir / "manifest.json")

    inserted_problems = 0
    for record in _jsonl(seed_dir / "problems.jsonl"):
        if await _problem_by_slug(session, record["slug"]):
            continue
        session.add(
            Problem(
                frontend_id=record["frontend_id"],
                slug=record["slug"],
                title=record["title"],
                translated_title=record["translated_title"],
                difficulty=record["difficulty"],
                statement_md=record["statement_md"],
                metadata_json=record["metadata"],
                leetcode_url=record["leetcode_url"],
                is_paid_only=record["is_paid_only"],
            )
        )
        inserted_problems += 1
    await session.flush()

    inserted_categories = 0
    for record in _jsonl(seed_dir / "problem_categories.jsonl"):
        if await _category_by_slug(session, record["slug"]):
            continue
        session.add(
            ProblemCategory(
                slug=record["slug"],
                name=record["name"],
                description=record.get("description", ""),
            )
        )
        inserted_categories += 1
    await session.flush()

    inserted_category_items = 0
    for record in _jsonl(seed_dir / "problem_category_items.jsonl"):
        category = await _category_by_slug(session, record["category_slug"])
        problem = await _problem_by_slug(session, record["problem_slug"])
        if category is None or problem is None:
            raise ValueError(f"Invalid category item: {record}")
        existing = await session.execute(
            select(ProblemCategoryItem).where(
                ProblemCategoryItem.category_id == category.id,
                ProblemCategoryItem.problem_id == problem.id,
            )
        )
        if existing.scalar_one_or_none():
            continue
        session.add(
            ProblemCategoryItem(
                category_id=category.id,
                problem_id=problem.id,
                sort_order=record.get("sort_order"),
            )
        )
        inserted_category_items += 1

    await session.commit()
    return SeedImportStats(
        inserted_problems=inserted_problems,
        inserted_categories=inserted_categories,
        inserted_category_items=inserted_category_items,
    )
