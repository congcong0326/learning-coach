from __future__ import annotations

from typing import Any, cast

import pytest

from backend.app.services.learning_plan_llm import (
    LearningPlanLlmClient,
    generate_plan_with_repair,
)


class FakeLearningPlanClient(LearningPlanLlmClient):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def followup_question(
        self,
        payload: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {"question_id": "q1", "question": "你的面试时间是？"}

    async def plan_draft(
        self,
        payload: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.calls.append("plan")
        return {
            "title": "面试冲刺计划",
            "target_snapshot": payload,
            "generation_summary_md": "按面试冲刺生成。",
            "stages": [
                {
                    "title": "数组基础",
                    "objective_md": "补齐数组基础。",
                    "focus_tags": ["array"],
                    "assessment_criteria": ["能讲清哈希表"],
                    "items": [
                        {
                            "problem_slug": "missing",
                            "difficulty": "Easy",
                            "skill_tags": ["array"],
                            "suggested_mode": "guided",
                            "recommendation_reason": "练数组",
                            "order_index": 1,
                        }
                    ],
                }
            ],
        }

    async def repair_plan_draft(
        self,
        payload: dict[str, Any],
        report: dict[str, Any],
        repair_log: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.calls.append("repair")
        repaired = await self.plan_draft(payload, [])
        repaired["stages"][0]["items"][0]["problem_slug"] = "two-sum"
        return repaired


@pytest.mark.asyncio
async def test_generate_plan_with_repair_uses_repair_when_validation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_validate(
        session: Any,
        draft: dict[str, Any],
        *,
        locked_problem_slugs: set[str] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        if draft["stages"][0]["items"][0]["problem_slug"] == "two-sum":
            return draft, {"valid": True, "issues": []}, []
        return draft, {"valid": False, "issues": ["problem_not_found"]}, []

    monkeypatch.setattr(
        "backend.app.services.learning_plan_llm.validate_and_repair_plan_draft",
        fake_validate,
    )

    client = FakeLearningPlanClient()
    draft, report, repair_log = await generate_plan_with_repair(
        session=cast(Any, None),
        client=client,
        payload={"goal_type": "interview_sprint"},
        history=[],
        max_repairs=2,
    )

    assert draft["stages"][0]["items"][0]["problem_slug"] == "two-sum"
    assert report["valid"] is True
    assert repair_log == []
    assert client.calls == ["plan", "repair", "plan"]
