from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from backend.app.services.llm_run_registry import (
    CoachSummaryHandler,
    CoachTurnHandler,
    GoalFollowupHandler,
    GoalPlanGenerateHandler,
    handler_for_kind,
    related_from_payload,
    requires_model_for_kind,
    supported_run_kinds,
)


def test_supported_run_kinds_contains_current_streaming_flows() -> None:
    assert supported_run_kinds() == {
        "coach_summary",
        "coach_turn",
        "goal_followup",
        "goal_plan_generate",
    }


def test_related_from_payload_returns_empty_for_initial_goal_followup() -> None:
    related_type, related_id = related_from_payload(
        "goal_followup",
        {
            "goal_type": "interview_sprint",
            "target_timeline": "within_1_month",
        },
    )

    assert related_type == ""
    assert related_id is None


def test_related_from_payload_maps_goal_followup_answer_to_draft() -> None:
    related_type, related_id = related_from_payload(
        "goal_followup",
        {"draft_id": 15, "question_id": "q1", "answer": "边界条件容易漏"},
    )

    assert related_type == "goal_calibration_draft"
    assert related_id == 15


def test_related_from_payload_maps_goal_plan_generate_to_draft() -> None:
    related_type, related_id = related_from_payload(
        "goal_plan_generate",
        {"draft_id": 15},
    )

    assert related_type == "goal_calibration_draft"
    assert related_id == 15


def test_related_from_payload_rejects_boolean_draft_id() -> None:
    related_type, related_id = related_from_payload(
        "goal_plan_generate",
        {"draft_id": True},
    )

    assert related_type == ""
    assert related_id is None


def test_related_from_payload_maps_study_plan_adjustment_to_plan() -> None:
    related_type, related_id = related_from_payload(
        "study_plan_adjustment",
        {"plan_id": 9},
    )

    assert related_type == "study_plan"
    assert related_id == 9


def test_related_from_payload_maps_coach_turn_to_practice_session() -> None:
    related_type, related_id = related_from_payload(
        "coach_turn",
        {"session_id": 23},
    )

    assert related_type == "practice_session"
    assert related_id == 23


def test_related_from_payload_maps_coach_summary_to_practice_session() -> None:
    related_type, related_id = related_from_payload(
        "coach_summary",
        {"session_id": 23},
    )

    assert related_type == "practice_session"
    assert related_id == 23


def test_related_from_payload_rejects_boolean_plan_id() -> None:
    related_type, related_id = related_from_payload(
        "study_plan_adjustment",
        {"plan_id": True},
    )

    assert related_type == ""
    assert related_id is None


def test_handler_for_kind_returns_registered_handler() -> None:
    assert isinstance(handler_for_kind("goal_followup"), GoalFollowupHandler)
    assert isinstance(handler_for_kind("goal_plan_generate"), GoalPlanGenerateHandler)
    assert isinstance(handler_for_kind("coach_turn"), CoachTurnHandler)
    assert isinstance(handler_for_kind("coach_summary"), CoachSummaryHandler)
    assert handler_for_kind("study_plan_adjustment") is None


def test_current_model_backed_run_kinds_require_model_asset() -> None:
    assert requires_model_for_kind("goal_followup") is True
    assert requires_model_for_kind("goal_plan_generate") is True
    assert requires_model_for_kind("coach_turn") is True
    assert requires_model_for_kind("coach_summary") is True
    assert requires_model_for_kind("study_plan_adjustment") is False


@pytest.mark.asyncio
async def test_goal_followup_handler_delegates_to_existing_flow(monkeypatch) -> None:
    calls: list[tuple[str, int, str]] = []

    async def fake_flow(
        session: Any,
        *,
        user_id: int,
        run: Any,
        provider: Any,
        model_name: str,
        publish: Any,
    ) -> dict[str, Any]:
        assert session == "session"
        assert run == "run"
        assert provider == "provider"
        assert publish == "publish"
        calls.append(("followup", user_id, model_name))
        return {"draft_id": 15, "status": "asking_followup"}

    monkeypatch.setattr(
        "backend.app.services.llm_run_registry.run_goal_followup",
        fake_flow,
    )
    context = SimpleNamespace(
        session="session",
        user_id=42,
        run="run",
        provider="provider",
        model_name="gpt-test",
        publish="publish",
    )

    result = await GoalFollowupHandler().execute(cast(Any, context))

    assert result == {"draft_id": 15, "status": "asking_followup"}
    assert calls == [("followup", 42, "gpt-test")]


@pytest.mark.asyncio
async def test_goal_plan_handler_delegates_to_existing_flow(monkeypatch) -> None:
    calls: list[tuple[str, int, str]] = []

    async def fake_flow(
        session: Any,
        *,
        user_id: int,
        run: Any,
        provider: Any,
        model_name: str,
        publish: Any,
    ) -> dict[str, Any]:
        assert session == "session"
        assert run == "run"
        assert provider == "provider"
        assert publish == "publish"
        calls.append(("plan", user_id, model_name))
        return {"draft_id": 15, "stage_count": 2, "item_count": 8}

    monkeypatch.setattr(
        "backend.app.services.llm_run_registry.run_goal_plan_generate",
        fake_flow,
    )
    context = SimpleNamespace(
        session="session",
        user_id=42,
        run="run",
        provider="provider",
        model_name="gpt-test",
        publish="publish",
    )

    result = await GoalPlanGenerateHandler().execute(cast(Any, context))

    assert result == {"draft_id": 15, "stage_count": 2, "item_count": 8}
    assert calls == [("plan", 42, "gpt-test")]
