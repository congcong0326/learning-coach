from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.practice import ProfileDelta, UserProfileSnapshot
from backend.app.services.profile_provider import ProfileSnapshot
from backend.app.services.profile_service import (
    ProfileServiceError,
    apply_profile_delta,
    apply_profile_delta_result,
    validate_profile_patch,
)


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
        coach_strategy={
            "start_phase": "understand_problem",
            "nested": {"code_text": "完整代码: class Solution: pass"},
        },
        evidence=[
            {
                "source": "study_plan",
                "summary": "计划项聚焦哈希表",
                "raw": "完整题解: 直接返回答案",
            }
        ],
    )

    payload = snapshot.to_prompt_payload()

    assert payload["source"] == "mock_from_goal_and_plan"
    assert "完整代码" not in str(payload)
    assert "完整题解" not in str(payload)
    assert "code_text" not in str(payload)
    assert "raw" not in str(payload)


def test_profile_snapshot_sanitizes_nested_strategy_and_evidence() -> None:
    snapshot = ProfileSnapshot(
        id=1,
        version="profile-snapshot-v2",
        source="summary_patch",
        confidence="medium",
        overall_level="beginner",
        preferred_training_mode="guided",
        coach_strategy={
            "start_phase": "understand_problem",
            "steps": [
                {"tag": "boundary", "content": "完整代码不应进入画像"},
                {"safe": "保留安全策略摘要"},
            ],
            "full_solution": "完整题解不应进入画像",
        },
        evidence=[
            {
                "source": "session_summary",
                "summary": "复盘证据",
                "session_id": 7,
                "code": "完整代码",
                "answer": "完整题解",
            }
        ],
    )

    payload = snapshot.to_prompt_payload()

    assert payload["coach_strategy"]["start_phase"] == "understand_problem"
    assert "完整代码" not in str(payload)
    assert "完整题解" not in str(payload)
    assert "content" not in str(payload)
    assert "full_solution" not in str(payload)
    assert payload["evidence"] == [
        {"source": "session_summary", "summary": "复盘证据", "session_id": 7}
    ]


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


def test_validate_profile_patch_rejects_invalid_confidence_source_and_unknown_key() -> None:
    evidence = [{"source": "summary", "summary": "复盘证据"}]

    with pytest.raises(ProfileServiceError):
        validate_profile_patch({"confidence": "certain"}, evidence)

    with pytest.raises(ProfileServiceError):
        validate_profile_patch({"source": "unknown_source"}, evidence)

    with pytest.raises(ProfileServiceError):
        validate_profile_patch({"unexpected": "value"}, evidence)


def test_validate_profile_patch_requires_structured_evidence_and_sections() -> None:
    with pytest.raises(ProfileServiceError):
        validate_profile_patch(
            {"skill_profile_json": {}},
            [{"source": "summary", "summary": ""}],
        )

    with pytest.raises(ProfileServiceError):
        validate_profile_patch(
            {"strategy_json": "先追问"},
            [{"source": "summary", "summary": "复盘证据"}],
        )

    result = validate_profile_patch(
        {"strategy_json": {"hint_policy_hint": "先追问边界"}},
        [{"source": "summary", "summary": "复盘证据"}],
    )

    assert result.accepted is True


def test_validate_profile_patch_rejects_too_deep_profile_sections() -> None:
    patch = {"strategy_json": {"a": {"b": {"c": {"d": {"e": "too deep"}}}}}}

    with pytest.raises(ProfileServiceError):
        validate_profile_patch(
            patch,
            [{"source": "summary", "summary": "复盘证据"}],
        )


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
        },
        execute_results=[delta, object(), previous],
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
        },
        execute_results=[delta, object(), previous],
    )

    with pytest.raises(ProfileServiceError):
        await apply_profile_delta(cast(AsyncSession, session), delta.id)

    assert session.added == []
    assert delta.status == "rejected"
    assert delta.next_snapshot_id is None
    assert delta.rejection_reason == "profile_delta_missing_evidence"


