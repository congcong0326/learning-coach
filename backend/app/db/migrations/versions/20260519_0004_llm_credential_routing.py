"""add llm credential routing fields

Revision ID: 20260519_0004
Revises: 20260519_0003
Create Date: 2026-05-19 00:00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260519_0004"
down_revision: str | None = "20260519_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "llm_credential",
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "llm_credential",
        sa.Column(
            "is_preferred",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "llm_credential",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "llm_credential",
        sa.Column(
            "failure_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "llm_credential",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE llm_credential "
            "SET is_preferred = is_default "
            "WHERE is_default IS NOT NULL"
        )
    )
    op.create_index(
        "ix_llm_credential_user_preferred",
        "llm_credential",
        ["user_id", "is_preferred"],
    )
    op.create_index(
        "ix_llm_credential_user_active",
        "llm_credential",
        ["user_id", "is_active"],
    )
    op.create_index(
        "ix_llm_credential_user_enabled",
        "llm_credential",
        ["user_id", "is_enabled"],
    )


def downgrade() -> None:
    op.drop_index("ix_llm_credential_user_enabled", table_name="llm_credential")
    op.drop_index("ix_llm_credential_user_active", table_name="llm_credential")
    op.drop_index("ix_llm_credential_user_preferred", table_name="llm_credential")
    op.drop_column("llm_credential", "last_used_at")
    op.drop_column("llm_credential", "failure_count")
    op.drop_column("llm_credential", "is_active")
    op.drop_column("llm_credential", "is_preferred")
    op.drop_column("llm_credential", "is_enabled")
