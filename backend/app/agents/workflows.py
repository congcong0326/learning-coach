from __future__ import annotations

from typing import Any

from backend.app.agents.loop import AgentLoopContext, AgentWorkflow
from backend.app.services.learning_flows.coach_summary import run_coach_summary
from backend.app.services.learning_flows.coach_turn import run_coach_turn
from backend.app.services.learning_flows.goal_calibration import run_goal_followup
from backend.app.services.learning_flows.goal_plan import run_goal_plan_generate


async def _goal_followup_step(context: AgentLoopContext) -> dict[str, Any]:
    return await run_goal_followup(
        context.session,
        user_id=context.user_id,
        run=context.run,
        provider=context.provider,
        model_name=context.model_name,
        publish=context.publish,
    )


async def _goal_plan_generate_step(context: AgentLoopContext) -> dict[str, Any]:
    return await run_goal_plan_generate(
        context.session,
        user_id=context.user_id,
        run=context.run,
        provider=context.provider,
        model_name=context.model_name,
        publish=context.publish,
    )


async def _coach_turn_step(context: AgentLoopContext) -> dict[str, Any]:
    return await run_coach_turn(
        context.session,
        user_id=context.user_id,
        run=context.run,
        provider=context.provider,
        model_name=context.model_name,
        publish=context.publish,
    )


async def _coach_summary_step(context: AgentLoopContext) -> dict[str, Any]:
    return await run_coach_summary(
        context.session,
        user_id=context.user_id,
        run=context.run,
        provider=context.provider,
        model_name=context.model_name,
        publish=context.publish,
    )


WORKFLOWS: dict[str, AgentWorkflow] = {
    "goal_followup": AgentWorkflow(
        name="goal_followup",
        steps=(("goal_followup", _goal_followup_step),),
    ),
    "goal_plan_generate": AgentWorkflow(
        name="goal_plan_generate",
        steps=(("goal_plan_generate", _goal_plan_generate_step),),
    ),
    "coach_turn": AgentWorkflow(
        name="coach_turn",
        steps=(("coach_turn", _coach_turn_step),),
    ),
    "coach_summary": AgentWorkflow(
        name="coach_summary",
        steps=(("coach_summary", _coach_summary_step),),
    ),
}


def workflow_for_kind(kind: str) -> AgentWorkflow | None:
    return WORKFLOWS.get(kind)
