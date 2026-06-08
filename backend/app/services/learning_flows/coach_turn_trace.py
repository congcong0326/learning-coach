from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.coach_graph import CoachGraphState
from backend.app.models.llm_run import LlmRun
from backend.app.models.practice import PracticeSession
from backend.app.services.agent_trace_service import append_agent_trace
from backend.app.services.learning_flows.coach_turn_context import selected_rag_chunk_ids
from backend.app.services.learning_flows.coach_turn_policy import PROMPT_VERSION


async def append_coach_turn_traces(
    session: AsyncSession,
    *,
    practice_session: PracticeSession,
    run: LlmRun,
    graph_state: CoachGraphState,
    coach_decision: dict[str, Any],
    decision_accepted: bool,
    guard_reason: str,
    reply_md: str,
    model_name: str,
    phase_before: str,
) -> None:
    common: dict[str, Any] = {
        "session_id": practice_session.id,
        "thread_id": graph_state["thread_id"],
        "problem_slug": practice_session.problem_slug,
        "prompt_version": PROMPT_VERSION,
        "model_name": model_name,
    }
    await append_agent_trace(
        session,
        **common,
        node_name="llm_run_started",
        phase=phase_before,
        hint_level=practice_session.current_hint_level,
        input_summary={"run_id": run.id, "kind": run.kind},
        output_summary={"status": "started"},
    )
    for item in graph_state["trace"]:
        node_name = str(item.get("node") or "")
        if node_name == "guard_transition":
            continue
        output_summary: dict[str, Any] = {"status": "completed"}
        if node_name == "retrieve_supporting_context":
            retrieval_context = graph_state["retrieval_context"]
            selected_chunk_ids = selected_rag_chunk_ids(retrieval_context)
            output_summary = {
                "retrieval_status": retrieval_context.get("status"),
                "trace_id": retrieval_context.get("trace_id"),
                "selected_chunk_ids": selected_chunk_ids,
                "filtered_reasons": [
                    item.get("reason")
                    for item in retrieval_context.get("filtered", [])
                    if isinstance(item, dict)
                ],
            }
        await append_agent_trace(
            session,
            **common,
            node_name=node_name,
            phase=str(item.get("phase") or practice_session.phase),
            hint_level=item.get("hint_level"),
            input_summary={"run_id": run.id},
            output_summary=output_summary,
            retrieved_chunk_ids=(
                selected_rag_chunk_ids(graph_state["retrieval_context"])
                if node_name == "retrieve_supporting_context"
                else None
            ),
        )
    await append_agent_trace(
        session,
        **common,
        node_name="guard_transition",
        phase=phase_before,
        hint_level=practice_session.current_hint_level,
        input_summary={
            "model_phase_after": coach_decision["phase_after"],
            "should_reveal_solution": coach_decision["should_reveal_solution"],
        },
        output_summary={
            "guard_accepted": decision_accepted,
            "guard_reason": guard_reason,
            "phase_after": practice_session.phase,
        },
        stuck_point=coach_decision["diagnosed_stuck_point"],
        should_reveal_solution=bool(coach_decision["should_reveal_solution"]),
    )
    await append_agent_trace(
        session,
        **common,
        node_name="final_reply",
        phase=practice_session.phase,
        hint_level=practice_session.current_hint_level,
        input_summary={"reply_length": len(reply_md)},
        output_summary={"reply_preview": reply_md[:240]},
        stuck_point=coach_decision["diagnosed_stuck_point"],
        should_reveal_solution=bool(coach_decision["should_reveal_solution"]),
    )
    await append_agent_trace(
        session,
        **common,
        node_name="llm_run_completed",
        phase=practice_session.phase,
        hint_level=practice_session.current_hint_level,
        input_summary={"run_id": run.id, "kind": run.kind},
        output_summary={"status": "completed"},
        error_summary=str(coach_decision.get("error_summary") or ""),
    )
