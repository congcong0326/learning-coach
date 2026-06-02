from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.trace import RetrievalTrace
from backend.app.rag.retrieval import HINT_LEVEL_INDEX, RetrievalRequest, RetrievalResult

logger = logging.getLogger(__name__)

_MAX_QUERY_LENGTH = 480


async def write_retrieval_trace(
    session: AsyncSession,
    *,
    request: RetrievalRequest,
    result: RetrievalResult,
    used_in_prompt: bool,
) -> RetrievalTrace:
    trace = RetrievalTrace(
        session_id=str(request.session_id),
        problem_slug=request.problem_slug,
        query=_safe_query_summary(request.query_summary),
        retrieved_doc_ids=result.candidate_chunk_ids,
        selected_chunk_ids=[chunk.chunk_id for chunk in result.selected_chunks],
        current_hint_level=HINT_LEVEL_INDEX.get(request.hint_level),
        retrieval_intent=request.retrieval_intent,
        filtered_out_chunk_ids=[
            {"chunk_id": item.chunk_id, "reason": item.reason}
            for item in result.filtered_chunks
        ],
        used_in_prompt=used_in_prompt,
        created_at=datetime.now(UTC),
    )
    session.add(trace)
    await session.flush()
    logger.info(
        "retrieval_trace_appended session_id=%s problem_slug=%s status=%s selected=%s",
        trace.session_id,
        trace.problem_slug,
        result.status,
        len(result.selected_chunks),
    )
    return trace


def _safe_query_summary(value: str) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= _MAX_QUERY_LENGTH:
        return normalized
    return normalized[:_MAX_QUERY_LENGTH] + "..."
