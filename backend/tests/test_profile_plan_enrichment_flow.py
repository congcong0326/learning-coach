from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

from backend.app.models.learning import ProfilePlanEnrichmentDraft
from backend.app.models.llm_run import LlmRun
from backend.app.services.learning_flows.goal_plan import LearningFlowError
from backend.app.services.learning_flows.profile_plan_enrichment import (
    run_profile_plan_enrichment,
)
from backend.app.services.llm_providers.base import ProviderChunk
from backend.app.services.llm_run_events import LlmRunEvent
from backend.tests.test_profile_plan_enrichment_service import (
    create_user_plan,
    db_session,  # noqa: F401
)


class FakeProvider:
    def __init__(self, final_text: str | list[str]) -> None:
        self.final_texts = final_text if isinstance(final_text, list) else [final_text]
        self.input_text = ""
        self.instructions = ""
        self.call_count = 0

    async def stream_text(self, *, model: str, instructions: str, input_text: str):
        self.instructions = instructions
        self.input_text = input_text
        index = min(self.call_count, len(self.final_texts) - 1)
        self.call_count += 1
        yield ProviderChunk(final_text=self.final_texts[index])


@pytest.mark.asyncio
async def test_profile_plan_enrichment_handler_persists_generated_draft(
    db_session: Any,  # noqa: F811
) -> None:
    user, plan, _version = await create_user_plan(db_session)
    run = LlmRun(
        id=99,
        user_id=user.id,
        kind="profile_plan_enrichment",
        input_json={
            "plan_id": plan.id,
            "user_intent_md": "补哈希表边界",
            "item_count": 2,
            "difficulty_preference": "keep_current",
        },
        related_type="study_plan",
        related_id=plan.id,
        status="running",
        stage="selecting_credential",
        display_text_md="",
        result_json={},
        error_code="",
        error_message="",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    output = {
        "enrichment_theme": "哈希表边界补强",
        "plan_gap_assessment": {
            "gap_level": "medium",
            "summary_md": "当前计划需要连续边界训练。",
        },
        "overall_reason_md": "追加两道哈希表边界题。",
        "items": [
            {
                "problem_slug": "contains-duplicate",
                "target_stage_key": "stage-current",
                "weakness_targets": ["边界"],
                "difficulty": "Easy",
                "recommendation_reason_md": "练习重复元素。",
                "first_question_hint": "先列重复元素用例。",
                "review_focus": "检查 set 更新顺序。",
                "suggested_mode": "independent",
            }
        ],
        "not_added_reason_md": "",
    }
    provider = FakeProvider(json.dumps(output, ensure_ascii=False))
    events: list[LlmRunEvent] = []

    result = await run_profile_plan_enrichment(
        db_session,
        user_id=user.id,
        run=run,
        provider=provider,
        model_name="gpt-test",
        publish=lambda event: events.append(event),
    )

    assert result["status"] == "generated"
    assert result["items"][0]["problem_slug"] == "contains-duplicate"
    assert "candidate_problems" in provider.input_text
    assert any(event.name == "progress" for event in events)

    draft_result = await db_session.execute(
        select(ProfilePlanEnrichmentDraft).where(
            ProfilePlanEnrichmentDraft.llm_run_id == run.id
        )
    )
    draft = draft_result.scalar_one()
    assert draft.status == "generated"
    assert draft.candidate_problem_ids_json
    assert draft.model_output_json["items"][0]["problem_slug"] == "contains-duplicate"


@pytest.mark.asyncio
async def test_profile_plan_enrichment_handler_maps_invalid_payload_to_flow_error(
    db_session: Any,  # noqa: F811
) -> None:
    user, plan, _version = await create_user_plan(db_session)
    run = LlmRun(
        id=100,
        user_id=user.id,
        kind="profile_plan_enrichment",
        input_json={
            "plan_id": plan.id,
            "user_intent_md": "补哈希表边界",
            "item_count": 4,
            "difficulty_preference": "keep_current",
        },
        related_type="study_plan",
        related_id=plan.id,
        status="running",
        stage="selecting_credential",
        display_text_md="",
        result_json={},
        error_code="",
        error_message="",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    provider = FakeProvider("{}")

    with pytest.raises(LearningFlowError) as exc_info:
        await run_profile_plan_enrichment(
            db_session,
            user_id=user.id,
            run=run,
            provider=provider,
            model_name="gpt-test",
            publish=lambda event: None,
        )

    assert exc_info.value.code == "profile_plan_enrichment_invalid"
    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_profile_plan_enrichment_handler_maps_missing_plan_to_flow_error(
    db_session: Any,  # noqa: F811
) -> None:
    user, _plan, _version = await create_user_plan(db_session)
    run = LlmRun(
        id=100,
        user_id=user.id,
        kind="profile_plan_enrichment",
        input_json={
            "plan_id": 9999,
            "user_intent_md": "补哈希表边界",
            "item_count": 2,
            "difficulty_preference": "keep_current",
        },
        related_type="study_plan",
        related_id=9999,
        status="running",
        stage="selecting_credential",
        display_text_md="",
        result_json={},
        error_code="",
        error_message="",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    provider = FakeProvider("{}")

    with pytest.raises(LearningFlowError) as exc_info:
        await run_profile_plan_enrichment(
            db_session,
            user_id=user.id,
            run=run,
            provider=provider,
            model_name="gpt-test",
            publish=lambda event: None,
        )

    assert exc_info.value.code == "active_study_plan_not_found"


@pytest.mark.asyncio
async def test_profile_plan_enrichment_handler_rejects_invalid_top_level_output(
    db_session: Any,  # noqa: F811
) -> None:
    user, plan, _version = await create_user_plan(db_session)
    run = LlmRun(
        id=101,
        user_id=user.id,
        kind="profile_plan_enrichment",
        input_json={
            "plan_id": plan.id,
            "user_intent_md": "补哈希表边界",
            "item_count": 2,
            "difficulty_preference": "keep_current",
        },
        related_type="study_plan",
        related_id=plan.id,
        status="running",
        stage="selecting_credential",
        display_text_md="",
        result_json={},
        error_code="",
        error_message="",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    output = {
        "enrichment_theme": "哈希表边界补强",
        "plan_gap_assessment": {
            "gap_level": "severe",
            "summary_md": "当前计划需要连续边界训练。",
        },
        "overall_reason_md": "追加两道哈希表边界题。",
        "items": [
            {
                "problem_slug": "contains-duplicate",
                "target_stage_key": "stage-current",
                "weakness_targets": ["边界"],
                "difficulty": "Easy",
                "recommendation_reason_md": "练习重复元素。",
                "first_question_hint": "先列重复元素用例。",
                "review_focus": "检查 set 更新顺序。",
                "suggested_mode": "independent",
            }
        ],
        "not_added_reason_md": "",
    }
    provider = FakeProvider(json.dumps(output, ensure_ascii=False))

    with pytest.raises(LearningFlowError) as exc_info:
        await run_profile_plan_enrichment(
            db_session,
            user_id=user.id,
            run=run,
            provider=provider,
            model_name="gpt-test",
            publish=lambda event: None,
        )

    assert exc_info.value.code == "profile_plan_enrichment_invalid"
    assert provider.call_count == 3


@pytest.mark.asyncio
async def test_profile_plan_enrichment_handler_repairs_invalid_first_output(
    db_session: Any,  # noqa: F811
) -> None:
    user, plan, _version = await create_user_plan(db_session)
    run = LlmRun(
        id=102,
        user_id=user.id,
        kind="profile_plan_enrichment",
        input_json={
            "plan_id": plan.id,
            "user_intent_md": "补哈希表边界",
            "item_count": 2,
            "difficulty_preference": "keep_current",
        },
        related_type="study_plan",
        related_id=plan.id,
        status="running",
        stage="selecting_credential",
        display_text_md="",
        result_json={},
        error_code="",
        error_message="",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    invalid_output = {
        "enrichment_theme": "哈希表边界补强",
        "plan_gap_assessment": {
            "gap_level": "medium",
            "summary_md": "当前计划需要连续边界训练。",
        },
        "overall_reason_md": "追加两道哈希表边界题。",
        "items": [
            {
                "problem_slug": "not-in-candidates",
                "target_stage_key": "stage-current",
                "weakness_targets": ["边界"],
                "difficulty": "Easy",
                "recommendation_reason_md": "练习重复元素。",
                "first_question_hint": "先列重复元素用例。",
                "review_focus": "检查 set 更新顺序。",
                "suggested_mode": "independent",
            }
        ],
        "not_added_reason_md": "",
    }
    repaired_output = {
        **invalid_output,
        "items": [
            {
                "problem_slug": "contains-duplicate",
                "target_stage_key": "stage-current",
                "weakness_targets": ["边界"],
                "difficulty": "Easy",
                "recommendation_reason_md": "练习重复元素。",
                "first_question_hint": "先列重复元素用例。",
                "review_focus": "检查 set 更新顺序。",
                "suggested_mode": "independent",
            }
        ],
    }
    provider = FakeProvider(
        [
            json.dumps(invalid_output, ensure_ascii=False),
            json.dumps(repaired_output, ensure_ascii=False),
        ]
    )
    events: list[LlmRunEvent] = []

    result = await run_profile_plan_enrichment(
        db_session,
        user_id=user.id,
        run=run,
        provider=provider,
        model_name="gpt-test",
        publish=lambda event: events.append(event),
    )

    assert result["status"] == "generated"
    assert result["items"][0]["problem_slug"] == "contains-duplicate"
    assert provider.call_count == 2
    assert any(event.data["stage"] == "repairing_output" for event in events)
