from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import backend.app.models.llm_run  # noqa: F401
from backend.app.models.auth import AppUser
from backend.app.models.learning import (
    StudyPlan,
    StudyPlanItem,
    StudyPlanStage,
    StudyPlanVersion,
)
from backend.app.models.practice import (
    PracticeSession,
    SessionSummary,
    UserProfileSnapshot,
)
from backend.app.models.problem import Base, Problem
from backend.app.schemas.learning import ProfilePlanEnrichmentRequest


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def make_problem(
    slug: str,
    *,
    difficulty: str = "Easy",
    tags: list[str] | None = None,
    paid: bool = False,
) -> Problem:
    now = datetime.now(UTC)
    topic_tags = [
        {"slug": tag, "name": tag.title(), "translated_name": tag}
        for tag in (tags or ["array"])
    ]
    return Problem(
        frontend_id=slug,
        slug=slug,
        title=slug.replace("-", " ").title(),
        translated_title=slug,
        difficulty=difficulty,
        statement_md="# statement",
        metadata_json={"topic_tags": topic_tags},
        leetcode_url=f"https://leetcode.cn/problems/{slug}/",
        is_paid_only=paid,
        created_at=now,
        updated_at=now,
    )


async def create_user_plan(
    db_session: AsyncSession,
) -> tuple[AppUser, StudyPlan, StudyPlanVersion]:
    now = datetime.now(UTC)
    unique = uuid4().hex
    user = AppUser(
        username=f"user-{unique}",
        email=f"user-{unique}@example.com",
        password_hash="hash",
        display_name="learner",
        status="active",
        created_at=now,
        updated_at=now,
    )
    existing = make_problem("two-sum", tags=["array", "hash-table"])
    candidates = [
        make_problem("contains-duplicate", tags=["array", "hash-table"]),
        make_problem("valid-anagram", tags=["hash-table", "string"]),
        make_problem("binary-search", difficulty="Easy", tags=["binary-search"]),
        make_problem("premium-only", tags=["array"], paid=True),
    ]
    db_session.add_all([user, existing, *candidates])
    await db_session.flush()

    plan = StudyPlan(
        user_id=user.id,
        title="面试冲刺计划",
        status="active",
        active_version_number=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add(plan)
    await db_session.flush()

    version = StudyPlanVersion(
        plan_id=plan.id,
        version_number=1,
        status="active",
        target_snapshot_json={
            "goal_type": "interview_sprint",
            "preferred_language": "java",
            "target_timeline": "within_1_month",
            "weekly_days": 4,
        },
        generation_summary_md="面试高频训练计划",
        adjustment_summary_md="",
        validation_report_json={"valid": True},
        repair_log_json=[],
        created_at=now,
        activated_at=now,
    )
    db_session.add(version)
    await db_session.flush()

    stage = StudyPlanStage(
        version_id=version.id,
        stage_index=0,
        title="哈希表基础",
        objective_md="强化哈希表和边界条件",
        focus_tags_json=["hash-table", "array"],
        assessment_criteria_json=["能解释边界用例"],
        status="in_progress",
        created_at=now,
        updated_at=now,
    )
    db_session.add(stage)
    await db_session.flush()

    item = StudyPlanItem(
        version_id=version.id,
        stage_id=stage.id,
        problem_id=existing.id,
        problem_slug=existing.slug,
        skill_tags_json=["array", "hash-table"],
        difficulty=existing.difficulty,
        suggested_mode="independent",
        recommendation_reason="原计划题",
        status="in_progress",
        order_index=0,
        locked=False,
        created_at=now,
        updated_at=now,
    )
    db_session.add(item)
    await db_session.flush()

    practice_session = PracticeSession(
        user_id=user.id,
        study_plan_id=plan.id,
        problem_id=existing.id,
        problem_slug=existing.slug,
        origin_plan_version_id=version.id,
        latest_plan_version_id=version.id,
        latest_plan_item_id=item.id,
        thread_id=f"test-{uuid4().hex}",
        training_mode="independent",
        phase="summarize",
        status="completed",
        current_hint_level="key_hint",
        visible_hint_gear=2,
        max_hint_level_used="key_hint",
        attempt_count=2,
        final_result="ac",
        profile_snapshot_json={},
        started_at=now,
        completed_at=now,
        last_activity_at=now,
        created_at=now,
        updated_at=now,
    )
    db_session.add(practice_session)
    await db_session.flush()

    summary = SessionSummary(
        session_id=practice_session.id,
        user_id=user.id,
        problem_id=existing.id,
        result="completed",
        final_submission_result="ac",
        training_mode="independent",
        phases_visited_json=["review_code", "summarize"],
        transitions_json=[],
        main_stuck_points_json=["submission_wa"],
        error_types_json=["wa"],
        max_hint_level_used="key_hint",
        avg_hint_level=None,
        attempt_count=2,
        time_spent_seconds=None,
        complexity_analysis_json={},
        invariant_summary_md="哈希表状态维护不稳定。",
        review_summary_md="WA：重复元素失败。",
        profile_signals_json={"weak_skill_tags": ["边界"]},
        profile_update_suggestion_json={},
        next_recommendation_json={},
        created_at=now,
        updated_at=now,
    )
    db_session.add(summary)
    await db_session.flush()

    snapshot = UserProfileSnapshot(
        user_id=user.id,
        version_number=1,
        source="summary_patch",
        confidence="medium",
        overall_level="advanced",
        preferred_training_mode="independent",
        ability_profile_json={},
        skill_profile_json={"weak_skill_tags": ["边界", "哈希表"]},
        stuck_point_profile_json={"weak_stuck_points": ["submission_wa"]},
        strategy_json={
            "hint_policy_hint": "下次先要求列边界用例。",
            "next_review_focus": "重点检查重复元素。",
        },
        recent_summary_md="最近 WA 与重复元素边界有关。",
        evidence_summary_json=[
            {"source": "session_summary", "summary": "two-sum WA 后 AC"}
        ],
        created_from_summary_id=summary.id,
        created_at=now,
    )
    db_session.add(snapshot)
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(plan)
    await db_session.refresh(version)
    return user, plan, version


def validation_context(*, item_count: int = 3) -> dict[str, object]:
    return {
        "user_request": {
            "item_count": item_count,
            "difficulty_preference": "keep_current",
        },
        "current_plan": {
            "existing_problem_slugs": ["two-sum"],
            "current_stage": {"id": 10, "title": "哈希表基础"},
        },
        "candidate_problems": [
            {
                "problem_id": 2,
                "slug": "contains-duplicate",
                "title": "Contains Duplicate",
                "translated_title": "存在重复元素",
                "difficulty": "Easy",
                "tags": ["array", "hash-table"],
                "is_paid_only": False,
                "match_reasons": ["边界"],
            },
            {
                "problem_id": 3,
                "slug": "valid-anagram",
                "title": "Valid Anagram",
                "translated_title": "有效的字母异位词",
                "difficulty": "Easy",
                "tags": ["hash-table", "string"],
                "is_paid_only": False,
                "match_reasons": ["哈希表"],
            },
        ],
    }


@pytest.mark.asyncio
async def test_build_candidate_pool_excludes_existing_and_paid_only(
    db_session: AsyncSession,
) -> None:
    from backend.app.services.profile_plan_enrichment import build_enrichment_context

    user, plan, version = await create_user_plan(db_session)
    request = ProfilePlanEnrichmentRequest(
        user_intent_md="我想补哈希表边界，保持当前难度。",
        item_count=3,
        difficulty_preference="keep_current",
    )

    context = await build_enrichment_context(db_session, user, plan.id, request)

    slugs = [item["slug"] for item in context["candidate_problems"]]
    assert "contains-duplicate" in slugs
    assert "valid-anagram" in slugs
    assert "two-sum" not in slugs
    assert "premium-only" not in slugs
    assert context["current_plan"]["version_id"] == version.id
    assert context["profile_snapshot"]["recent_summary"] == "最近 WA 与重复元素边界有关。"
    assert context["user_request"]["user_intent_md"] == "我想补哈希表边界，保持当前难度。"


def test_validate_model_output_rejects_slug_outside_candidate_pool() -> None:
    from backend.app.services.profile_plan_enrichment import validate_model_output

    output = {
        "enrichment_theme": "哈希表补强",
        "plan_gap_assessment": {
            "gap_level": "medium",
            "summary_md": "需要补边界。",
        },
        "overall_reason_md": "追加哈希表边界题。",
        "items": [
            {
                "problem_slug": "not-in-candidates",
                "target_stage_key": "stage-current",
                "weakness_targets": ["边界"],
                "difficulty": "Easy",
                "recommendation_reason_md": "练习边界。",
                "first_question_hint": "先列边界。",
                "review_focus": "检查重复元素。",
                "suggested_mode": "independent",
            }
        ],
        "not_added_reason_md": "",
    }
    context = validation_context()

    report, items = validate_model_output(output, context)

    assert report["valid"] is False
    assert "candidate_slug_not_allowed:not-in-candidates" in report["issues"]
    assert items == []


def test_training_facts_reports_highest_hint_level_by_rank() -> None:
    from backend.app.services.profile_plan_enrichment import _training_facts

    now = datetime.now(UTC)
    summaries = [
        SessionSummary(
            session_id=1,
            user_id=1,
            problem_id=1,
            result="completed",
            final_submission_result="ac",
            training_mode="independent",
            phases_visited_json=[],
            transitions_json=[],
            main_stuck_points_json=[],
            error_types_json=[],
            max_hint_level_used="direction",
            avg_hint_level=None,
            attempt_count=1,
            time_spent_seconds=None,
            complexity_analysis_json={},
            invariant_summary_md="",
            review_summary_md="",
            profile_signals_json={},
            profile_update_suggestion_json={},
            next_recommendation_json={},
            created_at=now,
            updated_at=now,
        ),
        SessionSummary(
            session_id=2,
            user_id=1,
            problem_id=2,
            result="completed",
            final_submission_result="wa",
            training_mode="guided",
            phases_visited_json=[],
            transitions_json=[],
            main_stuck_points_json=[],
            error_types_json=[],
            max_hint_level_used="reflection",
            avg_hint_level=None,
            attempt_count=1,
            time_spent_seconds=None,
            complexity_analysis_json={},
            invariant_summary_md="",
            review_summary_md="",
            profile_signals_json={},
            profile_update_suggestion_json={},
            next_recommendation_json={},
            created_at=now,
            updated_at=now,
        ),
    ]

    facts = _training_facts(summaries)

    assert facts["highest_hint_level"] == "reflection"


def test_validate_model_output_normalizes_valid_candidate_item() -> None:
    from backend.app.services.profile_plan_enrichment import validate_model_output

    output = {
        "enrichment_theme": "哈希表补强",
        "plan_gap_assessment": {
            "gap_level": "medium",
            "summary_md": "需要补边界。",
        },
        "overall_reason_md": "追加哈希表边界题。",
        "items": [
            {
                "problem_slug": "contains-duplicate",
                "target_stage_key": "stage-current",
                "weakness_targets": ["边界"],
                "difficulty": "Medium",
                "recommendation_reason_md": "练习重复元素。",
                "first_question_hint": "先列边界。",
                "review_focus": "检查重复元素。",
                "suggested_mode": "unknown",
            }
        ],
        "not_added_reason_md": "",
    }
    context = validation_context()

    report, items = validate_model_output(output, context)

    assert report == {
        "valid": True,
        "issues": [],
        "candidate_count": 2,
        "item_count": 1,
    }
    assert items == [
        {
            "problem_id": 2,
            "problem_slug": "contains-duplicate",
            "title": "Contains Duplicate",
            "translated_title": "存在重复元素",
            "difficulty": "Easy",
            "skill_tags": ["array", "hash-table"],
            "target_stage_id": 10,
            "target_stage_title": "哈希表基础",
            "weakness_targets": ["边界"],
            "recommendation_reason_md": "练习重复元素。",
            "first_question_hint": "先列边界。",
            "review_focus": "检查重复元素。",
            "suggested_mode": "independent",
        }
    ]


@pytest.mark.parametrize(
    ("raw_items", "item_count", "expected_issue"),
    [
        (
            [
                {
                    "problem_slug": "contains-duplicate",
                    "recommendation_reason_md": "练习重复元素。",
                    "first_question_hint": "先列边界。",
                    "review_focus": "检查重复元素。",
                    "suggested_mode": "independent",
                },
                {
                    "problem_slug": "contains-duplicate",
                    "recommendation_reason_md": "再次推荐。",
                    "first_question_hint": "先列边界。",
                    "review_focus": "检查重复元素。",
                    "suggested_mode": "independent",
                },
            ],
            3,
            "duplicate_slug:contains-duplicate",
        ),
        (
            [
                {
                    "problem_slug": "two-sum",
                    "recommendation_reason_md": "练习重复元素。",
                    "first_question_hint": "先列边界。",
                    "review_focus": "检查重复元素。",
                    "suggested_mode": "independent",
                }
            ],
            1,
            "existing_slug_recommended:two-sum",
        ),
        (
            [
                {
                    "problem_slug": "contains-duplicate",
                    "recommendation_reason_md": "",
                    "first_question_hint": "先列边界。",
                    "review_focus": "检查重复元素。",
                    "suggested_mode": "independent",
                }
            ],
            1,
            "missing_recommendation_reason:contains-duplicate",
        ),
        (
            [
                {
                    "problem_slug": "contains-duplicate",
                    "recommendation_reason_md": "练习重复元素。",
                    "first_question_hint": "",
                    "review_focus": "检查重复元素。",
                    "suggested_mode": "independent",
                }
            ],
            1,
            "missing_first_question_hint:contains-duplicate",
        ),
        (
            [
                {
                    "problem_slug": "contains-duplicate",
                    "recommendation_reason_md": "练习重复元素。",
                    "first_question_hint": "先列边界。",
                    "review_focus": "",
                    "suggested_mode": "independent",
                }
            ],
            1,
            "missing_review_focus:contains-duplicate",
        ),
        (
            [
                {
                    "problem_slug": "contains-duplicate",
                    "recommendation_reason_md": "练习重复元素。",
                    "first_question_hint": "先列边界。",
                    "review_focus": "检查重复元素。",
                    "suggested_mode": "independent",
                },
                {
                    "problem_slug": "valid-anagram",
                    "recommendation_reason_md": "练习字符串哈希。",
                    "first_question_hint": "先说明计数结构。",
                    "review_focus": "检查长度不同。",
                    "suggested_mode": "independent",
                },
            ],
            1,
            "item_count_exceeded",
        ),
    ],
)
def test_validate_model_output_rejects_invalid_candidate_items(
    raw_items: list[dict[str, str]],
    item_count: int,
    expected_issue: str,
) -> None:
    from backend.app.services.profile_plan_enrichment import validate_model_output

    context = validation_context(item_count=item_count)
    output = {
        "enrichment_theme": "哈希表补强",
        "plan_gap_assessment": {
            "gap_level": "medium",
            "summary_md": "需要补边界。",
        },
        "overall_reason_md": "追加哈希表边界题。",
        "items": raw_items,
        "not_added_reason_md": "",
    }

    report, items = validate_model_output(output, context)

    assert report["valid"] is False
    assert expected_issue in report["issues"]
    assert report["item_count"] == 0
    assert items == []


@pytest.mark.asyncio
async def test_confirm_enrichment_draft_appends_items_to_current_stage(
    db_session: AsyncSession,
) -> None:
    from backend.app.models.learning import ProfilePlanEnrichmentDraft
    from backend.app.services.profile_plan_enrichment import (
        build_enrichment_context,
        confirm_enrichment_draft,
        persist_generated_draft,
        validate_model_output,
    )

    user, plan, version = await create_user_plan(db_session)
    request = ProfilePlanEnrichmentRequest(
        user_intent_md="补哈希表边界",
        item_count=2,
        difficulty_preference="keep_current",
    )
    context = await build_enrichment_context(db_session, user, plan.id, request)
    output = {
        "enrichment_theme": "哈希表边界补强",
        "plan_gap_assessment": {"gap_level": "medium", "summary_md": "需要补强。"},
        "overall_reason_md": "追加边界题。",
        "items": [
            {
                "problem_slug": "contains-duplicate",
                "target_stage_key": "stage-current",
                "weakness_targets": ["边界"],
                "difficulty": "Easy",
                "recommendation_reason_md": "练习重复元素。",
                "first_question_hint": "先列重复元素。",
                "review_focus": "检查 set。",
                "suggested_mode": "independent",
            }
        ],
        "not_added_reason_md": "",
    }
    report, items = validate_model_output(output, context)
    draft = await persist_generated_draft(
        db_session,
        user=user,
        plan_id=plan.id,
        version_id=version.id,
        profile_snapshot_id=context["profile_snapshot"]["id"],
        llm_run_id=1,
        payload=request,
        context=context,
        model_output=output,
        validation_report=report,
        normalized_items=items,
    )
    await db_session.commit()

    response = await confirm_enrichment_draft(db_session, user, plan.id, draft.id)

    added = [
        item
        for stage in response["active_version"]["stages"]
        for item in stage["items"]
        if item["problem_slug"] == "contains-duplicate"
    ]
    assert len(added) == 1
    assert added[0]["recommendation_reason"].startswith("画像补强：")
    refreshed = await db_session.get(ProfilePlanEnrichmentDraft, draft.id)
    assert refreshed is not None
    assert refreshed.status == "confirmed"
    assert len(refreshed.confirmed_item_ids_json) == 1
