from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


PracticePhase = Literal[
    "understand_problem",
    "propose_bruteforce",
    "optimize_solution",
    "define_invariant",
    "write_code",
    "review_code",
    "submit_to_leetcode",
    "analyze_feedback",
    "summarize",
]
HintLevel = Literal["questioning", "direction", "key_hint", "reflection"]
PracticeSessionStatus = Literal[
    "active",
    "waiting_user",
    "waiting_leetcode",
    "summarizing",
    "completed",
    "archived",
]
PracticeEventType = Literal[
    "session_started",
    "user_message",
    "assistant_message",
    "code_saved",
    "submission_feedback",
    "phase_changed",
    "summary_generated",
    "profile_updated",
]
PracticeRole = Literal["user", "assistant", "system", "tool"]
UserIntent = Literal[
    "describe_idea",
    "stuck",
    "request_hint",
    "code_review",
    "submit_feedback",
    "request_summary",
    "unknown",
]
SubmissionResult = Literal["ac", "wa", "tle", "re", "mle", "ce", "unknown"]
CodeSnapshotSource = Literal[
    "paste",
    "manual_save",
    "before_review",
    "chat_review",
    "before_submit",
    "final",
]
CodeAttemptQuality = Literal["pending", "needs_fix", "ready_to_submit"]
ProfileConfidence = Literal["low", "medium", "high"]
ProfileSource = Literal[
    "initial_goal_plan",
    "mock_from_goal_and_plan",
    "summary_patch",
    "manual_repair",
]
DiagnosisConfidence = Literal["low", "medium", "high"]


class StuckPointDiagnosis(BaseModel):
    category: str = Field(min_length=1, max_length=120)
    evidence: list[str] = Field(min_length=1, max_length=8)
    confidence: DiagnosisConfidence


class CodeReviewResult(BaseModel):
    quality_status: CodeAttemptQuality
    issue_type: str = Field(min_length=1, max_length=120)
    suspected_region: str = Field(default="", max_length=240)
    explanation_md: str = Field(min_length=1, max_length=2400)
    suggested_check: str = Field(default="", max_length=1200)


class CoachAction(BaseModel):
    phase_after: PracticePhase
    diagnosed_stuck_point: StuckPointDiagnosis
    next_action: str = Field(min_length=1, max_length=120)
    reply_md: str = Field(min_length=1, max_length=6000)
    should_reveal_solution: bool
    code_review: CodeReviewResult | None = None


class ProfileSnapshotPayload(BaseModel):
    id: int | None = None
    version: str
    source: ProfileSource
    confidence: ProfileConfidence
    overall_level: str
    preferred_training_mode: str
    weak_stuck_points: list[str] = Field(default_factory=list)
    strong_skill_tags: list[str] = Field(default_factory=list)
    weak_skill_tags: list[str] = Field(default_factory=list)
    recent_summary: str = ""
    hint_policy_hint: str = ""
    coach_strategy: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class PracticeMessageCreate(BaseModel):
    intent: UserIntent = "unknown"
    content_md: str = Field(min_length=1, max_length=12000)
    requested_hint_level: HintLevel | None = None


class CodeSnapshotCreate(BaseModel):
    language: Literal["c", "go", "python3", "javascript", "java"]
    code_text: str = Field(min_length=1, max_length=60000)
    source: CodeSnapshotSource = "manual_save"
    client_revision: int = Field(ge=0)


class SubmissionFeedbackCreate(BaseModel):
    code_snapshot_id: int | None = None
    result: SubmissionResult
    failed_case_text: str = Field(default="", max_length=12000)
    error_message: str = Field(default="", max_length=12000)
    note_md: str = Field(default="", max_length=4000)
    runtime_ms: int | None = Field(default=None, ge=0)
    memory_kb: int | None = Field(default=None, ge=0)


class PracticeEventResponse(BaseModel):
    id: int
    event_type: PracticeEventType
    role: PracticeRole
    phase: PracticePhase
    intent: UserIntent | None
    content_md: str
    payload: dict[str, Any]
    hint_level: HintLevel | None
    visible_hint_gear: HintLevel | None
    created_at: datetime


class CodeAttemptResponse(BaseModel):
    snapshot_id: int
    event_id: int | None
    language: str
    source: str
    client_revision: int
    code_hash: str
    code_preview: str
    code_text: str
    quality_status: CodeAttemptQuality
    quality_comment: str
    created_at: datetime


class SubmissionFeedbackHistoryResponse(BaseModel):
    id: int
    event_id: int | None
    code_snapshot_id: int | None
    result: SubmissionResult
    failed_case_text: str
    error_message: str
    note_md: str
    runtime_ms: int | None
    memory_kb: int | None
    created_at: datetime


class PracticeSessionReviewResponse(BaseModel):
    session_id: int
    summary_id: int
    problem_id: int
    problem_slug: str
    final_result: str
    training_mode: str
    phases_visited: list[str] = Field(default_factory=list)
    main_stuck_points: list[str] = Field(default_factory=list)
    error_types: list[str] = Field(default_factory=list)
    max_hint_level_used: HintLevel | None
    attempt_count: int
    complexity_analysis: dict[str, Any] = Field(default_factory=dict)
    core_idea_md: str = ""
    review_summary_md: str = ""
    profile_signals: dict[str, Any] = Field(default_factory=dict)
    profile_update_suggestion: dict[str, Any] = Field(default_factory=dict)
    profile_delta: dict[str, Any] = Field(default_factory=dict)
    next_recommendation: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime


class PracticeDashboardResponse(BaseModel):
    completed_problem_count: int
    common_stuck_points: list[dict[str, Any]] = Field(default_factory=list)
    average_hint_gear: float | None = None
    highest_hint_level: HintLevel | None = None
    recent_profile_summary: str = ""
    profile_snapshot_id: int | None = None


class PracticeSessionResponse(BaseModel):
    id: int
    study_plan_id: int
    problem_id: int
    problem_slug: str
    latest_plan_version_id: int
    latest_plan_item_id: int
    training_mode: str
    phase: PracticePhase
    status: PracticeSessionStatus
    current_hint_level: HintLevel
    visible_hint_gear: HintLevel
    max_hint_level_used: HintLevel | None
    attempt_count: int
    final_result: SubmissionResult | None
    profile_snapshot: ProfileSnapshotPayload
    events: list[PracticeEventResponse] = Field(default_factory=list)
    code_attempts: list[CodeAttemptResponse] = Field(default_factory=list)
    submission_feedbacks: list[SubmissionFeedbackHistoryResponse] = Field(
        default_factory=list
    )
    created_at: datetime
    updated_at: datetime


class PracticeMessageResponse(BaseModel):
    event_id: int
    run_id: int
    session_id: int


class CodeSnapshotResponse(BaseModel):
    id: int
    language: str
    source: str
    client_revision: int
    code_hash: str
    created_at: datetime


class SubmissionFeedbackResponse(BaseModel):
    id: int
    result: SubmissionResult
    event_id: int
    code_snapshot_id: int | None
    note_md: str = ""
    created_at: datetime
