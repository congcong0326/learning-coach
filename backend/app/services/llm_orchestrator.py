from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.services.llm_run_events import LlmRunEvent, event_hub


async def execute_llm_run(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: int,
    user_id: int,
) -> None:
    await event_hub.publish(run_id, LlmRunEvent("error", {"run_id": run_id, "error_code": "flow_not_implemented"}))
    await event_hub.publish(run_id, LlmRunEvent("done", {"run_id": run_id}))
