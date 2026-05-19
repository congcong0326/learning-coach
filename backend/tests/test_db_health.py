from collections.abc import Awaitable, Callable

from fastapi.testclient import TestClient

from backend.app.api import db_health as db_health_api
from backend.app.main import app


async def _database_reachable() -> bool:
    return True


async def _database_unreachable() -> bool:
    return False


def test_db_health_returns_ok_when_database_is_reachable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        db_health_api,
        "check_database",
        _database_reachable,
    )
    client = TestClient(app)

    response = client.get("/api/db/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "reachable",
    }


def test_db_health_returns_503_when_database_is_unreachable(
    monkeypatch,
) -> None:
    async def raise_if_called() -> bool:
        return False

    checker: Callable[[], Awaitable[bool]] = raise_if_called
    monkeypatch.setattr(db_health_api, "check_database", checker)
    client = TestClient(app)

    response = client.get("/api/db/health")

    assert response.status_code == 503
    assert response.json() == {"detail": "database_unreachable"}
