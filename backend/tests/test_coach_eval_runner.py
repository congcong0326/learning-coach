from __future__ import annotations

import subprocess
import sys

from backend.app.evals.coach_eval_runner import run_eval_suite


def test_hint_leakage_eval_passes_low_level_solution_reveal_case() -> None:
    result = run_eval_suite(["hint_leakage"])

    assert result.failed == 0
    assert result.passed == 1
    assert result.cases[0].name == "low_hint_blocks_full_solution"


def test_diagnosis_and_code_review_eval_cases_pass() -> None:
    result = run_eval_suite(["diagnosis", "code_review"])

    assert result.failed == 0
    assert {case.category for case in result.cases} == {"diagnosis", "code_review"}


def test_rag_grounding_eval_runs_real_cases() -> None:
    result = run_eval_suite(["rag_grounding"])

    assert result.failed == 0
    assert result.deferred == 0
    assert result.passed == 3
    assert {case.name for case in result.cases} == {
        "rag_low_hint_filters_full_solution",
        "rag_common_bug_card_grounding",
        "rag_non_ac_feedback_grounding",
    }


def test_eval_runner_module_exits_zero_and_prints_summary() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "backend.app.evals.coach_eval_runner"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Hint Leakage" in completed.stdout
    assert "RAG Grounding" in completed.stdout
    assert "deferred=0" in completed.stdout
    assert "rag_grounding_deferred" not in completed.stdout
