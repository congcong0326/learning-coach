from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint

from backend.app.models.practice import (
    CoachTurn,
    CodeSnapshot,
    PracticeEvent,
    PracticeSession,
    ProfileDelta,
    SessionSummary,
    SubmissionFeedback,
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


def _constraint_columns(constraint: UniqueConstraint) -> tuple[str, ...]:
    return tuple(column.name for column in constraint.columns)


def _foreign_key_pairs(constraint: ForeignKeyConstraint) -> tuple[tuple[str, str], ...]:
    return tuple(
        (element.parent.name, element.column.table.name + "." + element.column.name)
        for element in constraint.elements
    )


def _table_unique_constraints(model: type) -> dict[str, tuple[str, ...]]:
    return {
        constraint.name: _constraint_columns(constraint)
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _table_foreign_key_constraints(
    model: type,
) -> dict[str, tuple[tuple[str, str], ...]]:
    return {
        constraint.name: _foreign_key_pairs(constraint)
        for constraint in model.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }


def _table_index_names(model: type) -> set[str]:
    return {
        index.name
        for index in model.__table__.indexes
        if isinstance(index, Index) and index.name is not None
    }


def test_practice_session_has_identity_and_pointer_constraints() -> None:
    unique_constraints = _table_unique_constraints(PracticeSession)
    foreign_keys = _table_foreign_key_constraints(PracticeSession)

    assert unique_constraints["uq_practice_session_user_plan_problem"] == (
        "user_id",
        "study_plan_id",
        "problem_id",
    )
    assert unique_constraints["uq_practice_session_id_user"] == ("id", "user_id")
    assert unique_constraints["uq_practice_session_id_user_problem"] == (
        "id",
        "user_id",
        "problem_id",
    )
    assert foreign_keys["fk_practice_session_latest_code_snapshot"] == (
        ("latest_code_snapshot_id", "code_snapshot.id"),
        ("id", "code_snapshot.session_id"),
        ("user_id", "code_snapshot.user_id"),
    )
    assert foreign_keys["fk_practice_session_profile_snapshot"] == (
        ("profile_snapshot_id", "user_profile_snapshot.id"),
        ("user_id", "user_profile_snapshot.user_id"),
    )


def test_child_tables_enforce_session_user_context() -> None:
    practice_event_fks = _table_foreign_key_constraints(PracticeEvent)
    code_snapshot_fks = _table_foreign_key_constraints(CodeSnapshot)
    feedback_fks = _table_foreign_key_constraints(SubmissionFeedback)
    coach_turn_fks = _table_foreign_key_constraints(CoachTurn)
    profile_delta_fks = _table_foreign_key_constraints(ProfileDelta)

    assert practice_event_fks["fk_practice_event_session_user"] == (
        ("session_id", "practice_session.id"),
        ("user_id", "practice_session.user_id"),
    )
    assert code_snapshot_fks["fk_code_snapshot_session_user"] == (
        ("session_id", "practice_session.id"),
        ("user_id", "practice_session.user_id"),
    )
    assert feedback_fks["fk_submission_feedback_session_user"] == (
        ("session_id", "practice_session.id"),
        ("user_id", "practice_session.user_id"),
    )
    assert coach_turn_fks["fk_coach_turn_session_user"] == (
        ("session_id", "practice_session.id"),
        ("user_id", "practice_session.user_id"),
    )
    assert profile_delta_fks["fk_profile_delta_session_user"] == (
        ("session_id", "practice_session.id"),
        ("user_id", "practice_session.user_id"),
    )


def test_session_summary_enforces_session_user_problem_context() -> None:
    foreign_keys = _table_foreign_key_constraints(SessionSummary)

    assert foreign_keys["fk_session_summary_session_user_problem"] == (
        ("session_id", "practice_session.id"),
        ("user_id", "practice_session.user_id"),
        ("problem_id", "practice_session.problem_id"),
    )


def test_event_and_code_references_stay_inside_same_session_user_context() -> None:
    code_snapshot_fks = _table_foreign_key_constraints(CodeSnapshot)
    feedback_fks = _table_foreign_key_constraints(SubmissionFeedback)
    coach_turn_fks = _table_foreign_key_constraints(CoachTurn)

    assert code_snapshot_fks["fk_code_snapshot_event_context"] == (
        ("event_id", "practice_event.id"),
        ("session_id", "practice_event.session_id"),
        ("user_id", "practice_event.user_id"),
    )
    assert feedback_fks["fk_submission_feedback_event_context"] == (
        ("event_id", "practice_event.id"),
        ("session_id", "practice_event.session_id"),
        ("user_id", "practice_event.user_id"),
    )
    assert feedback_fks["fk_submission_feedback_code_snapshot_context"] == (
        ("code_snapshot_id", "code_snapshot.id"),
        ("session_id", "code_snapshot.session_id"),
        ("user_id", "code_snapshot.user_id"),
    )
    assert coach_turn_fks["fk_coach_turn_user_event_context"] == (
        ("user_event_id", "practice_event.id"),
        ("session_id", "practice_event.session_id"),
        ("user_id", "practice_event.user_id"),
    )
    assert coach_turn_fks["fk_coach_turn_assistant_event_context"] == (
        ("assistant_event_id", "practice_event.id"),
        ("session_id", "practice_event.session_id"),
        ("user_id", "practice_event.user_id"),
    )


def test_required_practice_indexes_are_declared() -> None:
    assert _table_index_names(PracticeSession) == {
        "ix_practice_session_user_status_activity",
        "ix_practice_session_plan_problem",
        "ix_practice_session_thread",
    }
    assert _table_index_names(PracticeEvent) == {
        "ix_practice_event_session_created",
        "ix_practice_event_user_created",
        "ix_practice_event_llm_run",
    }
    assert _table_index_names(CodeSnapshot) == {
        "ix_code_snapshot_session_created",
        "ix_code_snapshot_user_created",
        "ix_code_snapshot_hash",
    }
    assert _table_index_names(SubmissionFeedback) == {
        "ix_submission_feedback_session_created",
        "ix_submission_feedback_user_result_created",
        "ix_submission_feedback_code_snapshot",
    }
    assert _table_index_names(CoachTurn) == {
        "ix_coach_turn_session_created",
        "ix_coach_turn_session_phase_after",
        "ix_coach_turn_session_hint_after",
        "ix_coach_turn_llm_run",
    }
    assert _table_index_names(SessionSummary) == {
        "ix_session_summary_user_created",
        "ix_session_summary_problem",
    }
    assert _table_index_names(UserProfileSnapshot) == {
        "ix_user_profile_snapshot_user_created",
        "ix_user_profile_snapshot_user_source",
    }
    assert _table_index_names(ProfileDelta) == {
        "ix_profile_delta_user_created",
        "ix_profile_delta_session",
        "ix_profile_delta_summary",
        "ix_profile_delta_status",
    }
