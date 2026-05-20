from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.app.api.auth import current_user_dependency
from backend.app.main import app
from backend.app.models.auth import AppUser


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
