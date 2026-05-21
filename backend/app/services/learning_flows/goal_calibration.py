from __future__ import annotations


class GoalFollowupFlowUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("goal_followup_flow_unavailable")
