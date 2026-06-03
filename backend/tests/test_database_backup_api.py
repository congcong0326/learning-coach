from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.db.session import get_session
from backend.app.main import create_app
from backend.app.models.auth import AppUser


def test_export_requires_login() -> None:
    client = TestClient(create_app())

    response = client.get("/api/database-backups/export")

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


def test_restore_requires_login() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/database-backups/restore",
        content=b"PGDMP backup",
        headers={"Content-Type": "application/octet-stream"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


@pytest_asyncio.fixture
async def backup_session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(AppUser.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def backup_client(
    backup_session_factory: async_sessionmaker[AsyncSession],
) -> TestClient:
    app = create_app()

    async def override_session() -> AsyncGenerator[AsyncSession]:
        async with backup_session_factory() as session:
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


def test_export_returns_dump_file(
    backup_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import backend.app.api.database_backups as database_backups_api

    dump_path = tmp_path / "learning-coach-db-20260602-213000.dump"
    dump_bytes = b"PGDMP test dump"
    dump_path.write_bytes(dump_bytes)
    called: dict[str, int] = {}

    async def fake_create_database_backup(*, user_id: int):
        called["user_id"] = user_id
        return SimpleNamespace(
            path=dump_path,
            filename=dump_path.name,
            size_bytes=len(dump_bytes),
            created_at=datetime.now(UTC),
        )

    monkeypatch.setattr(
        database_backups_api,
        "create_database_backup",
        fake_create_database_backup,
        raising=False,
    )

    response = backup_client.get("/api/database-backups/export")

    assert response.status_code == 200
    assert response.content == dump_bytes
    assert response.headers["content-type"] == "application/octet-stream"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="learning-coach-db-20260602-213000.dump"'
    )
    assert called["user_id"] == 1


def test_restore_uploads_dump_file(
    backup_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.app.api.database_backups as database_backups_api

    dump_bytes = b"PGDMP restore dump"
    restored_at = datetime(2026, 6, 2, 21, 45, 0, tzinfo=UTC)
    captured: dict[str, object] = {}

    async def fake_restore_database_backup(*, backup_path: Path, user_id: int):
        captured["user_id"] = user_id
        captured["content"] = backup_path.read_bytes()
        captured["path_exists_during_restore"] = backup_path.exists()
        return SimpleNamespace(
            status="ok",
            restored_at=restored_at,
            file_size_bytes=len(dump_bytes),
        )

    monkeypatch.setattr(
        database_backups_api,
        "restore_database_backup",
        fake_restore_database_backup,
        raising=False,
    )

    response = backup_client.post(
        "/api/database-backups/restore",
        content=dump_bytes,
        headers={"Content-Type": "application/octet-stream"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "restored_at": "2026-06-02T21:45:00Z",
        "file_size_bytes": len(dump_bytes),
    }
    assert captured == {
        "user_id": 1,
        "content": dump_bytes,
        "path_exists_during_restore": True,
    }


def test_restore_releases_auth_session_before_pg_restore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.app.api.database_backups as database_backups_api
    from backend.app.core.config import settings

    app = create_app()
    session_state = {"closed": False}

    class FakeSession:
        async def close(self) -> None:
            session_state["closed"] = True

    async def override_session():
        yield FakeSession()

    async def fake_current_user_from_token(session, token: str | None):
        assert token == "restore-token"
        return SimpleNamespace(id=42)

    async def fake_restore_database_backup(*, backup_path: Path, user_id: int):
        assert user_id == 42
        assert session_state["closed"] is True
        return SimpleNamespace(
            status="ok",
            restored_at=datetime(2026, 6, 2, 21, 45, 0, tzinfo=UTC),
            file_size_bytes=backup_path.stat().st_size,
        )

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(
        database_backups_api,
        "get_current_user_from_token",
        fake_current_user_from_token,
        raising=False,
    )
    monkeypatch.setattr(
        database_backups_api,
        "restore_database_backup",
        fake_restore_database_backup,
    )

    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(settings.session_cookie_name, "restore-token")
    response = client.post(
        "/api/database-backups/restore",
        content=b"PGDMP restore dump",
        headers={"Content-Type": "application/octet-stream"},
    )

    assert response.status_code == 200


def test_restore_rejects_file_over_configured_limit(
    backup_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.app.api.database_backups as database_backups_api
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "database_backup_max_bytes", 8, raising=False)

    async def fail_if_called(*, backup_path: Path, user_id: int):
        raise AssertionError("restore service should not run for oversized uploads")

    monkeypatch.setattr(
        database_backups_api,
        "restore_database_backup",
        fail_if_called,
        raising=False,
    )

    response = backup_client.post(
        "/api/database-backups/restore",
        content=b"PGDMP payload over limit",
        headers={"Content-Type": "application/octet-stream"},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "backup_file_too_large"


def test_restore_maps_invalid_backup_file_to_400(
    backup_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.app.api.database_backups as database_backups_api
    from backend.app.services.database_backup_service import InvalidBackupFileError

    async def fake_restore_database_backup(*, backup_path: Path, user_id: int):
        raise InvalidBackupFileError("pg_restore could not list archive")

    monkeypatch.setattr(
        database_backups_api,
        "restore_database_backup",
        fake_restore_database_backup,
    )

    response = backup_client.post(
        "/api/database-backups/restore",
        content=b"not a dump",
        headers={"Content-Type": "application/octet-stream"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_backup_file"


def test_restore_maps_busy_operation_to_409(
    backup_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.app.api.database_backups as database_backups_api
    from backend.app.services.database_backup_service import BackupRestoreBusyError

    async def fake_restore_database_backup(*, backup_path: Path, user_id: int):
        raise BackupRestoreBusyError("database backup or restore already running")

    monkeypatch.setattr(
        database_backups_api,
        "restore_database_backup",
        fake_restore_database_backup,
    )

    response = backup_client.post(
        "/api/database-backups/restore",
        content=b"PGDMP dump",
        headers={"Content-Type": "application/octet-stream"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "backup_restore_busy"
