from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Protocol

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    @property
    def model_name(self) -> str:
        """Embedding model identifier used for traceable chunk metadata."""

    @property
    def dimensions(self) -> int:
        """Embedding vector dimensions."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding per input text."""


@dataclass(frozen=True)
class FakeEmbeddingProvider:
    dimensions: int = 8
    model_name: str = "fake-embedding"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [_fake_vector(text, self.dimensions) for text in texts]


class OpenAICompatibleEmbeddingProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        base_url: str | None = None,
        dimensions: int = 1536,
    ) -> None:
        self.model_name = model_name
        self.dimensions = dimensions
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        logger.info(
            "rag_embedding_requested model=%s text_count=%s",
            self.model_name,
            len(texts),
        )
        response = await self._client.embeddings.create(
            model=self.model_name,
            input=texts,
        )
        return [list(item.embedding) for item in response.data]


def _fake_vector(text: str, dimensions: int) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    cursor = 0
    while len(values) < dimensions:
        if cursor >= len(digest):
            digest = hashlib.sha256(digest).digest()
            cursor = 0
        chunk = digest[cursor : cursor + 2]
        values.append(round(int.from_bytes(chunk, "big") / 65535, 3))
        cursor += 2
    return values
