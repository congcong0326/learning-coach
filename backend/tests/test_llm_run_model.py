from __future__ import annotations

from typing import cast

from sqlalchemy import CheckConstraint, Table

from backend.app.models.llm_run import LlmRun


def llm_run_table() -> Table:
    return cast(Table, LlmRun.__table__)


def test_llm_run_table_shape() -> None:
    table = llm_run_table()

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
    table = llm_run_table()
    indexes = {index.name for index in table.indexes}

    assert "ix_llm_run_user_created" in indexes
    assert "ix_llm_run_user_kind_status" in indexes
    assert "ix_llm_run_related" in indexes
    assert "ix_llm_run_credential" in indexes


def test_llm_run_status_constraint_values() -> None:
    table = llm_run_table()
    constraints = {constraint.name: constraint for constraint in table.constraints}

    assert "ck_llm_run_status" in constraints
    status_constraint = cast(CheckConstraint, constraints["ck_llm_run_status"])
    status_sql = str(status_constraint.sqltext)
    assert "pending" in status_sql
    assert "running" in status_sql
    assert "succeeded" in status_sql
    assert "failed" in status_sql
    assert "canceled" in status_sql
