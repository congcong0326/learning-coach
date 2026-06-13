from __future__ import annotations

import types
from typing import Any

import pytest

from backend.app.agents.types import (
    AgentMessage,
    AgentToolCallRequest,
    AgentToolDefinition,
    AgentToolObservation,
)
from backend.app.llm.openai_responses import OpenAIResponsesDecisionEngine


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        return types.SimpleNamespace(
            id="resp_123",
            output_text="",
            output=[
                types.SimpleNamespace(
                    type="function_call",
                    call_id="call_1",
                    name="search_problems",
                    arguments='{"keyword": "array"}',
                )
            ],
        )


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


@pytest.mark.asyncio
async def test_openai_responses_provider_normalizes_payload_and_tool_calls() -> None:
    client = FakeClient()
    decision_engine = OpenAIResponsesDecisionEngine(
        model="test-model",
        client=client,  # type: ignore[arg-type]
    )

    response = await decision_engine.decide(
        agent_instructions="agent policy",
        history=[
            AgentMessage(role="user", content="hello"),
            AgentToolCallRequest(
                tool_call_id="call_old",
                name="search_problems",
                arguments={"keyword": "array"},
            ),
            AgentToolObservation(
                tool_call_id="call_old",
                name="search_problems",
                output='{"ok": true}',
            ),
        ],
        tools=[
            AgentToolDefinition(
                name="search_problems",
                description="search",
                parameters={"type": "object", "properties": {}},
            )
        ],
    )

    assert response.tool_calls[0].name == "search_problems"
    assert response.tool_calls[0].arguments == {"keyword": "array"}
    assert response.tool_calls[0].id == "call_1"
    assert client.responses.calls == [
        {
            "model": "test-model",
            "instructions": "agent policy",
            "input": [
                {"role": "user", "content": "hello"},
                {
                    "type": "function_call",
                    "call_id": "call_old",
                    "name": "search_problems",
                    "arguments": '{"keyword": "array"}',
                },
                {
                    "type": "function_call_output",
                    "call_id": "call_old",
                    "output": '{"ok": true}',
                },
            ],
            "tools": [
                {
                    "type": "function",
                    "name": "search_problems",
                    "description": "search",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
        }
    ]
