from __future__ import annotations

import logging
from typing import Any, NotRequired, Protocol, TypedDict, cast

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from backend.app.rag.retrieval import RetrievalRequest, RetrievalResult


logger = logging.getLogger(__name__)

_CHECKPOINTER = MemorySaver()
_NON_AC_RESULTS = {"wa", "tle", "re", "mle", "ce"}
_TERMINAL_RESULTS = {"ac", "accepted"}


class CoachRetrievalService(Protocol):
    async def retrieve_for_coach(self, request: RetrievalRequest) -> RetrievalResult:
        """Retrieve safe coaching context for the current graph state."""


class CoachGraphState(TypedDict):
    """单轮教练图的共享状态。

    这个 TypedDict 是各 LangGraph 节点之间的契约：入口 flow 负责填充训练事实，
    节点只追加摘要化判断结果，避免把完整用户输入、完整代码或大段 RAG 原文在图里扩散。
    """

    # 用户、会话和 thread_id 共同决定本轮教练状态归属；thread_id 还会传给
    # LangGraph checkpointer，用于后续按训练会话恢复图状态。
    user_id: int
    session_id: int
    thread_id: str

    # 学习计划上下文用于解释“为什么练这题”。plan version/item 可能为空，
    # 因为历史会话、自由选题或数据修复路径不一定都能追溯到具体计划项。
    study_plan_id: int
    latest_plan_version_id: int | None
    latest_plan_item_id: int | None

    # 当前题目上下文用于 RAG 过滤和打分；tags 使用题库中的规范 slug，
    # 不依赖用户自然语言描述。
    problem_id: int
    problem_slug: str
    problem_tags: list[str]

    # 训练状态主轴。phase 是当前训练阶段，hint_level 是当前提示档位；
    # 模型只能提出变更建议，最终是否允许跳转仍由后端 guard 控制。
    phase: str
    hint_level: str

    # 面向教练决策的安全画像摘要，只放短摘要，不放完整画像证据链或敏感内容。
    profile_summary: str

    # 最近关键事件用于恢复和判断上一轮状态；这里存摘要化事件，而不是完整聊天记录。
    recent_events: list[dict[str, Any]]

    # 用户本轮或最近一次代码尝试的元数据摘要；完整代码只留在 CodeSnapshot，
    # 不应复制进图状态或 trace。
    latest_code_attempt: dict[str, Any] | None

    # 最新 LeetCode 提交反馈摘要。聊天中识别出的 WA/TLE/RE 等也会被规整成同一形态，
    # 让图可以统一进入提交反馈分析。
    latest_submission_feedback: dict[str, Any] | None

    # 当前 LLM Run 的最小上下文，例如 run id、kind、关联实体和系统请求的跳转。
    run: dict[str, Any]

    # RAG 检索用的安全 query 摘要；必须从用户输入中去掉完整代码和冗长原文。
    user_query_summary: str

    # 图内节点轨迹，只记录节点名、阶段和提示档位，供后续写 agent_trace。
    trace: list[dict[str, Any]]

    # 图级错误摘要，保留稳定错误类型或短原因，避免记录原始异常上下文。
    error_summary: str

    # RAG 节点输出的安全上下文，只允许包含 chunk id、类型、标题、摘要和过滤原因。
    retrieval_context: dict[str, Any]

    # 以下字段是各节点追加的派生摘要。使用 NotRequired 是为了让每个节点只关心
    # 自己已产生的结果，避免入口 state 必须提前构造所有中间字段。
    recovery_summary: NotRequired[dict[str, Any]]
    input_classification: NotRequired[dict[str, Any]]
    diagnosis_summary: NotRequired[dict[str, Any]]
    action_summary: NotRequired[dict[str, Any]]
    guard_summary: NotRequired[dict[str, Any]]
    reply_summary: NotRequired[dict[str, Any]]
    persistence_summary: NotRequired[dict[str, Any]]
    summary_summary: NotRequired[dict[str, Any]]


