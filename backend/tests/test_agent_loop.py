from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from backend.app.agents.loop import (
    AgentLoopContext,
    AgentStepResult,
    AgentWorkflow,
    run_agent_loop,
)
from backend.app.agents.workflows import workflow_for_kind


@pytest.mark.asyncio
async def test_agent_loop_runs_async_steps_in_order() -> None:
    calls: list[str] = []
    context = AgentLoopContext(
        session="session",
        user_id=42,
        run=SimpleNamespace(id=7),
        provider="provider",
        model_name="gpt-test",
        publish="publish",
    )

    async def first_step(loop_context: AgentLoopContext) -> AgentStepResult:
        calls.append("first")
        loop_context.metadata["value"] = 1
        return AgentStepResult(output={"step": "first"})

    async def second_step(loop_context: AgentLoopContext) -> dict[str, Any]:
        calls.append("second")
        return {"value": loop_context.metadata["value"] + 1}

    result = await run_agent_loop(
        AgentWorkflow(
            name="test_workflow",
            steps=(("first", first_step), ("second", second_step)),
        ),
        context,
    )

    assert calls == ["first", "second"]
    assert result.workflow_name == "test_workflow"
    assert result.steps == ("first", "second")
    assert result.output == {"value": 2}


@pytest.mark.asyncio
async def test_agent_loop_propagates_step_error() -> None:
    async def failing_step(loop_context: AgentLoopContext) -> dict[str, Any]:
        del loop_context
        raise RuntimeError("boom")

    context = AgentLoopContext(
        session=None,
        user_id=1,
        run=SimpleNamespace(id=2),
        provider=None,
        model_name="",
        publish=None,
    )

    with pytest.raises(RuntimeError, match="boom"):
        await run_agent_loop(
            AgentWorkflow(name="failing", steps=(("failing", failing_step),)),
            context,
        )


def test_workflow_registry_contains_primary_llm_run_kinds() -> None:
    assert workflow_for_kind("goal_plan_generate") is not None
    assert workflow_for_kind("coach_turn") is not None
    assert workflow_for_kind("coach_summary") is not None
