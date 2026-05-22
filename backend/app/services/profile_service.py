from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.practice import ProfileDelta, UserProfileSnapshot
from backend.app.services.profile_provider import (
    ProfileConfidence,
    ProfileSnapshot,
    ProfileSource,
)

logger = logging.getLogger(__name__)


class ProfileServiceError(ValueError):
    """画像服务输入或状态不满足后端合并约束。"""


@dataclass(frozen=True)
class ProfilePatchValidation:
    accepted: bool
    rejection_reason: str = ""


async def latest_profile_snapshot(
    session: AsyncSession,
    user_id: int,
) -> UserProfileSnapshot | None:
    result = await session.execute(
        select(UserProfileSnapshot)
        .where(UserProfileSnapshot.user_id == user_id)
        .order_by(
            UserProfileSnapshot.version_number.desc(),
            UserProfileSnapshot.created_at.desc(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


def snapshot_payload(snapshot: UserProfileSnapshot) -> ProfileSnapshot:
    skill_profile = _dict_or_empty(snapshot.skill_profile_json)
    stuck_point_profile = _dict_or_empty(snapshot.stuck_point_profile_json)
    strategy = _dict_or_empty(snapshot.strategy_json)

    return ProfileSnapshot(
        id=snapshot.id,
        version=f"profile-snapshot-v{snapshot.version_number}",
        source=_profile_source(snapshot.source),
        confidence=_profile_confidence(snapshot.confidence),
        overall_level=snapshot.overall_level,
        preferred_training_mode=snapshot.preferred_training_mode,
        weak_stuck_points=_string_list(
            stuck_point_profile.get("weak_stuck_points")
            or stuck_point_profile.get("stuck_points")
        ),
        strong_skill_tags=_string_list(skill_profile.get("strong_skill_tags")),
        weak_skill_tags=_string_list(skill_profile.get("weak_skill_tags")),
        recent_summary=snapshot.recent_summary_md,
        hint_policy_hint=str(strategy.get("hint_policy_hint") or ""),
        coach_strategy=strategy,
        evidence=_evidence_list(snapshot.evidence_summary_json),
    )


async def ensure_initial_profile_snapshot(
    session: AsyncSession,
    user_id: int,
    plan_id: int,
) -> UserProfileSnapshot:
    existing = await latest_profile_snapshot(session, user_id)
    if existing is not None:
        logger.info(
            "profile_snapshot_initial_exists user_id=%s snapshot_id=%s version=%s",
            user_id,
            existing.id,
            existing.version_number,
        )
        return existing

    snapshot = UserProfileSnapshot(
        user_id=user_id,
        version_number=1,
        source="initial_goal_plan",
        confidence="low",
        overall_level="unknown",
        preferred_training_mode="independent",
        ability_profile_json={},
        skill_profile_json={"strong_skill_tags": [], "weak_skill_tags": []},
        stuck_point_profile_json={"weak_stuck_points": []},
        strategy_json={
            "start_phase": "understand_problem",
            "hint_policy_hint": "画像置信度低，先根据用户本轮输入判断训练阶段。",
        },
        recent_summary_md="初始画像来自学习计划入口，尚无稳定训练证据。",
        evidence_summary_json=[
            {
                "source": "study_plan",
                "plan_id": plan_id,
                "summary": "创建保守初始画像，等待训练复盘证据更新。",
            }
        ],
    )
    session.add(snapshot)
    await session.flush()
    logger.info(
        "profile_snapshot_initial_created user_id=%s plan_id=%s snapshot_id=%s",
        user_id,
        plan_id,
        snapshot.id,
    )
    return snapshot


def validate_profile_patch(
    patch_json: dict[str, Any],
    evidence_json: list[dict[str, Any]],
) -> ProfilePatchValidation:
    if not isinstance(patch_json, dict):
        raise ProfileServiceError("patch_json must be an object")
    if not isinstance(evidence_json, list):
        raise ProfileServiceError("evidence_json must be a list")
    if any(not isinstance(item, dict) for item in evidence_json):
        raise ProfileServiceError("evidence_json items must be objects")
    if not evidence_json:
        return ProfilePatchValidation(
            accepted=False,
            rejection_reason="profile_delta_missing_evidence",
        )
    return ProfilePatchValidation(accepted=True)


async def apply_profile_delta(
    session: AsyncSession,
    delta_id: int,
) -> UserProfileSnapshot:
    delta = await session.get(ProfileDelta, delta_id)
    if delta is None:
        raise ProfileServiceError(f"profile_delta not found: {delta_id}")
    if delta.status == "accepted":
        if delta.next_snapshot_id is None:
            raise ProfileServiceError("accepted profile_delta missing next_snapshot_id")
        next_snapshot = await session.get(UserProfileSnapshot, delta.next_snapshot_id)
        if next_snapshot is None or next_snapshot.user_id != delta.user_id:
            raise ProfileServiceError("accepted profile_delta next snapshot is inconsistent")
        logger.info(
            "profile_delta_already_accepted user_id=%s delta_id=%s snapshot_id=%s",
            delta.user_id,
            delta.id,
            next_snapshot.id,
        )
        return next_snapshot
    if delta.status == "rejected":
        raise ProfileServiceError(delta.rejection_reason or "profile_delta_already_rejected")
    if delta.status != "proposed":
        raise ProfileServiceError(f"profile_delta status is not processable: {delta.status}")

    validation = validate_profile_patch(delta.patch_json, delta.evidence_json)
    if not validation.accepted:
        delta.status = "rejected"
        delta.rejection_reason = validation.rejection_reason
        delta.applied_at = datetime.now(UTC)
        await session.flush()
        logger.warning(
            "profile_delta_rejected user_id=%s delta_id=%s reason=%s",
            delta.user_id,
            delta.id,
            validation.rejection_reason,
        )
        raise ProfileServiceError(validation.rejection_reason)

    previous = await _previous_snapshot_for_delta(session, delta)
    merged = _merge_snapshot_payload(previous, delta.patch_json, delta.evidence_json)
    version_number = 1 if previous is None else previous.version_number + 1

    # 长期画像只追加新版本，旧快照保持不可变，便于审计和回滚教练决策上下文。
    snapshot = UserProfileSnapshot(
        user_id=delta.user_id,
        version_number=version_number,
        source=merged["source"],
        confidence=merged["confidence"],
        overall_level=merged["overall_level"],
        preferred_training_mode=merged["preferred_training_mode"],
        ability_profile_json=merged["ability_profile_json"],
        skill_profile_json=merged["skill_profile_json"],
        stuck_point_profile_json=merged["stuck_point_profile_json"],
        strategy_json=merged["strategy_json"],
        recent_summary_md=merged["recent_summary_md"],
        evidence_summary_json=merged["evidence_summary_json"],
        created_from_summary_id=delta.summary_id,
    )
    session.add(snapshot)
    await session.flush()

    delta.status = "accepted"
    delta.previous_snapshot_id = previous.id if previous is not None else None
    delta.next_snapshot_id = snapshot.id
    delta.merge_result_json = {
        "snapshot_id": snapshot.id,
        "version_number": snapshot.version_number,
        "source": snapshot.source,
        "confidence": snapshot.confidence,
    }
    delta.rejection_reason = ""
    delta.applied_at = datetime.now(UTC)
    await session.flush()
    logger.info(
        "profile_delta_accepted user_id=%s delta_id=%s snapshot_id=%s version=%s",
        delta.user_id,
        delta.id,
        snapshot.id,
        snapshot.version_number,
    )
    return snapshot


async def _previous_snapshot_for_delta(
    session: AsyncSession,
    delta: ProfileDelta,
) -> UserProfileSnapshot | None:
    if delta.previous_snapshot_id is not None:
        snapshot = await session.get(UserProfileSnapshot, delta.previous_snapshot_id)
        if snapshot is None or snapshot.user_id != delta.user_id:
            raise ProfileServiceError("previous snapshot does not belong to delta user")
        return snapshot
    return await latest_profile_snapshot(session, delta.user_id)


def _merge_snapshot_payload(
    previous: UserProfileSnapshot | None,
    patch: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    previous_payload = _snapshot_json(previous)
    confidence = str(patch.get("confidence") or previous_payload["confidence"] or "low")

    # 低置信度增量只能补充摘要和策略，不直接覆盖已有稳定等级与训练模式。
    keep_stable_fields = previous is not None and confidence == "low"
    overall_level = (
        previous_payload["overall_level"]
        if keep_stable_fields
        else str(patch.get("overall_level") or previous_payload["overall_level"] or "unknown")
    )
    preferred_training_mode = (
        previous_payload["preferred_training_mode"]
        if keep_stable_fields
        else str(
            patch.get("preferred_training_mode")
            or previous_payload["preferred_training_mode"]
            or "independent"
        )
    )

    return {
        "source": str(patch.get("source") or "summary_patch"),
        "confidence": confidence,
        "overall_level": overall_level,
        "preferred_training_mode": preferred_training_mode,
        "ability_profile_json": _merged_dict(
            previous_payload["ability_profile_json"],
            patch.get("ability_profile_json") or patch.get("ability_profile"),
        ),
        "skill_profile_json": _merged_dict(
            previous_payload["skill_profile_json"],
            patch.get("skill_profile_json") or patch.get("skill_profile"),
        ),
        "stuck_point_profile_json": _merged_dict(
            previous_payload["stuck_point_profile_json"],
            patch.get("stuck_point_profile_json") or patch.get("stuck_point_profile"),
        ),
        "strategy_json": _merged_dict(
            previous_payload["strategy_json"],
            patch.get("strategy_json") or patch.get("strategy"),
        ),
        "recent_summary_md": str(
            patch.get("recent_summary_md")
            or patch.get("recent_summary")
            or previous_payload["recent_summary_md"]
        )[:1200],
        "evidence_summary_json": _evidence_list(evidence)[:12],
    }


def _snapshot_json(snapshot: UserProfileSnapshot | None) -> dict[str, Any]:
    if snapshot is None:
        return {
            "confidence": "low",
            "overall_level": "unknown",
            "preferred_training_mode": "independent",
            "ability_profile_json": {},
            "skill_profile_json": {},
            "stuck_point_profile_json": {},
            "strategy_json": {},
            "recent_summary_md": "",
        }
    return {
        "confidence": snapshot.confidence,
        "overall_level": snapshot.overall_level,
        "preferred_training_mode": snapshot.preferred_training_mode,
        "ability_profile_json": _dict_or_empty(snapshot.ability_profile_json),
        "skill_profile_json": _dict_or_empty(snapshot.skill_profile_json),
        "stuck_point_profile_json": _dict_or_empty(snapshot.stuck_point_profile_json),
        "strategy_json": _dict_or_empty(snapshot.strategy_json),
        "recent_summary_md": snapshot.recent_summary_md,
    }


def _merged_dict(base: dict[str, Any], patch: Any) -> dict[str, Any]:
    if patch is None:
        return dict(base)
    if not isinstance(patch, dict):
        raise ProfileServiceError("profile patch sections must be objects")
    merged = dict(base)
    merged.update(patch)
    return merged


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _evidence_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _profile_source(value: str) -> ProfileSource:
    if value in {
        "initial_goal_plan",
        "mock_from_goal_and_plan",
        "summary_patch",
        "manual_repair",
    }:
        return cast(ProfileSource, value)
    return "manual_repair"


def _profile_confidence(value: str) -> ProfileConfidence:
    if value in {"low", "medium", "high"}:
        return cast(ProfileConfidence, value)
    return "low"
