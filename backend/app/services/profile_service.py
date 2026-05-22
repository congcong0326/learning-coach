from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.auth import AppUser
from backend.app.models.practice import ProfileDelta, UserProfileSnapshot
from backend.app.services.profile_provider import (
    ProfileConfidence,
    ProfileSnapshot,
    ProfileSource,
)

logger = logging.getLogger(__name__)


_ALLOWED_PROFILE_SOURCES = {
    "initial_goal_plan",
    "mock_from_goal_and_plan",
    "summary_patch",
    "manual_repair",
}
_ALLOWED_PROFILE_CONFIDENCES = {"low", "medium", "high"}
_ALLOWED_PATCH_KEYS = {
    "ability_profile",
    "ability_profile_json",
    "confidence",
    "overall_level",
    "preferred_training_mode",
    "recent_summary",
    "recent_summary_md",
    "skill_profile",
    "skill_profile_json",
    "source",
    "strategy",
    "strategy_json",
    "stuck_point_profile",
    "stuck_point_profile_json",
}
_PROFILE_SECTION_KEYS = {
    "ability_profile",
    "ability_profile_json",
    "skill_profile",
    "skill_profile_json",
    "strategy",
    "strategy_json",
    "stuck_point_profile",
    "stuck_point_profile_json",
}
_SHORT_TEXT_LIMIT = 120
_LONG_TEXT_LIMIT = 1200
_EVIDENCE_SUMMARY_LIMIT = 400
_MAX_PROFILE_DEPTH = 4
_MAX_PROFILE_DICT_KEYS = 32
_MAX_PROFILE_LIST_LENGTH = 16
_MAX_PROFILE_STRING_LENGTH = 1200
_SAFE_EVIDENCE_KEYS = {
    "confidence",
    "problem_id",
    "session_id",
    "source",
    "summary",
    "summary_id",
    "tag",
}


class ProfileServiceError(ValueError):
    """画像服务输入或状态不满足后端合并约束。"""


@dataclass(frozen=True)
class ProfilePatchValidation:
    accepted: bool
    rejection_reason: str = ""


@dataclass(frozen=True)
class ApplyProfileDeltaResult:
    accepted: bool
    snapshot: UserProfileSnapshot | None
    delta: ProfileDelta
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
    await _lock_user(session, user_id)
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
    if not evidence_json:
        return ProfilePatchValidation(
            accepted=False,
            rejection_reason="profile_delta_missing_evidence",
        )
    unknown_keys = set(patch_json) - _ALLOWED_PATCH_KEYS
    if unknown_keys:
        raise ProfileServiceError(
            "profile patch contains unknown keys: " + ", ".join(sorted(unknown_keys))
        )
    confidence = patch_json.get("confidence")
    if confidence is not None and confidence not in _ALLOWED_PROFILE_CONFIDENCES:
        raise ProfileServiceError("profile patch confidence is invalid")
    source = patch_json.get("source")
    if source is not None and source not in _ALLOWED_PROFILE_SOURCES:
        raise ProfileServiceError("profile patch source is invalid")
    for key in ("overall_level", "preferred_training_mode"):
        _validate_text_field(key, patch_json.get(key), _SHORT_TEXT_LIMIT)
    for key in ("recent_summary", "recent_summary_md"):
        _validate_text_field(key, patch_json.get(key), _LONG_TEXT_LIMIT)
    for key in _PROFILE_SECTION_KEYS:
        value = patch_json.get(key)
        if value is not None:
            if not isinstance(value, dict):
                raise ProfileServiceError(f"profile patch section must be an object: {key}")
            _validate_section_value(value, path=key)
    for index, item in enumerate(evidence_json):
        if not isinstance(item, dict):
            raise ProfileServiceError("evidence_json items must be objects")
        source_value = item.get("source")
        summary_value = item.get("summary")
        if not isinstance(source_value, str) or not source_value.strip():
            raise ProfileServiceError(f"evidence_json[{index}].source is required")
        if not isinstance(summary_value, str) or not summary_value.strip():
            raise ProfileServiceError(f"evidence_json[{index}].summary is required")
        _validate_text_field(f"evidence_json[{index}].source", source_value, _SHORT_TEXT_LIMIT)
        _validate_text_field(
            f"evidence_json[{index}].summary",
            summary_value,
            _LONG_TEXT_LIMIT,
        )
    return ProfilePatchValidation(accepted=True)


async def apply_profile_delta(
    session: AsyncSession,
    delta_id: int,
) -> UserProfileSnapshot:
    result = await apply_profile_delta_result(session, delta_id)
    if not result.accepted or result.snapshot is None:
        raise ProfileServiceError(result.rejection_reason or "profile_delta_rejected")
    return result.snapshot


async def apply_profile_delta_result(
    session: AsyncSession,
    delta_id: int,
) -> ApplyProfileDeltaResult:
    """返回画像增量应用结果，不用异常表达可持久化拒绝状态。

    调用方如果需要提交“拒绝 delta”的状态，必须调用本函数并在返回
    `accepted=False` 后自行决定 commit；`apply_profile_delta()` 是便捷包装，
    会在拒绝时抛错，普通异常处理可能导致本事务回滚。
    """

    delta = await _load_delta_for_update(session, delta_id)
    if delta is None:
        raise ProfileServiceError(f"profile_delta not found: {delta_id}")
    await _lock_user(session, delta.user_id)
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
        return ApplyProfileDeltaResult(accepted=True, snapshot=next_snapshot, delta=delta)
    if delta.status == "rejected":
        return ApplyProfileDeltaResult(
            accepted=False,
            snapshot=None,
            delta=delta,
            rejection_reason=delta.rejection_reason or "profile_delta_already_rejected",
        )
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
        return ApplyProfileDeltaResult(
            accepted=False,
            snapshot=None,
            delta=delta,
            rejection_reason=validation.rejection_reason,
        )

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
    if delta.previous_snapshot_id is None:
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
    return ApplyProfileDeltaResult(accepted=True, snapshot=snapshot, delta=delta)


