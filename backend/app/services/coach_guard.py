from __future__ import annotations

from dataclasses import dataclass

EARLY_REASONING_PHASES = {
    "understand_problem",
    "propose_bruteforce",
    "optimize_solution",
    "define_invariant",
    "write_code",
}


@dataclass(frozen=True)
class GuardDecision:
    accepted: bool
    phase_after: str
    hint_level_after: str
    reason: str


def guard_transition(
    *,
    phase_before: str,
    proposed_phase_after: str,
    has_code: bool,
    has_submission_feedback: bool,
    hint_level: str,
    should_reveal_solution: bool,
) -> GuardDecision:
    if should_reveal_solution and hint_level in {"questioning", "direction"}:
        return GuardDecision(
            accepted=False,
            phase_after=phase_before,
            hint_level_after=hint_level,
            reason="hint_level_prevents_solution_reveal",
        )
    if proposed_phase_after == phase_before:
        return GuardDecision(
            accepted=True,
            phase_after=proposed_phase_after,
            hint_level_after=hint_level,
            reason="accepted",
        )
    if proposed_phase_after == "review_code" and not has_code:
        return GuardDecision(
            accepted=False,
            phase_after=phase_before,
            hint_level_after=hint_level,
            reason="code_required_for_review",
        )
    if (
        phase_before in EARLY_REASONING_PHASES
        and proposed_phase_after in EARLY_REASONING_PHASES
    ) or (
        phase_before == "review_code"
        and proposed_phase_after in EARLY_REASONING_PHASES
    ):
        return GuardDecision(
            accepted=True,
            phase_after=proposed_phase_after,
            hint_level_after=hint_level,
            reason="accepted",
        )
    if proposed_phase_after == "review_code":
        return GuardDecision(
            accepted=True,
            phase_after=proposed_phase_after,
            hint_level_after=hint_level,
            reason="accepted",
        )
    if proposed_phase_after == "submit_to_leetcode":
        if phase_before not in {"review_code", "submit_to_leetcode"} or not has_code:
            return GuardDecision(
                accepted=False,
                phase_after=phase_before,
                hint_level_after=hint_level,
                reason="phase_transition_not_allowed",
            )
        return GuardDecision(
            accepted=True,
            phase_after=proposed_phase_after,
            hint_level_after=hint_level,
            reason="accepted",
        )
    if proposed_phase_after == "analyze_feedback":
        if not has_submission_feedback:
            return GuardDecision(
                accepted=False,
                phase_after=phase_before,
                hint_level_after=hint_level,
                reason="submission_feedback_required",
            )
        return GuardDecision(
            accepted=True,
            phase_after=proposed_phase_after,
            hint_level_after=hint_level,
            reason="accepted",
        )
    if proposed_phase_after == "summarize":
        if phase_before == "summarize":
            return GuardDecision(
                accepted=True,
                phase_after=proposed_phase_after,
                hint_level_after=hint_level,
                reason="accepted",
            )
        if not has_submission_feedback:
            return GuardDecision(
                accepted=False,
                phase_after=phase_before,
                hint_level_after=hint_level,
                reason="submission_feedback_required",
            )
        if phase_before != "analyze_feedback":
            return GuardDecision(
                accepted=False,
                phase_after=phase_before,
                hint_level_after=hint_level,
                reason="phase_transition_not_allowed",
            )
        return GuardDecision(
            accepted=True,
            phase_after=proposed_phase_after,
            hint_level_after=hint_level,
            reason="accepted",
        )
    return GuardDecision(
        accepted=False,
        phase_after=phase_before,
        hint_level_after=hint_level,
        reason="phase_transition_not_allowed",
    )
