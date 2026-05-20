from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


GoalType = Literal["beginner", "interview_sprint", "strengthen_weakness", "maintain"]
TargetTimeline = Literal[
    "none", "within_1_month", "one_to_three_months", "over_three_months"
]
CurrentLevel = Literal["new", "easy_started", "medium_partial", "round_done_unstable"]
PreferredLanguage = Literal["c", "go", "python3", "javascript", "java"]
Weakness = Literal[
    "problem_understanding",
    "pattern",
    "complexity",
    "implementation",
    "edge_case",
    "interview_expression",
]
TrainingPreference = Literal["guided", "independent_first", "interviewer_style"]
TrainingMode = Literal["guided", "independent", "mock_interview"]
PlanStatus = Literal["active", "paused", "completed", "archived"]
VersionStatus = Literal["draft", "active", "superseded"]
StageStatus = Literal["not_started", "in_progress", "completed"]
PlanItemStatus = Literal[
    "pending", "in_progress", "completed", "skipped", "locked_completed"
]
DraftStatus = Literal[
    "collecting_input",
    "asking_followup",
    "generating",
    "validating",
    "needs_repair",
    "ready_for_review",
    "confirmed",
    "failed",
    "discarded",
]


class GoalCalibrationInput(BaseModel):
    goal_type: GoalType
    target_timeline: TargetTimeline
    weekly_days: int = Field(ge=1, le=7)
    session_minutes: int = Field(ge=15, le=180)
    current_level: CurrentLevel
    preferred_language: PreferredLanguage
    self_reported_weaknesses: list[Weakness] = Field(default_factory=list)
    extra_notes: str = Field(default="", max_length=2000)
    training_preference: TrainingPreference


class FollowupAnswer(BaseModel):
    question_id: str
    answer: str = Field(max_length=1000)


class GoalCalibrationStartResponse(BaseModel):
    draft_id: int
    status: DraftStatus
    followup_question: str | None = None
    followup_question_id: str | None = None
    remaining_followups: int


class PlanDraftItem(BaseModel):
    problem_slug: str
    title: str = ""
    difficulty: str
    skill_tags: list[str] = Field(default_factory=list)
    suggested_mode: TrainingMode
    recommendation_reason: str
    order_index: int


class PlanDraftStage(BaseModel):
    title: str
    objective_md: str
    focus_tags: list[str] = Field(default_factory=list)
    assessment_criteria: list[str] = Field(default_factory=list)
    items: list[PlanDraftItem] = Field(default_factory=list)


class PlanDraftResponse(BaseModel):
    draft_id: int
    status: DraftStatus
    target_snapshot: dict
    generation_summary_md: str
    stages: list[PlanDraftStage]
    validation_report: dict
    repair_log: list[dict]
    uncertainty_notes: list[str] = Field(default_factory=list)


class ConfirmPlanRequest(BaseModel):
    draft_id: int


class StudyPlanItemResponse(BaseModel):
    id: int
    problem_id: int
    problem_slug: str
    frontend_id: str
    title: str
    translated_title: str
    difficulty: str
    skill_tags: list[str]
    suggested_mode: str
    recommendation_reason: str
    status: str
    order_index: int
    locked: bool


class StudyPlanStageResponse(BaseModel):
    id: int
    stage_index: int
    title: str
    objective_md: str
    focus_tags: list[str]
    assessment_criteria: list[str]
    status: str
    items: list[StudyPlanItemResponse]


class StudyPlanVersionResponse(BaseModel):
    id: int
    version_number: int
    status: str
    target_snapshot: dict
    generation_summary_md: str
    adjustment_summary_md: str
    validation_report: dict
    repair_log: list[dict]
    stages: list[StudyPlanStageResponse]
    created_at: datetime
    activated_at: datetime | None


class StudyPlanResponse(BaseModel):
    id: int
    title: str
    status: str
    active_version_number: int
    created_at: datetime
    updated_at: datetime
    active_version: StudyPlanVersionResponse


class StudyPlanListItem(BaseModel):
    id: int
    title: str
    status: str
    active_version_number: int
    created_at: datetime
    updated_at: datetime


class StudyPlanListResponse(BaseModel):
    items: list[StudyPlanListItem]


class PlanItemStatusUpdateRequest(BaseModel):
    status: Literal["pending", "skipped"]


class PlanItemReorderRequest(BaseModel):
    item_ids: list[int] = Field(min_length=1)


class PlanAdjustmentRequest(BaseModel):
    reason: Literal[
        "time_change",
        "interview_date_change",
        "too_hard",
        "too_easy",
        "strengthen_topic",
        "reduce_topic",
        "language_change",
        "other",
    ]
    notes: str = Field(default="", max_length=2000)
    preferred_language: PreferredLanguage | None = None
