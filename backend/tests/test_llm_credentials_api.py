import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.core.config import settings
from backend.app.db.session import get_session
from backend.app.main import create_app
from backend.app.models.auth import AppUser


@pytest_asyncio.fixture
async def credential_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(AppUser.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def credential_client(credential_session_factory, monkeypatch) -> TestClient:
    monkeypatch.setattr(
        settings,
        "credential_encryption_key",
        Fernet.generate_key().decode(),
    )
    app = create_app()

    async def override_session():
        async with credential_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    response = client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "secret123",
        },
    )
    assert response.status_code == 200
    return client


def test_create_and_list_llm_credential_masks_api_key(
    credential_client: TestClient,
) -> None:
    response = credential_client.post(
        "/api/me/llm-credentials",
        json={
            "display_name": "个人 OpenAI key",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_mode": "responses",
            "model_name": "gpt-4.1-mini",
            "api_key": "sk-test-secret-abcd",
            "is_default": True,
        },
    )
    listed = credential_client.get("/api/me/llm-credentials")

    assert response.status_code == 200
    assert response.json()["api_key_mask"] == "sk-...abcd"
    assert "sk-test-secret-abcd" not in response.text
    assert listed.status_code == 200
    assert listed.json()["items"][0]["is_default"] is True
    assert listed.json()["items"][0]["api_key_mask"] == "sk-...abcd"


def test_create_response_includes_routing_fields_and_patch_disable_clears_active(
    credential_client: TestClient,
) -> None:
    response = credential_client.post(
        "/api/me/llm-credentials",
        json={
            "display_name": "primary",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_mode": "responses",
            "model_name": "gpt-4.1-mini",
            "api_key": "sk-test-secret-abcd",
            "is_enabled": True,
            "is_preferred": True,
        },
    )

    assert response.status_code == 200
    created = response.json()
    assert created["is_enabled"] is True
    assert created["is_preferred"] is True
    assert created["is_default"] is True
    assert created["is_active"] is True
    assert created["failure_count"] == 0
    assert created["last_used_at"] is None

    patched = credential_client.patch(
        f"/api/me/llm-credentials/{created['id']}",
        json={"is_enabled": False},
    )

    assert patched.status_code == 200
    updated = patched.json()
    assert updated["is_enabled"] is False
    assert updated["is_preferred"] is True
    assert updated["is_default"] is True
    assert updated["is_active"] is False


def test_patch_reenable_preferred_credential_makes_it_active(
    credential_client: TestClient,
) -> None:
    preferred = credential_client.post(
        "/api/me/llm-credentials",
        json={
            "display_name": "preferred",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_mode": "responses",
            "model_name": "gpt-4.1-mini",
            "api_key": "sk-preferred-secret-abcd",
            "is_preferred": True,
        },
    ).json()
    credential_client.patch(
        f"/api/me/llm-credentials/{preferred['id']}",
        json={"is_enabled": False},
    )

    reenabled = credential_client.patch(
        f"/api/me/llm-credentials/{preferred['id']}",
        json={"is_enabled": True},
    )
    listed = credential_client.get("/api/me/llm-credentials").json()["items"]

    assert reenabled.status_code == 200
    assert reenabled.json()["is_active"] is True
    assert {item["id"]: item["is_active"] for item in listed} == {preferred["id"]: True}


def test_set_default_clears_previous_default(credential_client: TestClient) -> None:
    first = credential_client.post(
        "/api/me/llm-credentials",
        json={
            "display_name": "first",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_mode": "responses",
            "model_name": "gpt-4.1-mini",
            "api_key": "sk-first-secret-abcd",
            "is_default": True,
        },
    ).json()
    second = credential_client.post(
        "/api/me/llm-credentials",
        json={
            "display_name": "second",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_mode": "responses",
            "model_name": "gpt-4.1",
            "api_key": "sk-second-secret-wxyz",
            "is_default": False,
        },
    ).json()

    response = credential_client.post(
        f"/api/me/llm-credentials/{second['id']}/default"
    )
    listed = credential_client.get("/api/me/llm-credentials").json()["items"]

    assert response.status_code == 200
    defaults = {item["id"]: item["is_default"] for item in listed}
    assert defaults[first["id"]] is False
    assert defaults[second["id"]] is True


