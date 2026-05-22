from backend.app.services.coach_guard import guard_transition


def test_rejects_feedback_analysis_without_submission_feedback() -> None:
    result = guard_transition(
        phase_before="review_code",
        proposed_phase_after="analyze_feedback",
        has_code=True,
        has_submission_feedback=False,
        hint_level="questioning",
        should_reveal_solution=False,
    )

    assert result.accepted is False
    assert result.phase_after == "review_code"


def test_ac_feedback_can_enter_summary() -> None:
    result = guard_transition(
        phase_before="analyze_feedback",
        proposed_phase_after="summarize",
        has_code=True,
        has_submission_feedback=True,
        hint_level="reflection",
        should_reveal_solution=False,
    )

    assert result.accepted is True
    assert result.phase_after == "summarize"


def test_low_hint_rejects_solution_reveal() -> None:
    result = guard_transition(
        phase_before="optimize_solution",
        proposed_phase_after="optimize_solution",
        has_code=False,
        has_submission_feedback=False,
        hint_level="questioning",
        should_reveal_solution=True,
    )

    assert result.accepted is False
    assert "hint" in result.reason
