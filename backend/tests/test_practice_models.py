from backend.app.models.practice import (
    PracticeSession,
    ProfileDelta,
    UserProfileSnapshot,
)


def test_practice_session_identity_columns_are_named_for_plan_problem_reuse() -> None:
    columns = PracticeSession.__table__.columns

    assert "user_id" in columns
    assert "study_plan_id" in columns
    assert "problem_id" in columns


def test_profile_snapshot_has_versioned_json_contract() -> None:
    columns = UserProfileSnapshot.__table__.columns

    assert "version_number" in columns
    assert "ability_profile_json" in columns
    assert "skill_profile_json" in columns
    assert "strategy_json" in columns
    assert "evidence_summary_json" in columns


def test_profile_delta_has_acceptance_and_evidence_fields() -> None:
    columns = ProfileDelta.__table__.columns

    assert "status" in columns
    assert "patch_json" in columns
    assert "evidence_json" in columns
    assert "rejection_reason" in columns
