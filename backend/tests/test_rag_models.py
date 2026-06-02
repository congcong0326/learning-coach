from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import backend.app.models.rag  # noqa: F401
from backend.app.models.problem import Base
from backend.app.models.rag import KnowledgeChunk, KnowledgeDoc, stable_chunk_uid


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_knowledge_models_store_required_metadata(
    db_session: AsyncSession,
) -> None:
    chunk_uid = stable_chunk_uid(
        source_name="manual-two-sum",
        source_locator="cards.jsonl:1",
        title="哈希表顺序",
        content_hash="abc123",
    )
    assert chunk_uid == stable_chunk_uid(
        source_name="manual-two-sum",
        source_locator="cards.jsonl:1",
        title="哈希表顺序",
        content_hash="abc123",
    )

    doc = KnowledgeDoc(
        source_name="manual-two-sum",
        source_type="manual_cards",
        language="zh",
        priority="P0",
        main_usage_json=["pattern_card", "common_bug_card"],
        local_path="data/sources/rag/two-sum.jsonl",
        license_note="本地人工整理",
        content_hash="doc-hash",
        metadata_json={"notes": "fixture"},
    )
    db_session.add(doc)
    await db_session.flush()

    chunk = KnowledgeChunk(
        doc_id=doc.id,
        chunk_uid=chunk_uid,
        chunk_kind="coach_card",
        knowledge_type="common_bug_card",
        title="哈希表顺序",
        summary_md="Two Sum 中应先查询 complement，再写入当前元素。",
        content_md="避免把当前元素和自己配对。",
        source_locator="cards.jsonl:1",
        problem_slug="two-sum",
        problem_tags_json=["hash-table", "array"],
        difficulty="easy",
        phases_json=["review_code"],
        stuck_points_json=["edge_case_missing"],
        hint_level_min=0,
        hint_level_max=2,
        has_full_solution=False,
        language="zh",
        quality_score=0.95,
        embedding=[0.1, 0.2, 0.3, 0.4],
        embedding_model="fake-4",
        content_hash="chunk-hash",
        metadata_json={"card_source": "manual"},
    )
    db_session.add(chunk)
    await db_session.flush()

    assert doc.id is not None
    assert chunk.id is not None
    assert chunk.doc_id == doc.id
    assert chunk.hint_level_min == 0
    assert chunk.hint_level_max == 2
    assert chunk.has_full_solution is False
    assert chunk.quality_score == 0.95
    assert chunk.chunk_uid == chunk_uid
