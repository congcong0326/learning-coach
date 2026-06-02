from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.rag import (
    KnowledgeChunk,
    KnowledgeDoc,
    content_hash_for,
    stable_chunk_uid,
)
from backend.app.rag.embedding import EmbeddingProvider
from backend.app.rag.manifest import SourceManifest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestSummary:
    doc_id: int
    chunks_upserted: int


class CardPayload(BaseModel):
    knowledge_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary_md: str = Field(min_length=1)
    content_md: str = Field(default="")
    source_locator: str = Field(min_length=1)
    problem_slug: str | None = None
    problem_tags: list[str] = Field(default_factory=list)
    difficulty: str | None = None
    phases: list[str] = Field(default_factory=list)
    stuck_points: list[str] = Field(default_factory=list)
    hint_level_min: int = 0
    hint_level_max: int = 3
    has_full_solution: bool = False
    language: str | None = None
    quality_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("hint_level_min", "hint_level_max")
    @classmethod
    def validate_hint_level(cls, value: int) -> int:
        if value < 0 or value > 3:
            raise ValueError("hint_level_out_of_range")
        return value


@dataclass(frozen=True)
class TextChunkPayload:
    chunk_uid: str
    chunk_kind: str
    knowledge_type: str
    title: str
    summary_md: str
    content_md: str
    source_locator: str
    problem_slug: str | None
    problem_tags: list[str]
    difficulty: str | None
    phases: list[str]
    stuck_points: list[str]
    hint_level_min: int
    hint_level_max: int
    has_full_solution: bool
    language: str
    quality_score: float
    content_hash: str
    metadata: dict[str, Any]


async def ingest_manifest(
    session: AsyncSession,
    *,
    manifest: SourceManifest,
    root_dir: str | Path,
    embedding_provider: EmbeddingProvider | None = None,
) -> IngestSummary:
    logger.info(
        "rag_ingest_started source_name=%s source_type=%s local_path=%s",
        manifest.source_name,
        manifest.source_type,
        manifest.local_path,
    )
    source_path = Path(root_dir) / manifest.local_path
    if manifest.source_type == "manual_cards":
        cards = _load_cards(source_path, manifest)
    else:
        cards = chunk_markdown_text(
            source_name=manifest.source_name,
            text=source_path.read_text(encoding="utf-8"),
            source_locator=manifest.local_path,
            language=manifest.language,
        )
    doc = await _upsert_doc(session, manifest=manifest, source_path=source_path)
    await _upsert_chunks(
        session,
        doc=doc,
        chunks=cards,
        embedding_provider=embedding_provider,
    )
    await session.flush()
    logger.info(
        "rag_ingest_completed source_name=%s doc_id=%s chunks=%s",
        manifest.source_name,
        doc.id,
        len(cards),
    )
    return IngestSummary(doc_id=doc.id, chunks_upserted=len(cards))


def chunk_markdown_text(
    *,
    source_name: str,
    text: str,
    source_locator: str,
    language: str,
    chunk_size: int = 900,
) -> list[TextChunkPayload]:
    sections = _split_markdown_sections(text)
    chunks: list[TextChunkPayload] = []
    for heading, body in sections:
        cleaned = _clean_text(body)
        if not cleaned:
            continue
        for index, piece in enumerate(_bounded_chunks(cleaned, chunk_size)):
            title = heading or Path(source_locator).stem
            locator = f"{source_locator}#{title}"
            if index:
                locator = f"{locator}:{index + 1}"
            content_hash = content_hash_for({"locator": locator, "content": piece})
            chunks.append(
                TextChunkPayload(
                    chunk_uid=stable_chunk_uid(
                        source_name=source_name,
                        source_locator=locator,
                        title=title,
                        content_hash=content_hash,
                    ),
                    chunk_kind="source_chunk",
                    knowledge_type="source_chunk",
                    title=title,
                    summary_md=piece[:300],
                    content_md=piece,
                    source_locator=locator,
                    problem_slug=None,
                    problem_tags=[],
                    difficulty=None,
                    phases=[],
                    stuck_points=[],
                    # 原文 chunk 未经过人工分档，默认只允许复盘档使用，避免低档泄题。
                    hint_level_min=3,
                    hint_level_max=3,
                    has_full_solution=True,
                    language=language,
                    quality_score=0.5,
                    content_hash=content_hash,
                    metadata={"source": "markdown_text"},
                )
            )
    return chunks


