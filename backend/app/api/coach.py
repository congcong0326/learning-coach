from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.problem_agent import AgentLoopError, ProblemAgentLoop
from backend.app.api.auth import current_user_dependency
from backend.app.db.session import get_session
from backend.app.llm.openai_responses import OpenAIResponsesDecisionEngine
from backend.app.models.auth import AppUser
from backend.app.schemas.coach import CoachChatRequest, CoachChatResponse


router = APIRouter(prefix="/coach", tags=["coach"])


def build_problem_agent_loop() -> ProblemAgentLoop:
    # API/factory 层选择当前模型适配器，ProblemAgentLoop 本身保持模型无关。
    return ProblemAgentLoop(decision_engine=OpenAIResponsesDecisionEngine())


@router.post("/chat", response_model=CoachChatResponse)
async def coach_chat(
    payload: CoachChatRequest,
    session: AsyncSession = Depends(get_session),
    user: AppUser = Depends(current_user_dependency),
) -> dict:
    del user
    try:
        result = await build_problem_agent_loop().run(session=session, message=payload.message)
    except AgentLoopError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "answer": result.answer,
        "tool_calls": [{"name": item.name} for item in result.tool_calls],
    }
