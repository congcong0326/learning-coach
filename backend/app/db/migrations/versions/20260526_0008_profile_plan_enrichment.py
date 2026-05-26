"""create profile plan enrichment draft table

Revision ID: 20260526_0008
Revises: 20260522_0007
Create Date: 2026-05-26 00:00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260526_0008"
down_revision: str | None = "20260522_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMPTY_JSON_ARRAY = sa.text("'[]'::json")
EMPTY_JSON_OBJECT = sa.text("'{}'::json")
EMPTY_TEXT = sa.text("''")


def upgrade() -> None:
    op.create_table(
        "profile_plan_enrichment_draft",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "study_plan_id",
            sa.BigInteger(),
            sa.ForeignKey("study_plan.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("study_plan_version_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "profile_snapshot_id",
            sa.BigInteger(),
            sa.ForeignKey("user_profile_snapshot.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "llm_run_id",
            sa.BigInteger(),
            sa.ForeignKey("llm_run.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'generating'"),
        ),
        sa.Column(
            "user_intent_md",
            sa.Text(),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("difficulty_preference", sa.String(length=30), nullable=False),
        sa.Column(
            "context_summary_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "candidate_problem_ids_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_ARRAY,
        ),
        sa.Column(
            "model_output_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "validation_report_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "confirmed_item_ids_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_ARRAY,
        ),
        sa.Column(
            "error_summary",
            sa.Text(),
            nullable=False,
            server_default=EMPTY_TEXT,
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
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["study_plan_version_id", "study_plan_id"],
            ["study_plan_version.id", "study_plan_version.plan_id"],
            name="fk_profile_plan_enrichment_version_plan",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_profile_plan_enrichment_user_status",
        "profile_plan_enrichment_draft",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_profile_plan_enrichment_plan_created",
        "profile_plan_enrichment_draft",
        ["study_plan_id", "created_at"],
    )
    op.create_index(
        "ix_profile_plan_enrichment_llm_run",
        "profile_plan_enrichment_draft",
        ["llm_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_profile_plan_enrichment_llm_run",
        table_name="profile_plan_enrichment_draft",
    )
    op.drop_index(
        "ix_profile_plan_enrichment_plan_created",
        table_name="profile_plan_enrichment_draft",
    )
    op.drop_index(
        "ix_profile_plan_enrichment_user_status",
        table_name="profile_plan_enrichment_draft",
    )
    op.drop_table("profile_plan_enrichment_draft")
