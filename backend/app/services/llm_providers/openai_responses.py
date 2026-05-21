from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from backend.app.services.llm_providers.base import ProviderChunk


def event_to_text_delta(event: Any) -> str:
    if getattr(event, "type", "") == "response.output_text.delta":
        return str(getattr(event, "delta", ""))
    return ""


class OpenAIResponsesProvider:
    def __init__(self, *, api_key: str, base_url: str) -> None:
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def stream_text(
        self,
        *,
        model: str,
        instructions: str,
        input_text: str,
    ) -> AsyncIterator[ProviderChunk]:
        stream = await self.client.responses.create(
            model=model,
            instructions=instructions,
            input=input_text,
            stream=True,
        )
        final_parts: list[str] = []
        async for event in stream:
            delta = event_to_text_delta(event)
            if not delta:
                continue
            final_parts.append(delta)
            yield ProviderChunk(text_delta=delta)
        yield ProviderChunk(final_text="".join(final_parts))
