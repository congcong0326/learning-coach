from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.problem import Base, ID_TYPE


EMPTY_OBJECT = text("'{}'")
EMPTY_TEXT = text("''")


class LlmRun(Base):
    __tablename__ = "llm_run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'canceled')",
            name="ck_llm_run_status",
        ),
        Index("ix_llm_run_user_created", "user_id", "created_at"),
        Index("ix_llm_run_user_kind_status", "user_id", "kind", "status"),
        Index("ix_llm_run_related", "related_type", "related_id"),
        Index("ix_llm_run_credential", "llm_credential_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    stage: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="queued",
        server_default=text("'queued'"),
    )
    display_text_md: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    input_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    result_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    error_code: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    error_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    llm_credential_id: Mapped[int | None] = mapped_column(
        ForeignKey("llm_credential.id", ondelete="SET NULL"),
        nullable=True,
    )
    model_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    related_type: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    related_id: Mapped[int | None] = mapped_column(ID_TYPE, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
