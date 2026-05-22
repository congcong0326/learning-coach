from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.practice import ProfileDelta, UserProfileSnapshot
from backend.app.services.profile_provider import ProfileSnapshot
from backend.app.services.profile_service import ProfileServiceError, apply_profile_delta


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


@pytest.mark.asyncio
async def test_apply_profile_delta_returns_existing_snapshot_for_accepted_delta() -> None:
    previous = _profile_snapshot(snapshot_id=10, user_id=1, version_number=1)
    next_snapshot = _profile_snapshot(snapshot_id=11, user_id=1, version_number=2)
    delta = _profile_delta(
        delta_id=7,
        user_id=1,
        status="accepted",
        previous_snapshot_id=previous.id,
        next_snapshot_id=next_snapshot.id,
    )
    session = _ProfileServiceFakeSession(
        {
            (ProfileDelta, delta.id): delta,
            (UserProfileSnapshot, previous.id): previous,
            (UserProfileSnapshot, next_snapshot.id): next_snapshot,
        }
    )

    result = await apply_profile_delta(cast(AsyncSession, session), delta.id)

    assert result is next_snapshot
    assert session.added == []
    assert delta.status == "accepted"
    assert delta.next_snapshot_id == next_snapshot.id


@pytest.mark.asyncio
async def test_apply_profile_delta_rejected_delta_is_not_mutated() -> None:
    previous = _profile_snapshot(snapshot_id=20, user_id=1, version_number=1)
    delta = _profile_delta(
        delta_id=8,
        user_id=1,
        status="rejected",
        previous_snapshot_id=previous.id,
        next_snapshot_id=None,
        rejection_reason="profile_delta_missing_evidence",
    )
    session = _ProfileServiceFakeSession(
        {
            (ProfileDelta, delta.id): delta,
            (UserProfileSnapshot, previous.id): previous,
        }
    )

    with pytest.raises(ProfileServiceError):
        await apply_profile_delta(cast(AsyncSession, session), delta.id)

    assert session.added == []
    assert delta.status == "rejected"
    assert delta.next_snapshot_id is None
    assert delta.rejection_reason == "profile_delta_missing_evidence"


class _ProfileServiceFakeSession:
    def __init__(self, objects: dict[tuple[type[Any], int | None], Any]) -> None:
        self._objects = objects
        self.added: list[Any] = []
        self.flush_count = 0

    async def get(self, model: type[Any], object_id: int | None) -> Any:
        return self._objects.get((model, object_id))

    def add(self, instance: Any) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flush_count += 1


def _profile_snapshot(
    *,
    snapshot_id: int,
    user_id: int,
    version_number: int,
) -> UserProfileSnapshot:
    return UserProfileSnapshot(
        id=snapshot_id,
        user_id=user_id,
        version_number=version_number,
        source="summary_patch",
        confidence="medium",
        overall_level="beginner",
        preferred_training_mode="guided",
        ability_profile_json={},
        skill_profile_json={},
        stuck_point_profile_json={},
        strategy_json={},
        recent_summary_md="",
        evidence_summary_json=[{"source": "summary", "summary": "已有证据"}],
    )


def _profile_delta(
    *,
    delta_id: int,
    user_id: int,
    status: str,
    previous_snapshot_id: int | None,
    next_snapshot_id: int | None,
    rejection_reason: str = "",
) -> ProfileDelta:
    return ProfileDelta(
        id=delta_id,
        user_id=user_id,
        session_id=100 + delta_id,
        summary_id=None,
        previous_snapshot_id=previous_snapshot_id,
        next_snapshot_id=next_snapshot_id,
        status=status,
        patch_json={"confidence": "medium", "recent_summary": "复盘后更新画像摘要。"},
        evidence_json=[{"source": "summary", "summary": "复盘证据"}],
        merge_result_json={},
        rejection_reason=rejection_reason,
    )