class CoachGraph:
    def __init__(self, retrieval_service: CoachRetrievalService | None = None) -> None:
        self._retrieval_service = retrieval_service
        graph = StateGraph(CoachGraphState)

        # load_training_context：恢复本训练会话的图状态入口，读取 thread_id、
        # checkpoint key 和最近阶段，确保后续节点基于同一轮训练事实继续判断。
        graph.add_node("load_training_context", self.load_training_context)

        # classify_user_input：把本轮输入归类为提交反馈、代码尝试、系统请求跳转
        # 或普通消息，决定后续诊断优先看哪类证据。
        graph.add_node("classify_user_input", self.classify_user_input)

        # diagnose_stuck_point：根据 LeetCode 结果、代码尝试和当前阶段生成卡点摘要，
        # 供 RAG 检索、动作决策和 trace 使用，不直接决定最终状态跳转。
        graph.add_node("diagnose_stuck_point", self.diagnose_stuck_point)

        # retrieve_supporting_context：按题目、阶段、提示档位和卡点检索安全教练知识，
        # 只注入摘要化 RAG 上下文，检索失败时回退到非 RAG 教练流程。
        graph.add_node("retrieve_supporting_context", self.retrieve_supporting_context)

        # decide_next_action：综合输入分类、诊断和提交结果提出下一步教练动作，
        # 例如代码 review、分析非 AC 反馈、AC 后复盘或继续追问。
        graph.add_node("decide_next_action", self.decide_next_action)

        # guard_transition：后端状态守卫，校验 proposed_phase 是否有足够证据，
        # 防止缺代码 review、缺提交反馈分析或未 AC 就进入复盘。
        graph.add_node("guard_transition", self.guard_transition)

        # generate_coach_reply：把守卫结果、阶段和下一步动作整理为回复摘要，
        # 后续 LLM flow 会据此生成用户可见的教练回复。
        graph.add_node("generate_coach_reply", self.generate_coach_reply)

        # persist_turn：记录本轮可持久化摘要，包括 thread_id、checkpoint key
        # 和节点轨迹数量，供 coach_turn 与 agent_trace 落库使用。
        graph.add_node("persist_turn", self.persist_turn)

        # maybe_generate_summary：在 AC 等终态反馈通过守卫后触发单题复盘，
        # 不满足终态条件时只记录未触发原因，避免过早生成画像沉淀。
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
        next_state = dict(state)
        if self._retrieval_service is None:
            next_state["retrieval_context"] = {
                "status": "error",
                "chunks": [],
                "filtered": [],
                "reason": "retrieval_service_unavailable",
            }
            return self._record_node(
                cast(CoachGraphState, next_state),
                "retrieve_supporting_context",
            )
        request = RetrievalRequest(
            user_id=state["user_id"],
            session_id=state["session_id"],
            problem_slug=state["problem_slug"],
            problem_tags=state.get("problem_tags", []),
            phase=state["phase"],
            hint_level=state["hint_level"],
            stuck_point=str(state.get("diagnosis_summary", {}).get("category") or ""),
            retrieval_intent=_retrieval_intent(state),
            query_summary=state.get("user_query_summary") or "coach_turn",
            top_k=5,
        )
        try:
            result = await self._retrieval_service.retrieve_for_coach(request)
            context = result.as_graph_context()
            context["retrieval_intent"] = request.retrieval_intent
            next_state["retrieval_context"] = context
        except Exception as exc:
            logger.warning(
                "coach_graph_retrieval_failed session_id=%s problem_slug=%s "
                "error_type=%s",
                state["session_id"],
                state["problem_slug"],
                type(exc).__name__,
            )
            next_state["retrieval_context"] = {
                "status": "error",
                "chunks": [],
                "filtered": [],
                "reason": type(exc).__name__,
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


def _retrieval_intent(state: CoachGraphState) -> str:
    feedback_result = _feedback_result(state["latest_submission_feedback"])
    if feedback_result in _NON_AC_RESULTS:
        return "submission_feedback"
    if feedback_result in _TERMINAL_RESULTS or state["run"].get("kind") == "coach_summary":
        return "session_summary"
    if state["latest_code_attempt"] is not None or state["phase"] == "review_code":
        return "code_review"
    if state["hint_level"] in {"direction", "key_hint"}:
        return "hint_progression"
    return "pattern_direction"
