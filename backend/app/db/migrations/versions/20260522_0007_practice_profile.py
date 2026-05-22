"""create practice and profile tables

Revision ID: 20260522_0007
Revises: 20260521_0006
Create Date: 2026-05-22 00:00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260522_0007"
down_revision: str | None = "20260521_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMPTY_JSON_ARRAY = sa.text("'[]'::json")
EMPTY_JSON_OBJECT = sa.text("'{}'::json")
EMPTY_TEXT = sa.text("''")


def upgrade() -> None:
    op.create_table(
        "practice_session",
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
        sa.Column(
            "problem_id",
            sa.BigInteger(),
            sa.ForeignKey("problem.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("problem_slug", sa.String(length=180), nullable=False),
        sa.Column(
            "origin_plan_version_id",
            sa.BigInteger(),
            sa.ForeignKey("study_plan_version.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "latest_plan_version_id",
            sa.BigInteger(),
            sa.ForeignKey("study_plan_version.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "latest_plan_item_id",
            sa.BigInteger(),
            sa.ForeignKey("study_plan_item.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "thread_id",
            sa.String(length=120),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column("training_mode", sa.String(length=30), nullable=False),
        sa.Column("phase", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "current_hint_level",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'questioning'"),
        ),
        sa.Column(
            "visible_hint_gear",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "max_hint_level_used",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'questioning'"),
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("latest_code_snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "final_result",
            sa.String(length=20),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column("profile_snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "profile_snapshot_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
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
            "user_id",
            "study_plan_id",
            "problem_id",
            name="uq_practice_session_user_plan_problem",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_practice_session_id_user"),
        sa.UniqueConstraint(
            "id",
            "user_id",
            "problem_id",
            name="uq_practice_session_id_user_problem",
        ),
    )
    op.create_index(
        "ix_practice_session_user_status_activity",
        "practice_session",
        ["user_id", "status", "last_activity_at"],
    )
    op.create_index(
        "ix_practice_session_plan_problem",
        "practice_session",
        ["study_plan_id", "problem_id"],
    )
    op.create_index(
        "ix_practice_session_thread",
        "practice_session",
        ["thread_id"],
    )

    op.create_table(
        "practice_event",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("practice_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "llm_run_id",
            sa.BigInteger(),
            sa.ForeignKey("llm_run.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("phase", sa.String(length=40), nullable=False),
        sa.Column("intent", sa.String(length=40), nullable=True),
        sa.Column(
            "content_md",
            sa.Text(),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column(
            "payload_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column("hint_level", sa.String(length=30), nullable=True),
        sa.Column("visible_hint_gear", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "id",
            "session_id",
            "user_id",
            name="uq_practice_event_id_session_user",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["practice_session.id", "practice_session.user_id"],
            name="fk_practice_event_session_user",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_practice_event_session_created",
        "practice_event",
        ["session_id", "created_at"],
    )
    op.create_index(
        "ix_practice_event_user_created",
        "practice_event",
        ["user_id", "created_at"],
    )
    op.create_index("ix_practice_event_llm_run", "practice_event", ["llm_run_id"])

    op.create_table(
        "code_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("practice_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.BigInteger(),
            sa.ForeignKey("practice_event.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("language", sa.String(length=30), nullable=False),
        sa.Column("code_text", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("client_revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "id",
            "session_id",
            "user_id",
            name="uq_code_snapshot_id_session_user",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["practice_session.id", "practice_session.user_id"],
            name="fk_code_snapshot_session_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "session_id", "user_id"],
            [
                "practice_event.id",
                "practice_event.session_id",
                "practice_event.user_id",
            ],
            name="fk_code_snapshot_event_context",
        ),
    )
    op.create_index(
        "ix_code_snapshot_session_created",
        "code_snapshot",
        ["session_id", "created_at"],
    )
    op.create_index(
        "ix_code_snapshot_user_created",
        "code_snapshot",
        ["user_id", "created_at"],
    )
    op.create_index("ix_code_snapshot_hash", "code_snapshot", ["code_hash"])

    op.create_table(
        "submission_feedback",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("practice_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.BigInteger(),
            sa.ForeignKey("practice_event.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "code_snapshot_id",
            sa.BigInteger(),
            sa.ForeignKey("code_snapshot.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source",
            sa.String(length=40),
            nullable=False,
            server_default=sa.text("'leetcode_manual'"),
        ),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("runtime_ms", sa.Integer(), nullable=True),
        sa.Column("memory_kb", sa.Integer(), nullable=True),
        sa.Column(
            "failed_case_text",
            sa.Text(),
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
            "raw_feedback_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["practice_session.id", "practice_session.user_id"],
            name="fk_submission_feedback_session_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "session_id", "user_id"],
            [
                "practice_event.id",
                "practice_event.session_id",
                "practice_event.user_id",
            ],
            name="fk_submission_feedback_event_context",
        ),
        sa.ForeignKeyConstraint(
            ["code_snapshot_id", "session_id", "user_id"],
            ["code_snapshot.id", "code_snapshot.session_id", "code_snapshot.user_id"],
            name="fk_submission_feedback_code_snapshot_context",
        ),
    )
    op.create_index(
        "ix_submission_feedback_session_created",
        "submission_feedback",
        ["session_id", "created_at"],
    )
    op.create_index(
        "ix_submission_feedback_user_result_created",
        "submission_feedback",
        ["user_id", "result", "created_at"],
    )
    op.create_index(
        "ix_submission_feedback_code_snapshot",
        "submission_feedback",
        ["code_snapshot_id"],
    )

    op.create_table(
        "coach_turn",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("practice_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "llm_run_id",
            sa.BigInteger(),
            sa.ForeignKey("llm_run.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_event_id",
            sa.BigInteger(),
            sa.ForeignKey("practice_event.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "assistant_event_id",
            sa.BigInteger(),
            sa.ForeignKey("practice_event.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column(
            "model_name",
            sa.String(length=120),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column("phase_before", sa.String(length=40), nullable=False),
        sa.Column("phase_after", sa.String(length=40), nullable=False),
        sa.Column("training_mode", sa.String(length=30), nullable=False),
        sa.Column(
            "diagnosed_stuck_point",
            sa.String(length=120),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column("user_intent", sa.String(length=40), nullable=False),
        sa.Column("next_action", sa.String(length=60), nullable=False),
        sa.Column("hint_level_before", sa.String(length=30), nullable=False),
        sa.Column("hint_level_after", sa.String(length=30), nullable=False),
        sa.Column("visible_hint_gear", sa.Integer(), nullable=False),
        sa.Column(
            "should_reveal_solution",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "transition_reason",
            sa.Text(),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column(
            "response_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "context_snapshot_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "input_tokens",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "output_tokens",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["practice_session.id", "practice_session.user_id"],
            name="fk_coach_turn_session_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_event_id", "session_id", "user_id"],
            [
                "practice_event.id",
                "practice_event.session_id",
                "practice_event.user_id",
            ],
            name="fk_coach_turn_user_event_context",
        ),
        sa.ForeignKeyConstraint(
            ["assistant_event_id", "session_id", "user_id"],
            [
                "practice_event.id",
                "practice_event.session_id",
                "practice_event.user_id",
            ],
            name="fk_coach_turn_assistant_event_context",
        ),
    )
    op.create_index(
        "ix_coach_turn_session_created",
        "coach_turn",
        ["session_id", "created_at"],
    )
    op.create_index(
        "ix_coach_turn_session_phase_after",
        "coach_turn",
        ["session_id", "phase_after"],
    )
    op.create_index(
        "ix_coach_turn_session_hint_after",
        "coach_turn",
        ["session_id", "hint_level_after"],
    )
    op.create_index("ix_coach_turn_llm_run", "coach_turn", ["llm_run_id"])

    op.create_table(
        "session_summary",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("practice_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "problem_id",
            sa.BigInteger(),
            sa.ForeignKey("problem.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("result", sa.String(length=30), nullable=False),
        sa.Column(
            "final_submission_result",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column("training_mode", sa.String(length=30), nullable=False),
        sa.Column(
            "phases_visited_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_ARRAY,
        ),
        sa.Column(
            "transitions_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_ARRAY,
        ),
        sa.Column(
            "main_stuck_points_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_ARRAY,
        ),
        sa.Column(
            "error_types_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_ARRAY,
        ),
        sa.Column("max_hint_level_used", sa.String(length=30), nullable=False),
        sa.Column("avg_hint_level", sa.Float(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("time_spent_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "complexity_analysis_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "invariant_summary_md",
            sa.Text(),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column(
            "review_summary_md",
            sa.Text(),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column(
            "profile_signals_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "profile_update_suggestion_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "next_recommendation_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
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
        sa.UniqueConstraint("session_id", name="uq_session_summary_session"),
        sa.UniqueConstraint(
            "id",
            "session_id",
            "user_id",
            name="uq_session_summary_id_session_user",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_session_summary_id_user"),
        sa.ForeignKeyConstraint(
            ["session_id", "user_id", "problem_id"],
            [
                "practice_session.id",
                "practice_session.user_id",
                "practice_session.problem_id",
            ],
            name="fk_session_summary_session_user_problem",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_session_summary_user_created",
        "session_summary",
        ["user_id", "created_at"],
    )
    op.create_index("ix_session_summary_problem", "session_summary", ["problem_id"])

    op.create_table(
        "user_profile_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column(
            "overall_level",
            sa.String(length=40),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column(
            "preferred_training_mode",
            sa.String(length=30),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column(
            "ability_profile_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "skill_profile_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "stuck_point_profile_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "strategy_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "recent_summary_md",
            sa.Text(),
            nullable=False,
            server_default=EMPTY_TEXT,
        ),
        sa.Column(
            "evidence_summary_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_ARRAY,
        ),
        sa.Column(
            "created_from_summary_id",
            sa.BigInteger(),
            sa.ForeignKey("session_summary.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "user_id",
            "version_number",
            name="uq_user_profile_snapshot_user_version",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_user_profile_snapshot_id_user"),
        sa.ForeignKeyConstraint(
            ["created_from_summary_id", "user_id"],
            ["session_summary.id", "session_summary.user_id"],
            name="fk_user_profile_snapshot_summary_user",
        ),
    )
    op.create_index(
        "ix_user_profile_snapshot_user_created",
        "user_profile_snapshot",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_user_profile_snapshot_user_source",
        "user_profile_snapshot",
        ["user_id", "source"],
    )

    op.create_table(
        "profile_delta",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("practice_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "summary_id",
            sa.BigInteger(),
            sa.ForeignKey("session_summary.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "previous_snapshot_id",
            sa.BigInteger(),
            sa.ForeignKey("user_profile_snapshot.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "next_snapshot_id",
            sa.BigInteger(),
            sa.ForeignKey("user_profile_snapshot.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'proposed'"),
        ),
        sa.Column(
            "patch_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "evidence_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_ARRAY,
        ),
        sa.Column(
            "merge_result_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "rejection_reason",
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
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["practice_session.id", "practice_session.user_id"],
            name="fk_profile_delta_session_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["summary_id", "session_id", "user_id"],
            [
                "session_summary.id",
                "session_summary.session_id",
                "session_summary.user_id",
            ],
            name="fk_profile_delta_summary_context",
        ),
        sa.ForeignKeyConstraint(
            ["previous_snapshot_id", "user_id"],
            ["user_profile_snapshot.id", "user_profile_snapshot.user_id"],
            name="fk_profile_delta_previous_snapshot_user",
        ),
        sa.ForeignKeyConstraint(
            ["next_snapshot_id", "user_id"],
            ["user_profile_snapshot.id", "user_profile_snapshot.user_id"],
            name="fk_profile_delta_next_snapshot_user",
        ),
    )
    op.create_index(
        "ix_profile_delta_user_created",
        "profile_delta",
        ["user_id", "created_at"],
    )
    op.create_index("ix_profile_delta_session", "profile_delta", ["session_id"])
    op.create_index("ix_profile_delta_summary", "profile_delta", ["summary_id"])
    op.create_index("ix_profile_delta_status", "profile_delta", ["status"])

    op.create_foreign_key(
        "fk_practice_session_latest_code_snapshot",
        "practice_session",
        "code_snapshot",
        ["latest_code_snapshot_id", "id", "user_id"],
        ["id", "session_id", "user_id"],
    )
    op.create_foreign_key(
        "fk_practice_session_profile_snapshot",
        "practice_session",
        "user_profile_snapshot",
        ["profile_snapshot_id", "user_id"],
        ["id", "user_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_practice_session_profile_snapshot",
        "practice_session",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_practice_session_latest_code_snapshot",
        "practice_session",
        type_="foreignkey",
    )

    op.drop_index("ix_profile_delta_status", table_name="profile_delta")
    op.drop_index("ix_profile_delta_summary", table_name="profile_delta")
    op.drop_index("ix_profile_delta_session", table_name="profile_delta")
    op.drop_index("ix_profile_delta_user_created", table_name="profile_delta")
    op.drop_table("profile_delta")

    op.drop_index(
        "ix_user_profile_snapshot_user_source",
        table_name="user_profile_snapshot",
    )
    op.drop_index(
        "ix_user_profile_snapshot_user_created",
        table_name="user_profile_snapshot",
    )
    op.drop_table("user_profile_snapshot")

    op.drop_index("ix_session_summary_problem", table_name="session_summary")
    op.drop_index("ix_session_summary_user_created", table_name="session_summary")
    op.drop_table("session_summary")

    op.drop_index("ix_coach_turn_llm_run", table_name="coach_turn")
    op.drop_index("ix_coach_turn_session_hint_after", table_name="coach_turn")
    op.drop_index("ix_coach_turn_session_phase_after", table_name="coach_turn")
    op.drop_index("ix_coach_turn_session_created", table_name="coach_turn")
    op.drop_table("coach_turn")

    op.drop_index(
        "ix_submission_feedback_code_snapshot",
        table_name="submission_feedback",
    )
    op.drop_index(
        "ix_submission_feedback_user_result_created",
        table_name="submission_feedback",
    )
    op.drop_index(
        "ix_submission_feedback_session_created",
        table_name="submission_feedback",
    )
    op.drop_table("submission_feedback")

    op.drop_index("ix_code_snapshot_hash", table_name="code_snapshot")
    op.drop_index("ix_code_snapshot_user_created", table_name="code_snapshot")
    op.drop_index("ix_code_snapshot_session_created", table_name="code_snapshot")
    op.drop_table("code_snapshot")

    op.drop_index("ix_practice_event_llm_run", table_name="practice_event")
    op.drop_index("ix_practice_event_user_created", table_name="practice_event")
    op.drop_index("ix_practice_event_session_created", table_name="practice_event")
    op.drop_table("practice_event")

    op.drop_index("ix_practice_session_thread", table_name="practice_session")
    op.drop_index("ix_practice_session_plan_problem", table_name="practice_session")
    op.drop_index(
        "ix_practice_session_user_status_activity",
        table_name="practice_session",
    )
    op.drop_table("practice_session")
