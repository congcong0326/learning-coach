from __future__ import annotations

from typing import Any

import pytest

from backend.app.agents.problem_agent import AgentLoopError, ProblemAgentLoop, ProblemAgentSpec
from backend.app.agents.types import (
    AgentConversationItem,
    AgentDecision,
    AgentMessage,
    AgentToolCall,
    AgentToolCallRequest,
    AgentToolDefinition,
    AgentToolObservation,
)


class FakeDecisionEngine:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def decide(
        self,
        *,
        agent_instructions: str,
        history: list[AgentConversationItem],
        tools: list[AgentToolDefinition],
    ) -> AgentDecision:
        self.calls.append(
            {
                "agent_instructions": agent_instructions,
                "history": history,
                "tools": tools,
            }
        )
        if len(self.calls) == 1:
            return AgentDecision(
                text="",
                tool_calls=[
                    AgentToolCall(
                        id="call_1",
                        name="search_problems",
                        arguments={"keyword": "array"},
                    )
                ],
            )
        return AgentDecision(text="找到几道数组题。", tool_calls=[])

class FakeTools:
    def definitions(self) -> list[AgentToolDefinition]:
        return [
            AgentToolDefinition(
                name="search_problems",
                description="search",
                parameters={"type": "object", "properties": {}},
            )
        ]

    async def execute(self, session: object, tool_call: AgentToolCall) -> str:
        return '{"ok": true, "data": {"items": []}}'


@pytest.mark.asyncio
async def test_problem_agent_loop_feeds_tool_result_back_to_provider() -> None:
    decision_engine = FakeDecisionEngine()
    loop = ProblemAgentLoop(
        decision_engine=decision_engine,
        spec=ProblemAgentSpec(
            agent_instructions="agent policy",
            tools=FakeTools(),
            max_turns=3,
        ),
    )

    result = await loop.run(session=object(), message="找数组题")  # type: ignore[arg-type]

    assert result.answer == "找到几道数组题。"
    assert [item.name for item in result.tool_calls] == ["search_problems"]
    assert decision_engine.calls[0]["agent_instructions"] == "agent policy"
    assert decision_engine.calls[1]["history"] == [
        AgentMessage(role="user", content="找数组题"),
        AgentToolCallRequest(
            tool_call_id="call_1",
            name="search_problems",
            arguments={"keyword": "array"},
        ),
        AgentToolObservation(
            tool_call_id="call_1",
            name="search_problems",
            output='{"ok": true, "data": {"items": []}}',
        ),
    ]


@pytest.mark.asyncio
async def test_problem_agent_loop_stops_at_max_turns() -> None:
    class AlwaysCallsTool(FakeDecisionEngine):
        async def decide(self, **kwargs: Any) -> AgentDecision:
            self.calls.append(kwargs)
            return AgentDecision(
                text="",
                tool_calls=[AgentToolCall(id="call_1", name="search_problems")],
            )

    loop = ProblemAgentLoop(
        decision_engine=AlwaysCallsTool(),
        spec=ProblemAgentSpec(
            agent_instructions="agent policy",
            tools=FakeTools(),
            max_turns=1,
        ),
    )

    with pytest.raises(AgentLoopError):
        await loop.run(session=object(), message="一直查")  # type: ignore[arg-type]
