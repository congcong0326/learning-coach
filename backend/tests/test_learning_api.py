from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.app.api.auth import current_user_dependency
from backend.app.main import app
from backend.app.models.auth import AppUser
from backend.app.services.study_plan_service import StudyPlanError


def fake_user() -> AppUser:
    now = datetime.now(UTC)
    return AppUser(
        id=42,
        username="alice",
        email="alice@example.com",
        password_hash="hash",
        display_name="Alice",
        status="active",
        created_at=now,
        updated_at=now,
    )


def test_learning_routes_require_authentication() -> None:
    client = TestClient(app)

    response = client.get("/api/study-plan/current")

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


def test_start_goal_calibration_returns_draft(monkeypatch) -> None:
    async def fake_start(*args, **kwargs):
        return {
            "draft_id": 1,
            "status": "asking_followup",
            "followup_question": "你的面试时间是？",
            "followup_question_id": "q1",
            "remaining_followups": 2,
        }

    monkeypatch.setattr(
        "backend.app.services.study_plan_service.start_goal_calibration",
        fake_start,
        raising=False,
    )
    app.dependency_overrides[current_user_dependency] = fake_user
    try:
        client = TestClient(app)
        response = client.post(
            "/api/goal-calibration",
            json={
                "goal_type": "interview_sprint",
                "target_timeline": "one_to_three_months",
                "weekly_days": 4,
                "session_minutes": 60,
                "current_level": "medium_partial",
                "preferred_language": "python3",
                "self_reported_weaknesses": ["pattern"],
                "extra_notes": "",
                "training_preference": "independent_first",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["followup_question"] == "你的面试时间是？"


def test_profile_enrichment_draft_route_returns_payload(monkeypatch) -> None:
    async def fake_get(session, user, plan_id, draft_id):
        assert plan_id == 7
        assert draft_id == 3
        now = datetime.now(UTC)
        return {
            "draft_id": 3,
            "status": "generated",
            "plan_id": 7,
            "plan_version_id": 9,
            "profile_snapshot_id": 11,
            "user_intent_md": "补边界",
            "item_count": 3,
            "difficulty_preference": "keep_current",
            "enrichment_theme": "边界补强",
            "plan_gap_assessment": {"gap_level": "medium", "summary_md": "需要补强"},
            "overall_reason_md": "追加题目",
            "not_added_reason_md": "",
            "items": [],
            "validation_report": {"valid": True},
            "created_at": now,
            "updated_at": now,
            "confirmed_at": None,
        }

    monkeypatch.setattr(
        "backend.app.services.profile_plan_enrichment.get_enrichment_draft_payload",
        fake_get,
        raising=False,
    )
    app.dependency_overrides[current_user_dependency] = fake_user
    try:
        client = TestClient(app)
        response = client.get("/api/study-plans/7/profile-enrichments/3")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["enrichment_theme"] == "边界补强"


def test_profile_enrichment_confirm_route_returns_updated_plan(monkeypatch) -> None:
    async def fake_confirm(session, user, plan_id, draft_id):
        assert plan_id == 7
        assert draft_id == 3
        now = datetime.now(UTC)
        return {
            "id": 7,
            "title": "计划",
            "status": "active",
            "active_version_number": 1,
            "created_at": now,
            "updated_at": now,
            "active_version": {
                "id": 9,
                "version_number": 1,
                "status": "active",
                "target_snapshot": {},
                "generation_summary_md": "",
                "adjustment_summary_md": "",
                "validation_report": {},
                "repair_log": [],
                "stages": [],
                "created_at": now,
                "activated_at": now,
            },
        }

    monkeypatch.setattr(
        "backend.app.services.profile_plan_enrichment.confirm_enrichment_draft",
        fake_confirm,
        raising=False,
    )
    app.dependency_overrides[current_user_dependency] = fake_user
    try:
        client = TestClient(app)
        response = client.post("/api/study-plans/7/profile-enrichments/3/confirm")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["id"] == 7


def test_profile_enrichment_confirm_route_maps_not_confirmable_to_conflict(
    monkeypatch,
) -> None:
    async def fake_confirm(session, user, plan_id, draft_id):
        del session, user, plan_id, draft_id
        raise StudyPlanError("profile_plan_enrichment_not_confirmable")

    monkeypatch.setattr(
        "backend.app.services.profile_plan_enrichment.confirm_enrichment_draft",
        fake_confirm,
        raising=False,
    )
    app.dependency_overrides[current_user_dependency] = fake_user
    try:
        client = TestClient(app)
        response = client.post("/api/study-plans/7/profile-enrichments/3/confirm")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"] == "profile_plan_enrichment_not_confirmable"


def test_profile_enrichment_draft_route_maps_not_found(monkeypatch) -> None:
    async def fake_get(session, user, plan_id, draft_id):
        del session, user, plan_id, draft_id
        raise StudyPlanError("profile_plan_enrichment_not_found")

    monkeypatch.setattr(
        "backend.app.services.profile_plan_enrichment.get_enrichment_draft_payload",
        fake_get,
        raising=False,
    )
    app.dependency_overrides[current_user_dependency] = fake_user
    try:
        client = TestClient(app)
        response = client.get("/api/study-plans/7/profile-enrichments/3")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "profile_plan_enrichment_not_found"
