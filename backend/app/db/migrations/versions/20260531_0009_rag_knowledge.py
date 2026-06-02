"""create rag knowledge tables

Revision ID: 20260531_0009
Revises: 20260526_0008
Create Date: 2026-05-31 00:09:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

from backend.app.models.rag import VectorType


revision: str = "20260531_0009"
down_revision: str | None = "20260526_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMPTY_JSON_ARRAY = sa.text("'[]'::json")
EMPTY_JSON_OBJECT = sa.text("'{}'::json")
EMPTY_TEXT = sa.text("''")


def upgrade() -> None:
    op.create_table(
        "knowledge_doc",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source_name", sa.String(length=180), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("source_locator", sa.String(length=500), nullable=True),
        sa.Column("local_path", sa.String(length=500), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.String(length=10), nullable=False),
        sa.Column("main_usage_json", sa.JSON(), nullable=False, server_default=EMPTY_JSON_ARRAY),
        sa.Column("license_note", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=80), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=EMPTY_JSON_OBJECT),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("source_name", name="uq_knowledge_doc_source_name"),
    )
    op.create_index("ix_knowledge_doc_source_name", "knowledge_doc", ["source_name"])
    op.create_index("ix_knowledge_doc_status", "knowledge_doc", ["status"])

    op.create_table(
        "knowledge_chunk",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "doc_id",
            sa.BigInteger(),
            sa.ForeignKey("knowledge_doc.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_uid", sa.String(length=120), nullable=False),
        sa.Column("chunk_kind", sa.String(length=40), nullable=False),
        sa.Column("knowledge_type", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("summary_md", sa.Text(), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("source_locator", sa.String(length=500), nullable=False),
        sa.Column("problem_slug", sa.String(length=180), nullable=True),
        sa.Column("problem_tags_json", sa.JSON(), nullable=False, server_default=EMPTY_JSON_ARRAY),
        sa.Column("difficulty", sa.String(length=20), nullable=True),
        sa.Column("phases_json", sa.JSON(), nullable=False, server_default=EMPTY_JSON_ARRAY),
        sa.Column("stuck_points_json", sa.JSON(), nullable=False, server_default=EMPTY_JSON_ARRAY),
        sa.Column("hint_level_min", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("hint_level_max", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("has_full_solution", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("embedding", VectorType(1536), nullable=True),
        sa.Column("embedding_model", sa.String(length=120), nullable=True),
        sa.Column("content_hash", sa.String(length=80), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=EMPTY_JSON_OBJECT),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("chunk_uid", name="uq_knowledge_chunk_uid"),
    )
    op.create_index("ix_knowledge_chunk_doc", "knowledge_chunk", ["doc_id"])
    op.create_index("ix_knowledge_chunk_chunk_uid", "knowledge_chunk", ["chunk_uid"])
    op.create_index("ix_knowledge_chunk_knowledge_type", "knowledge_chunk", ["knowledge_type"])
    op.create_index("ix_knowledge_chunk_problem_slug", "knowledge_chunk", ["problem_slug"])
    op.create_index(
        "ix_knowledge_chunk_hint_range",
        "knowledge_chunk",
        ["hint_level_min", "hint_level_max"],
    )
    op.create_index("ix_knowledge_chunk_quality_score", "knowledge_chunk", ["quality_score"])
    op.create_index(
        "ix_knowledge_chunk_has_full_solution",
        "knowledge_chunk",
        ["has_full_solution"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunk_has_full_solution", table_name="knowledge_chunk")
    op.drop_index("ix_knowledge_chunk_quality_score", table_name="knowledge_chunk")
    op.drop_index("ix_knowledge_chunk_hint_range", table_name="knowledge_chunk")
    op.drop_index("ix_knowledge_chunk_problem_slug", table_name="knowledge_chunk")
    op.drop_index("ix_knowledge_chunk_knowledge_type", table_name="knowledge_chunk")
    op.drop_index("ix_knowledge_chunk_chunk_uid", table_name="knowledge_chunk")
    op.drop_index("ix_knowledge_chunk_doc", table_name="knowledge_chunk")
    op.drop_table("knowledge_chunk")
    op.drop_index("ix_knowledge_doc_status", table_name="knowledge_doc")
    op.drop_index("ix_knowledge_doc_source_name", table_name="knowledge_doc")
    op.drop_table("knowledge_doc")
