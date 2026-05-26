from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentTraceResponse(BaseModel):
    id: int
    session_id: str | None
    thread_id: str | None
    problem_slug: str | None
    node_name: str
    phase: str | None
    hint_level: int | None
    model_name: str | None
    latency_ms: int | None
    stuck_point: str | None
    should_reveal_solution: bool | None
    input_summary: dict[str, Any] = Field(default_factory=dict)
    output_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
