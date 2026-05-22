from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession


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
            "coach_strategy": self.coach_strategy,
            "evidence": self.evidence[:8],
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
