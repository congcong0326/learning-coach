from fastapi.testclient import TestClient

from backend.app.main import app


def test_problem_list_response_has_only_static_fields(monkeypatch) -> None:
    async def fake_list_problems(*args, **kwargs):
        return {
            "items": [
                {
                    "id": 1,
                    "frontend_id": "1",
                    "slug": "two-sum",
                    "title": "Two Sum",
                    "translated_title": "两数之和",
                    "difficulty": "Easy",
                    "tags": [],
                    "categories": [],
                }
            ],
            "total": 1,
            "page": 1,
            "page_size": 20,
        }

    monkeypatch.setattr(
        "backend.app.api.problems.list_problems",
        fake_list_problems,
    )
    client = TestClient(app)

    response = client.get("/api/problems")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["slug"] == "two-sum"
    assert "status" not in payload["items"][0]
    assert "avg_hint_level" not in payload["items"][0]


def test_problem_detail_does_not_return_solution(monkeypatch) -> None:
    async def fake_get_problem_detail(*args, **kwargs):
        return {
            "id": 1,
            "frontend_id": "1",
            "slug": "two-sum",
            "title": "Two Sum",
            "translated_title": "两数之和",
            "difficulty": "Easy",
            "statement_md": "# Two Sum",
            "leetcode_url": "https://leetcode-cn.com/problems/two-sum/",
            "tags": [],
            "categories": [],
            "sample_test_case": "[2,7,11,15]\n9",
            "python3_snippet": "class Solution:",
        }

    monkeypatch.setattr(
        "backend.app.api.problems.get_problem_detail",
        fake_get_problem_detail,
    )
    client = TestClient(app)

    response = client.get("/api/problems/two-sum")

    assert response.status_code == 200
    assert "solution_md" not in response.json()
