from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.trace import AgentTrace

logger = logging.getLogger(__name__)

_HINT_LEVEL_INDEX = {
    "questioning": 0,
    "direction": 1,
    "key_hint": 2,
    "reflection": 3,
}
_MAX_TRACE_STRING_LENGTH = 480
_MAX_TRACE_LIST_LENGTH = 16
_MAX_TRACE_DICT_KEYS = 32
_MAX_TRACE_DEPTH = 4


async def append_agent_trace(
    session: AsyncSession,
    *,
    session_id: str | int | None = None,
    thread_id: str | None = None,
    problem_slug: str | None = None,
    node_name: str,
    phase: str | None = None,
    prompt_version: str | None = None,
    model_name: str | None = None,
    hint_level: str | int | None = None,
    input_summary: dict[str, Any] | None = None,
    output_summary: dict[str, Any] | None = None,
    latency_ms: int | None = None,
    stuck_point: str | None = None,
    should_reveal_solution: bool | None = None,
    error_summary: str | None = None,
) -> AgentTrace:
    sanitized_input = _sanitize_trace_value(input_summary or {})
    sanitized_output = _sanitize_trace_value(output_summary or {})
    tool_calls: dict[str, Any] = {
        "input_summary": sanitized_input,
        "output_summary": sanitized_output,
    }
    if error_summary:
        tool_calls["error_summary"] = _sanitize_trace_value(error_summary)
    trace = AgentTrace(
        session_id=str(session_id) if session_id is not None else None,
        thread_id=thread_id,
        problem_slug=problem_slug,
        node_name=node_name,
        phase=phase,
        prompt_version=prompt_version,
        model_name=model_name,
        input_tokens=None,
        output_tokens=None,
        latency_ms=latency_ms,
        retrieved_chunk_ids=[],
        tool_calls=tool_calls,
        hint_level=_hint_level_to_index(hint_level),
        stuck_point=(stuck_point or "")[:80] or None,
        should_reveal_solution=should_reveal_solution,
        created_at=datetime.now(UTC),
    )
    session.add(trace)
    await session.flush()
    logger.info(
        "agent_trace_appended session_id=%s thread_id=%s node=%s phase=%s",
        trace.session_id,
        trace.thread_id,
        trace.node_name,
        trace.phase,
    )
    return trace


async def list_agent_traces(
    session: AsyncSession,
    *,
    session_id: str | int | None = None,
    session_ids: list[str | int] | None = None,
    limit: int = 100,
) -> list[AgentTrace]:
    normalized_limit = min(max(limit, 1), 200)
    statement = select(AgentTrace).order_by(AgentTrace.created_at, AgentTrace.id)
    if session_id is not None:
        statement = statement.where(AgentTrace.session_id == str(session_id))
    elif session_ids is not None:
        normalized_ids = [str(item) for item in session_ids]
        if not normalized_ids:
            return []
        statement = statement.where(AgentTrace.session_id.in_(normalized_ids))
    result = await session.execute(statement.limit(normalized_limit))
    return list(result.scalars().all())


def _hint_level_to_index(value: str | int | None) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return _HINT_LEVEL_INDEX.get(value)
    return None


def _sanitize_trace_value(value: Any, *, depth: int = 0) -> Any:
    if depth > _MAX_TRACE_DEPTH:
        return "<max_depth>"
    if isinstance(value, str):
        if len(value) <= _MAX_TRACE_STRING_LENGTH:
            return value
        return value[:_MAX_TRACE_STRING_LENGTH] + "..."
    if isinstance(value, int | float | bool) or value is None:
        return value
    if isinstance(value, list):
        return [
            _sanitize_trace_value(item, depth=depth + 1)
            for item in value[:_MAX_TRACE_LIST_LENGTH]
        ]
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in list(value.items())[:_MAX_TRACE_DICT_KEYS]:
            sanitized[str(key)[:80]] = _sanitize_trace_value(item, depth=depth + 1)
        return sanitized
    return str(value)[:_MAX_TRACE_STRING_LENGTH]
