from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType

from backend.app.models.problem import Base, ID_TYPE


class VectorType(UserDefinedType[list[float]]):
    """Minimal pgvector-compatible type that remains usable in SQLite tests."""

    cache_ok = True

    def __init__(self, dimensions: int = 1536) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_: Any) -> str:
        return f"vector({self.dimensions})"

    def bind_processor(self, dialect: Any) -> Any:
        def process(value: list[float] | None) -> str | None:
            if value is None:
                return None
            # pgvector accepts bracketed numeric arrays; SQLite keeps the same
            # representation as text so tests do not need a vector extension.
            return "[" + ",".join(str(float(item)) for item in value) + "]"

        return process

    def result_processor(self, dialect: Any, coltype: Any) -> Any:
        def process(value: Any) -> list[float] | None:
            if value is None:
                return None
            if isinstance(value, list):
                return [float(item) for item in value]
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    return None
                if isinstance(parsed, list):
                    return [float(item) for item in parsed]
            return None

        return process


class KnowledgeDoc(Base):
    __tablename__ = "knowledge_doc"
    __table_args__ = (
        UniqueConstraint("source_name", name="uq_knowledge_doc_source_name"),
        Index("ix_knowledge_doc_source_name", "source_name"),
        Index("ix_knowledge_doc_status", "status"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(180), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_locator: Mapped[str | None] = mapped_column(String(500), nullable=True)
    local_path: Mapped[str] = mapped_column(String(500), nullable=False)
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    main_usage_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    license_note: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="active",
        server_default=text("'active'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    chunks: Mapped[list[KnowledgeChunk]] = relationship(
        back_populates="doc",
        cascade="all, delete-orphan",
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunk"
    __table_args__ = (
        UniqueConstraint("chunk_uid", name="uq_knowledge_chunk_uid"),
        Index("ix_knowledge_chunk_doc", "doc_id"),
        Index("ix_knowledge_chunk_chunk_uid", "chunk_uid"),
        Index("ix_knowledge_chunk_knowledge_type", "knowledge_type"),
        Index("ix_knowledge_chunk_problem_slug", "problem_slug"),
        Index("ix_knowledge_chunk_hint_range", "hint_level_min", "hint_level_max"),
        Index("ix_knowledge_chunk_quality_score", "quality_score"),
        Index("ix_knowledge_chunk_has_full_solution", "has_full_solution"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_doc.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_uid: Mapped[str] = mapped_column(String(120), nullable=False)
    chunk_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    knowledge_type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary_md: Mapped[str] = mapped_column(Text, nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    source_locator: Mapped[str] = mapped_column(String(500), nullable=False)
    problem_slug: Mapped[str | None] = mapped_column(String(180), nullable=True)
    problem_tags_json: Mapped[list[Any]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    difficulty: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phases_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    stuck_points_json: Mapped[list[Any]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    hint_level_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hint_level_max: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    has_full_solution: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    embedding: Mapped[list[float] | None] = mapped_column(VectorType(1536), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    doc: Mapped[KnowledgeDoc] = relationship(back_populates="chunks")


def stable_chunk_uid(
    *,
    source_name: str,
    source_locator: str,
    title: str,
    content_hash: str,
) -> str:
    payload = "|".join([source_name, source_locator, title, content_hash])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    normalized_source = _slug_part(source_name)
    return f"{normalized_source}:{digest}"


def content_hash_for(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _slug_part(value: str) -> str:
    chars = [item.lower() if item.isalnum() else "-" for item in value.strip()]
    slug = "".join(chars).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:48] or "source"
