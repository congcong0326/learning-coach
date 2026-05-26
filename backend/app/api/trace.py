from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.auth import current_user_dependency
from backend.app.db.session import get_session
from backend.app.models.auth import AppUser
from backend.app.models.practice import PracticeSession
from backend.app.models.trace import AgentTrace
from backend.app.schemas.trace import AgentTraceResponse
from backend.app.services.agent_trace_service import list_agent_traces

router = APIRouter(tags=["trace"])


@router.get("/traces", response_model=list[AgentTraceResponse])
async def list_agent_traces_route(
    session_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> list[AgentTraceResponse]:
    if session_id is not None:
        result = await session.execute(
            select(PracticeSession.id).where(
                PracticeSession.id == session_id,
                PracticeSession.user_id == user.id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="practice_session_not_found")
        traces = await list_agent_traces(
            session,
            session_id=session_id,
            limit=limit,
        )
    else:
        session_result = await session.execute(
            select(PracticeSession.id).where(PracticeSession.user_id == user.id)
        )
        traces = await list_agent_traces(
            session,
            session_ids=list(session_result.scalars().all()),
            limit=limit,
        )
    return [_trace_response(trace) for trace in traces]


def _trace_response(trace: AgentTrace) -> AgentTraceResponse:
    tool_calls = trace.tool_calls if isinstance(trace.tool_calls, dict) else {}
    input_summary = tool_calls.get("input_summary")
    output_summary = tool_calls.get("output_summary")
    return AgentTraceResponse.model_validate(
        {
            "id": trace.id,
            "session_id": trace.session_id,
            "thread_id": trace.thread_id,
            "problem_slug": trace.problem_slug,
            "node_name": trace.node_name,
            "phase": trace.phase,
            "hint_level": trace.hint_level,
            "model_name": trace.model_name,
            "latency_ms": trace.latency_ms,
            "stuck_point": trace.stuck_point,
            "should_reveal_solution": trace.should_reveal_solution,
            "input_summary": input_summary if isinstance(input_summary, dict) else {},
            "output_summary": output_summary if isinstance(output_summary, dict) else {},
            "created_at": trace.created_at,
        }
    )
