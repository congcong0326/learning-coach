from __future__ import annotations

from dataclasses import dataclass

COACH_PHASE_ORDER = (
    "understand_problem",
    "propose_bruteforce",
    "optimize_solution",
    "define_invariant",
    "write_code",
    "review_code",
    "submit_to_leetcode",
    "analyze_feedback",
    "summarize",
)
_PHASE_INDEX = {phase: index for index, phase in enumerate(COACH_PHASE_ORDER)}


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
    if proposed_phase_after == "review_code" and not has_code:
        return GuardDecision(
            accepted=False,
            phase_after=phase_before,
            hint_level_after=hint_level,
            reason="code_required_for_review",
        )
    if proposed_phase_after == "analyze_feedback" and not has_submission_feedback:
        return GuardDecision(
            accepted=False,
            phase_after=phase_before,
            hint_level_after=hint_level,
            reason="submission_feedback_required",
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
    if proposed_phase_after == "review_code":
        return GuardDecision(
            accepted=True,
            phase_after=proposed_phase_after,
            hint_level_after=hint_level,
            reason="accepted",
        )
    if proposed_phase_after == "analyze_feedback":
        return GuardDecision(
            accepted=True,
            phase_after=proposed_phase_after,
            hint_level_after=hint_level,
            reason="accepted",
        )
    if not _is_same_or_adjacent_forward(phase_before, proposed_phase_after):
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


def _is_same_or_adjacent_forward(phase_before: str, phase_after: str) -> bool:
    before_index = _PHASE_INDEX.get(phase_before)
    after_index = _PHASE_INDEX.get(phase_after)
    if before_index is None or after_index is None:
        return phase_before == phase_after
    return after_index == before_index or after_index == before_index + 1
