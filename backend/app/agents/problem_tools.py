from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.types import AgentToolCall, AgentToolDefinition
from backend.app.services.problem_service import (
    get_problem_detail,
    list_problem_categories,
    list_problems,
)


logger = logging.getLogger(__name__)

MAX_TOOL_OUTPUT_CHARS = 20_000

ToolHandler = Callable[[AsyncSession, dict[str, Any]], Awaitable[dict[str, Any]]]


class ProblemToolRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {
            "search_problems": _search_problems,
            "get_problem_detail": _get_problem_detail,
            "list_problem_categories": _list_problem_categories,
        }

    def definitions(self) -> list[AgentToolDefinition]:
        return [
            AgentToolDefinition(
                name="search_problems",
                description="按关键词、难度、标签或分类查询题库列表。",
                parameters={
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string"},
                        "difficulty": {
                            "type": "string",
                            "enum": ["Easy", "Medium", "Hard"],
                        },
                        "tag": {"type": "string"},
                        "category": {"type": "string"},
                        "page_size": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                        },
                    },
                    "additionalProperties": False,
                },
            ),
            AgentToolDefinition(
                name="get_problem_detail",
                description="按题目 slug 查询单题题面详情。",
                parameters={
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string"},
                    },
                    "required": ["slug"],
                    "additionalProperties": False,
                },
            ),
            AgentToolDefinition(
                name="list_problem_categories",
                description="列出题库分类。",
                parameters={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
        ]

    async def execute(self, session: AsyncSession, tool_call: AgentToolCall) -> str:
        handler = self._handlers.get(tool_call.name)
        if handler is None:
            logger.warning("agent_tool_rejected tool=%s reason=unknown", tool_call.name)
            return _json_result({"ok": False, "error": "unknown_tool"})

        logger.info("agent_tool_start tool=%s", tool_call.name)
        try:
            result = await handler(session, tool_call.arguments)
        except Exception as exc:
            logger.exception(
                "agent_tool_failed tool=%s error_type=%s",
                tool_call.name,
                type(exc).__name__,
            )
            return _json_result({"ok": False, "error": "tool_failed"})

        logger.info("agent_tool_complete tool=%s", tool_call.name)
        return _json_result({"ok": True, "data": result})


async def _search_problems(session: AsyncSession, arguments: dict[str, Any]) -> dict[str, Any]:
    page_size = _bounded_int(arguments.get("page_size"), default=5, minimum=1, maximum=10)
    return await list_problems(
        session,
        keyword=_optional_str(arguments.get("keyword")),
        difficulty=_optional_str(arguments.get("difficulty")),
        tag=_optional_str(arguments.get("tag")),
        category=_optional_str(arguments.get("category")),
        page=1,
        page_size=page_size,
    )


async def _get_problem_detail(session: AsyncSession, arguments: dict[str, Any]) -> dict[str, Any]:
    slug = _optional_str(arguments.get("slug"))
    if not slug:
        return {"found": False, "error": "missing_slug"}

    problem = await get_problem_detail(session, slug)
    if problem is None:
        return {"found": False}

    # 题面可能较长，第一版只给模型摘要上下文，避免单次工具输出过大。
    payload = dict(problem)
    statement = str(payload.get("statement_md", ""))
    payload["statement_md"] = statement[:6000]
    payload["statement_truncated"] = len(statement) > 6000
    return {"found": True, "problem": payload}


async def _list_problem_categories(
    session: AsyncSession,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    return await list_problem_categories(session)


def _json_result(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False)
    if len(encoded) <= MAX_TOOL_OUTPUT_CHARS:
        return encoded
    return encoded[:MAX_TOOL_OUTPUT_CHARS] + "...<truncated>"


def _optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    if not isinstance(value, int):
        return default
    return min(max(value, minimum), maximum)
