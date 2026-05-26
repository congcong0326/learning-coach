from __future__ import annotations

from typing import Any, NotRequired, TypedDict, cast

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph


_CHECKPOINTER = MemorySaver()
_NON_AC_RESULTS = {"wa", "tle", "re", "mle", "ce"}
_TERMINAL_RESULTS = {"ac", "accepted"}


class CoachGraphState(TypedDict):
    user_id: int
    session_id: int
    thread_id: str
    study_plan_id: int
    latest_plan_version_id: int | None
    latest_plan_item_id: int | None
    problem_id: int
    problem_slug: str
    phase: str
    hint_level: str
    profile_summary: str
    recent_events: list[dict[str, Any]]
    latest_code_attempt: dict[str, Any] | None
    latest_submission_feedback: dict[str, Any] | None
    run: dict[str, Any]
    trace: list[dict[str, Any]]
    error_summary: str
    retrieval_context: dict[str, Any]
    recovery_summary: NotRequired[dict[str, Any]]
    input_classification: NotRequired[dict[str, Any]]
    diagnosis_summary: NotRequired[dict[str, Any]]
    action_summary: NotRequired[dict[str, Any]]
    guard_summary: NotRequired[dict[str, Any]]
    reply_summary: NotRequired[dict[str, Any]]
    persistence_summary: NotRequired[dict[str, Any]]
    summary_summary: NotRequired[dict[str, Any]]


