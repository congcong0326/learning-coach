"""create auth and llm credential tables

Revision ID: 20260519_0003
Revises: 20260519_0002
Create Date: 2026-05-19 00:00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260519_0003"
down_revision: str | None = "20260519_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
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
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("username", name="uq_app_user_username"),
        sa.UniqueConstraint("email", name="uq_app_user_email"),
    )

    op.create_table(
        "auth_session",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "session_token_hash",
            name="uq_auth_session_token_hash",
        ),
    )
    op.create_index(
        "ix_auth_session_user_expires",
        "auth_session",
        ["user_id", "expires_at"],
    )

    op.create_table(
        "llm_credential",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "provider",
            sa.String(length=40),
            nullable=False,
            server_default=sa.text("'openai'"),
        ),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column(
            "api_mode",
            sa.String(length=40),
            nullable=False,
            server_default=sa.text("'responses'"),
        ),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=False),
        sa.Column("api_key_mask", sa.String(length=80), nullable=False),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'untested'"),
        ),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
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
    op.create_index(
        "ix_llm_credential_user_default",
        "llm_credential",
        ["user_id", "is_default"],
    )
    op.create_index(
        "ix_llm_credential_user_provider",
        "llm_credential",
        ["user_id", "provider"],
    )


def downgrade() -> None:
    op.drop_index("ix_llm_credential_user_provider", table_name="llm_credential")
    op.drop_index("ix_llm_credential_user_default", table_name="llm_credential")
    op.drop_table("llm_credential")
    op.drop_index("ix_auth_session_user_expires", table_name="auth_session")
    op.drop_table("auth_session")
    op.drop_table("app_user")
