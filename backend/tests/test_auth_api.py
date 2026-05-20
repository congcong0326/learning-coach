from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.db.session import get_session
from backend.app.main import create_app
from backend.app.models.auth import AppUser, AuthSession, LlmCredential
from backend.app.services.auth_service import (
    has_default_llm_credential,
    hash_password,
    verify_password,
)


def test_auth_models_expose_required_columns() -> None:
    assert {
        "id",
        "username",
        "email",
        "password_hash",
        "display_name",
        "status",
        "created_at",
        "updated_at",
        "last_login_at",
    } <= set(AppUser.__table__.columns.keys())
    assert {
        "id",
        "user_id",
        "session_token_hash",
        "expires_at",
        "revoked_at",
        "created_at",
        "last_seen_at",
    } <= set(AuthSession.__table__.columns.keys())
    assert {
        "id",
        "user_id",
        "provider",
        "display_name",
        "base_url",
        "api_mode",
        "model_name",
        "api_key_ciphertext",
        "api_key_mask",
        "is_default",
        "is_enabled",
        "is_preferred",
        "is_active",
        "failure_count",
        "status",
        "last_tested_at",
        "last_used_at",
        "last_error",
        "created_at",
        "updated_at",
    } <= set(LlmCredential.__table__.columns.keys())


def test_password_hash_uses_argon2id_and_verifies_password() -> None:
    password_hash = hash_password("secret123")

    assert password_hash.startswith("$argon2id$")
    assert verify_password("secret123", password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


@pytest.mark.asyncio
async def test_has_default_llm_credential_tolerates_duplicate_enabled_preferred_rows(
    auth_session_factory,
) -> None:
    async with auth_session_factory() as session:
        now = datetime.now(UTC)
        user = AppUser(
            username="alice",
            email="alice@example.com",
            password_hash="hash",
            display_name="alice",
            status="active",
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        await session.flush()
        session.add_all(
            [
                LlmCredential(
                    user_id=user.id,
                    provider="openai",
                    display_name="first",
                    base_url="https://api.openai.com/v1",
                    api_mode="responses",
                    model_name="gpt-4.1-mini",
                    api_key_ciphertext="cipher-first",
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
                ),
                LlmCredential(
                    user_id=user.id,
                    provider="openai",
                    display_name="second",
                    base_url="https://api.openai.com/v1",
                    api_mode="responses",
                    model_name="gpt-4.1-mini",
                    api_key_ciphertext="cipher-second",
                    api_key_mask="sk-...test",
                    is_default=True,
                    is_enabled=True,
                    is_preferred=True,
                    is_active=False,
                    failure_count=0,
                    status="valid",
                    last_error="",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await session.commit()

        assert await has_default_llm_credential(session, user) is True


@pytest_asyncio.fixture
async def auth_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(AppUser.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def auth_client(auth_session_factory) -> TestClient:
    app = create_app()

    async def override_session():
        async with auth_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def test_register_creates_user_and_sets_session_cookie(
    auth_client: TestClient,
) -> None:
    response = auth_client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "secret123",
        },
    )

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "alice"
    assert "learning_coach_session" in response.cookies
    assert "password_hash" not in response.text


def test_me_requires_login(auth_client: TestClient) -> None:
    response = auth_client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


def test_login_and_logout_session(auth_client: TestClient) -> None:
    auth_client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "secret123",
        },
    )
    logout = auth_client.post("/api/auth/logout")
    login = auth_client.post(
        "/api/auth/login",
        json={"login": "alice", "password": "secret123"},
    )
    me = auth_client.get("/api/auth/me")

    assert logout.status_code == 200
    assert login.status_code == 200
    assert me.status_code == 200
    assert me.json()["username"] == "alice"
