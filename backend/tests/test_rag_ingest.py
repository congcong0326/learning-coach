from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import backend.app.models.rag  # noqa: F401
from backend.app.models.problem import Base
from backend.app.models.rag import KnowledgeChunk, KnowledgeDoc
from backend.app.rag.embedding import FakeEmbeddingProvider
from backend.app.rag.ingest import chunk_markdown_text, ingest_manifest
from backend.app.rag.manifest import load_source_manifest


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _write_manifest(tmp_path: Path, local_path: str) -> Path:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "source_name": "manual-two-sum",
                "source_type": "manual_cards",
                "language": "zh",
                "priority": "P0",
                "main_usage": ["pattern_card", "common_bug_card", "hint_card"],
                "local_path": local_path,
                "license_note": "本地人工整理",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return manifest_path


@pytest.mark.asyncio
async def test_ingest_manual_cards_is_idempotent_and_preserves_metadata(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    cards_path = cards_dir / "two-sum.jsonl"
    cards = [
        {
            "knowledge_type": "pattern_card",
            "title": "Two Sum 识别信号",
            "summary_md": "看到目标和与下标，优先考虑哈希表记录已见元素。",
            "content_md": "训练重点是先说出 complement，再说明不能复用同一元素。",
            "source_locator": "cards.jsonl:1",
            "problem_slug": "two-sum",
            "problem_tags": ["hash-table", "array"],
            "phases": ["understand_problem", "think_solution"],
            "hint_level_min": 0,
            "hint_level_max": 1,
            "has_full_solution": False,
            "quality_score": 0.9,
        },
        {
            "knowledge_type": "common_bug_card",
            "title": "查询和写入顺序",
            "summary_md": "先查 complement 再写入当前元素，避免同一位置被用两次。",
            "content_md": "如果先写入当前值，nums=[3,3] 这类用例可能暴露问题。",
            "source_locator": "cards.jsonl:2",
            "problem_slug": "two-sum",
            "problem_tags": ["hash-table"],
            "phases": ["review_code"],
            "hint_level_min": 0,
            "hint_level_max": 2,
            "has_full_solution": False,
            "quality_score": 0.95,
        },
        {
            "knowledge_type": "hint_card",
            "title": "完整复盘思路",
            "summary_md": "复盘时可以讲完整哈希表流程。",
            "content_md": "包含完整流程，因此低提示档不能注入。",
            "source_locator": "cards.jsonl:3",
            "problem_slug": "two-sum",
            "problem_tags": ["hash-table"],
            "phases": ["summarize"],
            "hint_level_min": 3,
            "hint_level_max": 3,
            "has_full_solution": True,
            "quality_score": 0.85,
        },
    ]
    cards_path.write_text(
        "\n".join(json.dumps(card, ensure_ascii=False) for card in cards),
        encoding="utf-8",
    )
    manifest = load_source_manifest(_write_manifest(tmp_path, "cards/two-sum.jsonl"))

    summary = await ingest_manifest(
        db_session,
        manifest=manifest,
        root_dir=tmp_path,
        embedding_provider=FakeEmbeddingProvider(dimensions=4),
    )
    second_summary = await ingest_manifest(
        db_session,
        manifest=manifest,
        root_dir=tmp_path,
        embedding_provider=FakeEmbeddingProvider(dimensions=4),
    )

    assert summary.chunks_upserted == 3
    assert second_summary.chunks_upserted == 3
    doc_count = await db_session.scalar(select(func.count(KnowledgeDoc.id)))
    chunk_count = await db_session.scalar(select(func.count(KnowledgeChunk.id)))
    assert doc_count == 1
    assert chunk_count == 3

    chunk = await db_session.scalar(
        select(KnowledgeChunk).where(KnowledgeChunk.knowledge_type == "common_bug_card")
    )
    assert chunk is not None
    assert chunk.problem_tags_json == ["hash-table"]
    expected_embedding = await FakeEmbeddingProvider(dimensions=4).embed(
        [f"{chunk.title}\n{chunk.summary_md}"]
    )
    assert chunk.embedding == expected_embedding[0]
    assert chunk.has_full_solution is False


def test_chunk_markdown_text_uses_safe_defaults_and_heading_locators() -> None:
    text = """# Hash Table

Two Sum 常见训练点。

```python
def two_sum(nums, target):
    return []
```

## Common Bug

先写入当前元素再查询 complement，会影响重复元素用例。
"""

    chunks = chunk_markdown_text(
        source_name="manual-markdown",
        text=text,
        source_locator="hash-table.md",
        language="zh",
        chunk_size=120,
    )

    assert len(chunks) >= 2
    assert chunks[0].source_locator == "hash-table.md#Hash Table"
    assert chunks[0].chunk_kind == "source_chunk"
    assert chunks[0].has_full_solution is True
    assert chunks[0].hint_level_min == 3
    assert chunks[0].hint_level_max == 3
    assert "\n\n\n" not in chunks[0].content_md
    assert any(chunk.source_locator.endswith("#Common Bug") for chunk in chunks)
