"""create problem library tables

Revision ID: 20260519_0002
Revises: 20260519_0001
Create Date: 2026-05-19 00:00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260519_0002"
down_revision: str | None = "20260519_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "problem",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("frontend_id", sa.String(length=40), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("translated_title", sa.String(length=240), nullable=False),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("statement_md", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("leetcode_url", sa.String(length=500), nullable=False),
        sa.Column(
            "is_paid_only",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
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
    )
    op.create_unique_constraint("uq_problem_frontend_id", "problem", ["frontend_id"])
    op.create_unique_constraint("uq_problem_slug", "problem", ["slug"])
    op.create_index("ix_problem_difficulty", "problem", ["difficulty"])
    op.create_index("ix_problem_updated_at", "problem", ["updated_at"])

    op.create_table(
        "problem_category",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
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
    op.create_unique_constraint(
        "uq_problem_category_slug",
        "problem_category",
        ["slug"],
    )

    op.create_table(
        "problem_category_item",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "category_id",
            sa.BigInteger(),
            sa.ForeignKey("problem_category.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "problem_id",
            sa.BigInteger(),
            sa.ForeignKey("problem.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer(), nullable=True),
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
        sa.UniqueConstraint(
            "category_id",
            "problem_id",
            name="uq_problem_category_item_category_problem",
        ),
    )
    op.create_index(
        "ix_problem_category_item_category_order",
        "problem_category_item",
        ["category_id", "sort_order"],
    )
    op.create_index(
        "ix_problem_category_item_problem",
        "problem_category_item",
        ["problem_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_problem_category_item_problem",
        table_name="problem_category_item",
    )
    op.drop_index(
        "ix_problem_category_item_category_order",
        table_name="problem_category_item",
    )
    op.drop_table("problem_category_item")
    op.drop_constraint(
        "uq_problem_category_slug",
        "problem_category",
        type_="unique",
    )
    op.drop_table("problem_category")
    op.drop_index("ix_problem_updated_at", table_name="problem")
    op.drop_index("ix_problem_difficulty", table_name="problem")
    op.drop_constraint("uq_problem_slug", "problem", type_="unique")
    op.drop_constraint("uq_problem_frontend_id", "problem", type_="unique")
    op.drop_table("problem")
