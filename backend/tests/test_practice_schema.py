from pydantic import ValidationError

from backend.app.schemas.practice import (
    CodeSnapshotCreate,
    CoachAction,
    CodeReviewResult,
    PracticeMessageCreate,
    StuckPointDiagnosis,
    SubmissionFeedbackCreate,
)


def test_practice_message_accepts_known_intent_and_hint_level() -> None:
    payload = PracticeMessageCreate(
        intent="describe_idea",
        content_md="我先说暴力解法，再说明哈希表优化。",
        requested_hint_level="questioning",
    )

    assert payload.intent == "describe_idea"
    assert payload.requested_hint_level == "questioning"


def test_practice_message_rejects_empty_content() -> None:
    try:
        PracticeMessageCreate(intent="describe_idea", content_md="")
    except ValidationError as exc:
        assert "content_md" in str(exc)
    else:
        raise AssertionError("empty content should be rejected")


def test_code_snapshot_limits_language_to_supported_values() -> None:
    snapshot = CodeSnapshotCreate(
        language="python3",
        code_text="class Solution:\n    pass",
        source="manual_save",
        client_revision=1,
    )

    assert snapshot.language == "python3"


def test_submission_feedback_accepts_structured_wa() -> None:
    feedback = SubmissionFeedbackCreate(
        code_snapshot_id=7,
        result="wa",
        failed_case_text="nums = [3,3], target = 6",
        error_message="",
        runtime_ms=None,
        memory_kb=None,
    )

    assert feedback.result == "wa"


def test_coach_action_accepts_structured_diagnosis_and_review_result() -> None:
    action = CoachAction(
        phase_after="analyze_feedback",
        diagnosed_stuck_point=StuckPointDiagnosis(
            category="edge_case_missing",
            evidence=["WA 失败用例涉及重复元素"],
            confidence="medium",
        ),
        next_action="analyze_submission_feedback",
        reply_md="先根据失败用例缩小问题区域，再判断哈希表更新顺序。",
        should_reveal_solution=False,
        code_review=CodeReviewResult(
            quality_status="needs_fix",
            issue_type="edge_case_missing",
            suspected_region="哈希表更新顺序",
            explanation_md="失败用例提示重复元素场景没有覆盖。",
            suggested_check="手动 trace nums=[3,3], target=6。",
        ),
    )

    assert action.diagnosed_stuck_point.category == "edge_case_missing"
    assert action.code_review is not None
    assert action.code_review.quality_status == "needs_fix"


def test_coach_action_rejects_empty_evidence_for_diagnosis() -> None:
    try:
        CoachAction(
            phase_after="review_code",
            diagnosed_stuck_point=StuckPointDiagnosis(
                category="implementation_bug",
                evidence=[],
                confidence="medium",
            ),
            next_action="review_code",
            reply_md="我会先定位代码问题。",
            should_reveal_solution=False,
        )
    except ValidationError as exc:
        assert "evidence" in str(exc)
    else:
        raise AssertionError("diagnosis evidence should be required")
