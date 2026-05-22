from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession


_SENSITIVE_PROMPT_KEYS = {
    "answer",
    "chat",
    "code",
    "code_text",
    "content",
    "full_code",
    "full_solution",
    "prompt",
    "raw",
    "solution",
}
_SAFE_EVIDENCE_KEYS = {
    "confidence",
    "problem_id",
    "session_id",
    "source",
    "summary",
    "summary_id",
    "tag",
}


ProfileSource = Literal[
    "initial_goal_plan",
    "mock_from_goal_and_plan",
    "summary_patch",
    "manual_repair",
]
ProfileConfidence = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ProfileSnapshot:
    id: int | None
    version: str
    source: ProfileSource
    confidence: ProfileConfidence
    overall_level: str
    preferred_training_mode: str
    weak_stuck_points: list[str] = field(default_factory=list)
    strong_skill_tags: list[str] = field(default_factory=list)
    weak_skill_tags: list[str] = field(default_factory=list)
    recent_summary: str = ""
    hint_policy_hint: str = ""
    coach_strategy: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "source": self.source,
            "confidence": self.confidence,
            "overall_level": self.overall_level,
            "preferred_training_mode": self.preferred_training_mode,
            "weak_stuck_points": self.weak_stuck_points,
            "strong_skill_tags": self.strong_skill_tags,
            "weak_skill_tags": self.weak_skill_tags,
            "recent_summary": self.recent_summary[:800],
            "hint_policy_hint": self.hint_policy_hint[:400],
            "coach_strategy": _sanitize_prompt_value(self.coach_strategy),
            "evidence": [_sanitize_evidence(item) for item in self.evidence[:8]],
        }


class ProfileProvider(Protocol):
    async def get_snapshot(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        problem_id: int,
        study_plan_id: int,
        plan_item_id: int | None = None,
    ) -> ProfileSnapshot:
        ...


class EmptyProfileProvider:
    async def get_snapshot(
        self,
        session: AsyncSession | None = None,
        *,
        user_id: int,
        problem_id: int,
        study_plan_id: int,
        plan_item_id: int | None = None,
    ) -> ProfileSnapshot:
        return ProfileSnapshot(
            id=None,
            version="profile-snapshot-v1",
            source="mock_from_goal_and_plan",
            confidence="low",
            overall_level="unknown",
            preferred_training_mode="independent",
            hint_policy_hint="画像置信度低，先根据用户本轮输入判断训练阶段。",
            coach_strategy={"start_phase": "understand_problem"},
            evidence=[
                {
                    "source": "fallback",
                    "summary": "尚无长期画像，使用保守起手策略。",
                }
            ],
        )


def _sanitize_prompt_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return None
    if isinstance(value, str):
        return value[:300]
    if isinstance(value, int | float | bool) or value is None:
        return value
    if isinstance(value, list):
        return [
            sanitized
            for item in value[:8]
            if (sanitized := _sanitize_prompt_value(item, depth=depth + 1)) is not None
        ]
    if isinstance(value, dict):
        sanitized_dict: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in _SENSITIVE_PROMPT_KEYS:
                continue
            sanitized = _sanitize_prompt_value(item, depth=depth + 1)
            if sanitized is not None:
                sanitized_dict[key_text[:80]] = sanitized
        return sanitized_dict
    return str(value)[:300]


def _sanitize_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key in _SAFE_EVIDENCE_KEYS:
        if key not in evidence:
            continue
        value = evidence[key]
        if isinstance(value, str):
            safe[key] = value[:400] if key == "summary" else value[:120]
        elif isinstance(value, int | float | bool) or value is None:
            safe[key] = value
    return safe
