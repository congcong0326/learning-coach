from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.models.problem import Base, Problem
from backend.app.services.learning_plan_validator import (
    ValidationIssue,
    validate_and_repair_plan_draft,
)


@pytest_asyncio.fixture
async def validator_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def problem(slug: str, *, paid: bool = False, tag: str = "array") -> Problem:
    now = datetime.now(UTC)
    return Problem(
        frontend_id=slug,
        slug=slug,
        title=slug.replace("-", " ").title(),
        translated_title=slug,
        difficulty="Easy",
        statement_md="# statement",
        metadata_json={
            "topic_tags": [
                {"slug": tag, "name": tag.title(), "translated_name": tag}
            ]
        },
        leetcode_url=f"https://leetcode.cn/problems/{slug}/",
        is_paid_only=paid,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_validator_replaces_missing_problem_with_same_tag_candidate(
    validator_session_factory,
) -> None:
    async with validator_session_factory() as session:
        session.add(problem("two-sum"))
        await session.commit()

        draft = {
            "stages": [
                {
                    "title": "基础",
                    "objective_md": "练数组",
                    "focus_tags": ["array"],
                    "assessment_criteria": ["能讲清 complement"],
                    "items": [
                        {
                            "problem_slug": "missing-problem",
                            "difficulty": "Easy",
                            "skill_tags": ["array"],
                            "suggested_mode": "guided",
                            "recommendation_reason": "练数组",
                            "order_index": 1,
                        }
                    ],
                }
            ]
        }

        repaired, report, repair_log = await validate_and_repair_plan_draft(
            session,
            draft,
        )

        assert repaired["stages"][0]["items"][0]["problem_slug"] == "two-sum"
        assert report["valid"] is True
        assert repair_log[0]["reason"] == "problem_not_found"


@pytest.mark.asyncio
async def test_validator_reports_empty_problem_library(
    validator_session_factory,
) -> None:
    async with validator_session_factory() as session:
        repaired, report, repair_log = await validate_and_repair_plan_draft(
            session,
            {"stages": []},
        )

        assert repaired == {"stages": []}
        assert report["valid"] is False
        assert ValidationIssue.EMPTY_PROBLEM_LIBRARY.value in report["issues"]
        assert repair_log == []


@pytest.mark.asyncio
async def test_validator_replaces_paid_only_problem(
    validator_session_factory,
) -> None:
    async with validator_session_factory() as session:
        session.add_all([problem("premium-array", paid=True), problem("two-sum")])
        await session.commit()

        draft = {
            "stages": [
                {
                    "title": "基础",
                    "items": [
                        {
                            "problem_slug": "premium-array",
                            "skill_tags": ["array"],
                        }
                    ],
                }
            ]
        }

        repaired, report, repair_log = await validate_and_repair_plan_draft(
            session,
            draft,
        )

        assert repaired["stages"][0]["items"][0]["problem_slug"] == "two-sum"
        assert report["valid"] is True
        assert repair_log[0]["reason"] == ValidationIssue.PAID_ONLY_PROBLEM.value


@pytest.mark.asyncio
async def test_validator_replaces_duplicate_problem(
    validator_session_factory,
) -> None:
    async with validator_session_factory() as session:
        session.add_all([problem("two-sum"), problem("valid-anagram")])
        await session.commit()

        draft = {
            "stages": [
                {
                    "title": "基础",
                    "items": [
                        {"problem_slug": "two-sum", "skill_tags": ["array"]},
                        {"problem_slug": "two-sum", "skill_tags": ["array"]},
                    ],
                }
            ]
        }

        repaired, report, repair_log = await validate_and_repair_plan_draft(
            session,
            draft,
        )

        item_slugs = [
            item["problem_slug"] for item in repaired["stages"][0]["items"]
        ]
        assert item_slugs == ["two-sum", "valid-anagram"]
        assert report["valid"] is True
        assert repair_log[0]["reason"] == ValidationIssue.DUPLICATE_PROBLEM.value


@pytest.mark.asyncio
async def test_validator_skips_locked_replacement_candidate(
    validator_session_factory,
) -> None:
    async with validator_session_factory() as session:
        session.add_all([problem("aaa-array"), problem("zzz-array")])
        await session.commit()

        draft = {
            "stages": [
                {
                    "title": "基础",
                    "items": [
                        {"problem_slug": "missing-problem", "skill_tags": ["array"]}
                    ],
                }
            ]
        }

        repaired, report, repair_log = await validate_and_repair_plan_draft(
            session,
            draft,
            locked_problem_slugs={"aaa-array"},
        )

        assert repaired["stages"][0]["items"][0]["problem_slug"] == "zzz-array"
        assert report["valid"] is True
        assert repair_log[0]["replacement_problem_slug"] == "zzz-array"


@pytest.mark.asyncio
async def test_validator_reports_empty_library_when_replacement_candidates_exhausted(
    validator_session_factory,
) -> None:
    async with validator_session_factory() as session:
        session.add(problem("two-sum"))
        await session.commit()

        draft = {
            "stages": [
                {
                    "title": "基础",
                    "items": [
                        {"problem_slug": "missing-problem", "skill_tags": ["array"]}
                    ],
                }
            ]
        }

        repaired, report, repair_log = await validate_and_repair_plan_draft(
            session,
            draft,
            locked_problem_slugs={"two-sum"},
        )

        assert repaired["stages"][0]["items"] == []
        assert report["valid"] is False
        assert report["issues"] == [ValidationIssue.EMPTY_PROBLEM_LIBRARY.value]
        assert repair_log == []


@pytest.mark.asyncio
async def test_validator_drops_paid_only_items_when_library_has_no_free_candidates(
    validator_session_factory,
) -> None:
    async with validator_session_factory() as session:
        session.add(problem("premium-array", paid=True))
        await session.commit()

        draft = {
            "stages": [
                {
                    "title": "基础",
                    "items": [
                        {"problem_slug": "premium-array", "skill_tags": ["array"]}
                    ],
                }
            ]
        }

        repaired, report, repair_log = await validate_and_repair_plan_draft(
            session,
            draft,
        )

        assert repaired["stages"][0]["items"] == []
        assert report["valid"] is False
        assert report["issues"] == [ValidationIssue.EMPTY_PROBLEM_LIBRARY.value]
        assert repair_log == []


@pytest.mark.asyncio
@pytest.mark.parametrize("skill_tags", [None, "array"])
async def test_validator_normalizes_malformed_skill_tags(
    validator_session_factory,
    skill_tags,
) -> None:
    async with validator_session_factory() as session:
        session.add(problem("two-sum"))
        await session.commit()

        draft = {
            "stages": [
                {
                    "title": "基础",
                    "items": [
                        {
                            "problem_slug": "missing-problem",
                            "skill_tags": skill_tags,
                        }
                    ],
                }
            ]
        }

        repaired, report, repair_log = await validate_and_repair_plan_draft(
            session,
            draft,
        )

        assert repaired["stages"][0]["items"][0]["problem_slug"] == "two-sum"
        assert report["valid"] is True
        assert repair_log[0]["reason"] == ValidationIssue.PROBLEM_NOT_FOUND.value


@pytest.mark.asyncio
async def test_validator_ignores_null_stages_and_items(
    validator_session_factory,
) -> None:
    async with validator_session_factory() as session:
        session.add(problem("two-sum"))
        await session.commit()

        repaired, report, repair_log = await validate_and_repair_plan_draft(
            session,
            {"stages": [None, {"title": "基础", "items": None}]},
        )

        assert repaired["stages"] == [{"title": "基础", "items": []}]
        assert report["valid"] is False
        assert report["item_count"] == 0
        assert repair_log == []
