from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.types import (
    AgentConversationItem,
    AgentDecisionEngine,
    AgentMessage,
    AgentToolCallRequest,
    AgentToolExecutor,
    AgentToolObservation,
)
from backend.app.agents.problem_tools import ProblemToolRegistry


logger = logging.getLogger(__name__)

PROBLEM_AGENT_POLICY = """你是一个本地题库学习助手。
只能根据后端工具返回的题库数据回答；不要编造题目字段、题解或用户进度。
如果需要查询题库，请调用工具；如果信息不足，请明确说明需要用户补充。"""


@dataclass(frozen=True)
class AgentToolCallLogEntry:
    name: str


@dataclass(frozen=True)
class AgentRunResult:
    answer: str
    tool_calls: list[AgentToolCallLogEntry]


@dataclass(frozen=True)
class ProblemAgentSpec:
    agent_instructions: str
    tools: AgentToolExecutor
    max_turns: int = 6

    @classmethod
    def default(cls) -> ProblemAgentSpec:
        return cls(
            agent_instructions=PROBLEM_AGENT_POLICY,
            tools=ProblemToolRegistry(),
        )


class AgentLoopError(RuntimeError):
    pass


class ProblemAgentLoop:
    def __init__(
        self,
        *,
        decision_engine: AgentDecisionEngine,
        spec: ProblemAgentSpec | None = None,
    ) -> None:
        self._decision_engine = decision_engine
        self._spec = spec or ProblemAgentSpec.default()

    async def run(self, *, session: AsyncSession, message: str) -> AgentRunResult:
        # loop 只维护 agent-native 历史，模型、规则或其他决策引擎各自负责编译。
        history: list[AgentConversationItem] = [AgentMessage(role="user", content=message)]
        # 这是给 HTTP 响应/日志使用的执行摘要，不进入模型上下文；模型只看 history。
        tool_call_log: list[AgentToolCallLogEntry] = []

        logger.info("agent_loop_start max_turns=%s", self._spec.max_turns)
        for turn in range(1, self._spec.max_turns + 1):
            decision = await self._decision_engine.decide(
                agent_instructions=self._spec.agent_instructions,
                history=list(history),
                tools=self._spec.tools.definitions(),
            )
            logger.info(
                "agent_loop_turn_complete turn=%s tool_calls=%s has_answer=%s",
                turn,
                len(decision.tool_calls),
                bool(decision.text),
            )

            if decision.text:
                history.append(AgentMessage(role="assistant", content=decision.text))

            if not decision.tool_calls:
                logger.info("agent_loop_complete turns=%s tool_calls=%s", turn, len(tool_call_log))
                return AgentRunResult(answer=decision.text, tool_calls=tool_call_log)

            for tool_call in decision.tool_calls:
                history.append(
                    AgentToolCallRequest(
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                        arguments=tool_call.arguments,
                    )
                )
                tool_call_log.append(AgentToolCallLogEntry(name=tool_call.name))
                output = await self._spec.tools.execute(session, tool_call)
                # 工具结果必须按 tool_call_id 回灌，模型下一轮才能知道每个调用的执行结果。
                history.append(
                    AgentToolObservation(
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                        output=output,
                    )
                )

        logger.warning("agent_loop_stopped reason=max_turns max_turns=%s", self._spec.max_turns)
        raise AgentLoopError("agent_loop_max_turns_exceeded")