@pytest.mark.asyncio
async def test_apply_profile_delta_result_marks_missing_evidence_rejected() -> None:
    previous = _profile_snapshot(
        snapshot_id=30,
        user_id=1,
        version_number=1,
    )
    delta = _profile_delta(
        delta_id=9,
        user_id=1,
        status="proposed",
        previous_snapshot_id=previous.id,
        next_snapshot_id=None,
    )
    delta.evidence_json = []
    session = _ProfileServiceFakeSession(
        {
            (ProfileDelta, delta.id): delta,
            (UserProfileSnapshot, previous.id): previous,
        },
        execute_results=[delta, object(), previous],
    )

    result = await apply_profile_delta_result(cast(AsyncSession, session), delta.id)

    assert result.accepted is False
    assert result.snapshot is None
    assert result.delta is delta
    assert result.rejection_reason == "profile_delta_missing_evidence"
    assert delta.status == "rejected"
    assert delta.next_snapshot_id is None
    assert session.added == []


@pytest.mark.asyncio
async def test_apply_profile_delta_result_accepts_proposed_once_and_increments_version() -> None:
    previous = _profile_snapshot(
        snapshot_id=40,
        user_id=1,
        version_number=3,
    )
    delta = _profile_delta(
        delta_id=10,
        user_id=1,
        status="proposed",
        previous_snapshot_id=previous.id,
        next_snapshot_id=None,
    )
    session = _ProfileServiceFakeSession(
        {
            (ProfileDelta, delta.id): delta,
            (UserProfileSnapshot, previous.id): previous,
        },
        execute_results=[delta, object(), previous],
    )

    result = await apply_profile_delta_result(cast(AsyncSession, session), delta.id)

    assert result.accepted is True
    assert result.snapshot is session.added[0]
    assert result.snapshot is not None
    assert result.snapshot.version_number == 4
    assert result.snapshot.user_id == delta.user_id
    assert delta.status == "accepted"
    assert delta.next_snapshot_id == result.snapshot.id
    assert delta.next_snapshot_id == 1000
    assert len(session.added) == 1


@pytest.mark.asyncio
async def test_apply_profile_delta_sanitizes_persisted_evidence() -> None:
    previous = _profile_snapshot(
        snapshot_id=45,
        user_id=1,
        version_number=1,
    )
    delta = _profile_delta(
        delta_id=12,
        user_id=1,
        status="proposed",
        previous_snapshot_id=previous.id,
        next_snapshot_id=None,
    )
    delta.evidence_json = [
        {
            "source": "summary",
            "summary": "复盘证据" * 200,
            "session_id": 9,
            "code_text": "完整代码",
            "full_solution": "完整题解",
            "raw": "原始聊天",
        }
    ]
    session = _ProfileServiceFakeSession(
        {
            (ProfileDelta, delta.id): delta,
            (UserProfileSnapshot, previous.id): previous,
        },
        execute_results=[delta, object(), previous],
    )

    result = await apply_profile_delta_result(cast(AsyncSession, session), delta.id)

    assert result.snapshot is not None
    evidence = result.snapshot.evidence_summary_json
    assert evidence == [
        {"source": "summary", "summary": ("复盘证据" * 200)[:400], "session_id": 9}
    ]
    assert "code_text" not in str(evidence)
    assert "full_solution" not in str(evidence)
    assert "raw" not in str(evidence)
    assert "完整代码" not in str(evidence)
    assert "完整题解" not in str(evidence)


@pytest.mark.asyncio
async def test_low_confidence_patch_preserves_stable_fields_and_deep_merges() -> None:
    previous = _profile_snapshot(
        snapshot_id=50,
        user_id=1,
        version_number=2,
        overall_level="intermediate",
        preferred_training_mode="independent",
    )
    previous.skill_profile_json = {
        "weak_skill_tags": ["hash-table", "two-pointers"],
        "topic": {"array": {"score": 3, "notes": ["边界"]}},
    }
    delta = _profile_delta(
        delta_id=11,
        user_id=1,
        status="proposed",
        previous_snapshot_id=previous.id,
        next_snapshot_id=None,
    )
    delta.patch_json = {
        "confidence": "low",
        "overall_level": "advanced",
        "preferred_training_mode": "guided",
        "skill_profile_json": {
            "weak_skill_tags": ["hash-table", "binary-search"],
            "topic": {"array": {"notes": ["边界", "复杂度"], "recent": "wa"}},
        },
        "recent_summary": "低置信度补充摘要。",
    }
    session = _ProfileServiceFakeSession(
        {
            (ProfileDelta, delta.id): delta,
            (UserProfileSnapshot, previous.id): previous,
        },
        execute_results=[delta, object(), previous],
    )

    result = await apply_profile_delta_result(cast(AsyncSession, session), delta.id)

    assert result.snapshot is not None
    snapshot = result.snapshot
    assert snapshot.overall_level == "intermediate"
    assert snapshot.preferred_training_mode == "independent"
    assert snapshot.skill_profile_json["weak_skill_tags"] == [
        "hash-table",
        "two-pointers",
        "binary-search",
    ]
    assert snapshot.skill_profile_json["topic"]["array"] == {
        "score": 3,
        "notes": ["边界", "复杂度"],
        "recent": "wa",
    }


