from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.loop import AgentLoopContext, run_agent_loop
from backend.app.agents.workflows import workflow_for_kind
from backend.app.models.llm_run import LlmRun
from backend.app.services.llm_providers.base import LlmProvider
from backend.app.services.llm_run_events import LlmRunEvent


@dataclass(frozen=True)
class LlmRunContext:
    session: AsyncSession
    user_id: int
    run: LlmRun
    provider: LlmProvider
    model_name: str
    publish: Callable[[LlmRunEvent], Awaitable[None]]


class LlmRunHandler(Protocol):
    async def execute(self, context: LlmRunContext) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class RunKindSpec:
    handler: LlmRunHandler | None
    related_type: str = ""
    related_id_key: str = ""
    requires_model: bool = True


class AgentWorkflowHandler:
    def __init__(self, kind: str) -> None:
        self.kind = kind

    async def execute(self, context: LlmRunContext) -> dict[str, Any]:
        workflow = workflow_for_kind(self.kind)
        if workflow is None:
            return {}
        result = await run_agent_loop(
            workflow,
            AgentLoopContext(
                session=context.session,
                user_id=context.user_id,
                run=context.run,
                provider=context.provider,
                model_name=context.model_name,
                publish=context.publish,
            ),
        )
        output = result.output
        return output if isinstance(output, dict) else {}


class GoalFollowupHandler(AgentWorkflowHandler):
    def __init__(self) -> None:
        super().__init__("goal_followup")


class GoalPlanGenerateHandler(AgentWorkflowHandler):
    def __init__(self) -> None:
        super().__init__("goal_plan_generate")


class CoachTurnHandler(AgentWorkflowHandler):
    def __init__(self) -> None:
        super().__init__("coach_turn")


class CoachSummaryHandler(AgentWorkflowHandler):
    def __init__(self) -> None:
        super().__init__("coach_summary")


# related_type/related_id 只落库记录 LLM Run 和业务实体的索引关系，ORM 不会因此自动 join；
# 后续查询需要由服务层显式按这两个字段过滤或再读取对应表。
RUN_KIND_SPECS: dict[str, RunKindSpec] = {
    # goal_calibration_draft：目标校准草稿，承接首次目标输入、追问答案和最终计划草稿生成。
    "goal_followup": RunKindSpec(
        handler=GoalFollowupHandler(),
        related_type="goal_calibration_draft",
        related_id_key="draft_id",
    ),
    # goal_calibration_draft：计划生成基于已完成追问的草稿继续产出结构化学习计划。
    "goal_plan_generate": RunKindSpec(
        handler=GoalPlanGenerateHandler(),
        related_type="goal_calibration_draft",
        related_id_key="draft_id",
    ),
    # practice_session：单题训练会话中的 AI 教练回复，handler 负责持久化 assistant event 和 coach_turn。
    "coach_turn": RunKindSpec(
        handler=CoachTurnHandler(),
        related_type="practice_session",
        related_id_key="session_id",
        requires_model=True,
    ),
    # practice_session：单题训练复盘入口，当前已经升级为模型驱动复盘，
    # 必须走真实模型资产选择路径，缺资产时由 orchestrator 统一拒绝执行。
    "coach_summary": RunKindSpec(
        handler=CoachSummaryHandler(),
        related_type="practice_session",
        related_id_key="session_id",
        requires_model=True,
    ),
}


def supported_run_kinds() -> set[str]:
    return {kind for kind, spec in RUN_KIND_SPECS.items() if spec.handler is not None}


def handler_for_kind(kind: str) -> LlmRunHandler | None:
    spec = RUN_KIND_SPECS.get(kind)
    return spec.handler if spec is not None else None


def requires_model_for_kind(kind: str) -> bool:
    spec = RUN_KIND_SPECS.get(kind)
    return bool(spec is not None and spec.handler is not None and spec.requires_model)


def related_from_payload(kind: str, payload: dict[str, Any]) -> tuple[str, int | None]:
    spec = RUN_KIND_SPECS.get(kind)
    if spec is None or not spec.related_type or not spec.related_id_key:
        return "", None
    related_id = payload.get(spec.related_id_key)
    if isinstance(related_id, int) and not isinstance(related_id, bool):
        return spec.related_type, related_id
    return "", None
