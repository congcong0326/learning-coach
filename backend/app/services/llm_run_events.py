from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LlmRunEvent:
    name: str
    data: dict[str, Any]


def encode_sse(event: LlmRunEvent) -> str:
    payload = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.name}\ndata: {payload}\n\n"


class LlmRunEventHub:
    def __init__(self) -> None:
        self._subscribers: dict[int, set[asyncio.Queue[LlmRunEvent]]] = defaultdict(set)
        self._tasks: dict[int, asyncio.Task[None]] = {}

    def has_task(self, run_id: int) -> bool:
        task = self._tasks.get(run_id)
        return task is not None and not task.done()

    def set_task(self, run_id: int, task: asyncio.Task[None]) -> None:
        self._tasks[run_id] = task

    def clear_task(self, run_id: int) -> None:
        self._tasks.pop(run_id, None)

    async def publish(self, run_id: int, event: LlmRunEvent) -> None:
        for queue in list(self._subscribers.get(run_id, set())):
            await queue.put(event)

    async def subscribe(self, run_id: int) -> AsyncIterator[LlmRunEvent]:
        queue: asyncio.Queue[LlmRunEvent] = asyncio.Queue()
        self._subscribers[run_id].add(queue)
        try:
            while True:
                event = await queue.get()
                yield event
                if event.name == "done":
                    break
        finally:
            subscribers = self._subscribers.get(run_id)
            if subscribers is not None:
                subscribers.discard(queue)
                if not subscribers:
                    self._subscribers.pop(run_id, None)


event_hub = LlmRunEventHub()