def _load_cards(path: Path, manifest: SourceManifest) -> list[TextChunkPayload]:
    cards: list[TextChunkPayload] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        payload = CardPayload.model_validate(json.loads(line))
        content_hash = content_hash_for(payload.model_dump())
        locator = payload.source_locator or f"{manifest.local_path}:{line_number}"
        cards.append(
            TextChunkPayload(
                chunk_uid=stable_chunk_uid(
                    source_name=manifest.source_name,
                    source_locator=locator,
                    title=payload.title,
                    content_hash=content_hash,
                ),
                chunk_kind="coach_card",
                knowledge_type=payload.knowledge_type,
                title=payload.title,
                summary_md=_clean_text(payload.summary_md),
                content_md=_clean_text(payload.content_md or payload.summary_md),
                source_locator=locator,
                problem_slug=payload.problem_slug,
                problem_tags=payload.problem_tags,
                difficulty=payload.difficulty,
                phases=payload.phases,
                stuck_points=payload.stuck_points,
                hint_level_min=payload.hint_level_min,
                hint_level_max=payload.hint_level_max,
                has_full_solution=payload.has_full_solution,
                language=payload.language or manifest.language,
                quality_score=payload.quality_score,
                content_hash=content_hash,
                metadata=payload.metadata,
            )
        )
    return cards


async def _upsert_doc(
    session: AsyncSession,
    *,
    manifest: SourceManifest,
    source_path: Path,
) -> KnowledgeDoc:
    content_hash = content_hash_for(
        {
            "source_name": manifest.source_name,
            "local_path": manifest.local_path,
            "size": source_path.stat().st_size if source_path.exists() else 0,
        }
    )
    doc = await session.scalar(
        select(KnowledgeDoc).where(KnowledgeDoc.source_name == manifest.source_name)
    )
    if doc is None:
        doc = KnowledgeDoc(source_name=manifest.source_name)
        session.add(doc)
    doc.source_type = manifest.source_type
    doc.source_url = manifest.source_url
    doc.source_locator = manifest.source_locator
    doc.local_path = manifest.local_path
    doc.language = manifest.language
    doc.priority = manifest.priority
    doc.main_usage_json = manifest.main_usage
    doc.license_note = manifest.license_note
    doc.content_hash = content_hash
    doc.metadata_json = {"notes": manifest.notes or ""}
    doc.status = "active"
    await session.flush()
    return doc


async def _upsert_chunks(
    session: AsyncSession,
    *,
    doc: KnowledgeDoc,
    chunks: list[TextChunkPayload],
    embedding_provider: EmbeddingProvider | None,
) -> None:
    embeddings: list[list[float] | None] = [None] * len(chunks)
    if embedding_provider is not None and chunks:
        texts = [f"{chunk.title}\n{chunk.summary_md}" for chunk in chunks]
        embeddings = [embedding for embedding in await embedding_provider.embed(texts)]
    for index, payload in enumerate(chunks):
        chunk = await session.scalar(
            select(KnowledgeChunk).where(KnowledgeChunk.chunk_uid == payload.chunk_uid)
        )
        if chunk is None:
            chunk = KnowledgeChunk(doc_id=doc.id, chunk_uid=payload.chunk_uid)
            session.add(chunk)
        chunk.doc_id = doc.id
        chunk.chunk_kind = payload.chunk_kind
        chunk.knowledge_type = payload.knowledge_type
        chunk.title = payload.title
        chunk.summary_md = payload.summary_md
        chunk.content_md = payload.content_md
        chunk.source_locator = payload.source_locator
        chunk.problem_slug = payload.problem_slug
        chunk.problem_tags_json = payload.problem_tags
        chunk.difficulty = payload.difficulty
        chunk.phases_json = payload.phases
        chunk.stuck_points_json = payload.stuck_points
        chunk.hint_level_min = payload.hint_level_min
        chunk.hint_level_max = payload.hint_level_max
        chunk.has_full_solution = payload.has_full_solution
        chunk.language = payload.language
        chunk.quality_score = payload.quality_score
        chunk.embedding = embeddings[index]
        chunk.embedding_model = (
            embedding_provider.model_name if embedding_provider is not None else None
        )
        chunk.content_hash = payload.content_hash
        chunk.metadata_json = payload.metadata


def _split_markdown_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    current_heading = ""
    current_lines: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            if current_heading or current_lines:
                sections.append((current_heading, current_lines))
            current_heading = match.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_heading or current_lines:
        sections.append((current_heading, current_lines))
    return [(heading, "\n".join(lines)) for heading, lines in sections]


def _bounded_chunks(text: str, chunk_size: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        if len(current) + len(paragraph) + 2 <= chunk_size:
            current = f"{current}\n\n{paragraph}".strip()
            continue
        if current:
            chunks.append(current)
        current = paragraph
    if current:
        chunks.append(current)
    return chunks


def _clean_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    lines = [line.rstrip() for line in normalized.splitlines()]
    return "\n".join(lines).strip()
