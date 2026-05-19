from fastapi.testclient import TestClient

from backend.app.main import app


def test_root_health_returns_backend_status() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "learning-coach-backend",
    }


def test_api_health_returns_backend_status() -> None:
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "learning-coach-backend",
    }
