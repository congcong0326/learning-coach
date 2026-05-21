from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderChunk:
    text_delta: str = ""
    final_text: str = ""


class LlmProvider(Protocol):
    async def stream_text(
        self,
        *,
        model: str,
        instructions: str,
        input_text: str,
    ) -> AsyncIterator[ProviderChunk]: ...
