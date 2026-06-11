from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, func, select, update
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
from backend.app.models.practice import PracticeEvent, PracticeSession, SubmissionFeedback
from backend.app.models.problem import Problem
from backend.app.schemas.learning import (
    FollowupAnswer,
    GoalCalibrationInput,
)
from backend.app.services.credential_crypto import CredentialEncryptionError
from backend.app.services.learning_plan_llm import (
    PROMPT_VERSION,
    client_for_user,
    generate_plan_with_repair,
)
from backend.app.services.learning_plan_validator import normalise_suggested_mode
from backend.app.services.llm_credential_service import LlmCredentialError


# 调整计划时，已产生进度的题目会带入新版本，避免 LLM 新结构静默丢掉用户已投入的训练。
PRESERVED_ITEM_STATUSES = {"completed", "in_progress", "skipped"}
ACTIVE_VERSION_STATUSES = {"active", "draft"}
PRACTICE_PROGRESS_EVENT_TYPES = {
    "user_message",
    "assistant_message",
    "code_saved",
    "submission_feedback",
}
GENERATABLE_DRAFT_STATUSES = {
    "collecting_input",
    "asking_followup",
    "ready_for_review",
    "failed",
}
PLAN_TITLE_MAX_LENGTH = 180
GOAL_TYPE_LABELS = {
    "beginner": "刷题入门",
    "interview_sprint": "面试冲刺",
    "strengthen_weakness": "专项补弱",
    "maintain": "保持手感",
}
PREFERRED_LANGUAGE_LABELS = {
    "c": "C",
    "go": "Go",
    "python3": "Python3",
    "javascript": "JavaScript",
    "java": "Java",
}
MAX_FOLLOWUPS = 3
logger = logging.getLogger(__name__)