@pytest.mark.asyncio
async def test_deep_merge_caps_and_dedupes_oversized_lists() -> None:
    previous = _profile_snapshot(
        snapshot_id=60,
        user_id=1,
        version_number=1,
    )
    previous.skill_profile_json = {"weak_skill_tags": ["tag-0", "tag-1"]}
    delta = _profile_delta(
        delta_id=13,
        user_id=1,
        status="proposed",
        previous_snapshot_id=previous.id,
        next_snapshot_id=None,
    )
    delta.patch_json = {
        "skill_profile_json": {
            "weak_skill_tags": [f"tag-{index}" for index in range(40)]
        }
    }
    session = _ProfileServiceFakeSession(
        {
            (ProfileDelta, delta.id): delta,
            (UserProfileSnapshot, previous.id): previous,
        },
        execute_results=[delta, object(), previous],
    )

    result = await apply_profile_delta_result(cast(AsyncSession, session), delta.id)

    assert result.snapshot is not None
    assert result.snapshot.skill_profile_json["weak_skill_tags"] == [
        f"tag-{index}" for index in range(16)
    ]


@pytest.mark.asyncio
async def test_stale_previous_snapshot_uses_latest_version_as_merge_base() -> None:
    stale = _profile_snapshot(
        snapshot_id=70,
        user_id=1,
        version_number=2,
    )
    latest = _profile_snapshot(
        snapshot_id=71,
        user_id=1,
        version_number=5,
        overall_level="intermediate",
        preferred_training_mode="independent",
    )
    latest.skill_profile_json = {"weak_skill_tags": ["graph"]}
    delta = _profile_delta(
        delta_id=14,
        user_id=1,
        status="proposed",
        previous_snapshot_id=stale.id,
        next_snapshot_id=None,
    )
    delta.patch_json = {
        "confidence": "low",
        "overall_level": "advanced",
        "skill_profile_json": {"weak_skill_tags": ["dp"]},
    }
    session = _ProfileServiceFakeSession(
        {
            (ProfileDelta, delta.id): delta,
            (UserProfileSnapshot, stale.id): stale,
            (UserProfileSnapshot, latest.id): latest,
        },
        execute_results=[delta, object(), latest],
    )

    result = await apply_profile_delta_result(cast(AsyncSession, session), delta.id)

    assert result.snapshot is not None
    assert result.snapshot.version_number == 6
    assert result.snapshot.overall_level == "intermediate"
    assert result.snapshot.skill_profile_json["weak_skill_tags"] == ["graph", "dp"]
    assert delta.previous_snapshot_id == stale.id


class _ScalarResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _ProfileServiceFakeSession:
    def __init__(
        self,
        objects: dict[tuple[type[Any], int | None], Any],
        execute_results: list[Any] | None = None,
    ) -> None:
        self._objects = objects
        self._execute_results = list(execute_results or [])
        self.added: list[Any] = []
        self.flush_count = 0
        self.execute_count = 0

    async def execute(self, statement: Any) -> _ScalarResult:
        self.execute_count += 1
        if not self._execute_results:
            raise AssertionError(f"unexpected execute call: {statement}")
        return _ScalarResult(self._execute_results.pop(0))

    async def get(self, model: type[Any], object_id: int | None) -> Any:
        return self._objects.get((model, object_id))

    def add(self, instance: Any) -> None:
        if isinstance(instance, UserProfileSnapshot) and instance.id is None:
            instance.id = 1000 + len(self.added)
        self.added.append(instance)

    async def flush(self) -> None:
        self.flush_count += 1


def _profile_snapshot(
    *,
    snapshot_id: int,
    user_id: int,
    version_number: int,
    overall_level: str = "beginner",
    preferred_training_mode: str = "guided",
) -> UserProfileSnapshot:
    return UserProfileSnapshot(
        id=snapshot_id,
        user_id=user_id,
        version_number=version_number,
        source="summary_patch",
        confidence="medium",
        overall_level=overall_level,
        preferred_training_mode=preferred_training_mode,
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
