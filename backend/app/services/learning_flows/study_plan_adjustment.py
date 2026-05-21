from __future__ import annotations


class StudyPlanAdjustmentFlowUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("study_plan_adjustment_flow_unavailable")
