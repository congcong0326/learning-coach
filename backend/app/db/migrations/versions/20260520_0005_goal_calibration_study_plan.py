"""create goal calibration and study plan tables

Revision ID: 20260520_0005
Revises: 20260519_0004
Create Date: 2026-05-20 00:00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260520_0005"
down_revision: str | None = "20260519_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMPTY_JSON_ARRAY = sa.text("'[]'::json")
EMPTY_JSON_OBJECT = sa.text("'{}'::json")
EMPTY_TEXT = sa.text("''")


def upgrade() -> None:
    op.create_table(
        "study_plan",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "active_version_number",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
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
    op.create_index(
        "ix_study_plan_user_status",
        "study_plan",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_study_plan_user_updated",
        "study_plan",
        ["user_id", "updated_at"],
    )

    op.create_table(
        "goal_calibration_draft",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "llm_credential_id",
            sa.BigInteger(),
            sa.ForeignKey("llm_credential.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column(
            "followup_messages_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_ARRAY,
        ),
        sa.Column(
            "draft_goal_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "draft_plan_json",
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
            "repair_log_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_ARRAY,
        ),
        sa.Column(
            "prompt_version",
            sa.String(length=80),
            nullable=False,
            server_default=sa.text("'goal-plan-v1'"),
        ),
        sa.Column(
            "model_name",
            sa.String(length=120),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column(
            "status",
            sa.String(length=40),
            nullable=False,
            server_default=sa.text("'collecting_input'"),
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column(
            "confirmed_plan_id",
            sa.BigInteger(),
            sa.ForeignKey("study_plan.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("confirmed_version_id", sa.BigInteger(), nullable=True),
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
    )
    op.create_index(
        "ix_goal_calibration_draft_user_status",
        "goal_calibration_draft",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_goal_calibration_draft_created",
        "goal_calibration_draft",
        ["created_at"],
    )

    op.create_table(
        "study_plan_version",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "plan_id",
            sa.BigInteger(),
            sa.ForeignKey("study_plan.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_draft_id",
            sa.BigInteger(),
            sa.ForeignKey("goal_calibration_draft.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "cloned_from_version_id",
            sa.BigInteger(),
            sa.ForeignKey("study_plan_version.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("target_snapshot_json", sa.JSON(), nullable=False),
        sa.Column(
            "generation_summary_md",
            sa.Text(),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column(
            "adjustment_summary_md",
            sa.Text(),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column(
            "validation_report_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "repair_log_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_ARRAY,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "plan_id",
            "version_number",
            name="uq_study_plan_version_plan_number",
        ),
    )
    op.create_index(
        "ix_study_plan_version_plan_status",
        "study_plan_version",
        ["plan_id", "status"],
    )
    op.create_foreign_key(
        "fk_goal_draft_confirmed_version",
        "goal_calibration_draft",
        "study_plan_version",
        ["confirmed_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "study_plan_stage",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "version_id",
            sa.BigInteger(),
            sa.ForeignKey("study_plan_version.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("objective_md", sa.Text(), nullable=False),
        sa.Column(
            "focus_tags_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_ARRAY,
        ),
        sa.Column(
            "assessment_criteria_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_ARRAY,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'not_started'"),
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
        sa.UniqueConstraint(
            "version_id",
            "stage_index",
            name="uq_study_plan_stage_version_index",
        ),
        sa.UniqueConstraint(
            "id",
            "version_id",
            name="uq_study_plan_stage_id_version",
        ),
    )
    op.create_index(
        "ix_study_plan_stage_version",
        "study_plan_stage",
        ["version_id"],
    )

    op.create_table(
        "study_plan_item",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "version_id",
            sa.BigInteger(),
            sa.ForeignKey("study_plan_version.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "problem_id",
            sa.BigInteger(),
            sa.ForeignKey("problem.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("problem_slug", sa.String(length=180), nullable=False),
        sa.Column(
            "skill_tags_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_ARRAY,
        ),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("suggested_mode", sa.String(length=30), nullable=False),
        sa.Column("recommendation_reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column(
            "locked",
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
        sa.UniqueConstraint(
            "version_id",
            "problem_id",
            name="uq_study_plan_item_version_problem",
        ),
        sa.UniqueConstraint(
            "stage_id",
            "order_index",
            name="uq_study_plan_item_stage_order",
        ),
        sa.ForeignKeyConstraint(
            ["stage_id", "version_id"],
            ["study_plan_stage.id", "study_plan_stage.version_id"],
            name="fk_study_plan_item_stage_version",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_study_plan_item_version_status",
        "study_plan_item",
        ["version_id", "status"],
    )

    op.create_table(
        "plan_change_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "version_id",
            sa.BigInteger(),
            sa.ForeignKey("study_plan_version.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("change_type", sa.String(length=40), nullable=False),
        sa.Column(
            "problem_id",
            sa.BigInteger(),
            sa.ForeignKey("problem.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "detail_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "reason_md",
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
    )
    op.create_index(
        "ix_plan_change_log_version",
        "plan_change_log",
        ["version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_plan_change_log_version", table_name="plan_change_log")
    op.drop_table("plan_change_log")

    op.drop_index("ix_study_plan_item_version_status", table_name="study_plan_item")
    op.drop_table("study_plan_item")

    op.drop_index("ix_study_plan_stage_version", table_name="study_plan_stage")
    op.drop_table("study_plan_stage")

    op.drop_constraint(
        "fk_goal_draft_confirmed_version",
        "goal_calibration_draft",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_study_plan_version_plan_status",
        table_name="study_plan_version",
    )
    op.drop_table("study_plan_version")

    op.drop_index(
        "ix_goal_calibration_draft_created",
        table_name="goal_calibration_draft",
    )
    op.drop_index(
        "ix_goal_calibration_draft_user_status",
        table_name="goal_calibration_draft",
    )
    op.drop_table("goal_calibration_draft")

    op.drop_index("ix_study_plan_user_updated", table_name="study_plan")
    op.drop_index("ix_study_plan_user_status", table_name="study_plan")
    op.drop_table("study_plan")
