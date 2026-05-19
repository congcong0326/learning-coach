# Problem Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build static problem library ingestion from generated seed files, expose problem browsing APIs, and connect the React problem list/workspace to real problem data.

**Architecture:** Raw third-party problem data is parsed only by a local preparation script into ignored JSONL seed files. The backend imports seed files into PostgreSQL tables and serves static problem data through FastAPI APIs. The frontend consumes those APIs through TanStack Query and does not display user-specific progress fields in this milestone.

**Tech Stack:** Python 3.12, uv, FastAPI, SQLAlchemy async, Alembic, PostgreSQL, React, TypeScript, TanStack Query, Ant Design, Vitest.

---

## Source Documents

- Spec: `docs/superpowers/specs/2026-05-19-problem-ingestion-design.md`
- Architecture: `docs/architecture/foundation.md`
- Makefile contract: `docs/architecture/makefile.md`
- Dev setup: `docs/dev-setup.md`
- Project index: `docs/index.md`

## File Structure

Create:

- `scripts/prepare_problem_seed.py` - local data preparation script that converts `fishjar/leetcode-problemset` into JSONL seed files.
- `backend/app/models/problem.py` - SQLAlchemy models for `problem`, `problem_category`, and `problem_category_item`.
- `backend/app/schemas/problem.py` - Pydantic response schemas for problem APIs.
- `backend/app/services/problem_seed.py` - seed file reader and idempotent database importer.
- `backend/app/services/problem_service.py` - database query helpers for problem list/detail/category APIs.
- `backend/app/api/problems.py` - FastAPI problem routes.
- `backend/app/cli/__init__.py` - CLI package marker.
- `backend/app/cli/problem_seed.py` - `make db-seed` command entrypoint.
- `backend/app/db/migrations/versions/20260519_0002_problem_library.py` - problem library database tables.
- `backend/tests/test_prepare_problem_seed.py` - seed preparation unit tests.
- `backend/tests/test_problem_seed.py` - seed import unit tests.
- `backend/tests/test_problems_api.py` - API route tests.
- `frontend/src/api/problems.ts` - frontend problem API client and types.
- `frontend/src/pages/ProblemLibraryPage.test.tsx` - problem list tests.
- `frontend/src/pages/WorkspacePage.test.tsx` - workspace detail tests.
- `data/seed/.gitkeep` - keeps seed directory present while ignoring generated data files.

Modify:

- `.gitignore` - ignore `data/sources/` and generated seed files.
- `Makefile` - add `prepare-problem-seed`, update `db-seed`.
- `backend/app/core/config.py` - add `problem_seed_path` and optional startup seed flag.
- `backend/app/main.py` - register problem API router.
- `infra/docker/backend.Dockerfile` - copy `data/seed/` into backend image when present.
- `frontend/src/routes/AppRoutes.tsx` - add `/workspace/:slug`.
- `frontend/src/pages/ProblemLibraryPage.tsx` - replace static row with API data and static filters.
- `frontend/src/pages/WorkspacePage.tsx` - load problem detail by slug and render statement.
- `frontend/src/styles/app.css` - add focused styles for filters, tags, and Markdown statement area.
- `docs/index.md` - document new problem modules and scripts.
- `docs/architecture/foundation.md` - document seed-file based problem data flow.
- `docs/architecture/docker.md` - document packaged seed behavior.
- `docs/architecture/makefile.md` - document `prepare-problem-seed` and real `db-seed`.
- `docs/dev-setup.md` - document local reference repo clone and seed workflow.
- `docs/prd/prd.md` - align problem table and category model with approved design.

---

### Task 1: Seed Preparation Script

**Files:**
- Create: `scripts/prepare_problem_seed.py`
- Create: `backend/tests/test_prepare_problem_seed.py`
- Modify: `.gitignore`
- Create: `data/seed/.gitkeep`

- [ ] **Step 1: Add failing tests for Markdown splitting and JSONL output**

Create `backend/tests/test_prepare_problem_seed.py`:

