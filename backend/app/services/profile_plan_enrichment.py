from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.auth import AppUser
from backend.app.models.learning import (
    PlanChangeLog,
    ProfilePlanEnrichmentDraft,
    StudyPlan,
    StudyPlanItem,
    StudyPlanStage,
    StudyPlanVersion,
)
from backend.app.models.practice import SessionSummary, UserProfileSnapshot
from backend.app.models.problem import Problem
from backend.app.schemas.learning import (
    ProfilePlanEnrichmentDraftResponse,
    ProfilePlanEnrichmentItem,
    ProfilePlanGapAssessment,
    ProfilePlanEnrichmentRequest,
)
from backend.app.services.profile_service import latest_profile_snapshot, snapshot_payload
from backend.app.services.study_plan_service import StudyPlanError, study_plan_payload


logger = logging.getLogger(__name__)

MAX_CANDIDATES = 60
MAX_RECENT_SUMMARIES = 5
MAX_REPAIR_ATTEMPTS = 2
ENRICHMENT_REASON_PREFIX = "画像补强："
DIFFICULTY_RANK = {"Easy": 1, "Medium": 2, "Hard": 3}
HINT_LEVEL_RANK = {
    "questioning": 0,
    "direction": 1,
    "key_hint": 2,
    "reflection": 3,
}

_VALID_TRAINING_MODES = {"guided", "independent", "mock_interview"}
_TOKEN_SPLIT_RE = re.compile(r"[\s,，。；;、.!?！？:：()（）\[\]{}<>《》\"'`]+")


async def build_enrichment_context(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
    payload: ProfilePlanEnrichmentRequest,
) -> dict[str, Any]:
    logger.info(
        "profile_plan_enrichment_context_started user_id=%s plan_id=%s item_count=%s difficulty=%s intent_length=%s",
        user.id,
        plan_id,
        payload.item_count,
        payload.difficulty_preference,
        len(payload.user_intent_md),
    )
    try:
        plan, version = await _load_active_plan_version(db, user, plan_id)
        profile_snapshot = await latest_profile_snapshot(db, user.id)
        recent_summaries = await _recent_session_summaries(db, user.id)
        current_stage = _current_stage(version)
        existing_slugs = {str(item.problem_slug) for item in version.items}
        candidates = await _candidate_problems(
            db,
            existing_slugs=existing_slugs,
            current_stage=current_stage,
            profile_snapshot=profile_snapshot,
            payload=payload,
        )
    except StudyPlanError:
        logger.warning(
            "profile_plan_enrichment_context_rejected user_id=%s plan_id=%s reason=study_plan_state",
            user.id,
            plan_id,
        )
        raise
    except Exception:
        logger.exception(
            "profile_plan_enrichment_context_failed user_id=%s plan_id=%s",
            user.id,
            plan_id,
        )
        raise

    logger.info(
        "profile_plan_enrichment_context_completed user_id=%s plan_id=%s version_id=%s candidate_count=%s",
        user.id,
        plan_id,
        version.id,
        len(candidates),
    )
    return {
        "task": "profile_plan_enrichment",
        "user_request": payload.model_dump(),
        "goal_context": {
            "target_snapshot": _dict_value(version.target_snapshot_json),
            "preferred_language": str(
                _dict_value(version.target_snapshot_json).get("preferred_language") or ""
            ),
            "timeline": str(
                _dict_value(version.target_snapshot_json).get("target_timeline") or ""
            ),
            "weekly_commitment": str(
                _dict_value(version.target_snapshot_json).get("weekly_days") or ""
            ),
        },
        "profile_snapshot": _profile_context(profile_snapshot),
        "training_facts": _training_facts(recent_summaries),
        "current_plan": _plan_context(plan, version, current_stage, existing_slugs),
        "candidate_problems": candidates,
        "output_contract": {
            "format": "json",
            "item_count_max": payload.item_count,
            "must_choose_from_candidate_problems": True,
            "insert_position": "current_stage_tail",
        },
    }


