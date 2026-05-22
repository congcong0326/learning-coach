from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.llm_run import LlmRun
from backend.app.services.learning_flows.coach_turn import run_coach_turn
from backend.app.services.llm_providers.base import LlmProvider
from backend.app.services.llm_run_events import LlmRunEvent
from backend.app.services.profile_service import persist_session_summary_profile_update


async def run_coach_summary(
    session: AsyncSession,
    *,
    user_id: int,
    run: LlmRun,
    provider: LlmProvider,
    model_name: str,
    publish: Callable[[LlmRunEvent], Awaitable[None]],
) -> dict[str, Any]:
    result = await run_coach_turn(
        session,
        user_id=user_id,
        run=run,
        provider=provider,
        model_name=model_name,
        publish=publish,
    )
    summary_result = await persist_session_summary_profile_update(
        session,
        user_id=user_id,
        session_id=result["session_id"],
    )
    result.update(
        {
            "summary_status": "completed",
            "summary_id": summary_result.summary_id,
            "profile_delta_id": summary_result.delta_id,
            "profile_delta_status": (
                "accepted" if summary_result.accepted else "rejected"
            ),
            "profile_snapshot_id": summary_result.next_snapshot_id,
            "profile_rejection_reason": summary_result.rejection_reason,
        }
    )
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
