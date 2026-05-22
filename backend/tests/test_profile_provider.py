import pytest

from backend.app.services.profile_provider import ProfileSnapshot


def test_profile_snapshot_excludes_sensitive_long_form_content() -> None:
    snapshot = ProfileSnapshot(
        id=None,
        version="profile-snapshot-v1",
        source="mock_from_goal_and_plan",
        confidence="low",
        overall_level="beginner",
        preferred_training_mode="guided",
        weak_stuck_points=["edge_case"],
        strong_skill_tags=[],
        weak_skill_tags=["hash-table"],
        recent_summary="最近需要先确认边界。",
        hint_policy_hint="先追问边界，不直接给完整流程。",
        coach_strategy={"start_phase": "understand_problem"},
        evidence=[{"source": "study_plan", "summary": "计划项聚焦哈希表"}],
    )

    payload = snapshot.to_prompt_payload()

    assert payload["source"] == "mock_from_goal_and_plan"
    assert "完整代码" not in str(payload)
    assert "完整题解" not in str(payload)


@pytest.mark.asyncio
async def test_empty_profile_provider_returns_low_confidence_snapshot() -> None:
    from backend.app.services.profile_provider import EmptyProfileProvider

    provider = EmptyProfileProvider()
    snapshot = await provider.get_snapshot(
        user_id=1,
        problem_id=2,
        study_plan_id=3,
        plan_item_id=4,
    )

    assert snapshot.confidence == "low"
    assert snapshot.source == "mock_from_goal_and_plan"
