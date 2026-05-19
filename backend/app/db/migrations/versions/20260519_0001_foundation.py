"""create foundation tables

Revision ID: 20260519_0001
Revises:
Create Date: 2026-05-19 00:00:00

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260519_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "app_metadata",
        sa.Column("key", sa.String(length=120), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "agent_trace",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(length=80), nullable=True),
        sa.Column("thread_id", sa.String(length=120), nullable=True),
        sa.Column("problem_slug", sa.String(length=180), nullable=True),
        sa.Column("node_name", sa.String(length=120), nullable=False),
        sa.Column("phase", sa.String(length=40), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("retrieved_chunk_ids", sa.JSON(), nullable=True),
        sa.Column("tool_calls", sa.JSON(), nullable=True),
        sa.Column("hint_level", sa.Integer(), nullable=True),
        sa.Column("stuck_point", sa.String(length=80), nullable=True),
        sa.Column("should_reveal_solution", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_agent_trace_session_created_at",
        "agent_trace",
        ["session_id", "created_at"],
    )

    op.create_table(
        "retrieval_trace",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(length=80), nullable=True),
        sa.Column("problem_slug", sa.String(length=180), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("retrieved_doc_ids", sa.JSON(), nullable=True),
        sa.Column("selected_chunk_ids", sa.JSON(), nullable=True),
        sa.Column("current_hint_level", sa.Integer(), nullable=True),
        sa.Column("retrieval_intent", sa.String(length=80), nullable=True),
        sa.Column("filtered_out_chunk_ids", sa.JSON(), nullable=True),
        sa.Column("used_in_prompt", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_retrieval_trace_session_created_at",
        "retrieval_trace",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_retrieval_trace_session_created_at",
        table_name="retrieval_trace",
    )
    op.drop_table("retrieval_trace")
    op.drop_index("ix_agent_trace_session_created_at", table_name="agent_trace")
    op.drop_table("agent_trace")
    op.drop_table("app_metadata")
    op.execute("DROP EXTENSION IF EXISTS vector")
