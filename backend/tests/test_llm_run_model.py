from __future__ import annotations

from backend.app.models.llm_run import LlmRun


def test_llm_run_table_shape() -> None:
    table = LlmRun.__table__

    assert table.name == "llm_run"
    assert table.c.user_id.nullable is False
    assert table.c.kind.nullable is False
    assert table.c.status.server_default is not None
    assert table.c.stage.server_default is not None
    assert table.c.display_text_md.server_default is not None
    assert table.c.input_json.server_default is not None
    assert table.c.result_json.server_default is not None
    assert table.c.cancel_requested.server_default is not None


def test_llm_run_has_expected_indexes() -> None:
    table = LlmRun.__table__
    indexes = {index.name for index in table.indexes}

    assert "ix_llm_run_user_created" in indexes
    assert "ix_llm_run_user_kind_status" in indexes
    assert "ix_llm_run_related" in indexes
    assert "ix_llm_run_credential" in indexes


def test_llm_run_status_constraint_values() -> None:
    table = LlmRun.__table__
    constraints = {constraint.name: constraint for constraint in table.constraints}

    assert "ck_llm_run_status" in constraints
    assert "pending" in str(constraints["ck_llm_run_status"].sqltext)
    assert "running" in str(constraints["ck_llm_run_status"].sqltext)
    assert "succeeded" in str(constraints["ck_llm_run_status"].sqltext)
    assert "failed" in str(constraints["ck_llm_run_status"].sqltext)
    assert "canceled" in str(constraints["ck_llm_run_status"].sqltext)
