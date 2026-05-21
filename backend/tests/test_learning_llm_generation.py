from __future__ import annotations

import logging
from typing import Any, cast

import pytest

from backend.app.services.learning_plan_llm import (
    DEFAULT_LANGUAGE_CONTEXT_INSTRUCTIONS,
    LearningPlanLlmClient,
    PLAN_JSON_SCHEMA,
    PLAN_DRAFT_INSTRUCTIONS,
    REPAIR_PLAN_INSTRUCTIONS,
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


def test_plan_json_schema_requires_stage_items_with_problem_slugs() -> None:
    stage_schema = PLAN_JSON_SCHEMA["properties"]["stages"]["items"]
    item_schema = stage_schema["properties"]["items"]["items"]

    assert "items" in stage_schema["required"]
    assert "problem_slug" in item_schema["required"]
    assert "suggested_mode" in item_schema["required"]


def test_plan_prompts_inject_default_chinese_language_context() -> None:
    assert "默认语言语境：简体中文" in DEFAULT_LANGUAGE_CONTEXT_INSTRUCTIONS
    assert "默认语言语境：简体中文" in PLAN_DRAFT_INSTRUCTIONS
    assert "默认语言语境：简体中文" in REPAIR_PLAN_INSTRUCTIONS
    assert "面向用户展示的文本字段必须使用简体中文" in PLAN_DRAFT_INSTRUCTIONS
    assert "problem_slug" in PLAN_DRAFT_INSTRUCTIONS


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


@pytest.mark.asyncio
async def test_generate_plan_with_repair_logs_validation_details(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def fake_validate(
        session: Any,
        draft: dict[str, Any],
        *,
        locked_problem_slugs: set[str] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        return (
            draft,
            {"valid": False, "issues": ["empty_problem_library"], "item_count": 0},
            [],
        )

    monkeypatch.setattr(
        "backend.app.services.learning_plan_llm.validate_and_repair_plan_draft",
        fake_validate,
    )
    caplog.set_level(logging.INFO, logger="backend.app.services.learning_plan_llm")

    client = FakeLearningPlanClient()
    _draft, report, _repair_log = await generate_plan_with_repair(
        session=cast(Any, None),
        client=client,
        payload={"goal_type": "interview_sprint"},
        history=[],
        max_repairs=0,
    )

    assert report["valid"] is False
    assert (
        "learning plan draft validation result "
        "attempt=0 valid=False issues=empty_problem_library item_count=0"
    ) in caplog.text
