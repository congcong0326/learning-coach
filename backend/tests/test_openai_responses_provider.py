from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from backend.app.services.llm_providers.base import LlmProvider, ProviderChunk
from backend.app.services.llm_providers.openai_responses import (
    OpenAIResponsesProvider,
    event_to_text_delta,
)


def test_event_to_text_delta_reads_response_text_delta() -> None:
    event = SimpleNamespace(type="response.output_text.delta", delta="你好")

    assert event_to_text_delta(event) == "你好"


def test_event_to_text_delta_ignores_non_text_events() -> None:
    event = SimpleNamespace(type="response.created")

    assert event_to_text_delta(event) == ""


@pytest.mark.asyncio
async def test_openai_responses_provider_streams_text_chunks_without_network() -> None:
    class FakeStream:
        def __init__(self) -> None:
            self.events = iter(
                [
                    SimpleNamespace(type="response.created"),
                    SimpleNamespace(type="response.output_text.delta", delta="你"),
                    SimpleNamespace(type="response.output_text.delta", delta="好"),
                ]
            )

        def __aiter__(self) -> FakeStream:
            return self

        async def __anext__(self) -> SimpleNamespace:
            try:
                return next(self.events)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    class FakeResponses:
        def __init__(self) -> None:
            self.create_kwargs: dict[str, Any] | None = None

        async def create(self, **kwargs: Any) -> FakeStream:
            self.create_kwargs = kwargs
            return FakeStream()

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    provider = OpenAIResponsesProvider(api_key="test-key", base_url="http://example.test")
    provider_contract: LlmProvider = provider
    fake_client = FakeClient()
    cast(Any, provider).client = fake_client

    chunks = [
        chunk
        async for chunk in provider_contract.stream_text(
            model="gpt-test",
            instructions="请回答",
            input_text="say hello",
        )
    ]

    assert chunks == [
        ProviderChunk(text_delta="你"),
        ProviderChunk(text_delta="好"),
        ProviderChunk(final_text="你好"),
    ]
    assert fake_client.responses.create_kwargs == {
        "model": "gpt-test",
        "instructions": "请回答",
        "input": "say hello",
        "stream": True,
    }