```python
import json
from pathlib import Path

from scripts.prepare_problem_seed import prepare_problem_seed, split_statement_markdown


def test_split_statement_markdown_removes_solution_section() -> None:
    markdown = "# Two Sum\n\nstatement\n\n## solution 题解\n\nanswer"

    result = split_statement_markdown(markdown)

    assert result.statement_md == "# Two Sum\n\nstatement"
    assert result.had_solution_section is True


def test_split_statement_markdown_keeps_full_text_without_solution() -> None:
    markdown = "# Title\n\nstatement only"

    result = split_statement_markdown(markdown)

    assert result.statement_md == markdown
    assert result.had_solution_section is False


def test_prepare_problem_seed_writes_static_problem_jsonl(tmp_path: Path) -> None:
    source = tmp_path / "leetcode-problemset"
    md_dir = source / "problemset_md"
    json_dir = source / "problemset"
    md_dir.mkdir(parents=True)
    json_dir.mkdir(parents=True)
    (source / ".git").mkdir()
    (source / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (md_dir / "0000001.two-sum.md").write_text(
        "# Two Sum 两数之和\n\n题面\n\n## solution 题解\n\n答案",
        encoding="utf-8",
    )
    (json_dir / "0000001.two-sum.json").write_text(
        json.dumps(
            {
                "data": {
                    "question": {
                        "questionFrontendId": "1",
                        "title": "Two Sum",
                        "translatedTitle": "两数之和",
                        "titleSlug": "two-sum",
                        "difficulty": "Easy",
                        "isPaidOnly": False,
                        "topicTags": [
                            {
                                "name": "Array",
                                "slug": "array",
                                "translatedName": "数组",
                            }
                        ],
                        "similarQuestions": "[]",
                        "codeSnippets": [
                            {
                                "langSlug": "python3",
                                "code": "class Solution:\n    def twoSum(self):",
                            }
                        ],
                        "sampleTestCase": "[2,7,11,15]\n9",
                        "metaData": "{\"name\":\"twoSum\"}",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "seed"

    stats = prepare_problem_seed(source, output)

    assert stats.problem_count == 1
    problem = json.loads((output / "problems.jsonl").read_text().splitlines()[0])
    assert problem["slug"] == "two-sum"
    assert problem["statement_md"] == "# Two Sum 两数之和\n\n题面"
    assert "solution" not in problem
    assert problem["metadata"]["python3_snippet"].startswith("class Solution")
    assert (output / "problem_categories.jsonl").read_text() == ""
    assert (output / "problem_category_items.jsonl").read_text() == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest backend/tests/test_prepare_problem_seed.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'scripts.prepare_problem_seed'`.

- [ ] **Step 3: Implement seed preparation script**

Create `scripts/prepare_problem_seed.py`:

