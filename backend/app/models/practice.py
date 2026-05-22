from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.learning import EMPTY_ARRAY, EMPTY_OBJECT, EMPTY_TEXT
from backend.app.models.problem import Base, ID_TYPE


class PracticeSession(Base):
    __tablename__ = "practice_session"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "study_plan_id",
            "problem_id",
            name="uq_practice_session_user_plan_problem",
        ),
        Index(
            "ix_practice_session_user_status_activity",
            "user_id",
            "status",
            "last_activity_at",
        ),
        Index("ix_practice_session_plan_problem", "study_plan_id", "problem_id"),
        Index("ix_practice_session_thread", "thread_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    # 会话身份只绑定 user + study_plan + problem；计划版本只做追溯，避免计划调整后丢失同一道题的训练上下文。
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    study_plan_id: Mapped[int] = mapped_column(
        ForeignKey("study_plan.id", ondelete="CASCADE"),
        nullable=False,
    )
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("problem.id", ondelete="RESTRICT"),
        nullable=False,
    )
    problem_slug: Mapped[str] = mapped_column(String(180), nullable=False)
    origin_plan_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_plan_version.id", ondelete="SET NULL"),
        nullable=True,
    )
    latest_plan_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_plan_version.id", ondelete="SET NULL"),
        nullable=True,
    )
    latest_plan_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_plan_item.id", ondelete="SET NULL"),
        nullable=True,
    )
    thread_id: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    training_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    phase: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="active",
        server_default=text("'active'"),
    )
    current_hint_level: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="questioning",
        server_default=text("'questioning'"),
    )
    visible_hint_gear: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    max_hint_level_used: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="questioning",
        server_default=text("'questioning'"),
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    latest_code_snapshot_id: Mapped[int | None] = mapped_column(ID_TYPE, nullable=True)
    final_result: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    profile_snapshot_id: Mapped[int | None] = mapped_column(ID_TYPE, nullable=True)
    profile_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PracticeEvent(Base):
    __tablename__ = "practice_event"
    __table_args__ = (
        Index("ix_practice_event_session_created", "session_id", "created_at"),
        Index("ix_practice_event_user_created", "user_id", "created_at"),
        Index("ix_practice_event_llm_run", "llm_run_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("practice_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    llm_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("llm_run.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    phase: Mapped[str] = mapped_column(String(40), nullable=False)
    intent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    content_md: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    hint_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    visible_hint_gear: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class CodeSnapshot(Base):
    __tablename__ = "code_snapshot"
    __table_args__ = (
        Index("ix_code_snapshot_session_created", "session_id", "created_at"),
        Index("ix_code_snapshot_user_created", "user_id", "created_at"),
        Index("ix_code_snapshot_hash", "code_hash"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("practice_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("practice_event.id", ondelete="SET NULL"),
        nullable=True,
    )
    language: Mapped[str] = mapped_column(String(30), nullable=False)
    code_text: Mapped[str] = mapped_column(Text, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    client_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SubmissionFeedback(Base):
    __tablename__ = "submission_feedback"
    __table_args__ = (
        Index("ix_submission_feedback_session_created", "session_id", "created_at"),
        Index("ix_submission_feedback_user_result_created", "user_id", "result", "created_at"),
        Index("ix_submission_feedback_code_snapshot", "code_snapshot_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("practice_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("practice_event.id", ondelete="SET NULL"),
        nullable=True,
    )
    code_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("code_snapshot.id", ondelete="SET NULL"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="leetcode_manual",
        server_default=text("'leetcode_manual'"),
    )
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    runtime_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory_kb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_case_text: Mapped[str] = mapped_column(
        Text,
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
    raw_feedback_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class CoachTurn(Base):
    __tablename__ = "coach_turn"
    __table_args__ = (
        Index("ix_coach_turn_session_created", "session_id", "created_at"),
        Index("ix_coach_turn_session_phase_after", "session_id", "phase_after"),
        Index("ix_coach_turn_session_hint_after", "session_id", "hint_level_after"),
        Index("ix_coach_turn_llm_run", "llm_run_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("practice_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    llm_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("llm_run.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("practice_event.id", ondelete="SET NULL"),
        nullable=True,
    )
    assistant_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("practice_event.id", ondelete="SET NULL"),
        nullable=True,
    )
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    phase_before: Mapped[str] = mapped_column(String(40), nullable=False)
    phase_after: Mapped[str] = mapped_column(String(40), nullable=False)
    training_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    diagnosed_stuck_point: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    user_intent: Mapped[str] = mapped_column(String(40), nullable=False)
    next_action: Mapped[str] = mapped_column(String(60), nullable=False)
    hint_level_before: Mapped[str] = mapped_column(String(30), nullable=False)
    hint_level_after: Mapped[str] = mapped_column(String(30), nullable=False)
    visible_hint_gear: Mapped[int] = mapped_column(Integer, nullable=False)
    should_reveal_solution: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    transition_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    response_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    context_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    input_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SessionSummary(Base):
    __tablename__ = "session_summary"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_session_summary_session"),
        Index("ix_session_summary_user_created", "user_id", "created_at"),
        Index("ix_session_summary_problem", "problem_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("practice_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("problem.id", ondelete="RESTRICT"),
        nullable=False,
    )
    result: Mapped[str] = mapped_column(String(30), nullable=False)
    final_submission_result: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="unknown",
        server_default=text("'unknown'"),
    )
    training_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    phases_visited_json: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=EMPTY_ARRAY,
    )
    transitions_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=EMPTY_ARRAY,
    )
    main_stuck_points_json: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=EMPTY_ARRAY,
    )
    error_types_json: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=EMPTY_ARRAY,
    )
    max_hint_level_used: Mapped[str] = mapped_column(String(30), nullable=False)
    avg_hint_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    complexity_analysis_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    invariant_summary_md: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    review_summary_md: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    profile_signals_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    profile_update_suggestion_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    next_recommendation_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class UserProfileSnapshot(Base):
    __tablename__ = "user_profile_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "version_number",
            name="uq_user_profile_snapshot_user_version",
        ),
        Index("ix_user_profile_snapshot_user_created", "user_id", "created_at"),
        Index("ix_user_profile_snapshot_user_source", "user_id", "source"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    overall_level: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    preferred_training_mode: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    # 长期画像保存决策摘要和证据摘要，不保存完整聊天、完整代码或完整题解，避免后续 Prompt 召回放大噪声。
    ability_profile_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    skill_profile_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    stuck_point_profile_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    strategy_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    recent_summary_md: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    evidence_summary_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=EMPTY_ARRAY,
    )
    created_from_summary_id: Mapped[int | None] = mapped_column(
        ForeignKey("session_summary.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ProfileDelta(Base):
    __tablename__ = "profile_delta"
    __table_args__ = (
        Index("ix_profile_delta_user_created", "user_id", "created_at"),
        Index("ix_profile_delta_session", "session_id"),
        Index("ix_profile_delta_summary", "summary_id"),
        Index("ix_profile_delta_status", "status"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("practice_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    summary_id: Mapped[int | None] = mapped_column(
        ForeignKey("session_summary.id", ondelete="SET NULL"),
        nullable=True,
    )
    previous_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_profile_snapshot.id", ondelete="SET NULL"),
        nullable=True,
    )
    next_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_profile_snapshot.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="proposed",
        server_default=text("'proposed'"),
    )
    patch_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    evidence_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=EMPTY_ARRAY,
    )
    merge_result_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    rejection_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
