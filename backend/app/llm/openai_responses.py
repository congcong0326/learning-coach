from __future__ import annotations

import json
import logging
from typing import Any, cast

from openai import APIError, AsyncOpenAI

from backend.app.agents.types import (
    AgentConversationItem,
    AgentDecision,
    AgentDecisionEngine,
    AgentMessage,
    AgentToolCall,
    AgentToolCallRequest,
    AgentToolDefinition,
    AgentToolObservation,
)
from backend.app.llm.local_openai_config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    OPENAI_TIMEOUT_SECONDS,
)


logger = logging.getLogger(__name__)


class OpenAIResponsesDecisionError(RuntimeError):
    pass


class OpenAIResponsesDecisionEngine(AgentDecisionEngine):
    """OpenAI Responses API 适配器。

    该类是唯一知道 Responses API payload 细节的地方；上层 Agent loop 只依赖
    AgentDecisionEngine 协议，后续替换模型或规则引擎不需要修改业务 loop。
    """

    def __init__(
        self,
        *,
        api_key: str = OPENAI_API_KEY,
        base_url: str = OPENAI_BASE_URL,
        model: str = OPENAI_MODEL,
        timeout: float = OPENAI_TIMEOUT_SECONDS,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._model = model
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    async def decide(
        self,
        *,
        agent_instructions: str,
        history: list[AgentConversationItem],
        tools: list[AgentToolDefinition],
    ) -> AgentDecision:
        logger.info(
            "llm_request_start provider=openai_responses model=%s history_items=%s tools=%s",
            self._model,
            len(history),
            len(tools),
        )
        try:
            response = await self._client.responses.create(
                model=self._model,
                instructions=agent_instructions,
                # OpenAI SDK 的 TypedDict 很细；这里把标准历史集中映射成
                # Responses API payload，避免 SDK 类型扩散到业务层。
                input=cast(Any, [_history_item_payload(item) for item in history]),
                tools=cast(Any, [_tool_payload(tool) for tool in tools]),
            )
        except APIError as exc:
            logger.exception(
                "llm_request_failed provider=openai_responses model=%s error_type=%s",
                self._model,
                type(exc).__name__,
            )
            raise OpenAIResponsesDecisionError("OpenAI Responses API request failed") from exc

        tool_calls = _extract_tool_calls(response)
        response_id = getattr(response, "id", None)
        logger.info(
            "llm_request_complete provider=openai_responses model=%s response_id=%s tool_calls=%s",
            self._model,
            response_id,
            len(tool_calls),
        )
        return AgentDecision(
            text=str(getattr(response, "output_text", "") or ""),
            tool_calls=tool_calls,
        )


def _history_item_payload(item: AgentConversationItem) -> dict[str, Any]:
    """把 agent-native 历史转换为 Responses API input item。"""

    if isinstance(item, AgentMessage):
        return {"role": item.role, "content": item.content}
    if isinstance(item, AgentToolCallRequest):
        return {
            "type": "function_call",
            "call_id": item.tool_call_id,
            "name": item.name,
            "arguments": json.dumps(item.arguments, ensure_ascii=False),
        }
    if isinstance(item, AgentToolObservation):
        # 工具结果在抽象层只表达“对应哪个工具调用”；OpenAI 适配器负责转成
        # Responses API 需要的 function_call_output 形态。
        return {
            "type": "function_call_output",
            "call_id": item.tool_call_id,
            "output": item.output,
        }
    raise TypeError(f"Unsupported agent input item: {type(item)!r}")


def _tool_payload(tool: AgentToolDefinition) -> dict[str, Any]:
    """把跨 provider 工具定义转换为 OpenAI function tool。"""

    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters,
    }


def _extract_tool_calls(response: Any) -> list[AgentToolCall]:
    """从 Responses API 输出中提取 function_call，屏蔽 SDK 原始对象形态。"""

    calls: list[AgentToolCall] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) != "function_call":
            continue
        name = getattr(item, "name", None)
        call_id = getattr(item, "call_id", None)
        if not isinstance(name, str) or not isinstance(call_id, str):
            logger.warning(
                "llm_tool_call_skipped provider=openai_responses reason=missing_name_or_call_id"
            )
            continue
        arguments = _parse_arguments(getattr(item, "arguments", "{}"))
        calls.append(AgentToolCall(id=call_id, name=name, arguments=arguments))
    return calls


def _parse_arguments(raw_arguments: Any) -> dict[str, Any]:
    """工具参数必须是 JSON object；解析失败时返回空对象并记录可检索日志。"""

    if isinstance(raw_arguments, dict):
        return raw_arguments
    if not isinstance(raw_arguments, str) or not raw_arguments:
        return {}
    try:
        parsed = json.loads(raw_arguments)
    except json.JSONDecodeError:
        logger.warning("llm_tool_arguments_invalid provider=openai_responses")
        return {}
    if not isinstance(parsed, dict):
        logger.warning("llm_tool_arguments_invalid provider=openai_responses reason=not_object")
        return {}
    return parsed
