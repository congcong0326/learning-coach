from __future__ import annotations

import pytest

from backend.app.prompts import get_prompt


def test_get_prompt_loads_resource_text() -> None:
    prompt = get_prompt("coach_turn")

    assert prompt.key == "coach_turn"
    assert prompt.version == "coach-turn-v2-structured"
    assert "单题 AI 教练" in prompt.instructions
    assert "reply_md" in prompt.instructions


def test_get_prompt_loads_coach_summary_resource() -> None:
    prompt = get_prompt("coach_summary")

    assert prompt.key == "coach_summary"
    assert prompt.version == "coach-summary-v1-coaching-review"
    assert "教练式单题复盘" in prompt.instructions
    assert "你做得好的地方" in prompt.instructions
    assert "需要补强的地方" in prompt.instructions


def test_prompt_registry_exposes_goal_plan_prompt_contracts() -> None:
    draft = get_prompt("goal_plan_draft")
    followup = get_prompt("goal_followup")

    assert draft.version == "goal-plan-v3-streaming"
    assert "默认语言语境：简体中文" in draft.instructions
    assert "problem_slug" in draft.instructions
    assert followup.version == "goal-plan-v3-streaming"
    assert "目标校准教练" in followup.instructions


def test_get_prompt_rejects_unknown_key() -> None:
    with pytest.raises(KeyError, match="unknown prompt key"):
        get_prompt("missing")
