"""create llm run table

Revision ID: 20260521_0006
Revises: 20260520_0005
Create Date: 2026-05-21 00:00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260521_0006"
down_revision: str | None = "20260520_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMPTY_JSON_OBJECT = sa.text("'{}'::json")
EMPTY_TEXT = sa.text("''")


def upgrade() -> None:
    op.create_table(
        "llm_run",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "stage",
            sa.String(length=80),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column(
            "display_text_md",
            sa.Text(),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column(
            "input_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "result_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "error_code",
            sa.String(length=80),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "llm_credential_id",
            sa.BigInteger(),
            sa.ForeignKey("llm_credential.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "model_name",
            sa.String(length=120),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column(
            "related_type",
            sa.String(length=80),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column("related_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'canceled')",
            name="ck_llm_run_status",
        ),
    )
    op.create_index(
        "ix_llm_run_user_created",
        "llm_run",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_llm_run_user_kind_status",
        "llm_run",
        ["user_id", "kind", "status"],
    )
    op.create_index(
        "ix_llm_run_related",
        "llm_run",
        ["related_type", "related_id"],
    )
    op.create_index(
        "ix_llm_run_credential",
        "llm_run",
        ["llm_credential_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_llm_run_credential", table_name="llm_run")
    op.drop_index("ix_llm_run_related", table_name="llm_run")
    op.drop_index("ix_llm_run_user_kind_status", table_name="llm_run")
    op.drop_index("ix_llm_run_user_created", table_name="llm_run")
    op.drop_table("llm_run")