class CoachGraph:
    def __init__(self) -> None:
        graph = StateGraph(CoachGraphState)
        graph.add_node("load_training_context", self.load_training_context)
        graph.add_node("classify_user_input", self.classify_user_input)
        graph.add_node("diagnose_stuck_point", self.diagnose_stuck_point)
        graph.add_node("retrieve_supporting_context", self.retrieve_supporting_context)
        graph.add_node("decide_next_action", self.decide_next_action)
        graph.add_node("guard_transition", self.guard_transition)
        graph.add_node("generate_coach_reply", self.generate_coach_reply)
        graph.add_node("persist_turn", self.persist_turn)
        graph.add_node("maybe_generate_summary", self.maybe_generate_summary)
        graph.set_entry_point("load_training_context")
        graph.add_edge("load_training_context", "classify_user_input")
        graph.add_edge("classify_user_input", "diagnose_stuck_point")
        graph.add_edge("diagnose_stuck_point", "retrieve_supporting_context")
        graph.add_edge("retrieve_supporting_context", "decide_next_action")
        graph.add_edge("decide_next_action", "guard_transition")
        graph.add_edge("guard_transition", "generate_coach_reply")
        graph.add_edge("generate_coach_reply", "persist_turn")
        graph.add_edge("persist_turn", "maybe_generate_summary")
        graph.add_edge("maybe_generate_summary", END)
        self._compiled = graph.compile(checkpointer=_CHECKPOINTER)

    async def run_turn(self, state: CoachGraphState) -> CoachGraphState:
        result = await self._compiled.ainvoke(
            state,
            config={"configurable": {"thread_id": state["thread_id"]}},
        )
        return cast(CoachGraphState, result)

    async def load_training_context(
        self,
        state: CoachGraphState,
    ) -> CoachGraphState:
        recovery_summary = {
            "thread_id": state["thread_id"],
            "checkpoint_key": f"coach:{state['thread_id']}",
            "last_phase_after": _last_phase_after(state["recent_events"]),
        }
        return self._record_node(
            self._updated_state(state, recovery_summary=recovery_summary),
            "load_training_context",
        )

    async def classify_user_input(
        self,
        state: CoachGraphState,
    ) -> CoachGraphState:
        feedback = state["latest_submission_feedback"]
        if _feedback_result(feedback):
            kind = "submission_feedback"
        elif state["latest_code_attempt"] is not None:
            kind = "code_attempt"
        elif state["run"].get("requested_phase_after"):
            kind = "system_requested_transition"
        else:
            kind = "message_or_resume"
        return self._record_node(
            self._updated_state(
                state,
                input_classification={
                    "kind": kind,
                    "run_kind": state["run"].get("kind"),
                    "has_code": state["latest_code_attempt"] is not None,
                    "has_submission_feedback": _feedback_result(feedback) != "",
                },
            ),
            "classify_user_input",
        )

    async def diagnose_stuck_point(
        self,
        state: CoachGraphState,
    ) -> CoachGraphState:
        feedback_result = _feedback_result(state["latest_submission_feedback"])
        if feedback_result in _NON_AC_RESULTS:
            diagnosis = {
                "category": f"submission_{feedback_result}",
                "evidence": ["latest_submission_feedback"],
                "confidence": "medium",
            }
        elif feedback_result in _TERMINAL_RESULTS:
            diagnosis = {
                "category": "terminal_feedback_ac",
                "evidence": ["latest_submission_feedback"],
                "confidence": "high",
            }
        elif state["latest_code_attempt"] is not None:
            diagnosis = {
                "category": "code_review_candidate",
                "evidence": ["latest_code_attempt"],
                "confidence": "medium",
            }
        else:
            diagnosis = {
                "category": "needs_clarification",
                "evidence": ["session_phase"],
                "confidence": "low",
            }
        return self._record_node(
            self._updated_state(state, diagnosis_summary=diagnosis),
            "diagnose_stuck_point",
        )

    async def retrieve_supporting_context(
        self,
        state: CoachGraphState,
    ) -> CoachGraphState:
        # RAG/T6 明确延后：图状态保留检索槽位，但当前节点不能访问知识库或向量检索。
        next_state = dict(state)
        next_state["retrieval_context"] = {
            "status": "rag_deferred",
            "chunks": [],
            "reason": "RAG/T6 延后，当前非 RAG 图节点不做检索。",
        }
        return self._record_node(
            cast(CoachGraphState, next_state),
            "retrieve_supporting_context",
        )

    async def decide_next_action(
        self,
        state: CoachGraphState,
    ) -> CoachGraphState:
        requested_phase_after = state["run"].get("requested_phase_after")
        feedback_result = _feedback_result(state["latest_submission_feedback"])
        if isinstance(requested_phase_after, str) and requested_phase_after:
            proposed_phase = requested_phase_after
            next_action = f"request_{requested_phase_after}"
            fast_forward = requested_phase_after != state["phase"]
        elif feedback_result in _TERMINAL_RESULTS:
            proposed_phase = "summarize"
            next_action = "summarize_session"
            fast_forward = True
        elif feedback_result in _NON_AC_RESULTS:
            proposed_phase = "analyze_feedback"
            next_action = "analyze_submission_feedback"
            fast_forward = state["phase"] != "analyze_feedback"
        elif state["latest_code_attempt"] is not None:
            proposed_phase = "review_code"
            next_action = "review_code"
            fast_forward = state["phase"] != "review_code"
        else:
            proposed_phase = state["phase"]
            next_action = "ask_clarifying_question"
            fast_forward = False
        return self._record_node(
            self._updated_state(
                state,
                action_summary={
                    "proposed_phase_after": proposed_phase,
                    "next_action": next_action,
                    "fast_forward": fast_forward,
                    "diagnosed_stuck_point": state.get("diagnosis_summary", {}).get(
                        "category",
                        "",
                    ),
                },
            ),
            "decide_next_action",
        )

    async def guard_transition(
        self,
        state: CoachGraphState,
    ) -> CoachGraphState:
        action_summary = state.get("action_summary", {})
        proposed_phase = str(action_summary.get("proposed_phase_after") or state["phase"])
        feedback_result = _feedback_result(state["latest_submission_feedback"])
        has_code = state["latest_code_attempt"] is not None
        has_feedback = feedback_result != ""
        accepted = True
        reason = "accepted"
        phase_after = proposed_phase
        if proposed_phase == "review_code" and not has_code:
            accepted = False
            reason = "code_required_for_review"
            phase_after = state["phase"]
        elif proposed_phase == "analyze_feedback" and not has_feedback:
            accepted = False
            reason = "submission_feedback_required_for_analysis"
            phase_after = state["phase"]
        elif proposed_phase == "summarize" and feedback_result not in _TERMINAL_RESULTS:
            accepted = False
            reason = "terminal_result_required_for_summary"
            phase_after = state["phase"]
        return self._record_node(
            self._updated_state(
                state,
                guard_summary={
                    "accepted": accepted,
                    "reason": reason,
                    "phase_after": phase_after,
                    "proposed_phase_after": proposed_phase,
                },
            ),
            "guard_transition",
        )

    async def generate_coach_reply(
        self,
        state: CoachGraphState,
    ) -> CoachGraphState:
        guard_summary = state.get("guard_summary", {})
        reply_summary = {
            "mode": "guarded" if guard_summary.get("accepted") is False else "normal",
            "phase_after": guard_summary.get("phase_after", state["phase"]),
            "next_action": state.get("action_summary", {}).get("next_action", ""),
        }
        return self._record_node(
            self._updated_state(state, reply_summary=reply_summary),
            "generate_coach_reply",
        )

    async def persist_turn(
        self,
        state: CoachGraphState,
    ) -> CoachGraphState:
        persistence_summary = {
            "thread_id": state["thread_id"],
            "checkpoint_key": f"coach:{state['thread_id']}",
            "trace_nodes": len(state["trace"]) + 1,
        }
        return self._record_node(
            self._updated_state(state, persistence_summary=persistence_summary),
            "persist_turn",
        )

    async def maybe_generate_summary(
        self,
        state: CoachGraphState,
    ) -> CoachGraphState:
        feedback_result = _feedback_result(state["latest_submission_feedback"])
        guard_summary = state.get("guard_summary", {})
        triggered = (
            guard_summary.get("accepted") is True
            and guard_summary.get("phase_after") == "summarize"
            and feedback_result in _TERMINAL_RESULTS
        )
        summary_summary = {
            "triggered": triggered,
            "reason": "terminal_feedback_ac" if triggered else "not_terminal",
        }
        return self._record_node(
            self._updated_state(state, summary_summary=summary_summary),
            "maybe_generate_summary",
        )

    def _updated_state(
        self,
        state: CoachGraphState,
        **updates: Any,
    ) -> CoachGraphState:
        next_state = dict(state)
        next_state.update(updates)
        return cast(CoachGraphState, next_state)

    def _record_node(
        self,
        state: CoachGraphState,
        node_name: str,
    ) -> CoachGraphState:
        next_state = dict(state)
        next_state["trace"] = [
            *state["trace"],
            {
                "node": node_name,
                "phase": state["phase"],
                "hint_level": state["hint_level"],
            },
        ]
        return cast(CoachGraphState, next_state)


def _feedback_result(feedback: dict[str, Any] | None) -> str:
    if not isinstance(feedback, dict):
        return ""
    result = feedback.get("result")
    return result if isinstance(result, str) else ""


def _last_phase_after(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        phase_after = event.get("phase_after")
        if isinstance(phase_after, str) and phase_after:
            return phase_after
    return ""
