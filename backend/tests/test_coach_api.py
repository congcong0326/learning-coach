from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.agents.problem_agent import AgentRunResult, AgentToolCallLogEntry
from backend.app.api.auth import current_user_dependency
from backend.app.db.session import get_session
from backend.app.main import create_app


class FakeUser:
    id = 1
    username = "alice"


class FakeAgentLoop:
    async def run(self, *, session: object, message: str) -> AgentRunResult:
        return AgentRunResult(
            answer=f"answer: {message}",
            tool_calls=[AgentToolCallLogEntry(name="search_problems")],
        )


def test_coach_chat_requires_login() -> None:
    client = TestClient(create_app())

    response = client.post("/api/coach/chat", json={"message": "hello"})

    assert response.status_code == 401


def test_coach_chat_returns_agent_result(monkeypatch) -> None:
    app = create_app()

    async def override_session():
        yield object()

    async def override_user():
        return FakeUser()

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[current_user_dependency] = override_user
    monkeypatch.setattr("backend.app.api.coach.build_problem_agent_loop", FakeAgentLoop)

    client = TestClient(app)
    response = client.post("/api/coach/chat", json={"message": "找数组题"})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "answer: 找数组题",
        "tool_calls": [{"name": "search_problems"}],
    }
