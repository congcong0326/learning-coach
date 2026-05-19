import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.models.problem import Problem, ProblemCategory, ProblemCategoryItem
from backend.app.services.problem_seed import import_problem_seed


def test_problem_model_excludes_source_hash_and_solution_fields() -> None:
    columns = set(Problem.__table__.columns.keys())

    assert {
        "id",
        "frontend_id",
        "slug",
        "title",
        "translated_title",
        "difficulty",
        "statement_md",
        "metadata_json",
        "leetcode_url",
        "is_paid_only",
        "created_at",
        "updated_at",
    } <= columns
    assert "solution_md" not in columns
    assert "source_commit" not in columns
    assert "content_hash" not in columns


def test_category_models_have_only_static_fields() -> None:
    assert set(ProblemCategory.__table__.columns.keys()) == {
        "id",
        "slug",
        "name",
        "description",
        "created_at",
        "updated_at",
    }


@pytest.mark.asyncio
async def test_import_problem_seed_is_idempotent(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "manifest.json").write_text('{"schema_version":1}\n', encoding="utf-8")
    (seed / "problems.jsonl").write_text(
        json.dumps(
            {
                "frontend_id": "1",
                "slug": "two-sum",
                "title": "Two Sum",
                "translated_title": "两数之和",
                "difficulty": "Easy",
                "statement_md": "# Two Sum",
                "leetcode_url": "https://leetcode-cn.com/problems/two-sum/",
                "is_paid_only": False,
                "metadata": {"topic_tags": [], "python3_snippet": ""},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (seed / "problem_categories.jsonl").write_text("", encoding="utf-8")
    (seed / "problem_category_items.jsonl").write_text("", encoding="utf-8")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Problem.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        first = await import_problem_seed(seed, session)
        second = await import_problem_seed(seed, session)
        rows = (await session.execute(select(Problem))).scalars().all()

    assert first.inserted_problems == 1
    assert second.inserted_problems == 0
    assert len(rows) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_import_problem_seed_creates_category_links(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "manifest.json").write_text('{"schema_version":1}\n', encoding="utf-8")
    (seed / "problems.jsonl").write_text(
        (
            '{"frontend_id":"1","slug":"two-sum","title":"Two Sum",'
            '"translated_title":"两数之和","difficulty":"Easy",'
            '"statement_md":"# Two Sum",'
            '"leetcode_url":"https://leetcode-cn.com/problems/two-sum/",'
            '"is_paid_only":false,"metadata":{"topic_tags":[]}}\n'
        ),
        encoding="utf-8",
    )
    (seed / "problem_categories.jsonl").write_text(
        '{"slug":"hot_100","name":"Hot 100","description":"LeetCode Hot 100"}\n',
        encoding="utf-8",
    )
    (seed / "problem_category_items.jsonl").write_text(
        '{"category_slug":"hot_100","problem_slug":"two-sum","sort_order":1}\n',
        encoding="utf-8",
    )
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Problem.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        stats = await import_problem_seed(seed, session)
        categories = (await session.execute(select(ProblemCategory))).scalars().all()
        links = (await session.execute(select(ProblemCategoryItem))).scalars().all()

    assert stats.inserted_problems == 1
    assert stats.inserted_categories == 1
    assert stats.inserted_category_items == 1
    assert categories[0].slug == "hot_100"
    assert links[0].sort_order == 1
    await engine.dispose()
    assert set(ProblemCategoryItem.__table__.columns.keys()) == {
        "id",
        "category_id",
        "problem_id",
        "sort_order",
        "created_at",
        "updated_at",
    }
