from __future__ import annotations

import asyncio
from importlib import import_module
import logging
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.api.auth import current_user_dependency
from backend.app.core.config import settings
from backend.app.models.auth import AppUser, LlmCredential
from backend.app.models.llm_run import LlmRun
from backend.app.models.problem import Base
from backend.app.services.credential_crypto import encrypt_api_key
from backend.app.services.llm_run_events import LlmRunEvent


app = cast(Any, import_module("backend.app.main").app)


@pytest_asyncio.fixture
async def orchestrator_session_factory() -> Any:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


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


async def create_orchestrator_user_run(
    session: AsyncSession,
    *,
    encryption_key: str,
    kind: str = "goal_plan_generate",
) -> tuple[AppUser, LlmRun]:
    now = datetime.now(UTC)
    unique = uuid4().hex
    user = AppUser(
        username=f"user-{unique}",
        email=f"user-{unique}@example.com",
        password_hash="hash",
        display_name="Learner",
        status="active",
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    await session.flush()
    credential = LlmCredential(
        user_id=user.id,
        provider="openai",
        display_name="Test",
        base_url="https://example.test/v1",
        api_mode="responses",
        model_name="gpt-test",
        api_key_ciphertext=encrypt_api_key("sk-test", encryption_key),
        api_key_mask="sk-...test",
        is_default=True,
        is_enabled=True,
        is_preferred=True,
        is_active=True,
        failure_count=0,
        status="valid",
        last_error="",
        created_at=now,
        updated_at=now,
    )
    session.add(credential)
    await session.flush()
    run = LlmRun(user_id=user.id, kind=kind)
    session.add(run)
    await session.commit()
    await session.refresh(user)
    await session.refresh(run)
    return user, run


@pytest.mark.asyncio
async def test_observe_llm_task_logs_sanitized_exception(caplog) -> None:
    _observe_llm_task = cast(Any, import_module("backend.app.api.llm_runs"))._observe_llm_task

    async def fail_with_secret() -> None:
        raise RuntimeError("secret prompt text")

    task = asyncio.create_task(fail_with_secret())
    with pytest.raises(RuntimeError):
        await task

    caplog.set_level(logging.ERROR, logger="backend.app.api.llm_runs")
    _observe_llm_task(77, task)

    assert "error_type=RuntimeError" in caplog.text
    assert "secret prompt text" not in caplog.text


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


def test_create_llm_run_uses_registry_related_mapping(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_create(
        session: Any,
        user: AppUser,
        *,
        kind: str,
        payload: dict[str, Any] | None = None,
        related_type: str = "",
        related_id: int | None = None,
    ):
        captured["kind"] = kind
        captured["payload"] = payload
        captured["related_type"] = related_type
        captured["related_id"] = related_id
        return type("Run", (), {"id": 10, "kind": kind, "status": "pending", "stage": "queued"})()

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
    assert captured == {
        "kind": "goal_plan_generate",
        "payload": {"draft_id": 3},
        "related_type": "goal_calibration_draft",
        "related_id": 3,
    }


def test_create_llm_run_preserves_study_plan_adjustment_related_mapping(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_create(
        session: Any,
        user: AppUser,
        *,
        kind: str,
        payload: dict[str, Any] | None = None,
        related_type: str = "",
        related_id: int | None = None,
    ):
        captured["kind"] = kind
        captured["payload"] = payload
        captured["related_type"] = related_type
        captured["related_id"] = related_id
        return type("Run", (), {"id": 11, "kind": kind, "status": "pending", "stage": "queued"})()

    monkeypatch.setattr("backend.app.api.llm_runs.create_llm_run", fake_create)
    app.dependency_overrides[current_user_dependency] = fake_user
    try:
        client = TestClient(app)
        response = client.post(
            "/api/llm-runs",
            json={"kind": "study_plan_adjustment", "payload": {"plan_id": 9}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured == {
        "kind": "study_plan_adjustment",
        "payload": {"plan_id": 9},
        "related_type": "study_plan",
        "related_id": 9,
    }


def test_profile_plan_enrichment_run_uses_registry_related_mapping(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_create(
        session: Any,
        user: AppUser,
        *,
        kind: str,
        payload: dict[str, Any] | None = None,
        related_type: str = "",
        related_id: int | None = None,
    ):
        captured["kind"] = kind
        captured["payload"] = payload
        captured["related_type"] = related_type
        captured["related_id"] = related_id
        return type("Run", (), {"id": 12, "kind": kind, "status": "pending", "stage": "queued"})()

    monkeypatch.setattr("backend.app.api.llm_runs.create_llm_run", fake_create)
    app.dependency_overrides[current_user_dependency] = fake_user
    try:
        client = TestClient(app)
        response = client.post(
            "/api/llm-runs",
            json={
                "kind": "profile_plan_enrichment",
                "payload": {
                    "plan_id": 9,
                    "user_intent_md": "补边界",
                    "item_count": 3,
                    "difficulty_preference": "keep_current",
                },
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured["related_type"] == "study_plan"
    assert captured["related_id"] == 9


@pytest.mark.parametrize("kind", ["coach_turn", "coach_summary"])
def test_create_llm_run_accepts_practice_run_kinds(monkeypatch, kind: str) -> None:
    captured: dict[str, Any] = {}

    async def fake_create(
        session: Any,
        user: AppUser,
        *,
        kind: str,
        payload: dict[str, Any] | None = None,
        related_type: str = "",
        related_id: int | None = None,
    ):
        captured["kind"] = kind
        captured["payload"] = payload
        captured["related_type"] = related_type
        captured["related_id"] = related_id
        return type("Run", (), {"id": 12, "kind": kind, "status": "pending", "stage": "queued"})()

    monkeypatch.setattr("backend.app.api.llm_runs.create_llm_run", fake_create)
    app.dependency_overrides[current_user_dependency] = fake_user
    try:
        client = TestClient(app)
        response = client.post(
            "/api/llm-runs",
            json={"kind": kind, "payload": {"session_id": 23}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured == {
        "kind": kind,
        "payload": {"session_id": 23},
        "related_type": "practice_session",
        "related_id": 23,
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


@pytest.mark.asyncio
async def test_orchestrator_goal_plan_success_publishes_result_after_success(monkeypatch) -> None:
    from backend.app.services import llm_orchestrator

    calls: list[str] = []
    events: list[LlmRunEvent] = []
    run = type(
        "Run",
        (),
        {
            "id": 9,
            "user_id": 42,
            "kind": "goal_plan_generate",
            "status": "pending",
            "display_text_md": "",
        },
    )()
    user = fake_user()
    credential = type(
        "Credential",
        (),
        {
            "id": 3,
            "api_key_ciphertext": "ciphertext",
            "base_url": "https://example.test/v1",
            "model_name": "gpt-test",
        },
    )()

    class FakeSession:
        async def rollback(self) -> None:
            calls.append("rollback")

    class FakeSessionContext:
        async def __aenter__(self) -> FakeSession:
            return FakeSession()

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeEventHub:
        async def publish(self, run_id: int, event: LlmRunEvent) -> None:
            assert run_id == 9
            calls.append(f"publish:{event.name}")
            events.append(event)

    class FakeProvider:
        def __init__(self, *, api_key: str, base_url: str) -> None:
            assert api_key == "plain-key"
            assert base_url == credential.base_url
            calls.append("provider")

    async def fake_load(session: Any, run_id: int, user_id: int):
        assert run_id == 9
        assert user_id == 42
        return run, user

    async def fake_select(session: Any, selected_user: AppUser):
        assert selected_user.id == user.id
        calls.append("select")
        return credential

    def fake_decrypt(ciphertext: str, encryption_key: str) -> str:
        assert ciphertext == "ciphertext"
        calls.append("decrypt")
        return "plain-key"

    async def fake_mark_running(
        session: Any,
        selected_run: Any,
        *,
        stage: str,
        llm_credential_id: int | None = None,
        model_name: str = "",
    ):
        assert selected_run is run
        assert stage == "selecting_credential"
        assert llm_credential_id == credential.id
        assert model_name == credential.model_name
        calls.append("mark_running")
        run.status = "running"
        return run

    class FakeHandler:
        async def execute(self, context: Any) -> dict[str, Any]:
            assert context.user_id == 42
            assert context.run is run
            assert isinstance(context.provider, FakeProvider)
            assert context.model_name == credential.model_name
            calls.append("flow")
            run.display_text_md = "draft text"
            return {"draft_id": 7, "stage_count": 2, "item_count": 8}

    def fake_handler_for_kind(kind: str) -> Any:
        assert kind == "goal_plan_generate"
        calls.append("handler")
        return FakeHandler()

    async def fake_succeed(
        session: Any,
        selected_run: Any,
        *,
        result: dict[str, Any],
        display_text_md: str,
    ):
        assert selected_run is run
        assert result["draft_id"] == 7
        assert display_text_md == "draft text"
        calls.append("succeed")
        run.status = "succeeded"
        return run

    monkeypatch.setattr(llm_orchestrator, "event_hub", FakeEventHub())
    monkeypatch.setattr(llm_orchestrator, "_load_run_and_user", fake_load)
    monkeypatch.setattr(llm_orchestrator, "select_llm_credential_for_user", fake_select)
    monkeypatch.setattr(llm_orchestrator, "decrypt_api_key", fake_decrypt)
    monkeypatch.setattr(llm_orchestrator, "mark_llm_run_running", fake_mark_running)
    monkeypatch.setattr(llm_orchestrator, "OpenAIResponsesProvider", FakeProvider)
    monkeypatch.setattr(llm_orchestrator, "handler_for_kind", fake_handler_for_kind)
    monkeypatch.setattr(llm_orchestrator, "succeed_llm_run", fake_succeed)

    await llm_orchestrator.execute_llm_run(cast(Any, lambda: FakeSessionContext()), 9, 42)

    assert [event.name for event in events] == ["started", "progress", "result", "done"]
    assert calls == [
        "publish:started",
        "handler",
        "publish:progress",
        "select",
        "decrypt",
        "mark_running",
        "provider",
        "flow",
        "succeed",
        "publish:result",
        "publish:done",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["coach_turn", "coach_summary"])
async def test_orchestrator_model_backed_coach_run_selects_model_asset(
    monkeypatch,
    kind: str,
) -> None:
    from backend.app.services import llm_orchestrator

    calls: list[str] = []
    events: list[LlmRunEvent] = []
    run = type(
        "Run",
        (),
        {
            "id": 13,
            "user_id": 42,
            "kind": kind,
            "status": "pending",
            "display_text_md": "",
        },
    )()
    user = fake_user()
    credential = type(
        "Credential",
        (),
        {
            "id": 77,
            "api_key_ciphertext": "ciphertext",
            "base_url": "https://example.test/v1",
            "model_name": "gpt-test",
        },
    )()

    class FakeSession:
        async def rollback(self) -> None:
            calls.append("rollback")

    class FakeSessionContext:
        async def __aenter__(self) -> FakeSession:
            return FakeSession()

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeEventHub:
        async def publish(self, run_id: int, event: LlmRunEvent) -> None:
            assert run_id == 13
            calls.append(f"publish:{event.name}")
            events.append(event)

    class FakeProvider:
        def __init__(self, *, api_key: str, base_url: str) -> None:
            assert api_key == "plain-key"
            assert base_url == credential.base_url
            calls.append("provider")

    async def fake_select(session: Any, selected_user: AppUser):
        assert selected_user.id == user.id
        calls.append("select")
        return credential

    def fake_decrypt(ciphertext: str, encryption_key: str) -> str:
        assert ciphertext == "ciphertext"
        calls.append("decrypt")
        return "plain-key"

    async def fake_mark_running(
        session: Any,
        selected_run: Any,
        *,
        stage: str,
        llm_credential_id: int | None = None,
        model_name: str = "",
    ):
        assert selected_run is run
        assert stage == "selecting_credential"
        assert llm_credential_id == credential.id
        assert model_name == credential.model_name
        calls.append("mark_running")
        run.status = "running"
        return run

    class FakeHandler:
        async def execute(self, context: Any) -> dict[str, Any]:
            assert context.user_id == 42
            assert context.run is run
            assert isinstance(context.provider, FakeProvider)
            assert context.model_name == credential.model_name
            calls.append("coach_flow")
            run.display_text_md = "coach text"
            return {"session_id": 9, "assistant_event_id": 20}

    def fake_handler_for_kind(selected_kind: str) -> Any:
        assert selected_kind == kind
        return FakeHandler()

    async def fake_succeed(
        session: Any,
        selected_run: Any,
        *,
        result: dict[str, Any],
        display_text_md: str,
    ):
        assert selected_run is run
        assert result["assistant_event_id"] == 20
        assert display_text_md == "coach text"
        calls.append("succeed")
        run.status = "succeeded"
        return run

    monkeypatch.setattr(llm_orchestrator, "event_hub", FakeEventHub())
    monkeypatch.setattr(llm_orchestrator, "_load_run_and_user", lambda session, run_id, user_id: _async_value((run, user)))
    monkeypatch.setattr(llm_orchestrator, "select_llm_credential_for_user", fake_select)
    monkeypatch.setattr(llm_orchestrator, "decrypt_api_key", fake_decrypt)
    monkeypatch.setattr(llm_orchestrator, "mark_llm_run_running", fake_mark_running)
    monkeypatch.setattr(llm_orchestrator, "OpenAIResponsesProvider", FakeProvider)
    monkeypatch.setattr(llm_orchestrator, "handler_for_kind", fake_handler_for_kind)
    monkeypatch.setattr(llm_orchestrator, "succeed_llm_run", fake_succeed)

    await llm_orchestrator.execute_llm_run(cast(Any, lambda: FakeSessionContext()), 13, 42)

    assert [event.name for event in events] == ["started", "progress", "result", "done"]
    assert events[1].data["stage"] == "selecting_credential"
    assert calls == [
        "publish:started",
        "publish:progress",
        "select",
        "decrypt",
        "mark_running",
        "provider",
        "coach_flow",
        "succeed",
        "publish:result",
        "publish:done",
    ]


@pytest.mark.asyncio
async def test_orchestrator_coach_summary_requires_model_asset(monkeypatch) -> None:
    from backend.app.services import llm_orchestrator
    from backend.app.services.llm_credential_service import LlmCredentialError

    calls: list[str] = []
    events: list[LlmRunEvent] = []
    failed: list[tuple[str, str]] = []
    run = type(
        "Run",
        (),
        {
            "id": 14,
            "user_id": 42,
            "kind": "coach_summary",
            "status": "pending",
            "display_text_md": "",
        },
    )()

    class FakeSession:
        async def rollback(self) -> None:
            calls.append("rollback")

        async def get(self, model: Any, run_id: int) -> Any:
            assert model is LlmRun
            assert run_id == 14
            return run

    class FakeSessionContext:
        async def __aenter__(self) -> FakeSession:
            return FakeSession()

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeEventHub:
        async def publish(self, run_id: int, event: LlmRunEvent) -> None:
            assert run_id == 14
            calls.append(f"publish:{event.name}")
            events.append(event)

    class FakeHandler:
        async def execute(self, context: Any) -> dict[str, Any]:
            raise AssertionError("coach_summary handler must not run without a model asset")

    async def fake_select(session: Any, selected_user: AppUser):
        assert selected_user.id == 42
        calls.append("select")
        raise LlmCredentialError("llm_credential_unavailable")

    async def fake_fail(
        session: Any,
        selected_run: Any,
        *,
        error_code: str,
        error_message: str,
    ):
        assert selected_run is run
        failed.append((error_code, error_message))
        run.status = "failed"
        return run

    monkeypatch.setattr(llm_orchestrator, "event_hub", FakeEventHub())
    monkeypatch.setattr(
        llm_orchestrator,
        "_load_run_and_user",
        lambda session, run_id, user_id: _async_value((run, fake_user())),
    )
    monkeypatch.setattr(llm_orchestrator, "select_llm_credential_for_user", fake_select)
    monkeypatch.setattr(llm_orchestrator, "handler_for_kind", lambda kind: FakeHandler())
    monkeypatch.setattr(llm_orchestrator, "fail_llm_run", fake_fail)

    await llm_orchestrator.execute_llm_run(cast(Any, lambda: FakeSessionContext()), 14, 42)

    assert failed == [("llm_credential_unavailable", "没有可用的模型资产，请检查 API 设置")]
    assert [event.name for event in events] == ["started", "progress", "error", "done"]
    assert events[1].data["stage"] == "selecting_credential"
    assert events[2].data["error_code"] == "llm_credential_unavailable"
    assert calls == [
        "publish:started",
        "publish:progress",
        "select",
        "rollback",
        "publish:error",
        "publish:done",
    ]


@pytest.mark.asyncio
async def test_orchestrator_goal_followup_success_publishes_result_after_success(monkeypatch) -> None:
    from backend.app.services import llm_orchestrator

    calls: list[str] = []
    events: list[LlmRunEvent] = []
    run = type(
        "Run",
        (),
        {
            "id": 12,
            "user_id": 42,
            "kind": "goal_followup",
            "status": "pending",
            "display_text_md": "",
        },
    )()
    user = fake_user()
    credential = type(
        "Credential",
        (),
        {
            "id": 6,
            "api_key_ciphertext": "ciphertext",
            "base_url": "https://example.test/v1",
            "model_name": "gpt-test",
        },
    )()

    class FakeSession:
        async def rollback(self) -> None:
            calls.append("rollback")

    class FakeSessionContext:
        async def __aenter__(self) -> FakeSession:
            return FakeSession()

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeEventHub:
        async def publish(self, run_id: int, event: LlmRunEvent) -> None:
            assert run_id == 12
            calls.append(f"publish:{event.name}")
            events.append(event)

    class FakeProvider:
        def __init__(self, *, api_key: str, base_url: str) -> None:
            assert api_key == "plain-key"
            assert base_url == credential.base_url
            calls.append("provider")

    async def fake_mark_running(
        session: Any,
        selected_run: Any,
        *,
        stage: str,
        llm_credential_id: int | None = None,
        model_name: str = "",
    ):
        assert selected_run is run
        assert stage == "selecting_credential"
        assert llm_credential_id == credential.id
        assert model_name == credential.model_name
        calls.append("mark_running")
        run.status = "running"
        return run

    class FakeHandler:
        async def execute(self, context: Any) -> dict[str, Any]:
            assert context.user_id == 42
            assert context.run is run
            assert isinstance(context.provider, FakeProvider)
            assert context.model_name == credential.model_name
            calls.append("followup_flow")
            run.display_text_md = "followup text"
            return {
                "draft_id": 7,
                "status": "asking_followup",
                "followup_question": "你的面试时间是？",
                "followup_question_id": "q1",
                "remaining_followups": 2,
            }

    def fake_handler_for_kind(kind: str) -> Any:
        assert kind == "goal_followup"
        return FakeHandler()

    async def fake_succeed(
        session: Any,
        selected_run: Any,
        *,
        result: dict[str, Any],
        display_text_md: str,
    ):
        assert selected_run is run
        assert result["draft_id"] == 7
        assert result["followup_question_id"] == "q1"
        assert display_text_md == "followup text"
        calls.append("succeed")
        run.status = "succeeded"
        return run

    monkeypatch.setattr(llm_orchestrator, "event_hub", FakeEventHub())
    monkeypatch.setattr(llm_orchestrator, "_load_run_and_user", lambda session, run_id, user_id: _async_value((run, user)))
    monkeypatch.setattr(llm_orchestrator, "select_llm_credential_for_user", lambda session, selected_user: _async_value(credential))
    monkeypatch.setattr(llm_orchestrator, "decrypt_api_key", lambda ciphertext, encryption_key: "plain-key")
    monkeypatch.setattr(llm_orchestrator, "mark_llm_run_running", fake_mark_running)
    monkeypatch.setattr(llm_orchestrator, "OpenAIResponsesProvider", FakeProvider)
    monkeypatch.setattr(llm_orchestrator, "handler_for_kind", fake_handler_for_kind)
    monkeypatch.setattr(llm_orchestrator, "succeed_llm_run", fake_succeed)

    await llm_orchestrator.execute_llm_run(cast(Any, lambda: FakeSessionContext()), 12, 42)

    assert [event.name for event in events] == ["started", "progress", "result", "done"]
    assert events[2].data == {
        "run_id": 12,
        "status": "succeeded",
        "result": {
            "draft_id": 7,
            "status": "asking_followup",
            "followup_question": "你的面试时间是？",
            "followup_question_id": "q1",
            "remaining_followups": 2,
        },
    }
    assert calls == [
        "publish:started",
        "publish:progress",
        "mark_running",
        "provider",
        "followup_flow",
        "succeed",
        "publish:result",
        "publish:done",
    ]


@pytest.mark.asyncio
async def test_orchestrator_unsupported_kind_fails_and_publishes_error(monkeypatch) -> None:
    from backend.app.services import llm_orchestrator

    events: list[LlmRunEvent] = []
    failed: list[tuple[str, str]] = []
    run = type(
        "Run",
        (),
        {
            "id": 10,
            "user_id": 42,
            "kind": "study_plan_adjustment",
            "status": "pending",
            "display_text_md": "",
        },
    )()
    credential = type(
        "Credential",
        (),
        {
            "id": 4,
            "api_key_ciphertext": "ciphertext",
            "base_url": "https://example.test/v1",
            "model_name": "gpt-test",
        },
    )()

    class FakeSession:
        async def rollback(self) -> None:
            return None

    class FakeSessionContext:
        async def __aenter__(self) -> FakeSession:
            return FakeSession()

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeEventHub:
        async def publish(self, run_id: int, event: LlmRunEvent) -> None:
            events.append(event)

    class FakeProvider:
        def __init__(self, *, api_key: str, base_url: str) -> None:
            return None

    async def fake_mark_running(*args: Any, **kwargs: Any):
        run.status = "running"
        return run

    async def fake_fail(
        session: Any,
        selected_run: Any,
        *,
        error_code: str,
        error_message: str,
    ):
        failed.append((error_code, error_message))
        run.status = "failed"
        return run

    monkeypatch.setattr(llm_orchestrator, "event_hub", FakeEventHub())
    monkeypatch.setattr(llm_orchestrator, "_load_run_and_user", lambda session, run_id, user_id: _async_value((run, fake_user())))
    monkeypatch.setattr(llm_orchestrator, "select_llm_credential_for_user", lambda session, user: _async_value(credential))
    monkeypatch.setattr(llm_orchestrator, "decrypt_api_key", lambda ciphertext, encryption_key: "plain-key")
    monkeypatch.setattr(llm_orchestrator, "mark_llm_run_running", fake_mark_running)
    monkeypatch.setattr(llm_orchestrator, "OpenAIResponsesProvider", FakeProvider)
    monkeypatch.setattr(llm_orchestrator, "fail_llm_run", fake_fail)

    await llm_orchestrator.execute_llm_run(cast(Any, lambda: FakeSessionContext()), 10, 42)

    assert failed == [("run_kind_unsupported", "当前生成类型暂未接入")]
    assert [event.name for event in events] == ["started", "error", "done"]
    assert events[1].data["error_code"] == "run_kind_unsupported"


@pytest.mark.asyncio
async def test_orchestrator_unsupported_kind_real_session_finishes_stream(
    monkeypatch,
    orchestrator_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from backend.app.services import llm_orchestrator

    encryption_key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "credential_encryption_key", encryption_key)
    async with orchestrator_session_factory() as session:
        user, run = await create_orchestrator_user_run(
            session,
            encryption_key=encryption_key,
            kind="study_plan_adjustment",
        )
        user_id = user.id
        run_id = run.id

    events: list[LlmRunEvent] = []

    class FakeEventHub:
        async def publish(self, published_run_id: int, event: LlmRunEvent) -> None:
            assert published_run_id == run_id
            events.append(event)

    monkeypatch.setattr(llm_orchestrator, "event_hub", FakeEventHub())

    await llm_orchestrator.execute_llm_run(orchestrator_session_factory, run_id, user_id)

    async with orchestrator_session_factory() as session:
        saved_run = await session.get(LlmRun, run_id)
        assert saved_run is not None
        assert saved_run.status == "failed"
        assert saved_run.error_code == "run_kind_unsupported"

    assert [event.name for event in events] == ["started", "error", "done"]


@pytest.mark.asyncio
async def test_orchestrator_status_conflict_rolls_back_without_result(monkeypatch) -> None:
    from backend.app.services import llm_orchestrator
    from backend.app.services.llm_run_service import LlmRunError

    events: list[LlmRunEvent] = []
    calls: list[str] = []
    run = type(
        "Run",
        (),
        {
            "id": 11,
            "user_id": 42,
            "kind": "goal_plan_generate",
            "status": "pending",
            "cancel_requested": False,
            "display_text_md": "",
        },
    )()
    credential = type(
        "Credential",
        (),
        {
            "id": 5,
            "api_key_ciphertext": "ciphertext",
            "base_url": "https://example.test/v1",
            "model_name": "gpt-test",
        },
    )()

    class FakeSession:
        async def rollback(self) -> None:
            calls.append("rollback")

    class FakeSessionContext:
        async def __aenter__(self) -> FakeSession:
            return FakeSession()

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeEventHub:
        async def publish(self, run_id: int, event: LlmRunEvent) -> None:
            calls.append(f"publish:{event.name}")
            events.append(event)

    class FakeProvider:
        def __init__(self, *, api_key: str, base_url: str) -> None:
            return None

    async def fake_mark_running(*args: Any, **kwargs: Any):
        run.status = "running"
        return run

    class FakeHandler:
        async def execute(self, context: Any) -> dict[str, Any]:
            run.display_text_md = "flushed draft text"
            return {"draft_id": 8}

    def fake_handler_for_kind(kind: str) -> Any:
        assert kind == "goal_plan_generate"
        return FakeHandler()

    async def fake_succeed(*args: Any, **kwargs: Any):
        run.status = "canceled"
        run.cancel_requested = True
        raise LlmRunError("run_status_conflict")

    monkeypatch.setattr(llm_orchestrator, "event_hub", FakeEventHub())
    monkeypatch.setattr(llm_orchestrator, "_load_run_and_user", lambda session, run_id, user_id: _async_value((run, fake_user())))
    monkeypatch.setattr(llm_orchestrator, "select_llm_credential_for_user", lambda session, user: _async_value(credential))
    monkeypatch.setattr(llm_orchestrator, "decrypt_api_key", lambda ciphertext, encryption_key: "plain-key")
    monkeypatch.setattr(llm_orchestrator, "mark_llm_run_running", fake_mark_running)
    monkeypatch.setattr(llm_orchestrator, "OpenAIResponsesProvider", FakeProvider)
    monkeypatch.setattr(llm_orchestrator, "handler_for_kind", fake_handler_for_kind)
    monkeypatch.setattr(llm_orchestrator, "succeed_llm_run", fake_succeed)

    await llm_orchestrator.execute_llm_run(cast(Any, lambda: FakeSessionContext()), 11, 42)

    assert [event.name for event in events] == ["started", "progress", "canceled", "done"]
    assert "publish:result" not in calls
    assert "rollback" in calls


async def _async_value(value: Any) -> Any:
    return value
