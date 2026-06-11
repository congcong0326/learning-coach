from __future__ import annotations

import pytest

from backend.app.agents.coach_loop import CoachLoop, CoachLoopState


def loop_state() -> CoachLoopState:
    return {
        "user_id": 1,
        "session_id": 2,
        "thread_id": "practice-session-2",
        "study_plan_id": 3,
        "latest_plan_version_id": 4,
        "latest_plan_item_id": 5,
        "problem_id": 6,
        "problem_slug": "two-sum",
        "problem_tags": ["hash-table"],
        "phase": "understand_problem",
        "hint_level": "questioning",
        "profile_summary": "画像置信度低，先追问。",
        "recent_events": [],
        "latest_code_attempt": None,
        "latest_submission_feedback": None,
        "run": {"id": 7, "kind": "coach_turn"},
        "user_query_summary": "用户想先说明暴力解法。",
        "trace": [],
        "error_summary": "",
    }


@pytest.mark.asyncio
async def test_loop_run_records_ordered_node_trace() -> None:
    loop = CoachLoop()

    next_state = await loop.run_turn(loop_state())

    assert [item["node"] for item in next_state["trace"]] == [
        "load_training_context",
        "classify_user_input",
        "diagnose_stuck_point",
        "decide_next_action",
        "guard_transition",
        "generate_coach_reply",
        "persist_turn",
        "maybe_generate_summary",
    ]


@pytest.mark.asyncio
async def test_loop_fast_forwards_code_attempt_to_review_action() -> None:
    state = loop_state()
    state["latest_code_attempt"] = {"snapshot_id": 10, "language": "python3"}

    next_state = await CoachLoop().run_turn(state)

    assert next_state["input_classification"]["kind"] == "code_attempt"
    assert next_state["action_summary"]["proposed_phase_after"] == "review_code"
    assert next_state["action_summary"]["fast_forward"] is True


@pytest.mark.asyncio
async def test_loop_non_ac_feedback_drives_feedback_analysis() -> None:
    state = loop_state()
    state["phase"] = "review_code"
    state["latest_submission_feedback"] = {
        "result": "wa",
        "failed_case_text": "[3,3], target=6",
    }

    next_state = await CoachLoop().run_turn(state)

    assert next_state["diagnosis_summary"]["category"] == "submission_wa"
    assert next_state["action_summary"]["proposed_phase_after"] == "analyze_feedback"
    assert next_state["action_summary"]["next_action"] == "analyze_submission_feedback"
    assert next_state["guard_summary"]["accepted"] is True


@pytest.mark.asyncio
async def test_loop_guard_rejects_summary_without_terminal_feedback() -> None:
    state = loop_state()
    state["run"] = {
        "id": 7,
        "kind": "coach_turn",
        "requested_phase_after": "summarize",
    }

    next_state = await CoachLoop().run_turn(state)

    assert next_state["guard_summary"]["accepted"] is False
    assert next_state["guard_summary"]["reason"] == "terminal_result_required_for_summary"
    assert next_state["guard_summary"]["phase_after"] == "understand_problem"


@pytest.mark.asyncio
async def test_loop_marks_summary_trigger_for_ac_feedback() -> None:
    state = loop_state()
    state["phase"] = "analyze_feedback"
    state["latest_submission_feedback"] = {"result": "ac"}

    next_state = await CoachLoop().run_turn(state)

    assert next_state["action_summary"]["proposed_phase_after"] == "summarize"
    assert next_state["summary_summary"]["triggered"] is True
    assert next_state["summary_summary"]["reason"] == "terminal_feedback_ac"


@pytest.mark.asyncio
async def test_loop_records_recovery_context_from_recent_transition() -> None:
    state = loop_state()
    state["recent_events"] = [
        {
            "event_type": "phase_changed",
            "phase_before": "review_code",
            "phase_after": "define_invariant",
            "reason": "guard_rejected",
        }
    ]

    next_state = await CoachLoop().run_turn(state)

    assert next_state["recovery_summary"]["thread_id"] == "practice-session-2"
    assert next_state["recovery_summary"]["last_phase_after"] == "define_invariant"