def validate_model_output(
    output: dict[str, Any],
    context: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[str] = []
    normalized_items: list[dict[str, Any]] = []
    _validate_top_level_output(output, issues)
    candidates = {
        str(item.get("slug")): item
        for item in _list_of_dicts(context.get("candidate_problems"))
        if item.get("slug")
    }
    current_plan = _dict_value(context.get("current_plan"))
    existing = set(_string_list(current_plan.get("existing_problem_slugs")))
    current_stage = _dict_value(current_plan.get("current_stage"))
    max_count = _int_value(_dict_value(context.get("user_request")).get("item_count"), 3)
    raw_items = output.get("items")
    if not isinstance(raw_items, list):
        issues.append("items_not_list")
        raw_items = []
    if len(raw_items) > max_count:
        issues.append("item_count_exceeded")

    seen: set[str] = set()
    for raw_item in raw_items[:max_count]:
        if not isinstance(raw_item, dict):
            issues.append("item_not_object")
            continue
        slug = str(raw_item.get("problem_slug") or "").strip()
        if not slug:
            issues.append("missing_problem_slug")
            continue
        if slug in seen:
            issues.append(f"duplicate_slug:{slug}")
            continue
        if slug in existing:
            issues.append(f"existing_slug_recommended:{slug}")
            continue
        candidate = candidates.get(slug)
        if candidate is None:
            issues.append(f"candidate_slug_not_allowed:{slug}")
            continue

        seen.add(slug)
        reason = str(raw_item.get("recommendation_reason_md") or "").strip()
        first_question = str(raw_item.get("first_question_hint") or "").strip()
        review_focus = str(raw_item.get("review_focus") or "").strip()
        if not reason:
            issues.append(f"missing_recommendation_reason:{slug}")
        if not first_question:
            issues.append(f"missing_first_question_hint:{slug}")
        if not review_focus:
            issues.append(f"missing_review_focus:{slug}")

        normalized_item = {
            "problem_id": _int_value(candidate.get("problem_id"), 0),
            "problem_slug": slug,
            "title": str(candidate.get("title") or ""),
            "translated_title": str(candidate.get("translated_title") or ""),
            "difficulty": str(
                candidate.get("difficulty") or raw_item.get("difficulty") or ""
            ),
            "skill_tags": _string_list(candidate.get("tags")),
            "target_stage_id": _int_value(current_stage.get("id"), 0),
            "target_stage_title": str(current_stage.get("title") or ""),
            "weakness_targets": _string_list(raw_item.get("weakness_targets")),
            "recommendation_reason_md": reason,
            "first_question_hint": first_question,
            "review_focus": review_focus,
            "suggested_mode": _suggested_mode(raw_item.get("suggested_mode")),
        }
        try:
            ProfilePlanEnrichmentItem.model_validate(normalized_item)
        except ValidationError:
            issues.append(f"item_schema_invalid:{slug}")
        normalized_items.append(normalized_item)

    valid = not issues
    if valid:
        logger.info(
            "profile_plan_enrichment_validation_accepted item_count=%s candidate_count=%s",
            len(normalized_items),
            len(candidates),
        )
    else:
        logger.warning(
            "profile_plan_enrichment_validation_rejected issue_count=%s candidate_count=%s",
            len(issues),
            len(candidates),
        )
    report = {
        "valid": valid,
        "issues": issues,
        "candidate_count": len(candidates),
        "item_count": len(normalized_items) if valid else 0,
    }
    return report, normalized_items if valid else []


def _validate_top_level_output(output: dict[str, Any], issues: list[str]) -> None:
    if not isinstance(output.get("enrichment_theme", ""), str):
        issues.append("enrichment_theme_not_string")
    if not isinstance(output.get("overall_reason_md", ""), str):
        issues.append("overall_reason_md_not_string")
    if not isinstance(output.get("not_added_reason_md", ""), str):
        issues.append("not_added_reason_md_not_string")
    gap = output.get("plan_gap_assessment")
    if gap is None:
        return
    if not isinstance(gap, dict):
        issues.append("plan_gap_assessment_not_object")
        return
    try:
        ProfilePlanGapAssessment.model_validate(gap)
    except ValidationError:
        issues.append("plan_gap_assessment_invalid")


async def persist_generated_draft(
    db: AsyncSession,
    *,
    user: AppUser,
    plan_id: int,
    version_id: int,
    profile_snapshot_id: int | None,
    llm_run_id: int,
    payload: ProfilePlanEnrichmentRequest,
    context: dict[str, Any],
    model_output: dict[str, Any],
    validation_report: dict[str, Any],
    normalized_items: list[dict[str, Any]],
) -> ProfilePlanEnrichmentDraft:
    now = datetime.now(UTC)
    issues = validation_report.get("issues", [])
    draft = ProfilePlanEnrichmentDraft(
        user_id=user.id,
        study_plan_id=plan_id,
        study_plan_version_id=version_id,
        profile_snapshot_id=profile_snapshot_id,
        llm_run_id=llm_run_id,
        status="generated" if validation_report.get("valid") else "failed",
        user_intent_md=payload.user_intent_md,
        item_count=payload.item_count,
        difficulty_preference=payload.difficulty_preference,
        context_summary_json=_safe_context_summary(context),
        candidate_problem_ids_json=[
            _int_value(item.get("problem_id"), 0)
            for item in _list_of_dicts(context.get("candidate_problems"))
            if _int_value(item.get("problem_id"), 0) > 0
        ],
        model_output_json={**model_output, "items": normalized_items},
        validation_report_json=validation_report,
        confirmed_item_ids_json=[],
        error_summary=";".join(str(issue) for issue in issues)
        if isinstance(issues, list)
        else str(issues or ""),
        created_at=now,
        updated_at=now,
        confirmed_at=None,
    )
    db.add(draft)
    await db.flush()
    logger.info(
        "profile_plan_enrichment_generated user_id=%s plan_id=%s draft_id=%s item_count=%s valid=%s",
        user.id,
        plan_id,
        draft.id,
        len(normalized_items),
        validation_report.get("valid"),
    )
    return draft


def _safe_context_summary(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_request": context.get("user_request", {}),
        "goal_context": context.get("goal_context", {}),
        "profile_snapshot": context.get("profile_snapshot", {}),
        "training_facts": context.get("training_facts", {}),
        "current_plan": context.get("current_plan", {}),
        "candidate_count": len(_list_of_dicts(context.get("candidate_problems"))),
    }


def draft_response(
    draft: ProfilePlanEnrichmentDraft,
) -> ProfilePlanEnrichmentDraftResponse:
    output = _dict_value(draft.model_output_json)
    gap = output.get("plan_gap_assessment")
    return ProfilePlanEnrichmentDraftResponse.model_validate(
        {
            "draft_id": draft.id,
            "status": draft.status,
            "plan_id": draft.study_plan_id,
            "plan_version_id": draft.study_plan_version_id,
            "profile_snapshot_id": draft.profile_snapshot_id,
            "user_intent_md": draft.user_intent_md,
            "item_count": draft.item_count,
            "difficulty_preference": draft.difficulty_preference,
            "enrichment_theme": str(output.get("enrichment_theme") or ""),
            "plan_gap_assessment": gap if isinstance(gap, dict) else None,
            "overall_reason_md": str(output.get("overall_reason_md") or ""),
            "not_added_reason_md": str(output.get("not_added_reason_md") or ""),
            "items": output.get("items") if isinstance(output.get("items"), list) else [],
            "validation_report": _dict_value(draft.validation_report_json),
            "created_at": draft.created_at,
            "updated_at": draft.updated_at,
            "confirmed_at": draft.confirmed_at,
        }
    )


async def get_enrichment_draft_payload(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
    draft_id: int,
) -> ProfilePlanEnrichmentDraftResponse:
    draft = await _load_draft(db, user, plan_id, draft_id, for_update=False)
    logger.info(
        "profile_plan_enrichment_draft_loaded user_id=%s plan_id=%s draft_id=%s status=%s",
        user.id,
        plan_id,
        draft_id,
        draft.status,
    )
    return draft_response(draft)


async def confirm_enrichment_draft(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
    draft_id: int,
) -> dict[str, Any]:
    user_id = user.id
    logger.info(
        "profile_plan_enrichment_confirm_started user_id=%s plan_id=%s draft_id=%s",
        user_id,
        plan_id,
        draft_id,
    )
    confirmed_plan_id = plan_id
    confirmed_draft_id = draft_id
    added_count = 0
    response_version: StudyPlanVersion | None = None
    try:
        draft = await _load_draft(db, user, plan_id, draft_id, for_update=True)
        if draft.status == "confirmed":
            logger.info(
                "profile_plan_enrichment_confirm_idempotent user_id=%s plan_id=%s draft_id=%s",
                user_id,
                plan_id,
                draft_id,
            )
            return await study_plan_payload(db, user, plan_id)
        if draft.status != "generated":
            raise StudyPlanError("profile_plan_enrichment_not_confirmable")

        await _lock_plan_for_confirmation(db, user, plan_id)
        plan, version = await _load_active_plan_version(db, user, plan_id)
        await _lock_version_content_for_confirmation(db, version.id)
        if version.id != draft.study_plan_version_id:
            raise StudyPlanError("profile_plan_enrichment_not_confirmable")
        await db.refresh(version, attribute_names=["stages", "items"])
        for stage in version.stages:
            await db.refresh(stage, attribute_names=["items"])

        output_items = _dict_value(draft.model_output_json).get("items")
        if not isinstance(output_items, list):
            raise StudyPlanError("profile_plan_enrichment_not_confirmable")

        current_stage = _current_stage(version)
        existing_slugs = {str(item.problem_slug) for item in version.items}
        problem_items: list[tuple[dict[str, Any], Problem]] = []
        draft_slugs: set[str] = set()
        for raw_item in output_items:
            if not isinstance(raw_item, dict):
                raise StudyPlanError("profile_plan_enrichment_not_confirmable")
            slug = str(raw_item.get("problem_slug") or "").strip()
            if not slug or slug in existing_slugs or slug in draft_slugs:
                raise StudyPlanError("profile_plan_enrichment_not_confirmable")
            problem = await _problem_by_slug(db, slug)
            problem_items.append((raw_item, problem))
            draft_slugs.add(slug)

        max_order = max([item.order_index for item in current_stage.items] or [-1])
        added_ids: list[int] = []
        now = datetime.now(UTC)
        for index, (item_payload, problem) in enumerate(problem_items, start=1):
            reason = ENRICHMENT_REASON_PREFIX + str(
                item_payload.get("recommendation_reason_md") or ""
            )
            item = StudyPlanItem(
                version_id=version.id,
                stage_id=current_stage.id,
                problem_id=problem.id,
                problem_slug=problem.slug,
                skill_tags_json=_merged_skill_tags(problem, item_payload),
                difficulty=problem.difficulty,
                suggested_mode=_suggested_mode(item_payload.get("suggested_mode")),
                recommendation_reason=reason,
                status="pending",
                order_index=max_order + index,
                locked=False,
                created_at=now,
                updated_at=now,
            )
            db.add(item)
            await db.flush()
            added_ids.append(item.id)
            _add_enrichment_change_log(db, version, item, draft)

        draft.status = "confirmed"
        draft.confirmed_item_ids_json = added_ids
        draft.confirmed_at = now
        draft.updated_at = now
        plan.updated_at = now
        confirmed_plan_id = plan.id
        confirmed_draft_id = draft.id
        added_count = len(added_ids)
        response_version = version
        await db.commit()
    except StudyPlanError as exc:
        await db.rollback()
        logger.warning(
            "profile_plan_enrichment_confirm_rejected user_id=%s plan_id=%s draft_id=%s reason=%s",
            user_id,
            plan_id,
            draft_id,
            exc.detail,
        )
        raise
    except IntegrityError as exc:
        await db.rollback()
        logger.warning(
            "profile_plan_enrichment_confirm_rejected user_id=%s plan_id=%s draft_id=%s reason=integrity_conflict",
            user_id,
            plan_id,
            draft_id,
        )
        raise StudyPlanError("profile_plan_enrichment_not_confirmable") from exc
    except Exception:
        await db.rollback()
        logger.exception(
            "profile_plan_enrichment_confirm_failed user_id=%s plan_id=%s draft_id=%s",
            user_id,
            plan_id,
            draft_id,
        )
        raise

    if response_version is not None:
        # 同一个 session 在生成上下文时已经加载过 version/stage.items；确认后必须刷新关系，
        # 否则返回 payload 可能复用旧集合，看不到刚追加的补强题。
        await db.refresh(response_version, attribute_names=["stages", "items"])
        for stage in response_version.stages:
            await db.refresh(stage, attribute_names=["items"])
            for stage_item in stage.items:
                await db.refresh(stage_item, attribute_names=["problem"])
    payload = await study_plan_payload(db, user, confirmed_plan_id)
    logger.info(
        "profile_plan_enrichment_confirmed user_id=%s plan_id=%s draft_id=%s added_count=%s",
        user_id,
        confirmed_plan_id,
        confirmed_draft_id,
        added_count,
    )
    return payload


async def _lock_plan_for_confirmation(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
) -> None:
    result = await db.execute(
        select(StudyPlan)
        .where(
            StudyPlan.id == plan_id,
            StudyPlan.user_id == user.id,
            StudyPlan.status == "active",
        )
        .with_for_update()
    )
    if result.scalar_one_or_none() is None:
        raise StudyPlanError("active_study_plan_not_found")


async def _lock_version_content_for_confirmation(
    db: AsyncSession,
    version_id: int,
) -> None:
    # 确认补强题时要串行化当前版本的阶段尾部和题目集合，避免并发确认时
    # 同时通过重复题检查或计算出相同 order_index。
    await db.execute(
        select(StudyPlanVersion)
        .where(StudyPlanVersion.id == version_id)
        .with_for_update()
    )
    await db.execute(
        select(StudyPlanStage)
        .where(StudyPlanStage.version_id == version_id)
        .with_for_update()
    )
    await db.execute(
        select(StudyPlanItem)
        .where(StudyPlanItem.version_id == version_id)
        .with_for_update()
    )


async def _load_draft(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
    draft_id: int,
    *,
    for_update: bool,
) -> ProfilePlanEnrichmentDraft:
    query = select(ProfilePlanEnrichmentDraft).where(
        ProfilePlanEnrichmentDraft.id == draft_id,
        ProfilePlanEnrichmentDraft.user_id == user.id,
        ProfilePlanEnrichmentDraft.study_plan_id == plan_id,
    )
    if for_update:
        query = query.with_for_update()
    result = await db.execute(query)
    draft = result.scalar_one_or_none()
    if draft is None:
        raise StudyPlanError("profile_plan_enrichment_not_found")
    return draft


async def _problem_by_slug(db: AsyncSession, slug: str) -> Problem:
    result = await db.execute(
        select(Problem).where(Problem.slug == slug, Problem.is_paid_only.is_(False))
    )
    problem = result.scalar_one_or_none()
    if problem is None:
        raise StudyPlanError("profile_plan_enrichment_not_confirmable")
    return problem


def _merged_skill_tags(problem: Problem, item_payload: dict[str, Any]) -> list[str]:
    tags = list(_problem_tag_slugs(problem))
    for value in _string_list(item_payload.get("weakness_targets")):
        if value not in tags:
            tags.append(value)
    return tags[:12]


def _add_enrichment_change_log(
    db: AsyncSession,
    version: StudyPlanVersion,
    item: StudyPlanItem,
    draft: ProfilePlanEnrichmentDraft,
) -> None:
    db.add(
        PlanChangeLog(
            version_id=version.id,
            change_type="profile_enrichment_added",
            problem_id=item.problem_id,
            detail_json={
                "draft_id": draft.id,
                "problem_slug": item.problem_slug,
                "source": "profile_plan_enrichment",
                "stage_id": item.stage_id,
                "study_plan_item_id": item.id,
            },
            reason_md=item.recommendation_reason,
        )
    )


async def _load_active_plan_version(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
) -> tuple[StudyPlan, StudyPlanVersion]:
    result = await db.execute(
        select(StudyPlan, StudyPlanVersion)
        .join(
            StudyPlanVersion,
            (StudyPlanVersion.plan_id == StudyPlan.id)
            & (StudyPlanVersion.version_number == StudyPlan.active_version_number),
        )
        .where(
            StudyPlan.id == plan_id,
            StudyPlan.user_id == user.id,
            StudyPlan.status == "active",
            StudyPlanVersion.status == "active",
        )
    )
    row = result.one_or_none()
    if row is None:
        raise StudyPlanError("active_study_plan_not_found")

    plan, version = row
    await db.refresh(version, attribute_names=["stages", "items"])
    for stage in version.stages:
        await db.refresh(stage, attribute_names=["items"])
    for item in version.items:
        await db.refresh(item, attribute_names=["problem"])
    return plan, version


def _current_stage(version: StudyPlanVersion) -> StudyPlanStage:
    sorted_stages = sorted(version.stages, key=lambda stage: stage.stage_index)
    if not sorted_stages:
        raise StudyPlanError("study_plan_stage_not_found")

    # 补强题追加到最接近当前训练状态的阶段；只读计划状态，不在生成上下文时改动正式计划。
    for item_status in ("in_progress", "completed"):
        for stage in sorted_stages:
            if any(item.status == item_status for item in stage.items):
                return stage
    for stage in sorted_stages:
        if any(item.status in {"pending", "in_progress"} for item in stage.items):
            return stage
    return sorted_stages[0]


async def _recent_session_summaries(
    db: AsyncSession,
    user_id: int,
) -> list[SessionSummary]:
    result = await db.execute(
        select(SessionSummary)
        .where(SessionSummary.user_id == user_id)
        .order_by(SessionSummary.updated_at.desc(), SessionSummary.id.desc())
        .limit(MAX_RECENT_SUMMARIES)
    )
    return list(result.scalars().all())


def _profile_context(snapshot: UserProfileSnapshot | None) -> dict[str, Any]:
    if snapshot is None:
        return {
            "id": None,
            "version": "",
            "confidence": "low",
            "overall_level": "unknown",
            "weak_stuck_points": [],
            "weak_skill_tags": [],
            "recent_summary": "",
            "coach_strategy": {},
        }

    payload = snapshot_payload(snapshot)
    return {
        "id": payload.id,
        "version": payload.version,
        "confidence": payload.confidence,
        "overall_level": payload.overall_level,
        "weak_stuck_points": payload.weak_stuck_points,
        "weak_skill_tags": payload.weak_skill_tags,
        "recent_summary": payload.recent_summary,
        "coach_strategy": payload.coach_strategy,
    }


def _training_facts(summaries: list[SessionSummary]) -> dict[str, Any]:
    common_stuck: dict[str, int] = {}
    highest_hint_level = ""
    for summary in summaries:
        if HINT_LEVEL_RANK.get(summary.max_hint_level_used, -1) > HINT_LEVEL_RANK.get(
            highest_hint_level,
            -1,
        ):
            highest_hint_level = summary.max_hint_level_used
        for point in _string_list(summary.main_stuck_points_json):
            common_stuck[point] = common_stuck.get(point, 0) + 1

    return {
        "completed_problem_count": sum(
            1 for summary in summaries if summary.final_submission_result == "ac"
        ),
        "common_stuck_points": [
            {"stuck_point": key, "count": value}
            for key, value in sorted(
                common_stuck.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ],
        "highest_hint_level": highest_hint_level,
        "recent_summaries": [
            {
                "problem_id": summary.problem_id,
                "result": summary.final_submission_result,
                "main_stuck_points": _string_list(summary.main_stuck_points_json),
                "error_types": _string_list(summary.error_types_json),
                "max_hint_level_used": summary.max_hint_level_used,
                "review_summary_md": str(summary.review_summary_md or "")[:600],
            }
            for summary in summaries
        ],
    }


def _plan_context(
    plan: StudyPlan,
    version: StudyPlanVersion,
    current_stage: StudyPlanStage,
    existing_slugs: set[str],
) -> dict[str, Any]:
    return {
        "plan_id": plan.id,
        "version_id": version.id,
        "title": plan.title,
        "current_stage": {
            "id": current_stage.id,
            "stage_index": current_stage.stage_index,
            "title": current_stage.title,
            "focus_tags": _string_list(current_stage.focus_tags_json),
        },
        "stages": [
            {
                "id": stage.id,
                "stage_index": stage.stage_index,
                "title": stage.title,
                "focus_tags": _string_list(stage.focus_tags_json),
                "items": [
                    {
                        "problem_slug": item.problem_slug,
                        "status": item.status,
                        "difficulty": item.difficulty,
                        "tags": _string_list(item.skill_tags_json),
                    }
                    for item in sorted(stage.items, key=lambda item: item.order_index)
                ],
            }
            for stage in sorted(version.stages, key=lambda stage: stage.stage_index)
        ],
        "existing_problem_slugs": sorted(existing_slugs),
    }


async def _candidate_problems(
    db: AsyncSession,
    *,
    existing_slugs: set[str],
    current_stage: StudyPlanStage,
    profile_snapshot: UserProfileSnapshot | None,
    payload: ProfilePlanEnrichmentRequest,
) -> list[dict[str, Any]]:
    query = select(Problem).where(Problem.is_paid_only.is_(False))
    if existing_slugs:
        query = query.where(Problem.slug.not_in(existing_slugs))
    result = await db.execute(query.order_by(Problem.id.asc()).limit(MAX_CANDIDATES * 3))
    problems = list(result.scalars().all())
    weak_terms = _weak_terms(profile_snapshot, current_stage, payload)

    # 先按画像和当前阶段做弱项命中排序，再用难度和题库 id 保持稳定输出。
    ranked = sorted(
        problems,
        key=lambda problem: (
            -_candidate_score(problem, weak_terms=weak_terms),
            DIFFICULTY_RANK.get(problem.difficulty, 99),
            problem.id,
        ),
    )
    return [
        _candidate_payload(problem, weak_terms=weak_terms)
        for problem in ranked[:MAX_CANDIDATES]
    ]


def _candidate_payload(problem: Problem, *, weak_terms: set[str]) -> dict[str, Any]:
    tags = _problem_tag_slugs(problem)
    searchable = _problem_search_terms(problem)
    return {
        "problem_id": problem.id,
        "slug": problem.slug,
        "title": problem.title,
        "translated_title": problem.translated_title,
        "difficulty": problem.difficulty,
        "tags": tags,
        "is_paid_only": bool(problem.is_paid_only),
        "match_reasons": [
            term
            for term in sorted(weak_terms)
            if term and any(term in value for value in searchable)
        ][:5],
    }


def _weak_terms(
    snapshot: UserProfileSnapshot | None,
    current_stage: StudyPlanStage,
    payload: ProfilePlanEnrichmentRequest,
) -> set[str]:
    terms = {_normalize_term(term) for term in _string_list(current_stage.focus_tags_json)}
    terms.update(_intent_tokens(payload.user_intent_md))
    if snapshot is not None:
        skill_profile = _dict_value(snapshot.skill_profile_json)
        stuck_profile = _dict_value(snapshot.stuck_point_profile_json)
        terms.update(
            _normalize_term(value)
            for value in _string_list(skill_profile.get("weak_skill_tags"))
        )
        terms.update(
            _normalize_term(value)
            for value in _string_list(stuck_profile.get("weak_stuck_points"))
        )
    return {term for term in terms if term}


def _intent_tokens(value: str) -> set[str]:
    return {
        token
        for token in (_normalize_term(part) for part in _TOKEN_SPLIT_RE.split(value))
        if token
    }


def _candidate_score(problem: Problem, *, weak_terms: set[str]) -> int:
    searchable = _problem_search_terms(problem)
    return sum(1 for term in weak_terms if any(term in value for value in searchable))


def _problem_tag_slugs(problem: Problem) -> list[str]:
    return [
        str(item.get("slug")).strip()
        for item in _problem_topic_tags(problem)
        if isinstance(item.get("slug"), str) and str(item.get("slug")).strip()
    ]


def _problem_search_terms(problem: Problem) -> set[str]:
    values = {
        _normalize_term(problem.slug),
        _normalize_term(problem.title),
        _normalize_term(problem.translated_title),
    }
    for item in _problem_topic_tags(problem):
        for key in ("slug", "name", "translated_name"):
            if isinstance(item.get(key), str):
                values.add(_normalize_term(item[key]))
    return {value for value in values if value}


def _problem_topic_tags(problem: Problem) -> list[dict[str, Any]]:
    metadata = _dict_value(problem.metadata_json)
    topic_tags = metadata.get("topic_tags")
    return _list_of_dicts(topic_tags)


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_term(value: Any) -> str:
    return str(value or "").strip().lower()


def _suggested_mode(value: Any) -> str:
    text = str(value or "")
    return text if text in _VALID_TRAINING_MODES else "independent"
