from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.problem import Base, ID_TYPE


class AgentTrace(Base):
    __tablename__ = "agent_trace"
    __table_args__ = (
        Index("ix_agent_trace_session_created_at", "session_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    problem_slug: Mapped[str | None] = mapped_column(String(180), nullable=True)
    node_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phase: Mapped[str | None] = mapped_column(String(40), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retrieved_chunk_ids: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    tool_calls: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    hint_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stuck_point: Mapped[str | None] = mapped_column(String(80), nullable=True)
    should_reveal_solution: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class RetrievalTrace(Base):
    __tablename__ = "retrieval_trace"
    __table_args__ = (
        Index("ix_retrieval_trace_session_created_at", "session_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    problem_slug: Mapped[str | None] = mapped_column(String(180), nullable=True)
    query: Mapped[str] = mapped_column(String(600), nullable=False)
    retrieved_doc_ids: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    selected_chunk_ids: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    current_hint_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retrieval_intent: Mapped[str | None] = mapped_column(String(80), nullable=True)
    filtered_out_chunk_ids: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    used_in_prompt: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