class StudyPlanError(RuntimeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


async def _client_for_user_or_error(
    db: AsyncSession,
    user: AppUser,
) -> tuple[Any, Any]:
    try:
        return await client_for_user(db, user)
    except LlmCredentialError as exc:
        raise StudyPlanError(exc.detail) from exc
    except CredentialEncryptionError as exc:
        raise StudyPlanError(str(exc)) from exc


def _followup_question_count(history: list[dict[str, Any]]) -> int:
    return sum(1 for item in history if item.get("role") == "assistant")


def _normalise_followup_question(
    question: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if question is None:
        return None
    question_id = question.get("question_id")
    question_text = question.get("question")
    if not isinstance(question_id, str) or not question_id:
        return None
    if not isinstance(question_text, str) or not question_text:
        return None
    return {
        "role": "assistant",
        "question_id": question_id,
        "question": question_text,
    }


def _goal_calibration_start_response(draft: GoalCalibrationDraft) -> dict[str, Any]:
    history = _list_of_dicts(draft.followup_messages_json)
    last_message = history[-1] if history else {}
    last_question = (
        last_message
        if draft.status == "asking_followup" and last_message.get("role") == "assistant"
        else {}
    )
    question_count = _followup_question_count(history)
    return {
        "draft_id": draft.id,
        "status": draft.status,
        "followup_question": last_question.get("question"),
        "followup_question_id": last_question.get("question_id"),
        "remaining_followups": (
            max(0, MAX_FOLLOWUPS - question_count)
            if draft.status == "asking_followup"
            else 0
        ),
    }


def _format_report_issues(report: dict[str, Any]) -> str:
    issues = report.get("issues", [])
    if isinstance(issues, list):
        return ",".join(str(issue) for issue in issues) or "none"
    return str(issues) if issues else "none"


def _draft_plan_counts(draft_plan_json: dict[str, Any]) -> tuple[int, int]:
    stages = _list_of_dicts(draft_plan_json.get("stages", []))
    item_count = sum(len(_list_of_dicts(stage.get("items", []))) for stage in stages)
    return len(stages), item_count


def _title_text(value: Any, fallback: str = "学习计划") -> str:
    if not isinstance(value, str):
        return fallback
    stripped = " ".join(value.split())
    return stripped or fallback


def _truncate_title(value: str, max_length: int = PLAN_TITLE_MAX_LENGTH) -> str:
    if len(value) <= max_length:
        return value
    return value[: max(0, max_length - 3)].rstrip() + "..."


def _plan_title_context(draft: GoalCalibrationDraft) -> dict[str, Any]:
    if isinstance(draft.draft_goal_json, dict) and draft.draft_goal_json:
        return draft.draft_goal_json
    return draft.input_json if isinstance(draft.input_json, dict) else {}


def _label_from_context(
    context: dict[str, Any],
    key: str,
    labels: dict[str, str],
) -> str:
    raw_value = context.get(key)
    if not isinstance(raw_value, str):
        return ""
    return labels.get(raw_value, "")


async def _existing_plan_titles(db: AsyncSession, user: AppUser) -> set[str]:
    result = await db.execute(select(StudyPlan.title).where(StudyPlan.user_id == user.id))
    return {str(title) for title in result.scalars().all()}


def _title_with_sequence(base_title: str, sequence: int) -> str:
    if sequence <= 1:
        return _truncate_title(base_title)
    suffix = f" ({sequence})"
    return f"{_truncate_title(base_title, PLAN_TITLE_MAX_LENGTH - len(suffix))}{suffix}"


async def _build_confirmed_plan_title(
    db: AsyncSession,
    user: AppUser,
    draft: GoalCalibrationDraft,
    now: datetime,
) -> str:
    context = _plan_title_context(draft)
    parts = [
        _title_text(draft.draft_plan_json.get("title")),
        _label_from_context(context, "goal_type", GOAL_TYPE_LABELS),
        _label_from_context(context, "preferred_language", PREFERRED_LANGUAGE_LABELS),
        now.strftime("%Y-%m-%d %H:%M"),
    ]
    title = _truncate_title(" · ".join(part for part in parts if part))
    existing_titles = await _existing_plan_titles(db, user)
    sequence = 1
    candidate = _title_with_sequence(title, sequence)
    while candidate in existing_titles:
        sequence += 1
        candidate = _title_with_sequence(title, sequence)
    return candidate


def _plan_draft_response_from_json(
    *,
    draft_id: int,
    status: str,
    draft_plan_json: dict[str, Any],
    target_snapshot: dict[str, Any],
    validation_report: dict[str, Any],
    repair_log: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "draft_id": draft_id,
        "status": status,
        "target_snapshot": target_snapshot,
        "generation_summary_md": str(draft_plan_json.get("generation_summary_md", "")),
        "stages": _list_of_dicts(draft_plan_json.get("stages", [])),
        "validation_report": validation_report,
        "repair_log": repair_log,
        "uncertainty_notes": _list_of_strings(
            draft_plan_json.get("uncertainty_notes", [])
        ),
    }


def _plan_draft_response_from_goal_draft(
    draft: GoalCalibrationDraft,
) -> dict[str, Any]:
    target_snapshot = draft.draft_goal_json or draft.draft_plan_json.get(
        "target_snapshot",
        {},
    )
    return _plan_draft_response_from_json(
        draft_id=draft.id,
        status=draft.status,
        draft_plan_json=draft.draft_plan_json,
        target_snapshot=target_snapshot,
        validation_report=draft.validation_report_json,
        repair_log=draft.repair_log_json,
    )


def _plan_draft_response_from_version(
    version: StudyPlanVersion,
    *,
    status: str = "ready_for_review",
) -> dict[str, Any]:
    items_by_stage_id: dict[int, list[StudyPlanItem]] = {}
    for item in version.items:
        items_by_stage_id.setdefault(item.stage_id, []).append(item)
    draft_plan_json = {
        "generation_summary_md": version.generation_summary_md,
        "stages": [
            _stage_payload_from_items(
                stage,
                _sort_items(items_by_stage_id.get(stage.id, [])),
            )
            for stage in _sort_stages(version.stages)
        ],
    }
    return _plan_draft_response_from_json(
        draft_id=version.id,
        status=status,
        draft_plan_json=draft_plan_json,
        target_snapshot=version.target_snapshot_json,
        validation_report=version.validation_report_json,
        repair_log=version.repair_log_json,
    )


async def start_goal_calibration(
    db: AsyncSession,
    user: AppUser,
    payload: GoalCalibrationInput,
) -> dict[str, Any]:
    # 目标校准的第一步只保存结构化输入和追问历史；正式学习计划必须等用户预览草稿后确认。
    payload_json = payload.model_dump()
    logger.info(
        "goal calibration start requested user_id=%s goal_type=%s "
        "timeline=%s preferred_language=%s weakness_count=%s",
        user.id,
        payload_json.get("goal_type"),
        payload_json.get("target_timeline"),
        payload_json.get("preferred_language"),
        len(payload_json.get("self_reported_weaknesses", [])),
    )
    client, credential = await _client_for_user_or_error(db, user)
    question = _normalise_followup_question(
        await client.followup_question(payload_json, [])
    )
    history = [question] if question is not None else []
    now = datetime.now(UTC)
    draft = GoalCalibrationDraft(
        user_id=user.id,
        llm_credential_id=credential.id,
        input_json=payload_json,
        followup_messages_json=history,
        draft_goal_json={},
        draft_plan_json={},
        validation_report_json={},
        repair_log_json=[],
        prompt_version=PROMPT_VERSION,
        model_name=credential.model_name,
        status="asking_followup" if question is not None else "collecting_input",
        error_message="",
        created_at=now,
        updated_at=now,
    )
    db.add(draft)
    await db.commit()
    await db.refresh(draft)
    logger.info(
        "goal calibration start completed user_id=%s draft_id=%s status=%s "
        "credential_id=%s model=%s has_followup=%s",
        user.id,
        draft.id,
        draft.status,
        credential.id,
        credential.model_name,
        question is not None,
    )
    return _goal_calibration_start_response(draft)


async def _load_goal_draft(
    db: AsyncSession,
    user: AppUser,
    draft_id: int,
) -> GoalCalibrationDraft:
    result = await db.execute(
        select(GoalCalibrationDraft).where(
            GoalCalibrationDraft.id == draft_id,
            GoalCalibrationDraft.user_id == user.id,
        )
    )
    draft = result.scalar_one_or_none()
    if draft is None:
        raise StudyPlanError("goal_calibration_draft_not_found")
    return draft


async def answer_goal_followup(
    db: AsyncSession,
    user: AppUser,
    draft_id: int,
    payload: FollowupAnswer,
) -> dict[str, Any]:
    draft = await _load_goal_draft(db, user, draft_id)
    if draft.status not in {"asking_followup", "collecting_input"}:
        logger.warning(
            "goal calibration followup rejected draft_id=%s user_id=%s "
            "status=%s reason=goal_calibration_draft_not_editable",
            draft.id,
            user.id,
            draft.status,
        )
        raise StudyPlanError("goal_calibration_draft_not_editable")

    history = _list_of_dicts(draft.followup_messages_json)
    logger.info(
        "goal calibration followup received draft_id=%s user_id=%s status=%s "
        "history_messages=%s",
        draft.id,
        user.id,
        draft.status,
        len(history),
    )
    history.append(
        {
            "role": "user",
            "question_id": payload.question_id,
            "answer": payload.answer,
        }
    )
    if _followup_question_count(history) < MAX_FOLLOWUPS:
        # 追问上限由后端兜住，即使模型持续想追问也不能阻塞用户生成计划。
        client, credential = await _client_for_user_or_error(db, user)
        question = _normalise_followup_question(
            await client.followup_question(draft.input_json, history)
        )
        draft.llm_credential_id = credential.id
        draft.model_name = credential.model_name
        if question is not None:
            history.append(question)
            draft.status = "asking_followup"
        else:
            draft.status = "collecting_input"
    else:
        draft.status = "collecting_input"

    draft.followup_messages_json = history
    draft.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(draft)
    response = _goal_calibration_start_response(draft)
    logger.info(
        "goal calibration followup completed draft_id=%s user_id=%s status=%s "
        "history_messages=%s remaining_followups=%s",
        draft.id,
        user.id,
        draft.status,
        len(history),
        response["remaining_followups"],
    )
    return response


async def generate_goal_plan_draft(
    db: AsyncSession,
    user: AppUser,
    draft_id: int,
) -> dict[str, Any]:
    draft = await _load_goal_draft(db, user, draft_id)
    if draft.status not in GENERATABLE_DRAFT_STATUSES:
        logger.warning(
            "goal plan draft generation rejected "
            "draft_id=%s user_id=%s status=%s reason=goal_calibration_draft_not_generatable",
            draft.id,
            user.id,
            draft.status,
        )
        raise StudyPlanError("goal_calibration_draft_not_generatable")
    if (
        draft.status == "ready_for_review"
        and draft.draft_plan_json
        and draft.prompt_version == PROMPT_VERSION
    ):
        # 同一 prompt 版本下的 ready 草稿可以直接复用，避免重复扣费和打乱用户正在预览的内容。
        logger.info(
            "goal plan draft generation reused existing draft "
            "draft_id=%s user_id=%s status=%s",
            draft.id,
            user.id,
            draft.status,
        )
        return _plan_draft_response_from_goal_draft(draft)

    try:
        client, credential = await _client_for_user_or_error(db, user)
    except StudyPlanError as exc:
        logger.warning(
            "goal plan draft generation unavailable "
            "draft_id=%s user_id=%s status=%s detail=%s",
            draft.id,
            user.id,
            draft.status,
            exc.detail,
        )
        raise
    logger.info(
        "goal plan draft generation started "
        "draft_id=%s user_id=%s status=%s credential_id=%s model=%s",
        draft.id,
        user.id,
        draft.status,
        credential.id,
        credential.model_name,
    )
    draft.status = "generating"
    draft.updated_at = datetime.now(UTC)
    try:
        # LLM 草稿通过本地校验前不写入正式计划表，确保最终 study_plan_item 都绑定真实题库。
        plan_json, report, repair_log = await generate_plan_with_repair(
            db,
            client,
            draft.input_json,
            _list_of_dicts(draft.followup_messages_json),
        )
    except Exception:
        logger.exception(
            "goal plan draft generation crashed "
            "draft_id=%s user_id=%s credential_id=%s model=%s",
            draft.id,
            user.id,
            credential.id,
            credential.model_name,
        )
        raise
    if not report.get("valid"):
        draft.status = "failed"
        draft.validation_report_json = report
        draft.repair_log_json = repair_log
        draft.error_message = str((report.get("issues") or ["invalid_plan"])[0])
        draft.updated_at = datetime.now(UTC)
        await db.commit()
        logger.warning(
            "goal plan draft generation failed validation "
            "draft_id=%s user_id=%s credential_id=%s model=%s issues=%s item_count=%s "
            "repair_log_count=%s",
            draft.id,
            user.id,
            credential.id,
            credential.model_name,
            _format_report_issues(report),
            report.get("item_count", 0),
            len(repair_log),
        )
        raise StudyPlanError(draft.error_message)

    draft.llm_credential_id = credential.id
    draft.model_name = credential.model_name
    draft.prompt_version = PROMPT_VERSION
    draft.draft_goal_json = plan_json.get("target_snapshot", draft.input_json)
    draft.draft_plan_json = plan_json
    draft.validation_report_json = report
    draft.repair_log_json = repair_log
    draft.status = "ready_for_review"
    draft.error_message = ""
    draft.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(draft)
    stage_count, item_count = _draft_plan_counts(plan_json)
    logger.info(
        "goal plan draft generation completed "
        "draft_id=%s user_id=%s credential_id=%s model=%s stage_count=%s "
        "item_count=%s repair_log_count=%s",
        draft.id,
        user.id,
        credential.id,
        credential.model_name,
        stage_count,
        item_count,
        len(repair_log),
    )
    return _plan_draft_response_from_goal_draft(draft)


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
    result = await db.execute(
        query.values(status="paused", updated_at=datetime.now(UTC))
    )
    paused_count = getattr(result, "rowcount", 0)
    if paused_count:
        logger.info(
            "study plan paused other active plans user_id=%s keep_plan_id=%s "
            "paused_count=%s",
            user.id,
            keep_plan_id,
            paused_count,
        )


async def get_active_plan_version(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
    *,
    commit_repair: bool = True,
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
    repaired = await _set_only_active_version(db, version)
    if repaired and commit_repair:
        logger.warning(
            "study plan active version invariant repaired user_id=%s plan_id=%s "
            "version_id=%s version_number=%s",
            user.id,
            plan.id,
            version.id,
            version.version_number,
        )
        await db.commit()
        await db.refresh(
            version,
            attribute_names=["stages", "items"],
        )
        for item in version.items:
            await db.refresh(item, attribute_names=["problem"])
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
) -> bool:
    was_already_active = version.status == "active"
    result = await db.execute(
        update(StudyPlanVersion)
        .where(
            StudyPlanVersion.plan_id == version.plan_id,
            StudyPlanVersion.id != version.id,
            StudyPlanVersion.status == "active",
        )
        .values(status="superseded")
    )
    version.status = "active"
    changed_count = getattr(result, "rowcount", 0)
    return bool(changed_count) or not was_already_active


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
    # 落库前重新解析每个 slug，防止调用方传入过期草稿导致计划项指向不存在的题目。
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
    # 一个版本的 stage 和 item 一次性写入，stage_index/order_index 是前端展示和重排的稳定顺序。
    normalized_stages = await _normalized_stage_payloads(db, draft_plan_json)
    item_count = 0
    for stage_index, (stage_payload, item_payloads) in enumerate(
        normalized_stages,
        start=1,
    ):
        item_count += len(item_payloads)
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
                    suggested_mode=normalise_suggested_mode(
                        item_payload.get("suggested_mode")
                    ),
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
    logger.info(
        "study plan version content written version_id=%s stage_count=%s item_count=%s",
        version.id,
        len(normalized_stages),
        item_count,
    )


async def confirm_plan_draft(
    db: AsyncSession,
    user: AppUser,
    draft_id: int,
) -> StudyPlan:
    logger.info(
        "study plan confirmation started user_id=%s draft_id=%s", user.id, draft_id
    )
    try:
        result = await db.execute(
            select(GoalCalibrationDraft).where(
                GoalCalibrationDraft.id == draft_id,
                GoalCalibrationDraft.user_id == user.id,
            )
        )
        draft = result.scalar_one_or_none()
        if draft is None:
            logger.warning(
                "study plan confirmation rejected user_id=%s draft_id=%s "
                "reason=plan_draft_not_ready",
                user.id,
                draft_id,
            )
            raise StudyPlanError("plan_draft_not_ready")
        if draft.status == "confirmed" and draft.confirmed_plan_id is not None:
            logger.info(
                "study plan confirmation reused confirmed draft user_id=%s "
                "draft_id=%s plan_id=%s",
                user.id,
                draft.id,
                draft.confirmed_plan_id,
            )
            return await _load_plan(db, user, draft.confirmed_plan_id)
        if draft.status != "ready_for_review":
            logger.warning(
                "study plan confirmation rejected user_id=%s draft_id=%s "
                "status=%s reason=plan_draft_not_ready",
                user.id,
                draft.id,
                draft.status,
            )
            raise StudyPlanError("plan_draft_not_ready")

        await pause_other_active_plans(db, user)
        stage_count, item_count = _draft_plan_counts(draft.draft_plan_json)
        now = datetime.now(UTC)
        plan_title = await _build_confirmed_plan_title(db, user, draft, now)
        # 确认草稿时才创建正式 v1；同时暂停用户其他 active 计划，保证训练上下文唯一。
        plan = StudyPlan(
            user_id=user.id,
            title=plan_title,
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
        logger.info(
            "study plan confirmation completed user_id=%s draft_id=%s plan_id=%s "
            "version_id=%s stage_count=%s item_count=%s",
            user.id,
            draft.id,
            plan.id,
            version.id,
            stage_count,
            item_count,
        )
        return plan
    except StudyPlanError:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception(
            "study plan confirmation crashed user_id=%s draft_id=%s",
            user.id,
            draft_id,
        )
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
                "suggested_mode": normalise_suggested_mode(item.suggested_mode),
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
    # 如果 LLM 调整草稿漏掉已锁定或已有进度的题，后端会把它们追加回新版本。
    preserved = _preserved_items(old_version)
    draft_slugs = _draft_problem_slugs(draft_plan_json)
    preserved_stages: list[dict[str, Any]] = []
    for stage in _sort_stages(old_version.stages):
        preserved_items = [
            item
            for item in _sort_items(stage.items)
            if item.problem_slug in preserved and item.problem_slug not in draft_slugs
        ]
        if preserved_items:
            preserved_stages.append(_stage_payload_from_items(stage, preserved_items))
    return {
        **draft_plan_json,
        "stages": preserved_stages + _list_of_dicts(draft_plan_json.get("stages", [])),
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
    logger.info(
        "study plan adjusted version clone started user_id=%s plan_id=%s",
        user.id,
        plan_id,
    )
    try:
        plan = await _load_plan(db, user, plan_id)
        old_version = await get_active_plan_version(
            db,
            user,
            plan_id,
            commit_repair=False,
        )
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
        stage_count, item_count = _draft_plan_counts(merged_draft)
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
        logger.info(
            "study plan adjusted version clone completed user_id=%s plan_id=%s "
            "old_version_id=%s new_version_id=%s version_number=%s "
            "stage_count=%s item_count=%s preserved_count=%s",
            user.id,
            plan.id,
            old_version.id,
            new_version.id,
            new_version.version_number,
            stage_count,
            item_count,
            len(preserved_by_slug),
        )
        return await get_active_plan_version(db, user, plan.id)
    except StudyPlanError:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception(
            "study plan adjusted version clone crashed user_id=%s plan_id=%s",
            user.id,
            plan_id,
        )
        raise


async def activate_plan_version(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
    version_id: int,
) -> StudyPlanVersion:
    logger.info(
        "study plan version activation requested user_id=%s plan_id=%s version_id=%s",
        user.id,
        plan_id,
        version_id,
    )
    try:
        plan = await _load_plan(db, user, plan_id)
        result = await db.execute(
            select(StudyPlanVersion).where(
                StudyPlanVersion.id == version_id,
                StudyPlanVersion.plan_id == plan.id,
            )
        )
        version = result.scalar_one_or_none()
        if version is None:
            logger.warning(
                "study plan version activation rejected user_id=%s plan_id=%s "
                "version_id=%s reason=study_plan_version_not_found",
                user.id,
                plan.id,
                version_id,
            )
            raise StudyPlanError("study_plan_version_not_found")
        if version.status not in {"draft", "active"}:
            logger.warning(
                "study plan version activation rejected user_id=%s plan_id=%s "
                "version_id=%s status=%s reason=study_plan_version_cannot_be_activated",
                user.id,
                plan.id,
                version.id,
                version.status,
            )
            raise StudyPlanError("study_plan_version_cannot_be_activated")

        await pause_other_active_plans(db, user, keep_plan_id=plan.id)
        await _set_only_active_version(db, version)
        now = datetime.now(UTC)
        version.activated_at = version.activated_at or now
        plan.status = "active"
        plan.active_version_number = version.version_number
        plan.updated_at = now
        await db.commit()
        await db.refresh(version)
        logger.info(
            "study plan version activation completed user_id=%s plan_id=%s "
            "version_id=%s version_number=%s",
            user.id,
            plan.id,
            version.id,
            version.version_number,
        )
        return version
    except StudyPlanError:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception(
            "study plan version activation crashed user_id=%s plan_id=%s version_id=%s",
            user.id,
            plan_id,
            version_id,
        )
        raise


async def activate_plan(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
) -> StudyPlan:
    logger.info(
        "study plan activation requested user_id=%s plan_id=%s", user.id, plan_id
    )
    try:
        plan = await _load_plan(db, user, plan_id)
        if plan.status not in {"active", "paused", "completed"}:
            logger.warning(
                "study plan activation rejected user_id=%s plan_id=%s status=%s "
                "reason=study_plan_cannot_be_activated",
                user.id,
                plan.id,
                plan.status,
            )
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
        logger.info(
            "study plan activation completed user_id=%s plan_id=%s "
            "active_version_number=%s",
            user.id,
            plan.id,
            plan.active_version_number,
        )
        return plan
    except StudyPlanError:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception(
            "study plan activation crashed user_id=%s plan_id=%s",
            user.id,
            plan_id,
        )
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
        logger.warning(
            "study plan active invariant repaired user_id=%s selected_plan_id=%s "
            "paused_count=%s",
            user.id,
            selected_plan.id,
            len(active_plans) - 1,
        )
    return selected_plan


async def _load_payload_version(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
    version_id: int | None = None,
) -> tuple[StudyPlan, StudyPlanVersion]:
    plan = await _load_plan(db, user, plan_id)
    if version_id is None:
        return plan, await get_active_plan_version(db, user, plan.id)

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
    version_query = version_query.where(StudyPlanVersion.id == version_id)
    result = await db.execute(version_query)
    version = result.scalar_one_or_none()
    if version is None:
        raise StudyPlanError("study_plan_version_not_found")
    return plan, version


def _item_payload(
    item: StudyPlanItem,
    *,
    practice_status_by_problem_id: dict[int, str],
) -> dict[str, Any]:
    status = _effective_item_status(
        item,
        practice_status_by_problem_id=practice_status_by_problem_id,
    )
    return {
        "id": item.id,
        "problem_id": item.problem_id,
        "problem_slug": item.problem_slug,
        "frontend_id": item.problem.frontend_id,
        "title": item.problem.title,
        "translated_title": item.problem.translated_title,
        "difficulty": item.difficulty,
        "skill_tags": item.skill_tags_json,
        "suggested_mode": normalise_suggested_mode(item.suggested_mode),
        "recommendation_reason": item.recommendation_reason,
        "status": status,
        "order_index": item.order_index,
        "locked": item.locked,
    }


def _effective_item_status(
    item: StudyPlanItem,
    *,
    practice_status_by_problem_id: dict[int, str],
) -> str:
    practice_status = practice_status_by_problem_id.get(item.problem_id)
    if practice_status == "completed":
        return "completed"
    if item.status in {"completed", "locked_completed"}:
        return item.status
    if practice_status == "in_progress":
        return "in_progress"
    return item.status


def _stage_response(
    stage: StudyPlanStage,
    *,
    practice_status_by_problem_id: dict[int, str],
) -> dict[str, Any]:
    return {
        "id": stage.id,
        "stage_index": stage.stage_index,
        "title": stage.title,
        "objective_md": stage.objective_md,
        "focus_tags": stage.focus_tags_json,
        "assessment_criteria": stage.assessment_criteria_json,
        "status": stage.status,
        "items": [
            _item_payload(
                item,
                practice_status_by_problem_id=practice_status_by_problem_id,
            )
            for item in _sort_items(stage.items)
        ],
    }


def _version_response(
    version: StudyPlanVersion,
    *,
    practice_status_by_problem_id: dict[int, str],
) -> dict[str, Any]:
    return {
        "id": version.id,
        "version_number": version.version_number,
        "status": version.status,
        "target_snapshot": version.target_snapshot_json,
        "generation_summary_md": version.generation_summary_md,
        "adjustment_summary_md": version.adjustment_summary_md,
        "validation_report": version.validation_report_json,
        "repair_log": version.repair_log_json,
        "stages": [
            _stage_response(
                stage,
                practice_status_by_problem_id=practice_status_by_problem_id,
            )
            for stage in _sort_stages(version.stages)
        ],
        "created_at": version.created_at,
        "activated_at": version.activated_at,
    }


async def _practice_item_statuses(
    db: AsyncSession,
    user: AppUser,
    *,
    plan: StudyPlan,
    version: StudyPlanVersion,
) -> dict[int, str]:
    problem_ids = {item.problem_id for item in version.items}
    if not problem_ids:
        return {}
    progress_rank = case(
        (
            (PracticeSession.final_result == "ac")
            | (SubmissionFeedback.result == "ac"),
            2,
        ),
        (PracticeEvent.event_type.in_(PRACTICE_PROGRESS_EVENT_TYPES), 1),
        else_=0,
    )
    result = await db.execute(
        select(PracticeSession.problem_id, func.max(progress_rank))
        .outerjoin(
            SubmissionFeedback,
            (SubmissionFeedback.session_id == PracticeSession.id)
            & (SubmissionFeedback.user_id == PracticeSession.user_id),
        )
        .outerjoin(
            PracticeEvent,
            (PracticeEvent.session_id == PracticeSession.id)
            & (PracticeEvent.user_id == PracticeSession.user_id),
        )
        .where(
            PracticeSession.user_id == user.id,
            PracticeSession.study_plan_id == plan.id,
            PracticeSession.problem_id.in_(problem_ids),
        )
        .group_by(PracticeSession.problem_id)
    )
    statuses: dict[int, str] = {}
    for problem_id, rank in result.all():
        if rank == 2:
            statuses[int(problem_id)] = "completed"
        elif rank == 1:
            statuses[int(problem_id)] = "in_progress"
    if statuses:
        completed_count = sum(1 for status in statuses.values() if status == "completed")
        in_progress_count = sum(
            1 for status in statuses.values() if status == "in_progress"
        )
        logger.info(
            "study plan item status projected from practice user_id=%s plan_id=%s "
            "version_id=%s completed_count=%s in_progress_count=%s",
            user.id,
            plan.id,
            version.id,
            completed_count,
            in_progress_count,
        )
    return statuses


async def study_plan_payload(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
    *,
    version_id: int | None = None,
) -> dict[str, Any]:
    plan, version = await _load_payload_version(db, user, plan_id, version_id)
    # 计划项自身只保存计划编辑状态；真实训练进度来自 practice 边界，读取 payload 时投影，
    # 兼容历史上已记录 AC 但未同步 study_plan_item.status 的数据。
    practice_status_by_problem_id = await _practice_item_statuses(
        db,
        user,
        plan=plan,
        version=version,
    )
    return {
        "id": plan.id,
        "title": plan.title,
        "status": plan.status,
        "active_version_number": plan.active_version_number,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
        "active_version": _version_response(
            version,
            practice_status_by_problem_id=practice_status_by_problem_id,
        ),
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
        logger.warning(
            "study plan item status update rejected user_id=%s item_id=%s "
            "status=%s reason=invalid_plan_item_status",
            user.id,
            item_id,
            status,
        )
        raise StudyPlanError("invalid_plan_item_status")
    logger.info(
        "study plan item status update requested user_id=%s item_id=%s status=%s",
        user.id,
        item_id,
        status,
    )
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
            logger.warning(
                "study plan item status update rejected user_id=%s item_id=%s "
                "status=%s reason=active_plan_item_not_found",
                user.id,
                item_id,
                status,
            )
            raise StudyPlanError("active_plan_item_not_found")
        item, plan = row
        if item.locked:
            logger.warning(
                "study plan item status update rejected user_id=%s plan_id=%s "
                "item_id=%s reason=locked_plan_item_cannot_be_updated",
                user.id,
                plan.id,
                item.id,
            )
            raise StudyPlanError("locked_plan_item_cannot_be_updated")
        item.status = status
        item.updated_at = datetime.now(UTC)
        plan.updated_at = datetime.now(UTC)
        await db.commit()
        logger.info(
            "study plan item status update completed user_id=%s plan_id=%s "
            "item_id=%s status=%s",
            user.id,
            plan.id,
            item.id,
            status,
        )
        return plan.id
    except StudyPlanError:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception(
            "study plan item status update crashed user_id=%s item_id=%s status=%s",
            user.id,
            item_id,
            status,
        )
        raise


async def reorder_stage_items(
    db: AsyncSession,
    user: AppUser,
    stage_id: int,
    item_ids: list[int],
) -> int:
    logger.info(
        "study plan stage reorder requested user_id=%s stage_id=%s item_count=%s",
        user.id,
        stage_id,
        len(item_ids),
    )
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
            logger.warning(
                "study plan stage reorder rejected user_id=%s stage_id=%s "
                "reason=active_plan_stage_not_found",
                user.id,
                stage_id,
            )
            raise StudyPlanError("active_plan_stage_not_found")
        stage, plan = row
        current_ids = {item.id for item in stage.items}
        if set(item_ids) != current_ids or len(item_ids) != len(current_ids):
            logger.warning(
                "study plan stage reorder rejected user_id=%s plan_id=%s "
                "stage_id=%s requested_count=%s actual_count=%s "
                "reason=stage_item_set_mismatch",
                user.id,
                plan.id,
                stage.id,
                len(item_ids),
                len(current_ids),
            )
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
        logger.info(
            "study plan stage reorder completed user_id=%s plan_id=%s "
            "stage_id=%s item_count=%s",
            user.id,
            plan.id,
            stage.id,
            len(item_ids),
        )
        return plan.id
    except StudyPlanError:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception(
            "study plan stage reorder crashed user_id=%s stage_id=%s item_count=%s",
            user.id,
            stage_id,
            len(item_ids),
        )
        raise


async def list_study_plan_payloads(
    db: AsyncSession,
    user: AppUser,
) -> dict[str, Any]:
    return await list_study_plans(db, user)
