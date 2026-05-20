from __future__ import annotations

from backend.app.models.learning import (
    GoalCalibrationDraft,
    PlanChangeLog,
    StudyPlan,
    StudyPlanItem,
    StudyPlanStage,
    StudyPlanVersion,
)


def test_learning_tables_are_registered_in_metadata() -> None:
    table_names = {
        GoalCalibrationDraft.__tablename__,
        StudyPlan.__tablename__,
        StudyPlanVersion.__tablename__,
        StudyPlanStage.__tablename__,
        StudyPlanItem.__tablename__,
        PlanChangeLog.__tablename__,
    }

    assert table_names == {
        "goal_calibration_draft",
        "study_plan",
        "study_plan_version",
        "study_plan_stage",
        "study_plan_item",
        "plan_change_log",
    }


def test_confirmed_version_fk_is_named_and_deferred() -> None:
    foreign_keys = list(GoalCalibrationDraft.__table__.foreign_keys)
    confirmed_version_fk = next(
        fk for fk in foreign_keys if fk.parent.name == "confirmed_version_id"
    )

    assert confirmed_version_fk.constraint.name == "fk_goal_draft_confirmed_version"
    assert confirmed_version_fk.constraint.use_alter is True


def test_default_empty_learning_columns_have_server_defaults() -> None:
    columns = [
        GoalCalibrationDraft.__table__.c.followup_messages_json,
        GoalCalibrationDraft.__table__.c.draft_goal_json,
        GoalCalibrationDraft.__table__.c.draft_plan_json,
        GoalCalibrationDraft.__table__.c.validation_report_json,
        GoalCalibrationDraft.__table__.c.repair_log_json,
        GoalCalibrationDraft.__table__.c.prompt_version,
        GoalCalibrationDraft.__table__.c.model_name,
        GoalCalibrationDraft.__table__.c.error_message,
        StudyPlanVersion.__table__.c.generation_summary_md,
        StudyPlanVersion.__table__.c.adjustment_summary_md,
        StudyPlanVersion.__table__.c.validation_report_json,
        StudyPlanVersion.__table__.c.repair_log_json,
        StudyPlanStage.__table__.c.focus_tags_json,
        StudyPlanStage.__table__.c.assessment_criteria_json,
        StudyPlanItem.__table__.c.skill_tags_json,
        PlanChangeLog.__table__.c.detail_json,
        PlanChangeLog.__table__.c.reason_md,
    ]

    assert all(column.server_default is not None for column in columns)


def test_study_plan_item_stage_fk_includes_version_guard() -> None:
    constraints = {
        constraint.name: constraint
        for constraint in StudyPlanItem.__table__.foreign_key_constraints
    }
    stage_version_fk = constraints["fk_study_plan_item_stage_version"]

    assert [element.parent.name for element in stage_version_fk.elements] == [
        "stage_id",
        "version_id",
    ]
    assert [element.column.name for element in stage_version_fk.elements] == [
        "id",
        "version_id",
    ]

    stage_unique_constraints = {
        constraint.name for constraint in StudyPlanStage.__table__.constraints
    }
    assert "uq_study_plan_stage_id_version" in stage_unique_constraints
