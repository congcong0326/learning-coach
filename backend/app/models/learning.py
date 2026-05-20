from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.problem import Base, ID_TYPE, Problem


EMPTY_ARRAY = text("'[]'")
EMPTY_OBJECT = text("'{}'")
EMPTY_TEXT = text("''")


class GoalCalibrationDraft(Base):
    __tablename__ = "goal_calibration_draft"
    __table_args__ = (
        Index("ix_goal_calibration_draft_user_status", "user_id", "status"),
        Index("ix_goal_calibration_draft_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    llm_credential_id: Mapped[int | None] = mapped_column(
        ForeignKey("llm_credential.id", ondelete="SET NULL"),
        nullable=True,
    )
    input_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    followup_messages_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=EMPTY_ARRAY,
    )
    draft_goal_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    draft_plan_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    validation_report_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    repair_log_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=EMPTY_ARRAY,
    )
    prompt_version: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="goal-plan-v1",
        server_default=text("'goal-plan-v1'"),
    )
    model_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        server_default=text("'collecting_input'"),
    )
    error_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    confirmed_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_plan.id", ondelete="SET NULL"),
        nullable=True,
    )
    confirmed_version_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "study_plan_version.id",
            name="fk_goal_draft_confirmed_version",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
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
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class StudyPlan(Base):
    __tablename__ = "study_plan"
    __table_args__ = (
        Index("ix_study_plan_user_status", "user_id", "status"),
        Index("ix_study_plan_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'active'"),
    )
    active_version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
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

    versions: Mapped[list[StudyPlanVersion]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
    )


class StudyPlanVersion(Base):
    __tablename__ = "study_plan_version"
    __table_args__ = (
        UniqueConstraint(
            "plan_id",
            "version_number",
            name="uq_study_plan_version_plan_number",
        ),
        Index("ix_study_plan_version_plan_status", "plan_id", "status"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("study_plan.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_draft_id: Mapped[int | None] = mapped_column(
        ForeignKey("goal_calibration_draft.id", ondelete="SET NULL"),
        nullable=True,
    )
    cloned_from_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_plan_version.id", ondelete="SET NULL"),
        nullable=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'draft'"),
    )
    target_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    generation_summary_md: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    adjustment_summary_md: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    validation_report_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    repair_log_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=EMPTY_ARRAY,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    plan: Mapped[StudyPlan] = relationship(
        back_populates="versions",
        foreign_keys=[plan_id],
    )
    stages: Mapped[list[StudyPlanStage]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
    )
    items: Mapped[list[StudyPlanItem]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
    )


class StudyPlanStage(Base):
    __tablename__ = "study_plan_stage"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "stage_index",
            name="uq_study_plan_stage_version_index",
        ),
        UniqueConstraint(
            "id",
            "version_id",
            name="uq_study_plan_stage_id_version",
        ),
        Index("ix_study_plan_stage_version", "version_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("study_plan_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    objective_md: Mapped[str] = mapped_column(Text, nullable=False)
    focus_tags_json: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=EMPTY_ARRAY,
    )
    assessment_criteria_json: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=EMPTY_ARRAY,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'not_started'"),
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

    version: Mapped[StudyPlanVersion] = relationship(back_populates="stages")
    items: Mapped[list[StudyPlanItem]] = relationship(
        back_populates="stage",
        overlaps="items",
    )


class StudyPlanItem(Base):
    __tablename__ = "study_plan_item"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "problem_id",
            name="uq_study_plan_item_version_problem",
        ),
        UniqueConstraint(
            "stage_id",
            "order_index",
            name="uq_study_plan_item_stage_order",
        ),
        ForeignKeyConstraint(
            ["stage_id", "version_id"],
            ["study_plan_stage.id", "study_plan_stage.version_id"],
            name="fk_study_plan_item_stage_version",
            ondelete="CASCADE",
        ),
        Index("ix_study_plan_item_version_status", "version_id", "status"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("study_plan_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("problem.id", ondelete="RESTRICT"),
        nullable=False,
    )
    problem_slug: Mapped[str] = mapped_column(String(180), nullable=False)
    skill_tags_json: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=EMPTY_ARRAY,
    )
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    suggested_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    recommendation_reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'pending'"),
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    locked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
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

    version: Mapped[StudyPlanVersion] = relationship(
        back_populates="items",
        overlaps="items",
    )
    stage: Mapped[StudyPlanStage] = relationship(
        back_populates="items",
        overlaps="items,version",
    )
    problem: Mapped[Problem] = relationship()


class PlanChangeLog(Base):
    __tablename__ = "plan_change_log"
    __table_args__ = (Index("ix_plan_change_log_version", "version_id"),)

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("study_plan_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    change_type: Mapped[str] = mapped_column(String(40), nullable=False)
    problem_id: Mapped[int | None] = mapped_column(
        ForeignKey("problem.id", ondelete="SET NULL"),
        nullable=True,
    )
    detail_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    reason_md: Mapped[str] = mapped_column(
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