def test_set_preferred_replaces_old_default_semantics_with_exactly_one_preferred(
    credential_client: TestClient,
) -> None:
    first = credential_client.post(
        "/api/me/llm-credentials",
        json={
            "display_name": "first",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_mode": "responses",
            "model_name": "gpt-4.1-mini",
            "api_key": "sk-first-secret-abcd",
            "is_preferred": True,
        },
    ).json()
    second = credential_client.post(
        "/api/me/llm-credentials",
        json={
            "display_name": "second",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_mode": "responses",
            "model_name": "gpt-4.1",
            "api_key": "sk-second-secret-wxyz",
            "is_preferred": False,
        },
    ).json()

    response = credential_client.post(
        f"/api/me/llm-credentials/{second['id']}/preferred"
    )
    listed = credential_client.get("/api/me/llm-credentials").json()["items"]

    assert response.status_code == 200
    preferred = [item for item in listed if item["is_preferred"]]
    defaults = [item for item in listed if item["is_default"]]
    assert [item["id"] for item in preferred] == [second["id"]]
    assert [item["id"] for item in defaults] == [second["id"]]
    assert {item["id"]: item["is_active"] for item in listed} == {
        first["id"]: False,
        second["id"]: True,
    }


def test_set_default_route_remains_preferred_alias(
    credential_client: TestClient,
) -> None:
    first = credential_client.post(
        "/api/me/llm-credentials",
        json={
            "display_name": "first",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_mode": "responses",
            "model_name": "gpt-4.1-mini",
            "api_key": "sk-first-secret-abcd",
            "is_preferred": True,
        },
    ).json()
    second = credential_client.post(
        "/api/me/llm-credentials",
        json={
            "display_name": "second",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_mode": "responses",
            "model_name": "gpt-4.1",
            "api_key": "sk-second-secret-wxyz",
        },
    ).json()

    response = credential_client.post(
        f"/api/me/llm-credentials/{second['id']}/default"
    )
    listed = credential_client.get("/api/me/llm-credentials").json()["items"]

    assert response.status_code == 200
    assert response.json()["is_preferred"] is True
    assert [item["id"] for item in listed if item["is_preferred"]] == [second["id"]]
    assert [item["id"] for item in listed if item["is_default"]] == [second["id"]]
    assert {item["id"]: item["is_preferred"] for item in listed}[first["id"]] is False


def test_first_credential_without_default_or_preferred_becomes_preferred(
    credential_client: TestClient,
) -> None:
    response = credential_client.post(
        "/api/me/llm-credentials",
        json={
            "display_name": "first",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_mode": "responses",
            "model_name": "gpt-4.1-mini",
            "api_key": "sk-first-secret-abcd",
        },
    )

    assert response.status_code == 200
    created = response.json()
    assert created["is_preferred"] is True
    assert created["is_default"] is True
    assert created["is_active"] is True


def test_test_connection_updates_status(credential_client: TestClient, monkeypatch) -> None:
    async def fake_test_openai_credential(*args, **kwargs):
        return {
            "status": "valid",
            "message": "connection_ok",
            "model_name": "gpt-4.1-mini",
        }

    monkeypatch.setattr(
        "backend.app.api.llm_credentials.test_openai_credential",
        fake_test_openai_credential,
    )
    created = credential_client.post(
        "/api/me/llm-credentials",
        json={
            "display_name": "个人 OpenAI key",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_mode": "responses",
            "model_name": "gpt-4.1-mini",
            "api_key": "sk-test-secret-abcd",
            "is_default": True,
        },
    ).json()

    response = credential_client.post(
        f"/api/me/llm-credentials/{created['id']}/test"
    )
    listed = credential_client.get("/api/me/llm-credentials").json()["items"]

    assert response.status_code == 200
    assert response.json()["status"] == "valid"
    assert listed[0]["status"] == "valid"
