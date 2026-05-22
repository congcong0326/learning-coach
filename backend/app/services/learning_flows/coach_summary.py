from __future__ import annotations

from typing import Any

from backend.app.services.learning_flows.coach_turn import run_coach_turn


async def run_coach_summary(*args: Any, **kwargs: Any) -> dict[str, Any]:
    result = await run_coach_turn(*args, **kwargs)
    result["summary_status"] = "deferred"
    return result


class CoachSummaryHandler:
    async def execute(self, context: Any) -> dict[str, Any]:
        return await run_coach_summary(
            context.session,
            user_id=context.user_id,
            run=context.run,
            provider=context.provider,
            model_name=context.model_name,
            publish=context.publish,
        )
