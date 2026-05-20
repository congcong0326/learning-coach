from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.auth import AppUser
from backend.app.models.learning import (
    GoalCalibrationDraft,
    PlanChangeLog,
    StudyPlan,
    StudyPlanItem,
    StudyPlanStage,
    StudyPlanVersion,
)
from backend.app.models.problem import Problem


PRESERVED_ITEM_STATUSES = {"completed", "in_progress", "skipped"}
ACTIVE_VERSION_STATUSES = {"active", "draft"}


class StudyPlanError(RuntimeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


async def pause_other_active_plans(
    db: AsyncSession,
    user: AppUser,
    keep_plan_id: int | None = None,
) -> None:
    query = update(StudyPlan).where(
        StudyPlan.user_id == user.id,
        StudyPlan.status == "active",
    )
    if keep_plan_id is not None:
        query = query.where(StudyPlan.id != keep_plan_id)
    await db.execute(query.values(status="paused", updated_at=datetime.now(UTC)))


async def get_active_plan_version(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
) -> StudyPlanVersion:
    plan = await _load_plan(db, user, plan_id)
    result = await db.execute(
        select(StudyPlanVersion)
        .options(
            selectinload(StudyPlanVersion.stages)
            .selectinload(StudyPlanStage.items)
            .selectinload(StudyPlanItem.problem),
            selectinload(StudyPlanVersion.items).selectinload(StudyPlanItem.problem),
        )
        .where(
            StudyPlanVersion.plan_id == plan.id,
            StudyPlanVersion.version_number == plan.active_version_number,
        )
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise StudyPlanError("active_study_plan_version_not_found")
    if version.status not in ACTIVE_VERSION_STATUSES:
        raise StudyPlanError("active_study_plan_version_inconsistent")
    await _set_only_active_version(db, version)
    return version


async def _problem_by_slug(db: AsyncSession, slug: str) -> Problem:
    result = await db.execute(select(Problem).where(Problem.slug == slug))
    problem = result.scalar_one_or_none()
    if problem is None:
        raise StudyPlanError("validated_problem_not_found")
    return problem


async def _load_plan(db: AsyncSession, user: AppUser, plan_id: int) -> StudyPlan:
    result = await db.execute(
        select(StudyPlan).where(StudyPlan.id == plan_id, StudyPlan.user_id == user.id)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise StudyPlanError("study_plan_not_found")
    return plan


async def _set_only_active_version(
    db: AsyncSession,
    version: StudyPlanVersion,
) -> None:
    await db.execute(
        update(StudyPlanVersion)
        .where(
            StudyPlanVersion.plan_id == version.plan_id,
            StudyPlanVersion.id != version.id,
            StudyPlanVersion.status == "active",
        )
        .values(status="superseded")
    )
    version.status = "active"


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _list_of_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


async def _normalized_stage_payloads(
    db: AsyncSession,
    draft_plan_json: dict[str, Any],
) -> list[tuple[dict[str, Any], list[tuple[dict[str, Any], Problem]]]]:
    seen_problem_ids: set[int] = set()
    normalized: list[tuple[dict[str, Any], list[tuple[dict[str, Any], Problem]]]] = []
    for stage_payload in _list_of_dicts(draft_plan_json.get("stages", [])):
        normalized_items: list[tuple[dict[str, Any], Problem]] = []
        for item_payload in _list_of_dicts(stage_payload.get("items", [])):
            slug = item_payload.get("problem_slug", "")
            if not isinstance(slug, str) or not slug:
                raise StudyPlanError("validated_problem_not_found")
            problem = await _problem_by_slug(db, slug)
            if problem.id in seen_problem_ids:
                raise StudyPlanError("duplicate_plan_item")
            seen_problem_ids.add(problem.id)
            normalized_items.append((item_payload, problem))
        normalized.append((stage_payload, normalized_items))
    return normalized


async def _write_version_content(
    db: AsyncSession,
    version: StudyPlanVersion,
    draft_plan_json: dict[str, Any],
) -> None:
    normalized_stages = await _normalized_stage_payloads(db, draft_plan_json)
    for stage_index, (stage_payload, item_payloads) in enumerate(
        normalized_stages,
        start=1,
    ):
        stage = StudyPlanStage(
            version_id=version.id,
            stage_index=stage_index,
            title=str(stage_payload.get("title", f"阶段 {stage_index}")),
            objective_md=str(stage_payload.get("objective_md", "")),
            focus_tags_json=_list_of_strings(stage_payload.get("focus_tags", [])),
            assessment_criteria_json=_list_of_strings(
                stage_payload.get("assessment_criteria", [])
            ),
            status="in_progress" if stage_index == 1 else "not_started",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(stage)
        await db.flush()
        for order_index, (item_payload, problem) in enumerate(
            item_payloads,
            start=1,
        ):
            db.add(
                StudyPlanItem(
                    version_id=version.id,
                    stage_id=stage.id,
                    problem_id=problem.id,
                    problem_slug=problem.slug,
                    skill_tags_json=_list_of_strings(
                        item_payload.get("skill_tags", [])
                    ),
                    difficulty=problem.difficulty,
                    suggested_mode=str(item_payload.get("suggested_mode", "guided")),
                    recommendation_reason=str(
                        item_payload.get("recommendation_reason", "")
                    ),
                    status="pending",
                    order_index=order_index,
                    locked=False,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )


async def confirm_plan_draft(
    db: AsyncSession,
    user: AppUser,
    draft_id: int,
) -> StudyPlan:
    try:
        result = await db.execute(
            select(GoalCalibrationDraft).where(
                GoalCalibrationDraft.id == draft_id,
                GoalCalibrationDraft.user_id == user.id,
                GoalCalibrationDraft.status == "ready_for_review",
            )
        )
        draft = result.scalar_one_or_none()
        if draft is None:
            raise StudyPlanError("plan_draft_not_ready")

        await pause_other_active_plans(db, user)
        now = datetime.now(UTC)
        plan = StudyPlan(
            user_id=user.id,
            title=str(draft.draft_plan_json.get("title", "学习计划")),
            status="active",
            active_version_number=1,
            created_at=now,
            updated_at=now,
        )
        db.add(plan)
        await db.flush()
        version = StudyPlanVersion(
            plan_id=plan.id,
            source_draft_id=draft.id,
            version_number=1,
            status="active",
            target_snapshot_json=draft.draft_goal_json,
            generation_summary_md=str(
                draft.draft_plan_json.get("generation_summary_md", "")
            ),
            adjustment_summary_md="",
            validation_report_json=draft.validation_report_json,
            repair_log_json=draft.repair_log_json,
            created_at=now,
            activated_at=now,
        )
        db.add(version)
        await db.flush()
        await _write_version_content(db, version, draft.draft_plan_json)
        draft.status = "confirmed"
        draft.confirmed_plan_id = plan.id
        draft.confirmed_version_id = version.id
        draft.confirmed_at = now
        draft.updated_at = now
        await db.commit()
        await db.refresh(plan)
        return plan
    except Exception:
        await db.rollback()
        raise


def _sort_stages(stages: list[StudyPlanStage]) -> list[StudyPlanStage]:
    return sorted(stages, key=lambda stage: stage.stage_index)


def _sort_items(items: list[StudyPlanItem]) -> list[StudyPlanItem]:
    return sorted(items, key=lambda item: item.order_index)


def _stage_payload_from_items(
    stage: StudyPlanStage,
    items: list[StudyPlanItem],
) -> dict[str, Any]:
    return {
        "title": stage.title,
        "objective_md": stage.objective_md,
        "focus_tags": stage.focus_tags_json,
        "assessment_criteria": stage.assessment_criteria_json,
        "items": [
            {
                "problem_slug": item.problem_slug,
                "skill_tags": item.skill_tags_json,
                "suggested_mode": item.suggested_mode,
                "recommendation_reason": item.recommendation_reason,
            }
            for item in items
        ],
    }


def _preserved_items(old_version: StudyPlanVersion) -> dict[str, StudyPlanItem]:
    return {
        item.problem_slug: item
        for item in old_version.items
        if item.locked or item.status in PRESERVED_ITEM_STATUSES
    }


def _draft_problem_slugs(draft_plan_json: dict[str, Any]) -> set[str]:
    return {
        str(item["problem_slug"])
        for stage in _list_of_dicts(draft_plan_json.get("stages", []))
        for item in _list_of_dicts(stage.get("items", []))
        if isinstance(item.get("problem_slug"), str)
    }


def _merged_adjustment_draft(
    old_version: StudyPlanVersion,
    draft_plan_json: dict[str, Any],
) -> dict[str, Any]:
    preserved = _preserved_items(old_version)
    draft_slugs = _draft_problem_slugs(draft_plan_json)
    preserved_stages: list[dict[str, Any]] = []
    for stage in _sort_stages(old_version.stages):
        preserved_items = [
            item
            for item in _sort_items(stage.items)
            if item.problem_slug in preserved
            and item.problem_slug not in draft_slugs
        ]
        if preserved_items:
            preserved_stages.append(_stage_payload_from_items(stage, preserved_items))
    return {
        **draft_plan_json,
        "stages": preserved_stages
        + _list_of_dicts(draft_plan_json.get("stages", [])),
    }


async def _copy_preserved_item_state(
    new_version: StudyPlanVersion,
    preserved_by_slug: dict[str, StudyPlanItem],
) -> None:
    for item in new_version.items:
        old_item = preserved_by_slug.get(item.problem_slug)
        if old_item is None:
            continue
        item.status = old_item.status
        item.locked = old_item.locked
        item.updated_at = datetime.now(UTC)


def _add_change_log(
    db: AsyncSession,
    version: StudyPlanVersion,
    change_type: str,
    *,
    problem_id: int | None = None,
    detail_json: dict[str, Any] | None = None,
    reason_md: str = "",
) -> None:
    db.add(
        PlanChangeLog(
            version_id=version.id,
            change_type=change_type,
            problem_id=problem_id,
            detail_json=detail_json or {},
            reason_md=reason_md,
        )
    )


def _write_adjustment_change_logs(
    db: AsyncSession,
    old_version: StudyPlanVersion,
    new_version: StudyPlanVersion,
    *,
    adjustment_summary_md: str,
) -> None:
    old_by_slug = {item.problem_slug: item for item in old_version.items}
    new_by_slug = {item.problem_slug: item for item in new_version.items}
    old_stage_by_id = {stage.id: stage for stage in old_version.stages}
    new_stage_by_id = {stage.id: stage for stage in new_version.stages}
    preserved_by_slug = _preserved_items(old_version)

    for slug, item in preserved_by_slug.items():
        if slug in new_by_slug:
            _add_change_log(
                db,
                new_version,
                "preserved",
                problem_id=item.problem_id,
                detail_json={"problem_slug": slug, "status": item.status},
                reason_md=adjustment_summary_md,
            )

    for slug, item in new_by_slug.items():
        if slug not in old_by_slug:
            _add_change_log(
                db,
                new_version,
                "added",
                problem_id=item.problem_id,
                detail_json={"problem_slug": slug},
                reason_md=adjustment_summary_md,
            )

    for slug, item in old_by_slug.items():
        if slug not in new_by_slug and slug not in preserved_by_slug:
            _add_change_log(
                db,
                new_version,
                "removed",
                problem_id=item.problem_id,
                detail_json={"problem_slug": slug},
                reason_md=adjustment_summary_md,
            )

    for slug, item in new_by_slug.items():
        old_item = old_by_slug.get(slug)
        if old_item is None:
            continue
        old_position = (
            old_stage_by_id[old_item.stage_id].stage_index,
            old_item.order_index,
        )
        new_position = (
            new_stage_by_id[item.stage_id].stage_index,
            item.order_index,
        )
        if old_position != new_position:
            _add_change_log(
                db,
                new_version,
                "reordered",
                problem_id=item.problem_id,
                detail_json={
                    "problem_slug": slug,
                    "from": list(old_position),
                    "to": list(new_position),
                },
                reason_md=adjustment_summary_md,
            )


async def clone_adjusted_version(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
    adjustment_summary_md: str,
    draft_plan_json: dict[str, Any],
    validation_report_json: dict[str, Any],
    repair_log_json: list[dict[str, Any]],
) -> StudyPlanVersion:
    try:
        plan = await _load_plan(db, user, plan_id)
        old_version = await get_active_plan_version(db, user, plan_id)
        now = datetime.now(UTC)
        old_version.status = "superseded"
        new_version = StudyPlanVersion(
            plan_id=plan.id,
            cloned_from_version_id=old_version.id,
            version_number=old_version.version_number + 1,
            status="active",
            target_snapshot_json=old_version.target_snapshot_json,
            generation_summary_md=old_version.generation_summary_md,
            adjustment_summary_md=adjustment_summary_md,
            validation_report_json=validation_report_json,
            repair_log_json=repair_log_json,
            created_at=now,
            activated_at=now,
        )
        db.add(new_version)
        await db.flush()
        preserved_by_slug = _preserved_items(old_version)
        merged_draft = _merged_adjustment_draft(old_version, draft_plan_json)
        await _write_version_content(db, new_version, merged_draft)
        await db.flush()
        await db.refresh(
            new_version,
            attribute_names=["stages", "items"],
        )
        for item in new_version.items:
            await db.refresh(item, attribute_names=["stage", "problem"])
        await _copy_preserved_item_state(new_version, preserved_by_slug)
        _write_adjustment_change_logs(
            db,
            old_version,
            new_version,
            adjustment_summary_md=adjustment_summary_md,
        )
        plan.active_version_number = new_version.version_number
        plan.updated_at = now
        await db.commit()
        return await get_active_plan_version(db, user, plan.id)
    except Exception:
        await db.rollback()
        raise


async def activate_plan(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
) -> StudyPlan:
    try:
        plan = await _load_plan(db, user, plan_id)
        if plan.status not in {"active", "paused", "completed"}:
            raise StudyPlanError("study_plan_cannot_be_activated")
        await pause_other_active_plans(db, user, keep_plan_id=plan.id)
        result = await db.execute(
            select(StudyPlanVersion).where(
                StudyPlanVersion.plan_id == plan.id,
                StudyPlanVersion.version_number == plan.active_version_number,
            )
        )
        version = result.scalar_one_or_none()
        if version is None:
            raise StudyPlanError("active_study_plan_version_not_found")
        await _set_only_active_version(db, version)
        version.activated_at = version.activated_at or datetime.now(UTC)
        plan.status = "active"
        plan.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(plan)
        return plan
    except Exception:
        await db.rollback()
        raise


async def list_study_plans(db: AsyncSession, user: AppUser) -> dict[str, Any]:
    result = await db.execute(
        select(StudyPlan)
        .where(StudyPlan.user_id == user.id)
        .order_by(StudyPlan.updated_at.desc(), StudyPlan.id.desc())
    )
    return {
        "items": [
            {
                "id": plan.id,
                "title": plan.title,
                "status": plan.status,
                "active_version_number": plan.active_version_number,
                "created_at": plan.created_at,
                "updated_at": plan.updated_at,
            }
            for plan in result.scalars().all()
        ]
    }


async def get_active_study_plan(db: AsyncSession, user: AppUser) -> StudyPlan:
    result = await db.execute(
        select(StudyPlan)
        .where(
            StudyPlan.user_id == user.id,
            StudyPlan.status == "active",
        )
        .order_by(StudyPlan.updated_at.desc(), StudyPlan.id.desc())
    )
    active_plans = list(result.scalars().all())
    if not active_plans:
        raise StudyPlanError("active_study_plan_not_found")
    selected_plan = active_plans[0]
    if len(active_plans) > 1:
        now = datetime.now(UTC)
        for plan in active_plans[1:]:
            plan.status = "paused"
            plan.updated_at = now
        await db.commit()
        await db.refresh(selected_plan)
    return selected_plan


async def _load_payload_version(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
    version_id: int | None = None,
) -> tuple[StudyPlan, StudyPlanVersion]:
    plan = await _load_plan(db, user, plan_id)
    version_query = (
        select(StudyPlanVersion)
        .options(
            selectinload(StudyPlanVersion.stages)
            .selectinload(StudyPlanStage.items)
            .selectinload(StudyPlanItem.problem),
            selectinload(StudyPlanVersion.items).selectinload(StudyPlanItem.problem),
        )
        .where(StudyPlanVersion.plan_id == plan.id)
    )
    if version_id is None:
        version_query = version_query.where(
            StudyPlanVersion.version_number == plan.active_version_number
        )
    else:
        version_query = version_query.where(StudyPlanVersion.id == version_id)
    result = await db.execute(version_query)
    version = result.scalar_one_or_none()
    if version is None:
        raise StudyPlanError("study_plan_version_not_found")
    return plan, version


def _item_payload(item: StudyPlanItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "problem_id": item.problem_id,
        "problem_slug": item.problem_slug,
        "frontend_id": item.problem.frontend_id,
        "title": item.problem.title,
        "translated_title": item.problem.translated_title,
        "difficulty": item.difficulty,
        "skill_tags": item.skill_tags_json,
        "suggested_mode": item.suggested_mode,
        "recommendation_reason": item.recommendation_reason,
        "status": item.status,
        "order_index": item.order_index,
        "locked": item.locked,
    }


def _stage_response(stage: StudyPlanStage) -> dict[str, Any]:
    return {
        "id": stage.id,
        "stage_index": stage.stage_index,
        "title": stage.title,
        "objective_md": stage.objective_md,
        "focus_tags": stage.focus_tags_json,
        "assessment_criteria": stage.assessment_criteria_json,
        "status": stage.status,
        "items": [_item_payload(item) for item in _sort_items(stage.items)],
    }


def _version_response(version: StudyPlanVersion) -> dict[str, Any]:
    return {
        "id": version.id,
        "version_number": version.version_number,
        "status": version.status,
        "target_snapshot": version.target_snapshot_json,
        "generation_summary_md": version.generation_summary_md,
        "adjustment_summary_md": version.adjustment_summary_md,
        "validation_report": version.validation_report_json,
        "repair_log": version.repair_log_json,
        "stages": [_stage_response(stage) for stage in _sort_stages(version.stages)],
        "created_at": version.created_at,
        "activated_at": version.activated_at,
    }


async def study_plan_payload(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
    *,
    version_id: int | None = None,
) -> dict[str, Any]:
    plan, version = await _load_payload_version(db, user, plan_id, version_id)
    return {
        "id": plan.id,
        "title": plan.title,
        "status": plan.status,
        "active_version_number": plan.active_version_number,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
        "active_version": _version_response(version),
    }


async def get_current_study_plan_payload(
    db: AsyncSession,
    user: AppUser,
) -> dict[str, Any]:
    plan = await get_active_study_plan(db, user)
    return await study_plan_payload(db, user, plan.id)


async def update_plan_item_status(
    db: AsyncSession,
    user: AppUser,
    item_id: int,
    status: str,
) -> int:
    if status not in {"pending", "skipped"}:
        raise StudyPlanError("invalid_plan_item_status")
    try:
        result = await db.execute(
            select(StudyPlanItem, StudyPlan)
            .join(StudyPlanVersion, StudyPlanVersion.id == StudyPlanItem.version_id)
            .join(StudyPlan, StudyPlan.id == StudyPlanVersion.plan_id)
            .where(
                StudyPlanItem.id == item_id,
                StudyPlan.user_id == user.id,
                StudyPlan.status == "active",
                StudyPlanVersion.status == "active",
                StudyPlanVersion.version_number == StudyPlan.active_version_number,
            )
        )
        row = result.one_or_none()
        if row is None:
            raise StudyPlanError("active_plan_item_not_found")
        item, plan = row
        if item.locked:
            raise StudyPlanError("locked_plan_item_cannot_be_updated")
        item.status = status
        item.updated_at = datetime.now(UTC)
        plan.updated_at = datetime.now(UTC)
        await db.commit()
        return plan.id
    except Exception:
        await db.rollback()
        raise


async def reorder_stage_items(
    db: AsyncSession,
    user: AppUser,
    stage_id: int,
    item_ids: list[int],
) -> int:
    try:
        result = await db.execute(
            select(StudyPlanStage, StudyPlan)
            .join(StudyPlanVersion, StudyPlanVersion.id == StudyPlanStage.version_id)
            .join(StudyPlan, StudyPlan.id == StudyPlanVersion.plan_id)
            .options(selectinload(StudyPlanStage.items))
            .where(
                StudyPlanStage.id == stage_id,
                StudyPlan.user_id == user.id,
                StudyPlan.status == "active",
                StudyPlanVersion.status == "active",
                StudyPlanVersion.version_number == StudyPlan.active_version_number,
            )
        )
        row = result.one_or_none()
        if row is None:
            raise StudyPlanError("active_plan_stage_not_found")
        stage, plan = row
        current_ids = {item.id for item in stage.items}
        if set(item_ids) != current_ids or len(item_ids) != len(current_ids):
            raise StudyPlanError("stage_item_set_mismatch")
        items_by_id = {item.id: item for item in stage.items}
        now = datetime.now(UTC)
        for temporary_index, item in enumerate(stage.items, start=1):
            item.order_index = -temporary_index
        await db.flush()
        for order_index, item_id in enumerate(item_ids, start=1):
            item = items_by_id[item_id]
            item.order_index = order_index
            item.updated_at = now
        plan.updated_at = now
        await db.commit()
        return plan.id
    except Exception:
        await db.rollback()
        raise


async def list_study_plan_payloads(
    db: AsyncSession,
    user: AppUser,
) -> dict[str, Any]:
    return await list_study_plans(db, user)
