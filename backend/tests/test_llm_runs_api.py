from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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


async def fake_current_user_from_token(session: Any, token: str | None) -> AppUser:
    return fake_user()


def test_create_llm_run_requires_authentication() -> None:
    client = TestClient(app)

    response = client.post("/api/llm-runs", json={"kind": "goal_plan_generate", "payload": {}})

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


def test_create_llm_run_returns_stream_url(monkeypatch) -> None:
    async def fake_create(
        session: Any,
        user: AppUser,
        *,
        kind: str,
        payload: dict[str, Any] | None = None,
        related_type: str = "",
        related_id: int | None = None,
    ):
        return type("Run", (), {"id": 9, "kind": kind, "status": "pending", "stage": "queued"})()

    monkeypatch.setattr("backend.app.api.llm_runs.create_llm_run", fake_create)
    app.dependency_overrides[current_user_dependency] = fake_user
    try:
        client = TestClient(app)
        response = client.post(
            "/api/llm-runs",
            json={"kind": "goal_plan_generate", "payload": {"draft_id": 3}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "run_id": 9,
        "kind": "goal_plan_generate",
        "status": "pending",
        "stage": "queued",
        "stream_url": "/api/llm-runs/9/stream",
    }


def test_cancel_llm_run_maps_status_conflict(monkeypatch) -> None:
    from backend.app.services.llm_run_service import LlmRunError

    async def fake_cancel(session: Any, user: AppUser, run_id: int):
        raise LlmRunError("run_status_conflict")

    monkeypatch.setattr("backend.app.api.llm_runs.cancel_llm_run", fake_cancel)
    app.dependency_overrides[current_user_dependency] = fake_user
    try:
        client = TestClient(app)
        response = client.post("/api/llm-runs/7/cancel")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"] == "run_status_conflict"


def test_status_route_allows_retry_for_canceled_run(monkeypatch) -> None:
    now = datetime.now(UTC)

    async def fake_get(session: Any, user: AppUser, run_id: int):
        return type(
            "Run",
            (),
            {
                "id": run_id,
                "kind": "goal_plan_generate",
                "status": "canceled",
                "stage": "canceled",
                "display_text_md": "",
                "result_json": {},
                "error_code": "",
                "error_message": "",
                "created_at": now,
                "started_at": now,
                "finished_at": now,
            },
        )()

    monkeypatch.setattr("backend.app.api.llm_runs.get_llm_run_for_user", fake_get)
    app.dependency_overrides[current_user_dependency] = fake_user
    try:
        client = TestClient(app)
        response = client.get("/api/llm-runs/7")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["can_retry"] is True


def test_stream_terminal_canceled_run_emits_canceled_and_done(monkeypatch) -> None:
    async def fake_get(session: Any, user: AppUser, run_id: int):
        return type(
            "Run",
            (),
            {
                "id": run_id,
                "user_id": user.id,
                "status": "canceled",
                "kind": "goal_plan_generate",
                "result_json": {},
                "error_code": "",
                "error_message": "",
            },
        )()

    monkeypatch.setattr("backend.app.api.llm_runs.get_llm_run_for_user", fake_get)
    monkeypatch.setattr("backend.app.api.llm_runs.get_current_user_from_token", fake_current_user_from_token)
    client = TestClient(app)
    with client.stream("GET", "/api/llm-runs/99/stream") as response:
        body = response.read().decode()

    assert response.status_code == 200
    assert "event: canceled" in body
    assert "event: done" in body


def test_stream_pending_run_emits_done_body(monkeypatch) -> None:
    started: list[int] = []

    async def fake_get(session: Any, user: AppUser, run_id: int):
        return type(
            "Run",
            (),
            {
                "id": run_id,
                "user_id": user.id,
                "status": "pending",
                "kind": "goal_plan_generate",
                "result_json": {},
                "error_code": "",
                "error_message": "",
            },
        )()

    from backend.app.services.llm_run_events import LlmRunEvent, event_hub

    async def fake_execute(session_factory: Any, run_id: int, user_id: int):
        started.append(run_id)
        await event_hub.publish(run_id, LlmRunEvent("done", {"run_id": run_id}))

    monkeypatch.setattr("backend.app.api.llm_runs.get_llm_run_for_user", fake_get)
    monkeypatch.setattr("backend.app.api.llm_runs.execute_llm_run", fake_execute)
    monkeypatch.setattr("backend.app.api.llm_runs.get_current_user_from_token", fake_current_user_from_token)
    client = TestClient(app)
    with client.stream("GET", "/api/llm-runs/99/stream") as response:
        body = response.read().decode()
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

    assert "event: done" in body
    assert started == [99]