```python
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SOLUTION_HEADING = "\n## solution 题解"


@dataclass(frozen=True)
class SplitMarkdownResult:
    statement_md: str
    had_solution_section: bool


@dataclass(frozen=True)
class PrepareStats:
    problem_count: int
    skipped_count: int


def split_statement_markdown(markdown: str) -> SplitMarkdownResult:
    index = markdown.find(SOLUTION_HEADING)
    if index < 0:
        return SplitMarkdownResult(markdown.rstrip(), False)
    return SplitMarkdownResult(markdown[:index].rstrip(), True)


def _source_commit(source_dir: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(source_dir), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def _question(json_path: Path) -> dict[str, Any]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    return payload["data"]["question"]


def _metadata(question: dict[str, Any]) -> dict[str, Any]:
    python3_snippet = ""
    for snippet in question.get("codeSnippets", []):
        if snippet.get("langSlug") == "python3":
            python3_snippet = snippet.get("code", "")
            break

    similar_questions = question.get("similarQuestions") or "[]"
    function_meta = question.get("metaData") or "{}"

    return {
        "topic_tags": [
            {
                "name": tag.get("name", ""),
                "slug": tag.get("slug", ""),
                "translated_name": tag.get("translatedName") or "",
            }
            for tag in question.get("topicTags", [])
        ],
        "similar_questions": json.loads(similar_questions),
        "sample_test_case": question.get("sampleTestCase") or "",
        "function_meta": json.loads(function_meta),
        "python3_snippet": python3_snippet,
    }


def _problem_record(md_path: Path, json_path: Path) -> dict[str, Any]:
    question = _question(json_path)
    split = split_statement_markdown(md_path.read_text(encoding="utf-8"))
    slug = question["titleSlug"]
    return {
        "frontend_id": question["questionFrontendId"],
        "slug": slug,
        "title": question["title"],
        "translated_title": question.get("translatedTitle") or "",
        "difficulty": question["difficulty"],
        "statement_md": split.statement_md,
        "leetcode_url": f"https://leetcode-cn.com/problems/{slug}/",
        "is_paid_only": bool(question.get("isPaidOnly", False)),
        "metadata": _metadata(question),
    }


def prepare_problem_seed(source_dir: Path, output_dir: Path) -> PrepareStats:
    md_dir = source_dir / "problemset_md"
    json_dir = source_dir / "problemset"
    if not md_dir.exists() or not json_dir.exists():
        raise FileNotFoundError(
            f"Expected problemset_md and problemset under {source_dir}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    skipped_count = 0
    for md_path in sorted(md_dir.glob("*.md")):
        json_path = json_dir / f"{md_path.stem}.json"
        if not json_path.exists():
            skipped_count += 1
            continue
        records.append(_problem_record(md_path, json_path))

    with (output_dir / "problems.jsonl").open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    (output_dir / "problem_categories.jsonl").write_text("", encoding="utf-8")
    (output_dir / "problem_category_items.jsonl").write_text("", encoding="utf-8")
    manifest = {
        "dataset": "leetcode-problemset",
        "source_repo": "https://github.com/fishjar/leetcode-problemset",
        "source_commit": _source_commit(source_dir),
        "generated_at": datetime.now(UTC).isoformat(),
        "problem_count": len(records),
        "category_count": 0,
        "category_item_count": 0,
        "schema_version": 1,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return PrepareStats(problem_count=len(records), skipped_count=skipped_count)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stats = prepare_problem_seed(args.source, args.output)
    print(f"Prepared {stats.problem_count} problems; skipped {stats.skipped_count}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Update ignored data paths**

Modify `.gitignore`:

```gitignore
# Local third-party datasets and generated seed data
data/sources/
data/seed/*.jsonl
data/seed/manifest.json
!data/seed/.gitkeep
```

Create `data/seed/.gitkeep` as an empty file.

- [ ] **Step 5: Run tests**

Run:

```bash
uv run pytest backend/tests/test_prepare_problem_seed.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add .gitignore data/seed/.gitkeep scripts/prepare_problem_seed.py backend/tests/test_prepare_problem_seed.py
git commit -m "feat: prepare problem seed data"
```

---

### Task 2: Database Models And Migration

**Files:**
- Create: `backend/app/models/problem.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/db/migrations/versions/20260519_0002_problem_library.py`
- Test: `backend/tests/test_problem_seed.py`

- [ ] **Step 1: Add model shape test**

Create `backend/tests/test_problem_seed.py` with the initial model assertion:

```python
from backend.app.models.problem import Problem, ProblemCategory, ProblemCategoryItem


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
    assert set(ProblemCategoryItem.__table__.columns.keys()) == {
        "id",
        "category_id",
        "problem_id",
        "sort_order",
        "created_at",
        "updated_at",
    }
```

- [ ] **Step 2: Run model test to verify failure**

Run:

```bash
uv run pytest backend/tests/test_problem_seed.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'backend.app.models.problem'`.

- [ ] **Step 3: Create SQLAlchemy models**

Create `backend/app/models/problem.py`:

```python
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Problem(Base):
    __tablename__ = "problem"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    frontend_id: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    translated_title: Mapped[str] = mapped_column(String(240), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    statement_md: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    leetcode_url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_paid_only: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    category_items: Mapped[list[ProblemCategoryItem]] = relationship(
        back_populates="problem",
        cascade="all, delete-orphan",
    )


class ProblemCategory(Base):
    __tablename__ = "problem_category"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    problem_items: Mapped[list[ProblemCategoryItem]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
    )


class ProblemCategoryItem(Base):
    __tablename__ = "problem_category_item"
    __table_args__ = (
        UniqueConstraint("category_id", "problem_id", name="uq_problem_category_item_category_problem"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("problem_category.id", ondelete="CASCADE"), nullable=False)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problem.id", ondelete="CASCADE"), nullable=False)
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    category: Mapped[ProblemCategory] = relationship(back_populates="problem_items")
    problem: Mapped[Problem] = relationship(back_populates="category_items")
```

Modify `backend/app/models/__init__.py`:

```python
from backend.app.models.problem import (
    Base,
    Problem,
    ProblemCategory,
    ProblemCategoryItem,
)

__all__ = ["Base", "Problem", "ProblemCategory", "ProblemCategoryItem"]
```

- [ ] **Step 4: Create Alembic migration**

Create `backend/app/db/migrations/versions/20260519_0002_problem_library.py`:

```python
"""create problem library tables

Revision ID: 20260519_0002
Revises: 20260519_0001
Create Date: 2026-05-19 00:00:00

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260519_0002"
down_revision: str | None = "20260519_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "problem",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("frontend_id", sa.String(length=40), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("translated_title", sa.String(length=240), nullable=False),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("statement_md", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("leetcode_url", sa.String(length=500), nullable=False),
        sa.Column("is_paid_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_problem_frontend_id", "problem", ["frontend_id"])
    op.create_unique_constraint("uq_problem_slug", "problem", ["slug"])
    op.create_index("ix_problem_difficulty", "problem", ["difficulty"])
    op.create_index("ix_problem_updated_at", "problem", ["updated_at"])

    op.create_table(
        "problem_category",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_problem_category_slug", "problem_category", ["slug"])

    op.create_table(
        "problem_category_item",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("category_id", sa.BigInteger(), sa.ForeignKey("problem_category.id", ondelete="CASCADE"), nullable=False),
        sa.Column("problem_id", sa.BigInteger(), sa.ForeignKey("problem.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("category_id", "problem_id", name="uq_problem_category_item_category_problem"),
    )
    op.create_index("ix_problem_category_item_category_order", "problem_category_item", ["category_id", "sort_order"])
    op.create_index("ix_problem_category_item_problem", "problem_category_item", ["problem_id"])


def downgrade() -> None:
    op.drop_index("ix_problem_category_item_problem", table_name="problem_category_item")
    op.drop_index("ix_problem_category_item_category_order", table_name="problem_category_item")
    op.drop_table("problem_category_item")
    op.drop_constraint("uq_problem_category_slug", "problem_category", type_="unique")
    op.drop_table("problem_category")
    op.drop_index("ix_problem_updated_at", table_name="problem")
    op.drop_index("ix_problem_difficulty", table_name="problem")
    op.drop_constraint("uq_problem_slug", "problem", type_="unique")
    op.drop_constraint("uq_problem_frontend_id", "problem", type_="unique")
    op.drop_table("problem")
```

- [ ] **Step 5: Run model tests**

Run:

```bash
uv run pytest backend/tests/test_problem_seed.py::test_problem_model_excludes_source_hash_and_solution_fields backend/tests/test_problem_seed.py::test_category_models_have_only_static_fields -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models backend/app/db/migrations/versions/20260519_0002_problem_library.py backend/tests/test_problem_seed.py
git commit -m "feat: add problem library schema"
```

---

### Task 3: Seed Import Service And Makefile Commands

**Files:**
- Create: `backend/app/services/problem_seed.py`
- Create: `backend/app/cli/__init__.py`
- Create: `backend/app/cli/problem_seed.py`
- Modify: `backend/app/core/config.py`
- Modify: `Makefile`
- Modify: `backend/tests/test_problem_seed.py`

- [ ] **Step 1: Add seed importer tests**

Append to `backend/tests/test_problem_seed.py`:

```python
import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from backend.app.models.problem import Base, Problem, ProblemCategory, ProblemCategoryItem
from backend.app.services.problem_seed import import_problem_seed


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
        await connection.run_sync(Base.metadata.create_all)
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
        '{"frontend_id":"1","slug":"two-sum","title":"Two Sum","translated_title":"两数之和","difficulty":"Easy","statement_md":"# Two Sum","leetcode_url":"https://leetcode-cn.com/problems/two-sum/","is_paid_only":false,"metadata":{"topic_tags":[]}}\n',
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
        await connection.run_sync(Base.metadata.create_all)
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
```

- [ ] **Step 2: Add sqlite test dependency**

Run:

```bash
uv add --dev aiosqlite
```

Expected: `pyproject.toml` and `uv.lock` update with `aiosqlite`.

- [ ] **Step 3: Run tests to verify importer missing**

Run:

```bash
uv run pytest backend/tests/test_problem_seed.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'backend.app.services.problem_seed'`.

- [ ] **Step 4: Implement seed importer**

Create `backend/app/services/problem_seed.py`:

```python
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
```

- [ ] **Step 5: Add config and CLI**

Modify `backend/app/core/config.py`:

```python
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "learning-coach-backend"
    environment: str = "local"
    api_prefix: str = "/api"
    database_url: str = (
        "postgresql+asyncpg://learning_coach:learning_coach"
        "@localhost:5432/learning_coach"
    )
    problem_seed_path: Path = Path("data/seed")
    seed_problems_on_startup: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
```

Create `backend/app/cli/__init__.py`:

```python
"""Command-line entrypoints for local maintenance tasks."""
```

Create `backend/app/cli/problem_seed.py`:

```python
from __future__ import annotations

import asyncio

from backend.app.core.config import settings
from backend.app.db.session import async_session_factory
from backend.app.services.problem_seed import import_problem_seed


async def _main() -> None:
    async with async_session_factory() as session:
        stats = await import_problem_seed(settings.problem_seed_path, session)
    print(
        "Problem seed import completed: "
        f"{stats.inserted_problems} problems, "
        f"{stats.inserted_categories} categories, "
        f"{stats.inserted_category_items} category items inserted"
    )


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Update Makefile commands**

Modify `Makefile`:

```make
.PHONY: prepare-problem-seed
prepare-problem-seed: ## Prepare local problem seed files from ignored source data
	uv run python scripts/prepare_problem_seed.py --source data/sources/leetcode-problemset --output data/seed

.PHONY: db-seed
db-seed: ## Import generated problem seed data into the database
	uv run python -m backend.app.cli.problem_seed
```

Ensure `make help` includes `prepare-problem-seed`.

- [ ] **Step 7: Run importer tests**

Run:

```bash
uv run pytest backend/tests/test_problem_seed.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock backend/app/core/config.py backend/app/services/problem_seed.py backend/app/cli Makefile backend/tests/test_problem_seed.py
git commit -m "feat: import problem seed data"
```

---

### Task 4: Problem API

**Files:**
- Create: `backend/app/schemas/problem.py`
- Create: `backend/app/services/problem_service.py`
- Create: `backend/app/api/problems.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_problems_api.py`

- [ ] **Step 1: Add API tests**

Create `backend/tests/test_problems_api.py`:

```python
from fastapi.testclient import TestClient

from backend.app.main import app


def test_problem_list_response_has_only_static_fields(monkeypatch) -> None:
    async def fake_list_problems(*args, **kwargs):
        return {
            "items": [
                {
                    "id": 1,
                    "frontend_id": "1",
                    "slug": "two-sum",
                    "title": "Two Sum",
                    "translated_title": "两数之和",
                    "difficulty": "Easy",
                    "tags": [],
                    "categories": [],
                }
            ],
            "total": 1,
            "page": 1,
            "page_size": 20,
        }

    monkeypatch.setattr(
        "backend.app.api.problems.list_problems",
        fake_list_problems,
    )
    client = TestClient(app)

    response = client.get("/api/problems")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["slug"] == "two-sum"
    assert "status" not in payload["items"][0]
    assert "avg_hint_level" not in payload["items"][0]


def test_problem_detail_does_not_return_solution(monkeypatch) -> None:
    async def fake_get_problem_detail(*args, **kwargs):
        return {
            "id": 1,
            "frontend_id": "1",
            "slug": "two-sum",
            "title": "Two Sum",
            "translated_title": "两数之和",
            "difficulty": "Easy",
            "statement_md": "# Two Sum",
            "leetcode_url": "https://leetcode-cn.com/problems/two-sum/",
            "tags": [],
            "categories": [],
            "sample_test_case": "[2,7,11,15]\n9",
            "python3_snippet": "class Solution:",
        }

    monkeypatch.setattr(
        "backend.app.api.problems.get_problem_detail",
        fake_get_problem_detail,
    )
    client = TestClient(app)

    response = client.get("/api/problems/two-sum")

    assert response.status_code == 200
    assert "solution_md" not in response.json()
```

- [ ] **Step 2: Run tests to verify route missing**

Run:

```bash
uv run pytest backend/tests/test_problems_api.py -q
```

Expected: fail because `backend.app.api.problems` does not exist or route returns `404`.

- [ ] **Step 3: Create schemas**

Create `backend/app/schemas/problem.py`:

```python
from pydantic import BaseModel


class ProblemTag(BaseModel):
    slug: str
    name: str
    translated_name: str


class ProblemCategorySummary(BaseModel):
    slug: str
    name: str
    description: str


class ProblemListItem(BaseModel):
    id: int
    frontend_id: str
    slug: str
    title: str
    translated_title: str
    difficulty: str
    tags: list[ProblemTag]
    categories: list[ProblemCategorySummary]


class ProblemListResponse(BaseModel):
    items: list[ProblemListItem]
    total: int
    page: int
    page_size: int


class ProblemDetailResponse(ProblemListItem):
    statement_md: str
    leetcode_url: str
    sample_test_case: str
    python3_snippet: str


class ProblemCategoryListResponse(BaseModel):
    items: list[ProblemCategorySummary]
```

- [ ] **Step 4: Create service**

Create `backend/app/services/problem_service.py` with query helpers:

```python
from __future__ import annotations

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

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


def _base_query() -> Select[tuple[Problem]]:
    return select(Problem)


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
    if tag:
        query = query.where(Problem.metadata_json["topic_tags"].as_string().contains(tag))
    if category:
        query = query.join(ProblemCategoryItem).join(ProblemCategory).where(
            ProblemCategory.slug == category
        )

    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    order_column = {
        "frontend_id": Problem.frontend_id,
        "difficulty": Problem.difficulty,
        "title": Problem.title,
    }.get(sort, Problem.frontend_id)
    result = await session.execute(
        query.order_by(order_column).offset((page - 1) * page_size).limit(page_size)
    )
    problems = result.scalars().all()
    return {
        "items": [
            {
                "id": problem.id,
                "frontend_id": problem.frontend_id,
                "slug": problem.slug,
                "title": problem.title,
                "translated_title": problem.translated_title,
                "difficulty": problem.difficulty,
                "tags": _tags(problem),
                "categories": _category_payload(problem.category_items),
            }
            for problem in problems
        ],
        "total": total or 0,
        "page": page,
        "page_size": page_size,
    }


async def get_problem_detail(session: AsyncSession, slug: str) -> dict | None:
    result = await session.execute(select(Problem).where(Problem.slug == slug))
    problem = result.scalar_one_or_none()
    if problem is None:
        return None
    return {
        "id": problem.id,
        "frontend_id": problem.frontend_id,
        "slug": problem.slug,
        "title": problem.title,
        "translated_title": problem.translated_title,
        "difficulty": problem.difficulty,
        "statement_md": problem.statement_md,
        "leetcode_url": problem.leetcode_url,
        "tags": _tags(problem),
        "categories": _category_payload(problem.category_items),
        "sample_test_case": problem.metadata_json.get("sample_test_case", ""),
        "python3_snippet": problem.metadata_json.get("python3_snippet", ""),
    }


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
```

- [ ] **Step 5: Create API router and register it**

Create `backend/app/api/problems.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_session
from backend.app.schemas.problem import (
    ProblemCategoryListResponse,
    ProblemDetailResponse,
    ProblemListResponse,
)
from backend.app.services.problem_service import (
    get_problem_detail,
    list_problem_categories,
    list_problems,
)


router = APIRouter()


@router.get("/problems", response_model=ProblemListResponse)
async def problem_list(
    keyword: str | None = None,
    difficulty: str | None = Query(default=None, pattern="^(Easy|Medium|Hard)$"),
    tag: str | None = None,
    category: str | None = None,
    sort: str = Query(default="frontend_id", pattern="^(frontend_id|difficulty|title)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await list_problems(
        session,
        keyword=keyword,
        difficulty=difficulty,
        tag=tag,
        category=category,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get("/problems/{slug}", response_model=ProblemDetailResponse)
async def problem_detail(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    problem = await get_problem_detail(session, slug)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    return problem


@router.get("/problem-categories", response_model=ProblemCategoryListResponse)
async def problem_categories(session: AsyncSession = Depends(get_session)) -> dict:
    return await list_problem_categories(session)
```

Modify `backend/app/main.py`:

```python
from backend.app.api.problems import router as problems_router

# inside create_app()
application.include_router(problems_router, prefix=settings.api_prefix)
```

- [ ] **Step 6: Run API tests**

Run:

```bash
uv run pytest backend/tests/test_problems_api.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/problems.py backend/app/main.py backend/app/schemas/problem.py backend/app/services/problem_service.py backend/tests/test_problems_api.py
git commit -m "feat: expose problem library api"
```

---

### Task 5: Frontend Problem Library And Workspace

**Files:**
- Create: `frontend/src/api/problems.ts`
- Modify: `frontend/src/pages/ProblemLibraryPage.tsx`
- Modify: `frontend/src/pages/WorkspacePage.tsx`
- Modify: `frontend/src/routes/AppRoutes.tsx`
- Modify: `frontend/src/styles/app.css`
- Create: `frontend/src/pages/ProblemLibraryPage.test.tsx`
- Create: `frontend/src/pages/WorkspacePage.test.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Add frontend page tests**

Create `frontend/src/pages/ProblemLibraryPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { ProblemLibraryPage } from './ProblemLibraryPage'

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ProblemLibraryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ProblemLibraryPage', () => {
  it('renders static problem fields from the API', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            items: [
              {
                id: 1,
                frontend_id: '1',
                slug: 'two-sum',
                title: 'Two Sum',
                translated_title: '两数之和',
                difficulty: 'Easy',
                tags: [{ slug: 'array', name: 'Array', translated_name: '数组' }],
                categories: [],
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )

    renderPage()

    expect(await screen.findByText('Two Sum')).toBeInTheDocument()
    expect(screen.getByText('两数之和')).toBeInTheDocument()
    expect(screen.getByText('数组')).toBeInTheDocument()
    expect(screen.queryByText('未开始')).not.toBeInTheDocument()
  })
})
```

Create `frontend/src/pages/WorkspacePage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { WorkspacePage } from './WorkspacePage'

describe('WorkspacePage', () => {
  it('renders problem statement and LeetCode link', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            id: 1,
            frontend_id: '1',
            slug: 'two-sum',
            title: 'Two Sum',
            translated_title: '两数之和',
            difficulty: 'Easy',
            statement_md: '# Two Sum\n\n题面内容',
            leetcode_url: 'https://leetcode-cn.com/problems/two-sum/',
            tags: [],
            categories: [],
            sample_test_case: '[2,7,11,15]\n9',
            python3_snippet: 'class Solution:',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/workspace/two-sum']}>
          <Routes>
            <Route path="/workspace/:slug" element={<WorkspacePage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByText('题面内容')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'LeetCode 原题' })).toHaveAttribute(
      'href',
      'https://leetcode-cn.com/problems/two-sum/',
    )
  })
})
```

- [ ] **Step 2: Run frontend tests to verify failure**

Run:

```bash
cd frontend && corepack pnpm test -- ProblemLibraryPage.test.tsx WorkspacePage.test.tsx
```

Expected: fail because `frontend/src/api/problems.ts` does not exist and pages still use static data.

- [ ] **Step 3: Add problem API client**

Create `frontend/src/api/problems.ts`:

```ts
import { requestJson } from './client'

export type ProblemTag = {
  slug: string
  name: string
  translated_name: string
}

export type ProblemCategorySummary = {
  slug: string
  name: string
  description: string
}

export type ProblemListItem = {
  id: number
  frontend_id: string
  slug: string
  title: string
  translated_title: string
  difficulty: 'Easy' | 'Medium' | 'Hard'
  tags: ProblemTag[]
  categories: ProblemCategorySummary[]
}

export type ProblemListResponse = {
  items: ProblemListItem[]
  total: number
  page: number
  page_size: number
}

export type ProblemDetail = ProblemListItem & {
  statement_md: string
  leetcode_url: string
  sample_test_case: string
  python3_snippet: string
}

export function getProblems(): Promise<ProblemListResponse> {
  return requestJson<ProblemListResponse>('/api/problems')
}

export function getProblem(slug: string): Promise<ProblemDetail> {
  return requestJson<ProblemDetail>(`/api/problems/${slug}`)
}
```

- [ ] **Step 4: Update routes**

Modify `frontend/src/routes/AppRoutes.tsx`:

```tsx
<Route path="/workspace" element={<WorkspacePage />} />
<Route path="/workspace/:slug" element={<WorkspacePage />} />
```

- [ ] **Step 5: Update problem list page**

Modify `frontend/src/pages/ProblemLibraryPage.tsx` to use `getProblems`, render title, difficulty, tags, categories, and a `Link` to `/workspace/${slug}`. Do not render user status, recent training time, or average hint level.

Use this column shape:

```tsx
{
  title: '标题',
  key: 'title',
  render: (_, row) => (
    <Link to={`/workspace/${row.slug}`}>
      <Space direction="vertical" size={0}>
        <span>{row.title}</span>
        <Typography.Text type="secondary">{row.translated_title}</Typography.Text>
      </Space>
    </Link>
  ),
}
```

- [ ] **Step 6: Update workspace page**

Modify `frontend/src/pages/WorkspacePage.tsx` to read `slug` from `useParams`, call `getProblem(slug)`, render `statement_md` in a pre-wrapped Markdown placeholder, and show the LeetCode link.

Use plain text rendering for Markdown in this task:

```tsx
<pre className="markdown-statement">{problem.statement_md}</pre>
```

Markdown renderer integration can be a later polish task if the project chooses a dependency.

- [ ] **Step 7: Add CSS**

Modify `frontend/src/styles/app.css`:

```css
.problem-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.markdown-statement {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: #243027;
  font: inherit;
}
```

- [ ] **Step 8: Run frontend tests**

Run:

```bash
cd frontend && corepack pnpm test
```

Expected: all frontend tests pass.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/api/problems.ts frontend/src/pages/ProblemLibraryPage.tsx frontend/src/pages/WorkspacePage.tsx frontend/src/pages/ProblemLibraryPage.test.tsx frontend/src/pages/WorkspacePage.test.tsx frontend/src/routes/AppRoutes.tsx frontend/src/styles/app.css frontend/src/App.test.tsx
git commit -m "feat: connect frontend to problem api"
```

---

### Task 6: Docker And Documentation Contracts

**Files:**
- Modify: `infra/docker/backend.Dockerfile`
- Modify: `docs/index.md`
- Modify: `docs/architecture/foundation.md`
- Modify: `docs/architecture/docker.md`
- Modify: `docs/architecture/makefile.md`
- Modify: `docs/dev-setup.md`
- Modify: `docs/prd/prd.md`

- [ ] **Step 1: Update backend Dockerfile**

Modify `infra/docker/backend.Dockerfile`:

```dockerfile
COPY backend ./backend
COPY scripts ./scripts
COPY data/seed ./data/seed
COPY alembic.ini ./alembic.ini
```

Keep `.dockerignore` from ignoring `data/seed`.

- [ ] **Step 2: Update docs/index.md**

Add or revise directory responsibilities:

```markdown
- `backend/app/api/problems.py`：题库列表、分类列表和题目详情 API。
- `backend/app/services/problem_seed.py`：从结构化 seed 文件导入题库数据。
- `scripts/prepare_problem_seed.py`：把本地忽略的第三方题库仓库清洗为 JSONL seed 文件。
- `data/sources/`：本地第三方原始题库目录，必须忽略不提交。
- `data/seed/`：本地生成的题库 seed 文件目录，题面数据默认不提交公开仓库。
```

- [ ] **Step 3: Update Makefile docs**

In `docs/architecture/makefile.md`, replace the placeholder `db-seed` section with:

```markdown
### `make prepare-problem-seed`

从 `data/sources/leetcode-problemset` 读取本地参考仓库，生成 `data/seed/problems.jsonl`、`data/seed/problem_categories.jsonl`、`data/seed/problem_category_items.jsonl` 和 `data/seed/manifest.json`。

成功标准：

- 原始参考仓库存在。
- seed 文件生成成功。
- 生成的题目 seed 不包含题解内容。

### `make db-seed`

从 `data/seed/` 导入题库基础数据。

成功标准：

- `problem` 表存在。
- seed 文件存在。
- 重复执行不会产生重复题目。
```

- [ ] **Step 4: Update dev setup docs**

In `docs/dev-setup.md`, add the workflow:

```bash
mkdir -p data/sources
git clone https://github.com/fishjar/leetcode-problemset.git data/sources/leetcode-problemset
make prepare-problem-seed
make db-migrate
make db-seed
```

State that `data/sources/` and generated seed files are local/private data and should not be committed publicly.

- [ ] **Step 5: Update PRD table design**

In `docs/prd/prd.md`, replace `is_hot100` / `hot100_order` in the problem table section with:

```text
problem_category
- id
- slug
- name
- description
- created_at
- updated_at

problem_category_item
- id
- category_id
- problem_id
- sort_order
- created_at
- updated_at
```

State that first-version problem browsing is static and does not include user progress fields until `practice_session` exists.

- [ ] **Step 6: Run full verification**

Run:

```bash
uv run ruff check .
uv run mypy backend
uv run pytest -q
cd frontend && corepack pnpm lint
cd frontend && corepack pnpm test
cd frontend && corepack pnpm build
```

Expected: all commands pass. Vite chunk-size warnings are acceptable if build exits with code 0.

- [ ] **Step 7: Commit**

```bash
git add infra/docker/backend.Dockerfile docs/index.md docs/architecture/foundation.md docs/architecture/docker.md docs/architecture/makefile.md docs/dev-setup.md docs/prd/prd.md
git commit -m "docs: document problem seed workflow"
```

---

## Self-Review Notes

- Spec coverage: Tasks cover local data preparation, seed import, schema, APIs, frontend static problem display, Docker packaging, and documentation maintenance.
- User progress fields: The plan explicitly excludes `status`, `last_practiced_at`, and `avg_hint_level` from the first problem list API and frontend page.
- Category model: Classification is optional; empty category seed files produce no default category data.
- Solution leakage: The preparation script drops the solution section and the database has no `solution_md` column.
- Verification: Each task has focused tests plus final backend/frontend build verification.
