from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import backend.app.models.rag  # noqa: F401
import backend.app.models.trace  # noqa: F401
from backend.app.models.problem import Base
from backend.app.models.rag import KnowledgeChunk, KnowledgeDoc, stable_chunk_uid
from backend.app.models.trace import RetrievalTrace
from backend.app.rag.embedding import FakeEmbeddingProvider
from backend.app.rag.retrieval import RetrievalRequest, RetrievalService
from backend.app.rag.tracing import write_retrieval_trace


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _add_doc(db_session: AsyncSession) -> KnowledgeDoc:
    doc = KnowledgeDoc(
        source_name="manual-two-sum",
        source_type="manual_cards",
        language="zh",
        priority="P0",
        main_usage_json=["pattern_card", "common_bug_card", "hint_card"],
        local_path="cards/two-sum.jsonl",
        license_note="本地人工整理",
        content_hash="doc-hash",
        metadata_json={},
    )
    db_session.add(doc)
    await db_session.flush()
    return doc


async def _add_chunk(
    db_session: AsyncSession,
    doc: KnowledgeDoc,
    *,
    title: str,
    knowledge_type: str,
    problem_slug: str | None = "two-sum",
    problem_tags: list[str] | None = None,
    phases: list[str] | None = None,
    hint_level_min: int = 0,
    hint_level_max: int = 3,
    has_full_solution: bool = False,
    quality_score: float = 0.9,
) -> KnowledgeChunk:
    content_hash = f"hash-{title}"
    chunk = KnowledgeChunk(
        doc_id=doc.id,
        chunk_uid=stable_chunk_uid(
            source_name=doc.source_name,
            source_locator=title,
            title=title,
            content_hash=content_hash,
        ),
        chunk_kind="coach_card",
        knowledge_type=knowledge_type,
        title=title,
        summary_md=f"{title} summary",
        content_md=f"{title} content",
        source_locator=title,
        problem_slug=problem_slug,
        problem_tags_json=problem_tags or ["hash-table"],
        phases_json=phases or [],
        stuck_points_json=[],
        hint_level_min=hint_level_min,
        hint_level_max=hint_level_max,
        has_full_solution=has_full_solution,
        language="zh",
        quality_score=quality_score,
        embedding=[0.1, 0.2, 0.3, 0.4],
        embedding_model="fake-4",
        content_hash=content_hash,
        metadata_json={},
    )
    db_session.add(chunk)
    await db_session.flush()
    return chunk


def _request(**overrides: object) -> RetrievalRequest:
    payload: dict[str, Any] = {
        "user_id": 1,
        "session_id": 10,
        "problem_slug": "two-sum",
        "problem_tags": ["hash-table"],
        "phase": "review_code",
        "hint_level": "questioning",
        "stuck_point": "edge_case_missing",
        "retrieval_intent": "code_review",
        "query_summary": "用户代码可能重复使用同一元素",
        "top_k": 3,
    }
    payload.update(overrides)
    return RetrievalRequest(**payload)


@pytest.mark.asyncio
async def test_retrieval_filters_full_solution_at_low_hint_level(
    db_session: AsyncSession,
) -> None:
    doc = await _add_doc(db_session)
    safe = await _add_chunk(
        db_session,
        doc,
        title="安全方向",
        knowledge_type="pattern_card",
        hint_level_max=1,
    )
    blocked = await _add_chunk(
        db_session,
        doc,
        title="完整题解",
        knowledge_type="hint_card",
        has_full_solution=True,
        hint_level_min=0,
        hint_level_max=3,
    )

    result = await RetrievalService(
        db_session,
        embedding_provider=FakeEmbeddingProvider(dimensions=4),
    ).retrieve_for_coach(_request())

    assert result.status == "used"
    assert [chunk.chunk_id for chunk in result.selected_chunks] == [safe.id]
    assert {"chunk_id": blocked.id, "reason": "full_solution_blocked"} in [
        {"chunk_id": item.chunk_id, "reason": item.reason}
        for item in result.filtered_chunks
    ]


@pytest.mark.asyncio
async def test_review_code_prefers_common_bug_cards(db_session: AsyncSession) -> None:
    doc = await _add_doc(db_session)
    await _add_chunk(db_session, doc, title="题型方向", knowledge_type="pattern_card")
    bug = await _add_chunk(
        db_session,
        doc,
        title="查询写入顺序",
        knowledge_type="common_bug_card",
        phases=["review_code"],
    )

    result = await RetrievalService(db_session).retrieve_for_coach(_request())

    assert result.status == "used"
    assert result.selected_chunks[0].chunk_id == bug.id


@pytest.mark.asyncio
async def test_problem_exact_match_outranks_tag_only_match(
    db_session: AsyncSession,
) -> None:
    doc = await _add_doc(db_session)
    await _add_chunk(
        db_session,
        doc,
        title="通用哈希表",
        knowledge_type="pattern_card",
        problem_slug=None,
        problem_tags=["hash-table"],
    )
    exact = await _add_chunk(
        db_session,
        doc,
        title="Two Sum 专用",
        knowledge_type="pattern_card",
        problem_slug="two-sum",
        problem_tags=["hash-table"],
    )

    result = await RetrievalService(db_session).retrieve_for_coach(
        _request(retrieval_intent="pattern_direction", phase="think_solution"),
    )

    assert result.status == "used"
    assert result.selected_chunks[0].chunk_id == exact.id


@pytest.mark.asyncio
async def test_retrieval_returns_no_match_for_low_quality_only(
    db_session: AsyncSession,
) -> None:
    doc = await _add_doc(db_session)
    await _add_chunk(
        db_session,
        doc,
        title="低质量卡片",
        knowledge_type="pattern_card",
        quality_score=0.2,
    )

    result = await RetrievalService(db_session).retrieve_for_coach(_request())

    assert result.status == "no_match"
    assert result.selected_chunks == []


@pytest.mark.asyncio
async def test_retrieval_trace_records_summary_ids_and_filter_reasons(
    db_session: AsyncSession,
) -> None:
    doc = await _add_doc(db_session)
    safe = await _add_chunk(
        db_session,
        doc,
        title="安全方向",
        knowledge_type="pattern_card",
        hint_level_max=1,
    )
    blocked = await _add_chunk(
        db_session,
        doc,
        title="完整题解",
        knowledge_type="hint_card",
        has_full_solution=True,
        hint_level_min=0,
        hint_level_max=3,
    )
    request = _request(query_summary="用户说代码在重复元素用例上 WA，不保存完整代码")
    result = await RetrievalService(db_session).retrieve_for_coach(request)

    trace = await write_retrieval_trace(
        db_session,
        request=request,
        result=result,
        used_in_prompt=True,
    )

    assert isinstance(trace, RetrievalTrace)
    assert trace.query == "用户说代码在重复元素用例上 WA，不保存完整代码"
    assert trace.retrieval_intent == "code_review"
    assert trace.current_hint_level == 0
    assert trace.selected_chunk_ids == [safe.id]
    assert trace.filtered_out_chunk_ids == [
        {"chunk_id": blocked.id, "reason": "full_solution_blocked"}
    ]
    assert trace.used_in_prompt is True
