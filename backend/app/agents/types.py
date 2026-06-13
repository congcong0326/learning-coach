from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class AgentToolDefinition:
    """Agent 可用工具的声明；具体模型适配器负责映射到自身工具格式。"""

    name: str
    description: str
    parameters: JsonObject


@dataclass(frozen=True)
class AgentMessage:
    """普通对话轮次；loop 维护完整历史，不绑定某个模型的状态续接机制。"""

    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class AgentToolCallRequest:
    """决策引擎发起的工具调用轮次，用于重放完整 agent 历史。"""

    tool_call_id: str
    name: str
    arguments: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class AgentToolObservation:
    """工具执行观察结果；tool_call_id 必须对应上一轮工具调用。"""

    tool_call_id: str
    name: str
    output: str


AgentConversationItem = AgentMessage | AgentToolCallRequest | AgentToolObservation


@dataclass(frozen=True)
class AgentToolCall:
    """决策引擎请求后端执行的工具调用，arguments 已解析为对象。"""

    id: str
    name: str
    arguments: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class AgentDecision:
    """标准化 agent 决策；loop 只判断最终文本和工具调用。"""

    text: str
    tool_calls: list[AgentToolCall]


class AgentDecisionEngine(Protocol):
    """模型无关的决策引擎协议。

    OpenAI、Claude、本地模型或规则引擎都应把自身输入输出映射到这些 agent
    类型，不能要求业务 loop 感知厂商状态续接或 SDK payload 细节。
    """

    async def decide(
        self,
        *,
        agent_instructions: str,
        history: list[AgentConversationItem],
        tools: list[AgentToolDefinition],
    ) -> AgentDecision:
        """根据 agent 历史生成下一步决策。"""


class AgentToolExecutor(Protocol):
    """Agent 工具集合协议，隐藏工具实现和持久化边界。"""

    def definitions(self) -> list[AgentToolDefinition]:
        """返回可暴露给决策引擎的工具声明。"""

    async def execute(self, session: Any, tool_call: AgentToolCall) -> str:
        """执行工具并返回可回灌给决策引擎的文本观察结果。"""
