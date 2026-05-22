from pydantic import ValidationError

from backend.app.schemas.practice import (
    CodeSnapshotCreate,
    PracticeMessageCreate,
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
