from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


logger = logging.getLogger(__name__)


@dataclass
class AgentLoopContext:
    """Agent loop 的最小运行上下文。

    loop 内核只负责把共享对象交给 step；业务状态、事务和安全边界仍由业务 flow 自己维护。
    """

    session: Any
    user_id: int
    run: Any
    provider: Any
    model_name: str
    publish: Any
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentStepResult:
    output: Any = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


AgentStep = Callable[[AgentLoopContext], Awaitable[AgentStepResult | Any]]


@dataclass(frozen=True)
class AgentWorkflow:
    name: str
    steps: Sequence[tuple[str, AgentStep]]


@dataclass(frozen=True)
class AgentLoopResult:
    workflow_name: str
    output: Any
    steps: tuple[str, ...]


async def run_agent_loop(
    workflow: AgentWorkflow,
    context: AgentLoopContext,
) -> AgentLoopResult:
    logger.info(
        "agent loop started workflow=%s run_id=%s user_id=%s step_count=%s",
        workflow.name,
        getattr(context.run, "id", ""),
        context.user_id,
        len(workflow.steps),
    )
    output: Any = None
    executed_steps: list[str] = []
    for step_name, step in workflow.steps:
        logger.info(
            "agent loop step started workflow=%s step=%s run_id=%s user_id=%s",
            workflow.name,
            step_name,
            getattr(context.run, "id", ""),
            context.user_id,
        )
        try:
            raw_result = await step(context)
        except Exception:
            logger.exception(
                "agent loop step failed workflow=%s step=%s run_id=%s user_id=%s",
                workflow.name,
                step_name,
                getattr(context.run, "id", ""),
                context.user_id,
            )
            raise
        executed_steps.append(step_name)
        if isinstance(raw_result, AgentStepResult):
            output = raw_result.output
            if raw_result.metadata:
                context.metadata.update(dict(raw_result.metadata))
        else:
            output = raw_result
        logger.info(
            "agent loop step completed workflow=%s step=%s run_id=%s user_id=%s",
            workflow.name,
            step_name,
            getattr(context.run, "id", ""),
            context.user_id,
        )
    logger.info(
        "agent loop completed workflow=%s run_id=%s user_id=%s step_count=%s",
        workflow.name,
        getattr(context.run, "id", ""),
        context.user_id,
        len(executed_steps),
    )
    return AgentLoopResult(
        workflow_name=workflow.name,
        output=output,
        steps=tuple(executed_steps),
    )
