from __future__ import annotations

from backend.app.services.recommendation_service import recommend_next_plan_item


def test_recommendation_prefers_same_weak_tag_next_pending_item() -> None:
    plan_payload = {
        "current_item_id": 11,
        "current_stage_index": 0,
        "items": [
            {
                "item_id": 11,
                "problem_slug": "two-sum",
                "problem_title": "Two Sum",
                "stage_index": 0,
                "order_index": 0,
                "difficulty": "Easy",
                "skill_tags": ["array", "hash-table"],
                "status": "completed",
            },
            {
                "item_id": 12,
                "problem_slug": "contains-duplicate",
                "problem_title": "Contains Duplicate",
                "stage_index": 0,
                "order_index": 1,
                "difficulty": "Easy",
                "skill_tags": ["array", "边界"],
                "status": "pending",
            },
            {
                "item_id": 13,
                "problem_slug": "valid-parentheses",
                "problem_title": "Valid Parentheses",
                "stage_index": 0,
                "order_index": 2,
                "difficulty": "Easy",
                "skill_tags": ["stack"],
                "status": "pending",
            },
        ],
    }
    summary = {
        "main_stuck_points": ["edge_case_missing"],
        "error_types": ["wa"],
        "profile_signals": {"weak_skill_tags": ["边界"]},
    }

    recommendation = recommend_next_plan_item(plan_payload, summary)

    assert recommendation["item_id"] == 12
    assert "边界" in recommendation["reason"]
    assert recommendation["first_question_hint"]
    assert recommendation["review_focus"]
