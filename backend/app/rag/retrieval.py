from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field, replace
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.rag import KnowledgeChunk, KnowledgeDoc
from backend.app.rag.embedding import EmbeddingProvider

logger = logging.getLogger(__name__)

HINT_LEVEL_INDEX = {
    "questioning": 0,
    "direction": 1,
    "key_hint": 2,
    "reflection": 3,
}
RetrievalStatus = Literal["used", "no_match", "filtered_empty", "error"]


@dataclass(frozen=True)
class RetrievalRequest:
    user_id: int
    session_id: int
    problem_slug: str
    problem_tags: list[str]
    phase: str
    hint_level: str
    stuck_point: str
    retrieval_intent: str
    query_summary: str
    top_k: int = 5


@dataclass(frozen=True)
class SelectedChunk:
    chunk_id: int
    chunk_uid: str
    knowledge_type: str
    title: str
    summary_md: str
    source_name: str


@dataclass(frozen=True)
class FilteredChunk:
    chunk_id: int
    reason: str


@dataclass(frozen=True)
class RetrievalResult:
    status: RetrievalStatus
    selected_chunks: list[SelectedChunk] = field(default_factory=list)
    candidate_chunk_ids: list[int] = field(default_factory=list)
    filtered_chunks: list[FilteredChunk] = field(default_factory=list)
    trace_id: int | None = None
    prompt_context_md: str = ""
    error_summary: str = ""

    def as_graph_context(self) -> dict[str, object]:
        return {
            "status": self.status,
            "trace_id": self.trace_id,
            "chunks": [chunk.__dict__ for chunk in self.selected_chunks],
            "filtered": [chunk.__dict__ for chunk in self.filtered_chunks],
            "candidate_chunk_ids": self.candidate_chunk_ids,
            "prompt_context_md": self.prompt_context_md,
            "error_summary": self.error_summary,
        }


class RetrievalService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        quality_threshold: float = 0.6,
    ) -> None:
        self._session = session
        self._embedding_provider = embedding_provider
        self._quality_threshold = quality_threshold

    async def retrieve_for_coach(self, request: RetrievalRequest) -> RetrievalResult:
        try:
            result = await self._retrieve(request)
            from backend.app.rag.tracing import write_retrieval_trace

            trace = await write_retrieval_trace(
                self._session,
                request=request,
                result=result,
                used_in_prompt=result.status == "used",
            )
            result = replace(result, trace_id=trace.id)
        except Exception as exc:
            logger.warning(
                "rag_retrieval_failed user_id=%s session_id=%s problem_slug=%s "
                "error_type=%s",
                request.user_id,
                request.session_id,
                request.problem_slug,
                type(exc).__name__,
            )
            return RetrievalResult(status="error", error_summary=type(exc).__name__)
        logger.info(
            "rag_retrieval_completed user_id=%s session_id=%s problem_slug=%s "
            "status=%s selected=%s filtered=%s",
            request.user_id,
            request.session_id,
            request.problem_slug,
            result.status,
            len(result.selected_chunks),
            len(result.filtered_chunks),
        )
        return result

    async def _retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        rows = await self._session.execute(
            select(KnowledgeChunk, KnowledgeDoc)
            .join(KnowledgeDoc, KnowledgeDoc.id == KnowledgeChunk.doc_id)
            .where(
                KnowledgeDoc.status == "active",
                KnowledgeChunk.quality_score >= self._quality_threshold,
            )
        )
        candidates = list(rows.all())
        if not candidates:
            return RetrievalResult(status="no_match")
        candidate_ids = [chunk.id for chunk, _doc in candidates]
        hint_index = HINT_LEVEL_INDEX.get(request.hint_level, 0)
        filtered: list[FilteredChunk] = []
        usable: list[tuple[KnowledgeChunk, KnowledgeDoc]] = []
        for chunk, doc in candidates:
            reason = _filter_reason(chunk, request=request, hint_index=hint_index)
            if reason:
                filtered.append(FilteredChunk(chunk_id=chunk.id, reason=reason))
                continue
            usable.append((chunk, doc))
        if not usable:
            return RetrievalResult(
                status="filtered_empty",
                candidate_chunk_ids=candidate_ids,
                filtered_chunks=filtered,
            )
        query_embedding: list[float] | None = None
        if self._embedding_provider is not None:
            embedded = await self._embedding_provider.embed([request.query_summary])
            query_embedding = embedded[0] if embedded else None
        ranked = sorted(
            usable,
            key=lambda item: _score_chunk(
                item[0],
                request=request,
                query_embedding=query_embedding,
            ),
            reverse=True,
        )
        selected = [
            SelectedChunk(
                chunk_id=chunk.id,
                chunk_uid=chunk.chunk_uid,
                knowledge_type=chunk.knowledge_type,
                title=chunk.title,
                summary_md=chunk.summary_md,
                source_name=doc.source_name,
            )
            for chunk, doc in ranked[: max(1, min(request.top_k, 5))]
        ]
        return RetrievalResult(
            status="used",
            selected_chunks=selected,
            candidate_chunk_ids=candidate_ids,
            filtered_chunks=filtered,
            prompt_context_md=_prompt_context(selected),
        )


def _filter_reason(
    chunk: KnowledgeChunk,
    *,
    request: RetrievalRequest,
    hint_index: int,
) -> str | None:
    if hint_index < chunk.hint_level_min or hint_index > chunk.hint_level_max:
        return "hint_level_blocked"
    if hint_index < HINT_LEVEL_INDEX["reflection"] and chunk.has_full_solution:
        return "full_solution_blocked"
    phases = _string_list(chunk.phases_json)
    if phases and request.phase not in phases:
        return "phase_mismatch"
    return None


def _score_chunk(
    chunk: KnowledgeChunk,
    *,
    request: RetrievalRequest,
    query_embedding: list[float] | None,
) -> float:
    score = float(chunk.quality_score)
    if chunk.problem_slug == request.problem_slug:
        score += 100.0
    elif chunk.problem_slug:
        score -= 20.0
    tags = set(_string_list(chunk.problem_tags_json))
    request_tags = set(request.problem_tags)
    score += len(tags & request_tags) * 10.0
    if request.phase in _string_list(chunk.phases_json):
        score += 8.0
    if request.stuck_point and request.stuck_point in _string_list(chunk.stuck_points_json):
        score += 4.0
    if request.retrieval_intent == "code_review" and chunk.knowledge_type in {
        "common_bug_card",
        "invariant_card",
    }:
        score += 25.0
    if request.retrieval_intent == "pattern_direction" and chunk.knowledge_type in {
        "pattern_card",
        "problem_coach_card",
    }:
        score += 15.0
    if query_embedding is not None and chunk.embedding:
        score += _cosine(query_embedding, chunk.embedding)
    return score


def _prompt_context(chunks: list[SelectedChunk]) -> str:
    if not chunks:
        return ""
    lines = [
        "RAG 教练知识只作为提示依据，不能绕过当前提示档位和 coach_guard。",
    ]
    for chunk in chunks:
        lines.append(
            f"- [{chunk.chunk_id}] {chunk.knowledge_type} / {chunk.title}: "
            f"{chunk.summary_md}",
        )
    return "\n".join(lines)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _cosine(left: list[float], right: list[float]) -> float:
    size = min(len(left), len(right))
    if size == 0:
        return 0.0
    dot = sum(left[index] * right[index] for index in range(size))
    left_norm = math.sqrt(sum(left[index] ** 2 for index in range(size)))
    right_norm = math.sqrt(sum(right[index] ** 2 for index in range(size)))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)
