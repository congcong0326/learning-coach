from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


LlmRunKind = Literal[
    "goal_followup",
    "goal_plan_generate",
    "study_plan_adjustment",
    "coach_turn",
    "coach_summary",
    "coach_message",
    "code_review",
    "reflection",
]
LlmRunStatus = Literal["pending", "running", "succeeded", "failed", "canceled"]


class LlmRunCreateRequest(BaseModel):
    kind: LlmRunKind
    payload: dict[str, Any] = Field(default_factory=dict)


class LlmRunCreateResponse(BaseModel):
    run_id: int
    kind: LlmRunKind
    status: LlmRunStatus
    stage: str
    stream_url: str


class LlmRunStatusResponse(BaseModel):
    run_id: int
    kind: str
    status: LlmRunStatus
    stage: str
    display_text_md: str
    result: dict[str, Any]
    error_code: str | None
    error_message: str | None
    can_retry: bool
    created_at: str
    started_at: str | None
    finished_at: str | None


class LlmRunCancelResponse(BaseModel):
    run_id: int
    status: LlmRunStatus
    cancel_requested: bool