async def _load_delta_for_update(
    session: AsyncSession,
    delta_id: int,
) -> ProfileDelta | None:
    result = await session.execute(
        select(ProfileDelta)
        .where(ProfileDelta.id == delta_id)
        .with_for_update()
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _lock_user(session: AsyncSession, user_id: int) -> AppUser:
    result = await session.execute(
        select(AppUser)
        .where(AppUser.id == user_id)
        .with_for_update()
        .limit(1)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise ProfileServiceError(f"profile user not found: {user_id}")
    return user


async def _previous_snapshot_for_delta(
    session: AsyncSession,
    delta: ProfileDelta,
) -> UserProfileSnapshot | None:
    if delta.previous_snapshot_id is not None:
        snapshot = await session.get(UserProfileSnapshot, delta.previous_snapshot_id)
        if snapshot is None or snapshot.user_id != delta.user_id:
            raise ProfileServiceError("previous snapshot does not belong to delta user")
        latest = await latest_profile_snapshot(session, delta.user_id)
        if latest is not None and latest.version_number > snapshot.version_number:
            logger.warning(
                "profile_delta_stale_previous user_id=%s delta_id=%s previous_id=%s latest_id=%s",
                delta.user_id,
                delta.id,
                snapshot.id,
                latest.id,
            )
            return latest
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
        "evidence_summary_json": _sanitize_evidence_list(evidence),
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
    return _deep_merge_dict(base, patch)


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _evidence_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _sanitize_evidence_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sanitized: list[dict[str, Any]] = []
    for item in value[:_MAX_PROFILE_LIST_LENGTH]:
        if not isinstance(item, dict):
            continue
        safe_item: dict[str, Any] = {}
        for key in _SAFE_EVIDENCE_KEYS:
            if key not in item:
                continue
            item_value = item[key]
            if isinstance(item_value, str):
                limit = _EVIDENCE_SUMMARY_LIMIT if key == "summary" else _SHORT_TEXT_LIMIT
                safe_item[key] = item_value[:limit]
            elif isinstance(item_value, int | float | bool) or item_value is None:
                safe_item[key] = item_value
        if safe_item:
            sanitized.append(safe_item)
    return sanitized


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _profile_source(value: str) -> ProfileSource:
    if value in _ALLOWED_PROFILE_SOURCES:
        return cast(ProfileSource, value)
    return "manual_repair"


def _profile_confidence(value: str) -> ProfileConfidence:
    if value in _ALLOWED_PROFILE_CONFIDENCES:
        return cast(ProfileConfidence, value)
    return "low"


def _deep_merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    return _deep_merge_dict_bounded(base, patch, depth=0)


def _deep_merge_dict_bounded(
    base: dict[str, Any],
    patch: dict[str, Any],
    *,
    depth: int,
) -> dict[str, Any]:
    if depth > _MAX_PROFILE_DEPTH:
        raise ProfileServiceError("profile patch exceeds max depth")
    merged = dict(base)
    for key, value in list(patch.items())[:_MAX_PROFILE_DICT_KEYS]:
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dict_bounded(current, value, depth=depth + 1)
        elif isinstance(current, list) and isinstance(value, list):
            merged[key] = _merge_lists(current, value)
        elif isinstance(value, list):
            merged[key] = _merge_lists([], value)
        elif isinstance(value, dict):
            merged[key] = _deep_merge_dict_bounded({}, value, depth=depth + 1)
        elif isinstance(value, str):
            merged[key] = value[:_MAX_PROFILE_STRING_LENGTH]
        else:
            merged[key] = value
        if len(merged) > _MAX_PROFILE_DICT_KEYS:
            allowed_keys = list(merged)[:_MAX_PROFILE_DICT_KEYS]
            merged = {key: merged[key] for key in allowed_keys}
    return merged


def _merge_lists(base: list[Any], patch: list[Any]) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for values in (base, patch):
        for item in values:
            normalized = str(item)
            if normalized in seen:
                continue
            seen.add(normalized)
            merged.append(item)
            if len(merged) >= _MAX_PROFILE_LIST_LENGTH:
                return merged
    return merged


def _validate_text_field(name: str, value: Any, limit: int) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ProfileServiceError(f"{name} must be a string")
    if len(value) > limit:
        raise ProfileServiceError(f"{name} exceeds length limit")


def _validate_section_value(value: Any, *, path: str, depth: int = 0) -> None:
    if depth > _MAX_PROFILE_DEPTH:
        raise ProfileServiceError(f"{path} exceeds max depth")
    if isinstance(value, str):
        if len(value) > _MAX_PROFILE_STRING_LENGTH:
            raise ProfileServiceError(f"{path} exceeds length limit")
        return
    if isinstance(value, dict):
        if len(value) > _MAX_PROFILE_DICT_KEYS:
            raise ProfileServiceError(f"{path} exceeds key limit")
        for key, item in value.items():
            _validate_section_value(item, path=f"{path}.{key}", depth=depth + 1)
        return
    if isinstance(value, list):
        if len(value) > _MAX_PROFILE_LIST_LENGTH:
            raise ProfileServiceError(f"{path} exceeds list length limit")
        for index, item in enumerate(value):
            _validate_section_value(item, path=f"{path}[{index}]", depth=depth + 1)
