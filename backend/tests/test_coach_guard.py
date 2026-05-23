from backend.app.services.coach_guard import guard_transition


def test_allows_adjacent_phase_progress() -> None:
    result = guard_transition(
        phase_before="understand_problem",
        proposed_phase_after="propose_bruteforce",
        has_code=False,
        has_submission_feedback=False,
        hint_level="questioning",
        should_reveal_solution=False,
    )

    assert result.accepted is True
    assert result.phase_after == "propose_bruteforce"


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


def test_code_review_with_code_can_enter_review_phase() -> None:
    result = guard_transition(
        phase_before="understand_problem",
        proposed_phase_after="review_code",
        has_code=True,
        has_submission_feedback=False,
        hint_level="questioning",
        should_reveal_solution=False,
    )

    assert result.accepted is True
    assert result.phase_after == "review_code"


def test_feedback_with_submission_feedback_can_enter_analysis() -> None:
    result = guard_transition(
        phase_before="write_code",
        proposed_phase_after="analyze_feedback",
        has_code=True,
        has_submission_feedback=True,
        hint_level="questioning",
        should_reveal_solution=False,
    )

    assert result.accepted is True
    assert result.phase_after == "analyze_feedback"


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


def test_summary_requires_submission_feedback() -> None:
    result = guard_transition(
        phase_before="analyze_feedback",
        proposed_phase_after="summarize",
        has_code=True,
        has_submission_feedback=False,
        hint_level="reflection",
        should_reveal_solution=False,
    )

    assert result.accepted is False
    assert result.phase_after == "analyze_feedback"
    assert result.reason == "submission_feedback_required"


def test_rejects_early_submit_transition() -> None:
    result = guard_transition(
        phase_before="understand_problem",
        proposed_phase_after="submit_to_leetcode",
        has_code=False,
        has_submission_feedback=False,
        hint_level="questioning",
        should_reveal_solution=False,
    )

    assert result.accepted is False
    assert result.phase_after == "understand_problem"
    assert result.reason == "phase_transition_not_allowed"


def test_rejects_early_summary_transition() -> None:
    result = guard_transition(
        phase_before="understand_problem",
        proposed_phase_after="summarize",
        has_code=False,
        has_submission_feedback=True,
        hint_level="reflection",
        should_reveal_solution=False,
    )

    assert result.accepted is False
    assert result.phase_after == "understand_problem"
    assert result.reason == "phase_transition_not_allowed"


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
