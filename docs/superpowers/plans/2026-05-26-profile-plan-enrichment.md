# 画像驱动的学习计划补强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在学习计划页提供用户画像查看和“基于画像补强计划”能力，让用户输入意愿、数量和难度倾向后，由大模型生成补强题预览，并在用户确认后追加到当前 active 学习计划。

**Architecture:** 后端新增 `profile_plan_enrichment` 独立 flow，复用 LLM Run、Prompt Registry、题库、画像快照、训练复盘和学习计划服务边界。大模型只在后端筛出的候选题池中选择题目，输出 draft，后端做 schema/题库/重复/paid only/阶段校验和 repair；确认接口负责把 draft 原子追加到 active plan 当前阶段末尾。前端在学习计划页增加抽屉，展示当前画像和表单，生成预览后再由用户确认。

**Tech Stack:** Python 3.12, uv, FastAPI, SQLAlchemy async, Alembic, Pydantic, OpenAI Responses provider via existing LLM Run, React, TypeScript, Ant Design, TanStack Query, Vitest, pytest.

---

## Current Context

- 已确认设计 spec：[docs/superpowers/specs/2026-05-26-profile-plan-enrichment-design.md](/root/code/py/learning-coach/docs/superpowers/specs/2026-05-26-profile-plan-enrichment-design.md)
- 现有计划 API 在 `backend/app/api/learning.py`。
- 现有学习计划模型在 `backend/app/models/learning.py`。
- 现有计划 service 在 `backend/app/services/study_plan_service.py`。
- 现有画像更新和读取在 `backend/app/services/profile_service.py`、`backend/app/services/profile_provider.py`。
- 现有 LLM Run handler 注册在 `backend/app/services/llm_run_registry.py`。
- 现有学习计划页在 `frontend/src/pages/StudyPlanPage.tsx`。

## File Structure

- Create: `backend/app/services/profile_plan_enrichment.py`
  - 聚合上下文、生成候选题池、解析模型输出、校验/repair、保存 draft、确认追加计划题。
- Create: `backend/app/services/learning_flows/profile_plan_enrichment.py`
  - LLM Run handler，调用 `profile_plan_enrichment` service 并发布 progress/delta/result。
- Create: `backend/app/prompts/resources/profile_plan_enrichment.v1.md`
  - 大模型补强题生成 prompt，声明上下文优先级、禁止输入、输出 JSON 契约。
- Create: `backend/app/db/migrations/versions/20260526_0008_profile_plan_enrichment.py`
  - 新增 `profile_plan_enrichment_draft` 表。
- Create: `backend/tests/test_profile_plan_enrichment_service.py`
  - 覆盖上下文、候选题、校验、确认追加、并发幂等。
- Create: `backend/tests/test_profile_plan_enrichment_flow.py`
  - 覆盖 LLM handler、prompt 输出解析、repair、LLM Run registry。
- Create: `frontend/src/pages/ProfilePlanEnrichmentDrawer.tsx`
  - 学习计划页抽屉，展示画像、收集用户意愿、生成预览、确认加入计划。
- Create: `frontend/src/pages/ProfilePlanEnrichmentDrawer.test.tsx`
  - 覆盖画像展示、表单、运行状态、预览、确认。
- Modify: `backend/app/models/learning.py`
  - 增加 `ProfilePlanEnrichmentDraft` ORM model。
- Modify: `backend/app/schemas/learning.py`
  - 增加补强请求、draft、预览、确认响应 schema。
- Modify: `backend/app/api/learning.py`
  - 增加 draft 查询和确认接口；生成入口由通用 `/api/llm-runs` 创建 run。
- Modify: `backend/app/services/llm_run_registry.py`
  - 注册 `profile_plan_enrichment` run kind。
- Modify: `backend/app/services/llm_orchestrator.py`
  - 增加用户可读错误码。
- Modify: `backend/app/prompts/registry.py`
  - 注册 `profile_plan_enrichment` prompt。
- Modify: `backend/tests/test_learning_plan_service.py`
  - 扩充模型注册/默认字段测试。
- Modify: `backend/tests/test_learning_api.py`
  - 覆盖 draft 查询和确认 API。
- Modify: `backend/tests/test_llm_runs_api.py`
  - 覆盖 LLM Run related mapping 和 requires_model。
- Modify: `frontend/src/api/learning.ts`
  - 增加补强 draft 类型、查询、确认 API。
- Modify: `frontend/src/api/llmRuns.ts`
  - 增加 `profile_plan_enrichment` run kind。
- Modify: `frontend/src/pages/StudyPlanPage.tsx`
  - 增加 `查看画像与补强` 入口并接入抽屉。
- Modify: `frontend/src/pages/StudyPlanPage.test.tsx`
  - 覆盖入口与确认后刷新计划。
- Modify: `docs/index.md`
  - 记录新增 service/model/API 边界。
- Modify: `docs/architecture/foundation.md`
  - 同步新增 API、LLM Run、draft 表和前端行为。
- Modify: `docs/prd/prd.md`
  - 学习计划页补充画像与补强入口。
- Modify: `docs/prd/ai-coach-user-profile-prd.md`
  - 用户画像新增“用户可见画像与计划补强”消费场景。
- Modify: `docs/project-todolist.md`
  - 新增 P1 任务并记录验证命令。

## Data Contracts

### Backend enums

```python
ProfilePlanEnrichmentStatus = Literal[
    "generating",
    "generated",
    "confirmed",
    "rejected",
    "failed",
]
ProfilePlanEnrichmentDifficulty = Literal[
    "foundational",
    "keep_current",
    "stretch",
]
ProfilePlanEnrichmentItemCount = Literal[2, 3, 5]
```

### Public request

```json
{
  "user_intent_md": "我下周面试，希望多加面试高频 Medium，不要再加太偏动态规划的题。",
  "item_count": 3,
  "difficulty_preference": "keep_current"
}
```

### LLM output

```json
{
  "enrichment_theme": "边界条件与哈希表状态维护补强",
  "plan_gap_assessment": {
    "gap_level": "medium",
    "summary_md": "当前计划已有哈希表题，但缺少针对重复元素和无解边界的连续训练。"
  },
  "overall_reason_md": "建议追加 3 道题，保持当前难度，以面试高频题强化边界检查。",
  "items": [
    {
      "problem_slug": "contains-duplicate",
      "target_stage_key": "stage-current",
      "weakness_targets": ["边界", "哈希表"],
      "difficulty": "Easy",
      "recommendation_reason_md": "这题能强化你提交前先排查重复元素和哈希表语义的习惯。",
      "first_question_hint": "先说明你准备用 set 维护什么，以及什么时候可以提前返回。",
      "review_focus": "重点检查空数组、重复元素和返回条件。",
      "suggested_mode": "independent"
    }
  ],
  "not_added_reason_md": ""
}
```

## Task 1: Backend Model, Migration, and Schemas

**Files:**
- Modify: `backend/app/models/learning.py`
- Modify: `backend/app/schemas/learning.py`
- Create: `backend/app/db/migrations/versions/20260526_0008_profile_plan_enrichment.py`
- Modify: `backend/tests/test_learning_plan_service.py`

- [ ] **Step 1: Write model registration tests**

Add these imports to `backend/tests/test_learning_plan_service.py`:

```python
from backend.app.models.learning import ProfilePlanEnrichmentDraft
```

Update `test_learning_tables_are_registered_in_metadata`:

```python
def test_learning_tables_are_registered_in_metadata() -> None:
    table_names = {
        GoalCalibrationDraft.__tablename__,
        StudyPlan.__tablename__,
        StudyPlanVersion.__tablename__,
        StudyPlanStage.__tablename__,
        StudyPlanItem.__tablename__,
        PlanChangeLog.__tablename__,
        ProfilePlanEnrichmentDraft.__tablename__,
    }

    assert table_names == {
        "goal_calibration_draft",
        "study_plan",
        "study_plan_version",
        "study_plan_stage",
        "study_plan_item",
        "plan_change_log",
        "profile_plan_enrichment_draft",
    }
```

Add a focused draft model test:

```python
def test_profile_plan_enrichment_draft_has_auditable_context_fields() -> None:
    columns = ProfilePlanEnrichmentDraft.__table__.columns

    assert "user_id" in columns
    assert "study_plan_id" in columns
    assert "study_plan_version_id" in columns
    assert "profile_snapshot_id" in columns
    assert "llm_run_id" in columns
    assert "status" in columns
    assert "user_intent_md" in columns
    assert "item_count" in columns
    assert "difficulty_preference" in columns
    assert "context_summary_json" in columns
    assert "candidate_problem_ids_json" in columns
    assert "model_output_json" in columns
    assert "validation_report_json" in columns
    assert "confirmed_item_ids_json" in columns
    assert "error_summary" in columns
    assert "confirmed_at" in columns
```

- [ ] **Step 2: Run model tests to verify failure**

Run:

```bash
uv run pytest backend/tests/test_learning_plan_service.py::test_learning_tables_are_registered_in_metadata backend/tests/test_learning_plan_service.py::test_profile_plan_enrichment_draft_has_auditable_context_fields -q
```

Expected: FAIL with import error or missing table/model.

- [ ] **Step 3: Add ORM model**

Add `ProfilePlanEnrichmentDraft` to `backend/app/models/learning.py` after `PlanChangeLog`:

```python
class ProfilePlanEnrichmentDraft(Base):
    __tablename__ = "profile_plan_enrichment_draft"
    __table_args__ = (
        ForeignKeyConstraint(
            ["study_plan_version_id", "study_plan_id"],
            ["study_plan_version.id", "study_plan_version.plan_id"],
            name="fk_profile_plan_enrichment_version_plan",
            ondelete="CASCADE",
        ),
        Index("ix_profile_plan_enrichment_user_status", "user_id", "status"),
        Index("ix_profile_plan_enrichment_plan_created", "study_plan_id", "created_at"),
        Index("ix_profile_plan_enrichment_llm_run", "llm_run_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    study_plan_id: Mapped[int] = mapped_column(
        ForeignKey("study_plan.id", ondelete="CASCADE"),
        nullable=False,
    )
    study_plan_version_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    profile_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_profile_snapshot.id", ondelete="SET NULL"),
        nullable=True,
    )
    llm_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("llm_run.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'generating'"),
    )
    user_intent_md: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty_preference: Mapped[str] = mapped_column(String(30), nullable=False)
    context_summary_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    candidate_problem_ids_json: Mapped[list[int]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=EMPTY_ARRAY,
    )
    model_output_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    validation_report_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    confirmed_item_ids_json: Mapped[list[int]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=EMPTY_ARRAY,
    )
    error_summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
```

- [ ] **Step 4: Add Alembic migration**

Create `backend/app/db/migrations/versions/20260526_0008_profile_plan_enrichment.py`:

```python
"""create profile plan enrichment draft table

Revision ID: 20260526_0008
Revises: 20260522_0007
Create Date: 2026-05-26 00:11:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260526_0008"
down_revision: str | None = "20260522_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMPTY_JSON_ARRAY = sa.text("'[]'::json")
EMPTY_JSON_OBJECT = sa.text("'{}'::json")
EMPTY_TEXT = sa.text("''")


def upgrade() -> None:
    op.create_table(
        "profile_plan_enrichment_draft",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "study_plan_id",
            sa.BigInteger(),
            sa.ForeignKey("study_plan.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("study_plan_version_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "profile_snapshot_id",
            sa.BigInteger(),
            sa.ForeignKey("user_profile_snapshot.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "llm_run_id",
            sa.BigInteger(),
            sa.ForeignKey("llm_run.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'generating'"),
        ),
        sa.Column("user_intent_md", sa.Text(), nullable=False, server_default=EMPTY_TEXT),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("difficulty_preference", sa.String(length=30), nullable=False),
        sa.Column(
            "context_summary_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "candidate_problem_ids_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_ARRAY,
        ),
        sa.Column(
            "model_output_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "validation_report_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_OBJECT,
        ),
        sa.Column(
            "confirmed_item_ids_json",
            sa.JSON(),
            nullable=False,
            server_default=EMPTY_JSON_ARRAY,
        ),
        sa.Column("error_summary", sa.Text(), nullable=False, server_default=EMPTY_TEXT),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["study_plan_version_id", "study_plan_id"],
            ["study_plan_version.id", "study_plan_version.plan_id"],
            name="fk_profile_plan_enrichment_version_plan",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_profile_plan_enrichment_user_status",
        "profile_plan_enrichment_draft",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_profile_plan_enrichment_plan_created",
        "profile_plan_enrichment_draft",
        ["study_plan_id", "created_at"],
    )
    op.create_index(
        "ix_profile_plan_enrichment_llm_run",
        "profile_plan_enrichment_draft",
        ["llm_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_profile_plan_enrichment_llm_run",
        table_name="profile_plan_enrichment_draft",
    )
    op.drop_index(
        "ix_profile_plan_enrichment_plan_created",
        table_name="profile_plan_enrichment_draft",
    )
    op.drop_index(
        "ix_profile_plan_enrichment_user_status",
        table_name="profile_plan_enrichment_draft",
    )
    op.drop_table("profile_plan_enrichment_draft")
```

The current migration head in this repository is `20260522_0007`, so this migration should use `down_revision = "20260522_0007"`. Confirm before editing with:

```bash
ls backend/app/db/migrations/versions
```

Expected: `20260522_0007_practice_profile.py` is the latest numbered migration before the new file.

- [ ] **Step 5: Add Pydantic schemas**

Append to `backend/app/schemas/learning.py`:

```python
ProfilePlanEnrichmentStatus = Literal[
    "generating",
    "generated",
    "confirmed",
    "rejected",
    "failed",
]
ProfilePlanEnrichmentDifficulty = Literal[
    "foundational",
    "keep_current",
    "stretch",
]


class ProfilePlanEnrichmentRequest(BaseModel):
    user_intent_md: str = Field(default="", max_length=2000)
    item_count: Literal[2, 3, 5] = 3
    difficulty_preference: ProfilePlanEnrichmentDifficulty = "keep_current"


class ProfilePlanGapAssessment(BaseModel):
    gap_level: Literal["low", "medium", "high", "insufficient_evidence"]
    summary_md: str = Field(default="", max_length=1600)


class ProfilePlanEnrichmentItem(BaseModel):
    problem_id: int
    problem_slug: str
    title: str
    translated_title: str
    difficulty: str
    skill_tags: list[str] = Field(default_factory=list)
    target_stage_id: int
    target_stage_title: str
    weakness_targets: list[str] = Field(default_factory=list)
    recommendation_reason_md: str
    first_question_hint: str
    review_focus: str
    suggested_mode: TrainingMode


class ProfilePlanEnrichmentDraftResponse(BaseModel):
    draft_id: int
    status: ProfilePlanEnrichmentStatus
    plan_id: int
    plan_version_id: int
    profile_snapshot_id: int | None
    user_intent_md: str
    item_count: int
    difficulty_preference: ProfilePlanEnrichmentDifficulty
    enrichment_theme: str = ""
    plan_gap_assessment: ProfilePlanGapAssessment | None = None
    overall_reason_md: str = ""
    not_added_reason_md: str = ""
    items: list[ProfilePlanEnrichmentItem] = Field(default_factory=list)
    validation_report: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None = None
```

- [ ] **Step 6: Run model/schema tests**

Run:

```bash
uv run pytest backend/tests/test_learning_plan_service.py::test_learning_tables_are_registered_in_metadata backend/tests/test_learning_plan_service.py::test_profile_plan_enrichment_draft_has_auditable_context_fields -q
```

Expected: PASS.

- [ ] **Step 7: Commit data contract**

Run:

```bash
git add backend/app/models/learning.py backend/app/schemas/learning.py backend/app/db/migrations/versions/20260526_0008_profile_plan_enrichment.py backend/tests/test_learning_plan_service.py
git commit -m "feat: add profile plan enrichment draft model"
```

Expected: commit succeeds.

## Task 2: Service Context, Candidate Pool, and Validation

**Files:**
- Create: `backend/app/services/profile_plan_enrichment.py`
- Create: `backend/tests/test_profile_plan_enrichment_service.py`

- [ ] **Step 1: Create service test fixtures**

Create `backend/tests/test_profile_plan_enrichment_service.py` with shared fixtures:

```python
from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import backend.app.models.llm_run  # noqa: F401
from backend.app.models.auth import AppUser
from backend.app.models.learning import (
    ProfilePlanEnrichmentDraft,
    StudyPlan,
    StudyPlanItem,
    StudyPlanStage,
    StudyPlanVersion,
)
from backend.app.models.practice import SessionSummary, UserProfileSnapshot
from backend.app.models.problem import Base, Problem
from backend.app.schemas.learning import ProfilePlanEnrichmentRequest


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def make_problem(
    slug: str,
    *,
    difficulty: str = "Easy",
    tags: list[str] | None = None,
    paid: bool = False,
) -> Problem:
    now = datetime.now(UTC)
    topic_tags = [
        {"slug": tag, "name": tag.title(), "translated_name": tag}
        for tag in (tags or ["array"])
    ]
    return Problem(
        frontend_id=slug,
        slug=slug,
        title=slug.replace("-", " ").title(),
        translated_title=slug,
        difficulty=difficulty,
        statement_md="# statement",
        metadata_json={"topic_tags": topic_tags},
        leetcode_url=f"https://leetcode.cn/problems/{slug}/",
        is_paid_only=paid,
        created_at=now,
        updated_at=now,
    )


async def create_user_plan(db_session: AsyncSession) -> tuple[AppUser, StudyPlan, StudyPlanVersion]:
    now = datetime.now(UTC)
    unique = uuid4().hex
    user = AppUser(
        username=f"user-{unique}",
        email=f"user-{unique}@example.com",
        password_hash="hash",
        display_name="learner",
        status="active",
        created_at=now,
        updated_at=now,
    )
    existing = make_problem("two-sum", tags=["array", "hash-table"])
    candidates = [
        make_problem("contains-duplicate", tags=["array", "hash-table"]),
        make_problem("valid-anagram", tags=["hash-table", "string"]),
        make_problem("binary-search", difficulty="Easy", tags=["binary-search"]),
        make_problem("premium-only", tags=["array"], paid=True),
    ]
    plan = StudyPlan(
        user_id=1,
        title="面试冲刺计划",
        status="active",
        active_version_number=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([user, existing, *candidates])
    await db_session.flush()
    plan.user_id = user.id
    db_session.add(plan)
    await db_session.flush()
    version = StudyPlanVersion(
        plan_id=plan.id,
        version_number=1,
        status="active",
        target_snapshot_json={
            "goal_type": "interview_sprint",
            "preferred_language": "java",
            "target_timeline": "within_1_month",
            "weekly_days": 4,
        },
        generation_summary_md="面试高频训练计划",
        adjustment_summary_md="",
        validation_report_json={"valid": True},
        repair_log_json=[],
        created_at=now,
        activated_at=now,
    )
    db_session.add(version)
    await db_session.flush()
    stage = StudyPlanStage(
        version_id=version.id,
        stage_index=0,
        title="哈希表基础",
        objective_md="强化哈希表和边界条件",
        focus_tags_json=["hash-table", "array"],
        assessment_criteria_json=["能解释边界用例"],
        status="in_progress",
        created_at=now,
        updated_at=now,
    )
    db_session.add(stage)
    await db_session.flush()
    item = StudyPlanItem(
        version_id=version.id,
        stage_id=stage.id,
        problem_id=existing.id,
        problem_slug=existing.slug,
        skill_tags_json=["array", "hash-table"],
        difficulty=existing.difficulty,
        suggested_mode="independent",
        recommendation_reason="原计划题",
        status="in_progress",
        order_index=0,
        locked=False,
        created_at=now,
        updated_at=now,
    )
    snapshot = UserProfileSnapshot(
        user_id=user.id,
        version_number=1,
        source="summary_patch",
        confidence="medium",
        overall_level="advanced",
        preferred_training_mode="independent",
        ability_profile_json={},
        skill_profile_json={"weak_skill_tags": ["边界", "哈希表"]},
        stuck_point_profile_json={"weak_stuck_points": ["submission_wa"]},
        strategy_json={
            "hint_policy_hint": "下次先要求列边界用例。",
            "next_review_focus": "重点检查重复元素。",
        },
        recent_summary_md="最近 WA 与重复元素边界有关。",
        evidence_summary_json=[
            {"source": "session_summary", "summary": "two-sum WA 后 AC"}
        ],
        created_at=now,
    )
    summary = SessionSummary(
        session_id=1,
        user_id=user.id,
        problem_id=existing.id,
        result="completed",
        final_submission_result="ac",
        training_mode="independent",
        phases_visited_json=["review_code", "summarize"],
        transitions_json=[],
        main_stuck_points_json=["submission_wa"],
        error_types_json=["wa"],
        max_hint_level_used="key_hint",
        avg_hint_level=None,
        attempt_count=2,
        time_spent_seconds=None,
        complexity_analysis_json={},
        invariant_summary_md="哈希表状态维护不稳定。",
        review_summary_md="WA：重复元素失败。",
        profile_signals_json={"weak_skill_tags": ["边界"]},
        profile_update_suggestion_json={},
        next_recommendation_json={},
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([item, snapshot, summary])
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(plan)
    await db_session.refresh(version)
    return user, plan, version
```

- [ ] **Step 2: Write candidate pool failing test**

Append:

```python
@pytest.mark.asyncio
async def test_build_candidate_pool_excludes_existing_and_paid_only(
    db_session: AsyncSession,
) -> None:
    from backend.app.services.profile_plan_enrichment import build_enrichment_context

    user, plan, version = await create_user_plan(db_session)
    request = ProfilePlanEnrichmentRequest(
        user_intent_md="我想补哈希表边界，保持当前难度。",
        item_count=3,
        difficulty_preference="keep_current",
    )

    context = await build_enrichment_context(db_session, user, plan.id, request)

    slugs = [item["slug"] for item in context["candidate_problems"]]
    assert "contains-duplicate" in slugs
    assert "valid-anagram" in slugs
    assert "two-sum" not in slugs
    assert "premium-only" not in slugs
    assert context["current_plan"]["version_id"] == version.id
    assert context["profile_snapshot"]["recent_summary"] == "最近 WA 与重复元素边界有关。"
    assert context["user_request"]["user_intent_md"] == "我想补哈希表边界，保持当前难度。"
```

- [ ] **Step 3: Write validation failing test**

Append:

```python
def test_validate_model_output_rejects_slug_outside_candidate_pool() -> None:
    from backend.app.services.profile_plan_enrichment import validate_model_output

    output = {
        "enrichment_theme": "哈希表补强",
        "plan_gap_assessment": {
            "gap_level": "medium",
            "summary_md": "需要补边界。",
        },
        "overall_reason_md": "追加哈希表边界题。",
        "items": [
            {
                "problem_slug": "not-in-candidates",
                "target_stage_key": "stage-current",
                "weakness_targets": ["边界"],
                "difficulty": "Easy",
                "recommendation_reason_md": "练习边界。",
                "first_question_hint": "先列边界。",
                "review_focus": "检查重复元素。",
                "suggested_mode": "independent",
            }
        ],
        "not_added_reason_md": "",
    }
    context = {
        "user_request": {"item_count": 3, "difficulty_preference": "keep_current"},
        "current_plan": {
            "existing_problem_slugs": ["two-sum"],
            "current_stage": {"id": 10, "title": "哈希表基础"},
        },
        "candidate_problems": [
            {
                "problem_id": 2,
                "slug": "contains-duplicate",
                "title": "Contains Duplicate",
                "translated_title": "存在重复元素",
                "difficulty": "Easy",
                "tags": ["array", "hash-table"],
                "is_paid_only": False,
                "match_reasons": ["边界"],
            }
        ],
    }

    report, items = validate_model_output(output, context)

    assert report["valid"] is False
    assert "candidate_slug_not_allowed:not-in-candidates" in report["issues"]
    assert items == []
```

- [ ] **Step 4: Run service tests to verify failure**

Run:

```bash
uv run pytest backend/tests/test_profile_plan_enrichment_service.py -q
```

Expected: FAIL because `profile_plan_enrichment` service does not exist.

- [ ] **Step 5: Implement context and validation service**

Create `backend/app/services/profile_plan_enrichment.py` with these public functions and constants:

```python
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.auth import AppUser
from backend.app.models.learning import (
    PlanChangeLog,
    ProfilePlanEnrichmentDraft,
    StudyPlan,
    StudyPlanItem,
    StudyPlanStage,
    StudyPlanVersion,
)
from backend.app.models.practice import SessionSummary, UserProfileSnapshot
from backend.app.models.problem import Problem
from backend.app.schemas.learning import (
    ProfilePlanEnrichmentDraftResponse,
    ProfilePlanEnrichmentItem,
    ProfilePlanEnrichmentRequest,
)
from backend.app.services.profile_service import latest_profile_snapshot, snapshot_payload
from backend.app.services.study_plan_service import StudyPlanError, study_plan_payload


logger = logging.getLogger(__name__)

MAX_CANDIDATES = 60
MAX_RECENT_SUMMARIES = 5
MAX_REPAIR_ATTEMPTS = 2
ENRICHMENT_REASON_PREFIX = "画像补强："
DIFFICULTY_RANK = {"Easy": 1, "Medium": 2, "Hard": 3}
```

Add `build_enrichment_context`:

```python
async def build_enrichment_context(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
    payload: ProfilePlanEnrichmentRequest,
) -> dict[str, Any]:
    plan, version = await _load_active_plan_version(db, user, plan_id)
    profile_snapshot = await latest_profile_snapshot(db, user.id)
    recent_summaries = await _recent_session_summaries(db, user.id)
    current_stage = _current_stage(version)
    existing_slugs = {item.problem_slug for item in version.items}
    candidates = await _candidate_problems(
        db,
        existing_slugs=existing_slugs,
        current_stage=current_stage,
        profile_snapshot=profile_snapshot,
        payload=payload,
    )
    return {
        "task": "profile_plan_enrichment",
        "user_request": payload.model_dump(),
        "goal_context": {
            "target_snapshot": version.target_snapshot_json,
            "preferred_language": str(version.target_snapshot_json.get("preferred_language") or ""),
            "timeline": str(version.target_snapshot_json.get("target_timeline") or ""),
            "weekly_commitment": str(version.target_snapshot_json.get("weekly_days") or ""),
        },
        "profile_snapshot": _profile_context(profile_snapshot),
        "training_facts": _training_facts(recent_summaries),
        "current_plan": _plan_context(plan, version, current_stage, existing_slugs),
        "candidate_problems": candidates,
        "output_contract": {
            "format": "json",
            "item_count_max": payload.item_count,
            "must_choose_from_candidate_problems": True,
            "insert_position": "current_stage_tail",
        },
    }
```

Add `validate_model_output`:

```python
def validate_model_output(
    output: dict[str, Any],
    context: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[str] = []
    normalized_items: list[dict[str, Any]] = []
    candidates = {
        str(item["slug"]): item
        for item in context.get("candidate_problems", [])
        if isinstance(item, dict) and item.get("slug")
    }
    existing = set(context.get("current_plan", {}).get("existing_problem_slugs", []))
    max_count = int(context.get("user_request", {}).get("item_count") or 3)
    raw_items = output.get("items")
    if not isinstance(raw_items, list):
        issues.append("items_not_list")
        raw_items = []
    if len(raw_items) > max_count:
        issues.append("item_count_exceeded")
    seen: set[str] = set()
    for raw_item in raw_items[:max_count]:
        if not isinstance(raw_item, dict):
            issues.append("item_not_object")
            continue
        slug = str(raw_item.get("problem_slug") or "")
        candidate = candidates.get(slug)
        if candidate is None:
            issues.append(f"candidate_slug_not_allowed:{slug}")
            continue
        if slug in existing:
            issues.append(f"existing_slug_recommended:{slug}")
            continue
        if slug in seen:
            issues.append(f"duplicate_slug:{slug}")
            continue
        seen.add(slug)
        reason = str(raw_item.get("recommendation_reason_md") or "").strip()
        first_question = str(raw_item.get("first_question_hint") or "").strip()
        review_focus = str(raw_item.get("review_focus") or "").strip()
        if not reason:
            issues.append(f"missing_reason:{slug}")
        if not first_question:
            issues.append(f"missing_first_question:{slug}")
        if not review_focus:
            issues.append(f"missing_review_focus:{slug}")
        normalized_items.append(
            {
                "problem_id": int(candidate["problem_id"]),
                "problem_slug": slug,
                "title": str(candidate.get("title") or ""),
                "translated_title": str(candidate.get("translated_title") or ""),
                "difficulty": str(candidate.get("difficulty") or raw_item.get("difficulty") or ""),
                "skill_tags": list(candidate.get("tags") or []),
                "target_stage_id": int(context["current_plan"]["current_stage"]["id"]),
                "target_stage_title": str(context["current_plan"]["current_stage"]["title"]),
                "weakness_targets": _string_list(raw_item.get("weakness_targets")),
                "recommendation_reason_md": reason,
                "first_question_hint": first_question,
                "review_focus": review_focus,
                "suggested_mode": _suggested_mode(raw_item.get("suggested_mode")),
            }
        )
    valid = not issues
    return {
        "valid": valid,
        "issues": issues,
        "candidate_count": len(candidates),
        "item_count": len(normalized_items) if valid else 0,
    }, normalized_items if valid else []
```

Add helper functions in the same file:

```python
async def _load_active_plan_version(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
) -> tuple[StudyPlan, StudyPlanVersion]:
    result = await db.execute(
        select(StudyPlan, StudyPlanVersion)
        .join(
            StudyPlanVersion,
            (StudyPlanVersion.plan_id == StudyPlan.id)
            & (StudyPlanVersion.version_number == StudyPlan.active_version_number),
        )
        .where(
            StudyPlan.id == plan_id,
            StudyPlan.user_id == user.id,
            StudyPlan.status == "active",
            StudyPlanVersion.status == "active",
        )
    )
    row = result.one_or_none()
    if row is None:
        raise StudyPlanError("active_study_plan_not_found")
    plan, version = row
    await db.refresh(version, attribute_names=["stages", "items"])
    for stage in version.stages:
        await db.refresh(stage, attribute_names=["items"])
    for item in version.items:
        await db.refresh(item, attribute_names=["problem"])
    return plan, version


def _current_stage(version: StudyPlanVersion) -> StudyPlanStage:
    sorted_stages = sorted(version.stages, key=lambda stage: stage.stage_index)
    for status in ("in_progress", "completed"):
        for stage in sorted_stages:
            if any(item.status == status for item in stage.items):
                return stage
    for stage in sorted_stages:
        if any(item.status in {"pending", "in_progress"} for item in stage.items):
            return stage
    if not sorted_stages:
        raise StudyPlanError("study_plan_stage_not_found")
    return sorted_stages[0]


async def _recent_session_summaries(
    db: AsyncSession,
    user_id: int,
) -> list[SessionSummary]:
    result = await db.execute(
        select(SessionSummary)
        .where(SessionSummary.user_id == user_id)
        .order_by(SessionSummary.updated_at.desc(), SessionSummary.id.desc())
        .limit(MAX_RECENT_SUMMARIES)
    )
    return list(result.scalars().all())


def _profile_context(snapshot: UserProfileSnapshot | None) -> dict[str, Any]:
    if snapshot is None:
        return {
            "id": None,
            "version": "",
            "confidence": "low",
            "overall_level": "unknown",
            "weak_stuck_points": [],
            "weak_skill_tags": [],
            "recent_summary": "",
            "coach_strategy": {},
        }
    payload = snapshot_payload(snapshot)
    return {
        "id": payload.id,
        "version": payload.version,
        "confidence": payload.confidence,
        "overall_level": payload.overall_level,
        "weak_stuck_points": payload.weak_stuck_points,
        "weak_skill_tags": payload.weak_skill_tags,
        "recent_summary": payload.recent_summary,
        "coach_strategy": payload.coach_strategy,
    }


def _training_facts(summaries: list[SessionSummary]) -> dict[str, Any]:
    common_stuck: dict[str, int] = {}
    for summary in summaries:
        for point in summary.main_stuck_points_json:
            if isinstance(point, str) and point:
                common_stuck[point] = common_stuck.get(point, 0) + 1
    return {
        "completed_problem_count": sum(
            1 for summary in summaries if summary.final_submission_result == "ac"
        ),
        "common_stuck_points": [
            {"stuck_point": key, "count": value}
            for key, value in sorted(common_stuck.items(), key=lambda item: (-item[1], item[0]))
        ],
        "recent_summaries": [
            {
                "problem_id": summary.problem_id,
                "result": summary.final_submission_result,
                "main_stuck_points": summary.main_stuck_points_json,
                "error_types": summary.error_types_json,
                "max_hint_level_used": summary.max_hint_level_used,
                "review_summary_md": (summary.review_summary_md or "")[:600],
            }
            for summary in summaries
        ],
    }


def _plan_context(
    plan: StudyPlan,
    version: StudyPlanVersion,
    current_stage: StudyPlanStage,
    existing_slugs: set[str],
) -> dict[str, Any]:
    return {
        "plan_id": plan.id,
        "version_id": version.id,
        "title": plan.title,
        "current_stage": {
            "id": current_stage.id,
            "stage_index": current_stage.stage_index,
            "title": current_stage.title,
            "focus_tags": current_stage.focus_tags_json,
        },
        "stages": [
            {
                "id": stage.id,
                "stage_index": stage.stage_index,
                "title": stage.title,
                "focus_tags": stage.focus_tags_json,
                "items": [
                    {
                        "problem_slug": item.problem_slug,
                        "status": item.status,
                        "difficulty": item.difficulty,
                        "skill_tags": item.skill_tags_json,
                    }
                    for item in sorted(stage.items, key=lambda item: item.order_index)
                ],
            }
            for stage in sorted(version.stages, key=lambda stage: stage.stage_index)
        ],
        "existing_problem_slugs": sorted(existing_slugs),
    }


async def _candidate_problems(
    db: AsyncSession,
    *,
    existing_slugs: set[str],
    current_stage: StudyPlanStage,
    profile_snapshot: UserProfileSnapshot | None,
    payload: ProfilePlanEnrichmentRequest,
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(Problem)
        .where(Problem.is_paid_only.is_(False), Problem.slug.not_in(existing_slugs))
        .order_by(Problem.id.asc())
        .limit(MAX_CANDIDATES * 3)
    )
    problems = list(result.scalars().all())
    weak_terms = _weak_terms(profile_snapshot, current_stage, payload)
    ranked = sorted(
        problems,
        key=lambda problem: (
            -_candidate_score(problem, weak_terms=weak_terms),
            DIFFICULTY_RANK.get(problem.difficulty, 9),
            problem.id,
        ),
    )
    return [_candidate_payload(problem, weak_terms=weak_terms) for problem in ranked[:MAX_CANDIDATES]]


def _candidate_payload(problem: Problem, *, weak_terms: set[str]) -> dict[str, Any]:
    tags = _problem_tags(problem)
    return {
        "problem_id": problem.id,
        "slug": problem.slug,
        "title": problem.title,
        "translated_title": problem.translated_title,
        "difficulty": problem.difficulty,
        "tags": tags,
        "is_paid_only": problem.is_paid_only,
        "match_reasons": [
            term for term in sorted(weak_terms) if term and any(term in tag for tag in tags)
        ][:5],
    }


def _problem_tags(problem: Problem) -> list[str]:
    topic_tags = problem.metadata_json.get("topic_tags") if isinstance(problem.metadata_json, dict) else []
    tags: list[str] = []
    if isinstance(topic_tags, list):
        for item in topic_tags:
            if isinstance(item, dict) and isinstance(item.get("slug"), str):
                tags.append(item["slug"])
    return tags


def _weak_terms(
    snapshot: UserProfileSnapshot | None,
    current_stage: StudyPlanStage,
    payload: ProfilePlanEnrichmentRequest,
) -> set[str]:
    terms = set(current_stage.focus_tags_json)
    terms.update(payload.user_intent_md.lower().split())
    if snapshot is not None:
        for value in snapshot.skill_profile_json.get("weak_skill_tags", []):
            if isinstance(value, str):
                terms.add(value.lower())
        for value in snapshot.stuck_point_profile_json.get("weak_stuck_points", []):
            if isinstance(value, str):
                terms.add(value.lower())
    return {term for term in terms if term}


def _candidate_score(problem: Problem, *, weak_terms: set[str]) -> int:
    searchable = {problem.slug.lower(), problem.title.lower(), problem.translated_title.lower()}
    searchable.update(_problem_tags(problem))
    return sum(1 for term in weak_terms if any(term in value for value in searchable))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _suggested_mode(value: Any) -> str:
    return value if value in {"guided", "independent", "mock_interview"} else "independent"
```

- [ ] **Step 6: Run service tests**

Run:

```bash
uv run pytest backend/tests/test_profile_plan_enrichment_service.py::test_build_candidate_pool_excludes_existing_and_paid_only backend/tests/test_profile_plan_enrichment_service.py::test_validate_model_output_rejects_slug_outside_candidate_pool -q
```

Expected: PASS.

- [ ] **Step 7: Commit context and validation service**

Run:

```bash
git add backend/app/services/profile_plan_enrichment.py backend/tests/test_profile_plan_enrichment_service.py
git commit -m "feat: build profile enrichment context"
```

Expected: commit succeeds.

## Task 3: LLM Flow, Prompt, Registry, and Draft Persistence

**Files:**
- Create: `backend/app/services/learning_flows/profile_plan_enrichment.py`
- Create: `backend/app/prompts/resources/profile_plan_enrichment.v1.md`
- Modify: `backend/app/prompts/registry.py`
- Modify: `backend/app/services/llm_run_registry.py`
- Modify: `backend/app/services/llm_orchestrator.py`
- Modify: `backend/app/services/profile_plan_enrichment.py`
- Create: `backend/tests/test_profile_plan_enrichment_flow.py`
- Modify: `backend/tests/test_llm_runs_api.py`

- [ ] **Step 1: Write registry tests**

Add to `backend/tests/test_llm_runs_api.py`:

```python
def test_profile_plan_enrichment_run_uses_registry_related_mapping(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_create(
        session: Any,
        user: AppUser,
        *,
        kind: str,
        payload: dict[str, Any] | None = None,
        related_type: str = "",
        related_id: int | None = None,
    ):
        captured["kind"] = kind
        captured["payload"] = payload
        captured["related_type"] = related_type
        captured["related_id"] = related_id
        return type("Run", (), {"id": 12, "kind": kind, "status": "pending", "stage": "queued"})()

    monkeypatch.setattr("backend.app.api.llm_runs.create_llm_run", fake_create)
    app.dependency_overrides[current_user_dependency] = fake_user
    try:
        client = TestClient(app)
        response = client.post(
            "/api/llm-runs",
            json={
                "kind": "profile_plan_enrichment",
                "payload": {
                    "plan_id": 9,
                    "user_intent_md": "补边界",
                    "item_count": 3,
                    "difficulty_preference": "keep_current",
                },
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured["related_type"] == "study_plan"
    assert captured["related_id"] == 9
```

- [ ] **Step 2: Write flow test**

Create `backend/tests/test_profile_plan_enrichment_flow.py`:

```python
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from backend.app.models.llm_run import LlmRun
from backend.app.services.learning_flows.profile_plan_enrichment import (
    run_profile_plan_enrichment,
)
from backend.app.services.llm_providers.base import ProviderChunk
from backend.app.services.llm_run_events import LlmRunEvent
from backend.tests.test_profile_plan_enrichment_service import (
    create_user_plan,
    db_session,  # noqa: F401
)


class FakeProvider:
    def __init__(self, final_text: str) -> None:
        self.final_text = final_text
        self.input_text = ""
        self.instructions = ""

    async def stream_text(self, *, model: str, instructions: str, input_text: str):
        self.instructions = instructions
        self.input_text = input_text
        yield ProviderChunk(final_text=self.final_text)


@pytest.mark.asyncio
async def test_profile_plan_enrichment_handler_persists_generated_draft(
    db_session: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, plan, _version = await create_user_plan(db_session)
    run = LlmRun(
        id=99,
        user_id=user.id,
        kind="profile_plan_enrichment",
        input_json={
            "plan_id": plan.id,
            "user_intent_md": "补哈希表边界",
            "item_count": 2,
            "difficulty_preference": "keep_current",
        },
        related_type="study_plan",
        related_id=plan.id,
        status="running",
        stage="selecting_credential",
        display_text_md="",
        result_json={},
        error_code="",
        error_message="",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    output = {
        "enrichment_theme": "哈希表边界补强",
        "plan_gap_assessment": {
            "gap_level": "medium",
            "summary_md": "当前计划需要连续边界训练。",
        },
        "overall_reason_md": "追加两道哈希表边界题。",
        "items": [
            {
                "problem_slug": "contains-duplicate",
                "target_stage_key": "stage-current",
                "weakness_targets": ["边界"],
                "difficulty": "Easy",
                "recommendation_reason_md": "练习重复元素。",
                "first_question_hint": "先列重复元素用例。",
                "review_focus": "检查 set 更新顺序。",
                "suggested_mode": "independent",
            }
        ],
        "not_added_reason_md": "",
    }
    provider = FakeProvider(json.dumps(output, ensure_ascii=False))
    events: list[LlmRunEvent] = []

    result = await run_profile_plan_enrichment(
        db_session,
        user_id=user.id,
        run=run,
        provider=provider,
        model_name="gpt-test",
        publish=lambda event: events.append(event),
    )

    assert result["status"] == "generated"
    assert result["items"][0]["problem_slug"] == "contains-duplicate"
    assert "candidate_problems" in provider.input_text
    assert any(event.event == "progress" for event in events)
```

The explicit import of `db_session` makes the fixture available in this module while keeping one source of truth for the test database setup.

- [ ] **Step 3: Run flow/registry tests to verify failure**

Run:

```bash
uv run pytest backend/tests/test_profile_plan_enrichment_flow.py backend/tests/test_llm_runs_api.py::test_profile_plan_enrichment_run_uses_registry_related_mapping -q
```

Expected: FAIL because flow, prompt, and registry entry do not exist.

- [ ] **Step 4: Add prompt resource**

Create `backend/app/prompts/resources/profile_plan_enrichment.v1.md`:

```markdown
你是 Agentic Coding Learning Coach 的学习计划补强规划器。

你必须只输出一个 JSON 对象，不要输出 Markdown、解释文本或代码块。

任务：根据用户本次意愿、当前学习计划、最新用户画像、最近复盘摘要和候选题池，为当前 active 学习计划生成补强题预览。

优先级从高到低：

1. 硬约束：
- 只能从 input.candidate_problems 中选择题目。
- 不推荐 current_plan.existing_problem_slugs 中已存在的题目。
- 不推荐 paid only 题目。
- 不修改、删除或移动已有题。
- items 数量不能超过 user_request.item_count。
- 用户确认前不会写入正式计划。

2. 用户意愿：
- 尊重 user_request.user_intent_md。
- 尊重 user_request.item_count。
- 尊重 user_request.difficulty_preference。

3. 学习目标和画像：
- 结合 goal_context、profile_snapshot、training_facts 和 recent_summaries。
- 不要编造没有证据的长期弱点。

4. 计划结构：
- 优先补当前阶段相关主题。
- 保持难度递进。

输出 JSON schema：
{
  "enrichment_theme": "短标题",
  "plan_gap_assessment": {
    "gap_level": "low | medium | high | insufficient_evidence",
    "summary_md": "计划差距说明"
  },
  "overall_reason_md": "整体加题理由",
  "items": [
    {
      "problem_slug": "候选题 slug",
      "target_stage_key": "stage-current",
      "weakness_targets": ["薄弱点"],
      "difficulty": "Easy | Medium | Hard",
      "recommendation_reason_md": "为什么加这题",
      "first_question_hint": "进入工作台时第一问建议",
      "review_focus": "代码 review 重点",
      "suggested_mode": "guided | independent | mock_interview"
    }
  ],
  "not_added_reason_md": "如果不建议加题，说明原因"
}
```

- [ ] **Step 5: Register prompt and run kind**

In `backend/app/prompts/registry.py`, add:

```python
"profile_plan_enrichment": _PromptDefinition(
    version="profile-plan-enrichment-v1",
    resource_name="profile_plan_enrichment.v1.md",
    output_fields=(
        "enrichment_theme",
        "plan_gap_assessment",
        "overall_reason_md",
        "items",
        "not_added_reason_md",
    ),
),
```

In `backend/app/services/llm_run_registry.py`, import the handler:

```python
from backend.app.services.learning_flows.profile_plan_enrichment import (
    ProfilePlanEnrichmentHandler,
)
```

Add to `RUN_KIND_SPECS`:

```python
"profile_plan_enrichment": RunKindSpec(
    handler=ProfilePlanEnrichmentHandler(),
    related_type="study_plan",
    related_id_key="plan_id",
    requires_model=True,
),
```

In `backend/app/services/llm_orchestrator.py`, extend `ERROR_MESSAGES`:

```python
"profile_plan_enrichment_invalid": "补强题生成结果未通过校验",
"profile_plan_enrichment_not_found": "补强题草稿不存在或无权访问",
"profile_plan_enrichment_not_confirmable": "补强题草稿当前不能确认",
"active_study_plan_not_found": "当前学习计划不存在",
```

- [ ] **Step 6: Add draft persistence and response helpers**

Append to `backend/app/services/profile_plan_enrichment.py`:

```python
async def persist_generated_draft(
    db: AsyncSession,
    *,
    user: AppUser,
    plan_id: int,
    version_id: int,
    profile_snapshot_id: int | None,
    llm_run_id: int,
    payload: ProfilePlanEnrichmentRequest,
    context: dict[str, Any],
    model_output: dict[str, Any],
    validation_report: dict[str, Any],
    normalized_items: list[dict[str, Any]],
) -> ProfilePlanEnrichmentDraft:
    now = datetime.now(UTC)
    draft = ProfilePlanEnrichmentDraft(
        user_id=user.id,
        study_plan_id=plan_id,
        study_plan_version_id=version_id,
        profile_snapshot_id=profile_snapshot_id,
        llm_run_id=llm_run_id,
        status="generated" if validation_report.get("valid") else "failed",
        user_intent_md=payload.user_intent_md,
        item_count=payload.item_count,
        difficulty_preference=payload.difficulty_preference,
        context_summary_json=_safe_context_summary(context),
        candidate_problem_ids_json=[
            int(item["problem_id"]) for item in context.get("candidate_problems", [])
        ],
        model_output_json={
            **model_output,
            "items": normalized_items,
        },
        validation_report_json=validation_report,
        confirmed_item_ids_json=[],
        error_summary=";".join(validation_report.get("issues", [])),
        created_at=now,
        updated_at=now,
        confirmed_at=None,
    )
    db.add(draft)
    await db.flush()
    logger.info(
        "profile_plan_enrichment_generated user_id=%s plan_id=%s draft_id=%s item_count=%s valid=%s",
        user.id,
        plan_id,
        draft.id,
        len(normalized_items),
        validation_report.get("valid"),
    )
    return draft


def _safe_context_summary(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_request": context.get("user_request", {}),
        "goal_context": context.get("goal_context", {}),
        "profile_snapshot": context.get("profile_snapshot", {}),
        "training_facts": context.get("training_facts", {}),
        "current_plan": context.get("current_plan", {}),
        "candidate_count": len(context.get("candidate_problems", [])),
    }


def draft_response(draft: ProfilePlanEnrichmentDraft) -> ProfilePlanEnrichmentDraftResponse:
    output = draft.model_output_json if isinstance(draft.model_output_json, dict) else {}
    gap = output.get("plan_gap_assessment")
    return ProfilePlanEnrichmentDraftResponse.model_validate(
        {
            "draft_id": draft.id,
            "status": draft.status,
            "plan_id": draft.study_plan_id,
            "plan_version_id": draft.study_plan_version_id,
            "profile_snapshot_id": draft.profile_snapshot_id,
            "user_intent_md": draft.user_intent_md,
            "item_count": draft.item_count,
            "difficulty_preference": draft.difficulty_preference,
            "enrichment_theme": str(output.get("enrichment_theme") or ""),
            "plan_gap_assessment": gap if isinstance(gap, dict) else None,
            "overall_reason_md": str(output.get("overall_reason_md") or ""),
            "not_added_reason_md": str(output.get("not_added_reason_md") or ""),
            "items": output.get("items") if isinstance(output.get("items"), list) else [],
            "validation_report": draft.validation_report_json,
            "created_at": draft.created_at,
            "updated_at": draft.updated_at,
            "confirmed_at": draft.confirmed_at,
        }
    )
```

- [ ] **Step 7: Implement LLM flow**

Create `backend/app/services/learning_flows/profile_plan_enrichment.py`:

```python
from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.auth import AppUser
from backend.app.models.llm_run import LlmRun
from backend.app.prompts import get_prompt
from backend.app.schemas.learning import ProfilePlanEnrichmentRequest
from backend.app.services.learning_flows.goal_plan import LearningFlowError
from backend.app.services.llm_providers.base import LlmProvider
from backend.app.services.llm_run_events import LlmRunEvent
from backend.app.services.profile_plan_enrichment import (
    build_enrichment_context,
    draft_response,
    persist_generated_draft,
    validate_model_output,
)


logger = logging.getLogger(__name__)
PROMPT = get_prompt("profile_plan_enrichment")


class ProfilePlanEnrichmentHandler:
    async def execute(self, context: Any) -> dict[str, Any]:
        return await run_profile_plan_enrichment(
            context.session,
            user_id=context.user_id,
            run=context.run,
            provider=context.provider,
            model_name=context.model_name,
            publish=context.publish,
        )


async def run_profile_plan_enrichment(
    session: AsyncSession,
    *,
    user_id: int,
    run: LlmRun,
    provider: LlmProvider,
    model_name: str,
    publish: Callable[[LlmRunEvent], Awaitable[None]],
) -> dict[str, Any]:
    payload = _payload(run)
    plan_id = payload.get("plan_id")
    if not isinstance(plan_id, int) or isinstance(plan_id, bool):
        raise LearningFlowError("active_study_plan_not_found")
    request = ProfilePlanEnrichmentRequest.model_validate(payload)
    user = await session.get(AppUser, user_id)
    if user is None:
        raise LearningFlowError("active_study_plan_not_found")
    await _progress(publish, run.id, "building_context", "正在整理画像、计划和训练事实")
    context = await build_enrichment_context(session, user, plan_id, request)
    await _progress(publish, run.id, "calling_model", "正在调用大模型生成补强题预览")
    model_output = await _model_output(provider, model_name=model_name, context=context)
    report, normalized_items = validate_model_output(model_output, context)
    if not report.get("valid"):
        await _progress(publish, run.id, "repairing_output", "正在修复补强题结构")
        model_output, report, normalized_items = await _repair_output(
            provider,
            model_name=model_name,
            context=context,
            model_output=model_output,
            report=report,
        )
    if not report.get("valid"):
        raise LearningFlowError("profile_plan_enrichment_invalid")
    await _progress(publish, run.id, "saving_draft", "正在保存补强题预览")
    draft = await persist_generated_draft(
        session,
        user=user,
        plan_id=plan_id,
        version_id=int(context["current_plan"]["version_id"]),
        profile_snapshot_id=context["profile_snapshot"].get("id"),
        llm_run_id=run.id,
        payload=request,
        context=context,
        model_output=model_output,
        validation_report=report,
        normalized_items=normalized_items,
    )
    run.display_text_md = str(model_output.get("overall_reason_md") or "")
    response = draft_response(draft).model_dump(mode="json")
    await session.flush()
    return response


def _payload(run: LlmRun) -> dict[str, Any]:
    if not isinstance(run.input_json, dict):
        raise LearningFlowError("profile_plan_enrichment_invalid")
    return run.input_json


async def _progress(
    publish: Callable[[LlmRunEvent], Awaitable[None]],
    run_id: int,
    stage: str,
    message: str,
) -> None:
    await publish(LlmRunEvent("progress", {"run_id": run_id, "stage": stage, "message": message}))


async def _model_output(
    provider: LlmProvider,
    *,
    model_name: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    raw_parts: list[str] = []
    final_text = ""
    async for chunk in provider.stream_text(
        model=model_name,
        instructions=PROMPT.instructions,
        input_text=json.dumps(context, ensure_ascii=False),
    ):
        if chunk.text_delta:
            raw_parts.append(chunk.text_delta)
        if chunk.final_text:
            final_text = chunk.final_text
    text = final_text or "".join(raw_parts)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LearningFlowError("profile_plan_enrichment_invalid") from exc
    if not isinstance(data, dict):
        raise LearningFlowError("profile_plan_enrichment_invalid")
    return data


async def _repair_output(
    provider: LlmProvider,
    *,
    model_name: str,
    context: dict[str, Any],
    model_output: dict[str, Any],
    report: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    repair_context = {
        "original_context": context,
        "invalid_output": model_output,
        "validation_report": report,
        "repair_instruction": "只修复 JSON，使题目来自 candidate_problems，并满足 validation_report。",
    }
    repaired = await _model_output(provider, model_name=model_name, context=repair_context)
    repaired_report, repaired_items = validate_model_output(repaired, context)
    return repaired, repaired_report, repaired_items
```

- [ ] **Step 8: Run flow/registry tests**

Run:

```bash
uv run pytest backend/tests/test_profile_plan_enrichment_flow.py backend/tests/test_llm_runs_api.py::test_profile_plan_enrichment_run_uses_registry_related_mapping -q
```

Expected: PASS.

- [ ] **Step 9: Commit LLM flow**

Run:

```bash
git add backend/app/services/learning_flows/profile_plan_enrichment.py backend/app/prompts/resources/profile_plan_enrichment.v1.md backend/app/prompts/registry.py backend/app/services/llm_run_registry.py backend/app/services/llm_orchestrator.py backend/app/services/profile_plan_enrichment.py backend/tests/test_profile_plan_enrichment_flow.py backend/tests/test_llm_runs_api.py
git commit -m "feat: generate profile-based plan enrichment drafts"
```

Expected: commit succeeds.

## Task 4: Draft Read and Confirm APIs

**Files:**
- Modify: `backend/app/api/learning.py`
- Modify: `backend/app/services/profile_plan_enrichment.py`
- Modify: `backend/tests/test_profile_plan_enrichment_service.py`
- Modify: `backend/tests/test_learning_api.py`

- [ ] **Step 1: Add confirm service tests**

Append to `backend/tests/test_profile_plan_enrichment_service.py`:

```python
@pytest.mark.asyncio
async def test_confirm_enrichment_draft_appends_items_to_current_stage(
    db_session: AsyncSession,
) -> None:
    from backend.app.services.profile_plan_enrichment import confirm_enrichment_draft

    user, plan, version = await create_user_plan(db_session)
    request = ProfilePlanEnrichmentRequest(
        user_intent_md="补哈希表边界",
        item_count=2,
        difficulty_preference="keep_current",
    )
    context = await build_enrichment_context(db_session, user, plan.id, request)
    output = {
        "enrichment_theme": "哈希表边界补强",
        "plan_gap_assessment": {"gap_level": "medium", "summary_md": "需要补强。"},
        "overall_reason_md": "追加边界题。",
        "items": [
            {
                "problem_slug": "contains-duplicate",
                "target_stage_key": "stage-current",
                "weakness_targets": ["边界"],
                "difficulty": "Easy",
                "recommendation_reason_md": "练习重复元素。",
                "first_question_hint": "先列重复元素。",
                "review_focus": "检查 set。",
                "suggested_mode": "independent",
            }
        ],
        "not_added_reason_md": "",
    }
    report, items = validate_model_output(output, context)
    draft = await persist_generated_draft(
        db_session,
        user=user,
        plan_id=plan.id,
        version_id=version.id,
        profile_snapshot_id=context["profile_snapshot"]["id"],
        llm_run_id=1,
        payload=request,
        context=context,
        model_output=output,
        validation_report=report,
        normalized_items=items,
    )
    await db_session.commit()

    response = await confirm_enrichment_draft(db_session, user, plan.id, draft.id)

    added = [
        item
        for stage in response["active_version"]["stages"]
        for item in stage["items"]
        if item["problem_slug"] == "contains-duplicate"
    ]
    assert len(added) == 1
    assert added[0]["recommendation_reason"].startswith("画像补强：")
    refreshed = await db_session.get(ProfilePlanEnrichmentDraft, draft.id)
    assert refreshed is not None
    assert refreshed.status == "confirmed"
    assert len(refreshed.confirmed_item_ids_json) == 1
```

- [ ] **Step 2: Run confirm test to verify failure**

Run:

```bash
uv run pytest backend/tests/test_profile_plan_enrichment_service.py::test_confirm_enrichment_draft_appends_items_to_current_stage -q
```

Expected: FAIL because `confirm_enrichment_draft` does not exist.

- [ ] **Step 3: Implement draft load and confirm**

Append to `backend/app/services/profile_plan_enrichment.py`:

```python
async def get_enrichment_draft_payload(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
    draft_id: int,
) -> ProfilePlanEnrichmentDraftResponse:
    draft = await _load_draft(db, user, plan_id, draft_id, for_update=False)
    return draft_response(draft)


async def confirm_enrichment_draft(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
    draft_id: int,
) -> dict[str, Any]:
    try:
        draft = await _load_draft(db, user, plan_id, draft_id, for_update=True)
        if draft.status == "confirmed":
            return await study_plan_payload(db, user, plan_id)
        if draft.status != "generated":
            raise StudyPlanError("profile_plan_enrichment_not_confirmable")
        plan, version = await _load_active_plan_version(db, user, plan_id)
        if version.id != draft.study_plan_version_id:
            raise StudyPlanError("profile_plan_enrichment_not_confirmable")
        output_items = draft.model_output_json.get("items")
        if not isinstance(output_items, list):
            raise StudyPlanError("profile_plan_enrichment_not_confirmable")
        current_stage = _current_stage(version)
        existing_slugs = {item.problem_slug for item in version.items}
        max_order = max([item.order_index for item in current_stage.items] or [-1])
        added_ids: list[int] = []
        now = datetime.now(UTC)
        for index, item_payload in enumerate(output_items, start=1):
            slug = str(item_payload.get("problem_slug") or "")
            if slug in existing_slugs:
                raise StudyPlanError("profile_plan_enrichment_not_confirmable")
            problem = await _problem_by_slug(db, slug)
            reason = ENRICHMENT_REASON_PREFIX + str(
                item_payload.get("recommendation_reason_md") or ""
            )
            item = StudyPlanItem(
                version_id=version.id,
                stage_id=current_stage.id,
                problem_id=problem.id,
                problem_slug=problem.slug,
                skill_tags_json=_merged_skill_tags(problem, item_payload),
                difficulty=problem.difficulty,
                suggested_mode=_suggested_mode(item_payload.get("suggested_mode")),
                recommendation_reason=reason,
                status="pending",
                order_index=max_order + index,
                locked=False,
                created_at=now,
                updated_at=now,
            )
            db.add(item)
            await db.flush()
            added_ids.append(item.id)
            _add_enrichment_change_log(db, version, item, draft)
            existing_slugs.add(slug)
        draft.status = "confirmed"
        draft.confirmed_item_ids_json = added_ids
        draft.confirmed_at = now
        draft.updated_at = now
        plan.updated_at = now
        await db.commit()
        logger.info(
            "profile_plan_enrichment_confirmed user_id=%s plan_id=%s draft_id=%s added_count=%s",
            user.id,
            plan.id,
            draft.id,
            len(added_ids),
        )
        return await study_plan_payload(db, user, plan.id)
    except StudyPlanError:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception(
            "profile_plan_enrichment_confirm_failed user_id=%s plan_id=%s draft_id=%s",
            user.id,
            plan_id,
            draft_id,
        )
        raise


async def _load_draft(
    db: AsyncSession,
    user: AppUser,
    plan_id: int,
    draft_id: int,
    *,
    for_update: bool,
) -> ProfilePlanEnrichmentDraft:
    query = select(ProfilePlanEnrichmentDraft).where(
        ProfilePlanEnrichmentDraft.id == draft_id,
        ProfilePlanEnrichmentDraft.user_id == user.id,
        ProfilePlanEnrichmentDraft.study_plan_id == plan_id,
    )
    if for_update:
        query = query.with_for_update()
    result = await db.execute(query)
    draft = result.scalar_one_or_none()
    if draft is None:
        raise StudyPlanError("profile_plan_enrichment_not_found")
    return draft


async def _problem_by_slug(db: AsyncSession, slug: str) -> Problem:
    result = await db.execute(
        select(Problem).where(Problem.slug == slug, Problem.is_paid_only.is_(False))
    )
    problem = result.scalar_one_or_none()
    if problem is None:
        raise StudyPlanError("profile_plan_enrichment_not_confirmable")
    return problem


def _merged_skill_tags(problem: Problem, item_payload: dict[str, Any]) -> list[str]:
    tags = _problem_tags(problem)
    for value in _string_list(item_payload.get("weakness_targets")):
        if value not in tags:
            tags.append(value)
    return tags[:12]


def _add_enrichment_change_log(
    db: AsyncSession,
    version: StudyPlanVersion,
    item: StudyPlanItem,
    draft: ProfilePlanEnrichmentDraft,
) -> None:
    db.add(
        PlanChangeLog(
            version_id=version.id,
            change_type="profile_enrichment_added",
            problem_id=item.problem_id,
            detail_json={
                "draft_id": draft.id,
                "problem_slug": item.problem_slug,
                "source": "profile_plan_enrichment",
            },
            reason_md=item.recommendation_reason,
        )
    )
```

- [ ] **Step 4: Add learning API route tests**

Append to `backend/tests/test_learning_api.py`:

```python
def test_profile_enrichment_draft_route_returns_payload(monkeypatch) -> None:
    async def fake_get(session, user, plan_id, draft_id):
        assert plan_id == 7
        assert draft_id == 3
        now = datetime.now(UTC)
        return {
            "draft_id": 3,
            "status": "generated",
            "plan_id": 7,
            "plan_version_id": 9,
            "profile_snapshot_id": 11,
            "user_intent_md": "补边界",
            "item_count": 3,
            "difficulty_preference": "keep_current",
            "enrichment_theme": "边界补强",
            "plan_gap_assessment": {"gap_level": "medium", "summary_md": "需要补强"},
            "overall_reason_md": "追加题目",
            "not_added_reason_md": "",
            "items": [],
            "validation_report": {"valid": True},
            "created_at": now,
            "updated_at": now,
            "confirmed_at": None,
        }

    monkeypatch.setattr(
        "backend.app.services.profile_plan_enrichment.get_enrichment_draft_payload",
        fake_get,
        raising=False,
    )
    app.dependency_overrides[current_user_dependency] = fake_user
    try:
        client = TestClient(app)
        response = client.get("/api/study-plans/7/profile-enrichments/3")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["enrichment_theme"] == "边界补强"
```

Add confirm route test:

```python
def test_profile_enrichment_confirm_route_returns_updated_plan(monkeypatch) -> None:
    async def fake_confirm(session, user, plan_id, draft_id):
        assert plan_id == 7
        assert draft_id == 3
        now = datetime.now(UTC)
        return {
            "id": 7,
            "title": "计划",
            "status": "active",
            "active_version_number": 1,
            "created_at": now,
            "updated_at": now,
            "active_version": {
                "id": 9,
                "version_number": 1,
                "status": "active",
                "target_snapshot": {},
                "generation_summary_md": "",
                "adjustment_summary_md": "",
                "validation_report": {},
                "repair_log": [],
                "stages": [],
                "created_at": now,
                "activated_at": now,
            },
        }

    monkeypatch.setattr(
        "backend.app.services.profile_plan_enrichment.confirm_enrichment_draft",
        fake_confirm,
        raising=False,
    )
    app.dependency_overrides[current_user_dependency] = fake_user
    try:
        client = TestClient(app)
        response = client.post("/api/study-plans/7/profile-enrichments/3/confirm")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["id"] == 7
```

- [ ] **Step 5: Add API routes**

In `backend/app/api/learning.py`, import schemas:

```python
from backend.app.schemas.learning import ProfilePlanEnrichmentDraftResponse
```

Add routes:

```python
@router.get(
    "/study-plans/{plan_id}/profile-enrichments/{draft_id}",
    response_model=ProfilePlanEnrichmentDraftResponse,
)
async def profile_enrichment_draft_route(
    plan_id: int,
    draft_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        from backend.app.services.profile_plan_enrichment import (
            get_enrichment_draft_payload,
        )

        response = await get_enrichment_draft_payload(session, user, plan_id, draft_id)
        return response.model_dump()
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/study-plans/{plan_id}/profile-enrichments/{draft_id}/confirm",
    response_model=StudyPlanResponse,
)
async def confirm_profile_enrichment_route(
    plan_id: int,
    draft_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        from backend.app.services.profile_plan_enrichment import (
            confirm_enrichment_draft,
        )

        return await confirm_enrichment_draft(session, user, plan_id, draft_id)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc
```

Update `_http_error`:

```python
if exc.detail in {
    "llm_credential_unavailable",
    "empty_problem_library",
    "profile_plan_enrichment_not_confirmable",
}:
    status = 409
```

- [ ] **Step 6: Run API and confirm tests**

Run:

```bash
uv run pytest backend/tests/test_profile_plan_enrichment_service.py::test_confirm_enrichment_draft_appends_items_to_current_stage backend/tests/test_learning_api.py::test_profile_enrichment_draft_route_returns_payload backend/tests/test_learning_api.py::test_profile_enrichment_confirm_route_returns_updated_plan -q
```

Expected: PASS.

- [ ] **Step 7: Commit API and confirm**

Run:

```bash
git add backend/app/api/learning.py backend/app/services/profile_plan_enrichment.py backend/tests/test_profile_plan_enrichment_service.py backend/tests/test_learning_api.py
git commit -m "feat: confirm profile enrichment plan items"
```

Expected: commit succeeds.

## Task 5: Frontend API and Drawer Component

**Files:**
- Modify: `frontend/src/api/learning.ts`
- Modify: `frontend/src/api/llmRuns.ts`
- Create: `frontend/src/pages/ProfilePlanEnrichmentDrawer.tsx`
- Create: `frontend/src/pages/ProfilePlanEnrichmentDrawer.test.tsx`

- [ ] **Step 1: Add frontend API types**

In `frontend/src/api/llmRuns.ts`, add to `LlmRunKind`:

```ts
| 'profile_plan_enrichment'
```

In `frontend/src/api/learning.ts`, append:

```ts
export type ProfilePlanEnrichmentDifficulty =
  | 'foundational'
  | 'keep_current'
  | 'stretch'

export type ProfilePlanEnrichmentPayload = {
  user_intent_md: string
  item_count: 2 | 3 | 5
  difficulty_preference: ProfilePlanEnrichmentDifficulty
}

export type ProfilePlanEnrichmentItem = {
  problem_id: number
  problem_slug: string
  title: string
  translated_title: string
  difficulty: string
  skill_tags: string[]
  target_stage_id: number
  target_stage_title: string
  weakness_targets: string[]
  recommendation_reason_md: string
  first_question_hint: string
  review_focus: string
  suggested_mode: string
}

export type ProfilePlanEnrichmentDraft = {
  draft_id: number
  status: string
  plan_id: number
  plan_version_id: number
  profile_snapshot_id: number | null
  user_intent_md: string
  item_count: number
  difficulty_preference: ProfilePlanEnrichmentDifficulty
  enrichment_theme: string
  plan_gap_assessment: {
    gap_level: string
    summary_md: string
  } | null
  overall_reason_md: string
  not_added_reason_md: string
  items: ProfilePlanEnrichmentItem[]
  validation_report: Record<string, unknown>
  created_at: string
  updated_at: string
  confirmed_at: string | null
}

export function getProfilePlanEnrichmentDraft(planId: number, draftId: number) {
  return requestJson<ProfilePlanEnrichmentDraft>(
    `/api/study-plans/${planId}/profile-enrichments/${draftId}`,
  )
}

export function confirmProfilePlanEnrichment(planId: number, draftId: number) {
  return requestJson<StudyPlan>(
    `/api/study-plans/${planId}/profile-enrichments/${draftId}/confirm`,
    { method: 'POST' },
  )
}
```

- [ ] **Step 2: Write drawer component tests**

Create `frontend/src/pages/ProfilePlanEnrichmentDrawer.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ProfilePlanEnrichmentDrawer } from './ProfilePlanEnrichmentDrawer'
import type { StudyPlan } from '../api/learning'

const fetchMock = vi.fn()
const drawerMocks = vi.hoisted(() => ({
  startRun: vi.fn(),
  cancelRun: vi.fn(),
  draft: {
    draft_id: 12,
    status: 'generated',
    plan_id: 7,
    plan_version_id: 9,
    profile_snapshot_id: 31,
    user_intent_md: '补哈希表边界',
    item_count: 3,
    difficulty_preference: 'keep_current',
    enrichment_theme: '哈希表边界补强',
    plan_gap_assessment: {
      gap_level: 'medium',
      summary_md: '需要连续边界训练。',
    },
    overall_reason_md: '建议追加哈希表边界题。',
    not_added_reason_md: '',
    items: [
      {
        problem_id: 2,
        problem_slug: 'contains-duplicate',
        title: 'Contains Duplicate',
        translated_title: '存在重复元素',
        difficulty: 'Easy',
        skill_tags: ['array', 'hash-table'],
        target_stage_id: 10,
        target_stage_title: '哈希表基础',
        weakness_targets: ['边界'],
        recommendation_reason_md: '练习重复元素边界。',
        first_question_hint: '先列重复元素用例。',
        review_focus: '检查 set 更新顺序。',
        suggested_mode: 'independent',
      },
    ],
    validation_report: { valid: true },
    created_at: '2026-05-26T00:00:00Z',
    updated_at: '2026-05-26T00:00:00Z',
    confirmed_at: null,
  },
}))

vi.mock('../hooks/useLlmRun', () => ({
  useLlmRun: (options: { onResult?: (result: unknown) => void } = {}) => {
    drawerMocks.startRun.mockImplementation(async () => {
      options.onResult?.(drawerMocks.draft)
      return { run_id: 88 }
    })
    return {
      isRunning: false,
      stage: '',
      displayText: '',
      result: null,
      error: null,
      startRun: drawerMocks.startRun,
      cancelRun: drawerMocks.cancelRun,
    }
  },
}))

function renderDrawer(plan: StudyPlan, onUpdated = vi.fn()) {
  const queryClient = new QueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <ProfilePlanEnrichmentDrawer
        open
        plan={plan}
        onClose={vi.fn()}
        onPlanUpdated={onUpdated}
      />
    </QueryClientProvider>,
  )
}

function stubPlan(): StudyPlan {
  return {
    id: 7,
    title: '面试冲刺计划',
    status: 'active',
    active_version_number: 1,
    active_version: {
      id: 9,
      version_number: 1,
      status: 'active',
      target_snapshot: { preferred_language: 'java' },
      generation_summary_md: '计划摘要',
      adjustment_summary_md: '',
      stages: [],
    },
  }
}

describe('ProfilePlanEnrichmentDrawer', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('shows profile summary and enrichment controls', () => {
    renderDrawer(stubPlan())

    expect(screen.getByText('画像与计划补强')).toBeInTheDocument()
    expect(screen.getByLabelText('这次你希望怎么补强？')).toBeInTheDocument()
    expect(screen.getByText('想增加几道题？')).toBeInTheDocument()
    expect(screen.getByText('难度倾向')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '生成补强题预览' })).toBeInTheDocument()
  })

  it('confirms a generated draft and returns updated plan', async () => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(stubPlan()), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const onUpdated = vi.fn()
    renderDrawer(stubPlan(), onUpdated)

    await userEvent.type(
      screen.getByLabelText('这次你希望怎么补强？'),
      '补哈希表边界',
    )
    await userEvent.click(screen.getByRole('button', { name: '生成补强题预览' }))
    expect(await screen.findByText('建议追加哈希表边界题。')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '确认加入当前计划' }))

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/study-plans/7/profile-enrichments/12/confirm',
      expect.objectContaining({ method: 'POST' }),
    )
    await waitFor(() => expect(onUpdated).toHaveBeenCalled())
  })
})
```

- [ ] **Step 3: Run drawer tests to verify failure**

Run:

```bash
cd frontend && corepack pnpm vitest run src/pages/ProfilePlanEnrichmentDrawer.test.tsx
```

Expected: FAIL because component does not exist.

- [ ] **Step 4: Implement drawer component**

Create `frontend/src/pages/ProfilePlanEnrichmentDrawer.tsx`:

```tsx
import { Alert, Button, Descriptions, Drawer, Form, Input, Radio, Space, Spin, Tag, Typography } from 'antd'
import { useState } from 'react'

import {
  confirmProfilePlanEnrichment,
  type ProfilePlanEnrichmentDraft,
  type ProfilePlanEnrichmentPayload,
  type StudyPlan,
} from '../api/learning'
import { useLlmRun } from '../hooks/useLlmRun'

type Props = {
  open: boolean
  plan: StudyPlan
  onClose: () => void
  onPlanUpdated: (plan: StudyPlan) => void
}

const countOptions = [
  { label: '2 道', value: 2 },
  { label: '3 道', value: 3 },
  { label: '5 道', value: 5 },
]

const difficultyOptions = [
  { label: '降低难度打基础', value: 'foundational' },
  { label: '保持当前难度', value: 'keep_current' },
  { label: '稍微加难', value: 'stretch' },
]

export function ProfilePlanEnrichmentDrawer({
  open,
  plan,
  onClose,
  onPlanUpdated,
}: Props) {
  const [form] = Form.useForm<ProfilePlanEnrichmentPayload>()
  const [draft, setDraft] = useState<ProfilePlanEnrichmentDraft | null>(null)
  const [isConfirming, setIsConfirming] = useState(false)
  const llmRun = useLlmRun({
    onResult: (result) => {
      const parsed = result as ProfilePlanEnrichmentDraft
      setDraft(parsed)
    },
  })
  const targetSnapshot = plan.active_version.target_snapshot
  const profileSummary = String(targetSnapshot.recent_profile_summary ?? '')

  async function handleGenerate(values: ProfilePlanEnrichmentPayload) {
    setDraft(null)
    await llmRun.startRun('profile_plan_enrichment', {
      plan_id: plan.id,
      user_intent_md: values.user_intent_md,
      item_count: values.item_count,
      difficulty_preference: values.difficulty_preference,
    })
  }

  async function handleConfirm() {
    if (!draft) {
      return
    }
    setIsConfirming(true)
    try {
      const updated = await confirmProfilePlanEnrichment(plan.id, draft.draft_id)
      onPlanUpdated(updated)
    } finally {
      setIsConfirming(false)
    }
  }

  return (
    <Drawer
      title="画像与计划补强"
      open={open}
      onClose={onClose}
      width={720}
      destroyOnClose
    >
      <Space direction="vertical" size="large" className="profile-enrichment-drawer">
        <Alert
          showIcon
          type="info"
          message="这是重量级操作"
          description="系统会调用大模型分析你的当前画像、训练记录和学习计划。生成结果会先进入预览，不会直接修改当前计划。"
        />

        <section>
          <Typography.Title level={4}>当前画像</Typography.Title>
          <Descriptions
            bordered
            size="small"
            column={1}
            items={[
              {
                key: 'language',
                label: '默认语言',
                children: String(targetSnapshot.preferred_language ?? '-'),
              },
              {
                key: 'summary',
                label: '老师式说明',
                children: profileSummary || '当前训练证据还不够，建议先完成 1-2 道计划题后再生成补强题。',
              },
            ]}
          />
        </section>

        <Form
          form={form}
          layout="vertical"
          initialValues={{
            user_intent_md: '',
            item_count: 3,
            difficulty_preference: 'keep_current',
          }}
          onFinish={handleGenerate}
        >
          <Form.Item label="这次你希望怎么补强？" name="user_intent_md">
            <Input.TextArea
              rows={4}
              maxLength={2000}
              placeholder="例如：我下周面试，希望多加面试高频 Medium，不要再加太偏 DP 的题。"
            />
          </Form.Item>
          <Form.Item label="想增加几道题？" name="item_count">
            <Radio.Group options={countOptions} optionType="button" />
          </Form.Item>
          <Form.Item label="难度倾向" name="difficulty_preference">
            <Radio.Group options={difficultyOptions} optionType="button" />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={llmRun.isRunning}>
              生成补强题预览
            </Button>
            {llmRun.isRunning ? <Button onClick={() => void llmRun.cancelRun()}>取消</Button> : null}
          </Space>
        </Form>

        {llmRun.isRunning ? (
          <Alert showIcon type="info" message={llmRun.stage || '正在生成补强题预览'} />
        ) : null}
        {llmRun.error ? <Alert showIcon type="error" message={llmRun.error.message} /> : null}
        {draft ? (
          <section>
            <Typography.Title level={4}>补强题预览</Typography.Title>
            <Typography.Paragraph>{draft.overall_reason_md}</Typography.Paragraph>
            <Space direction="vertical" className="profile-enrichment-preview">
              {draft.items.map((item) => (
                <div className="plan-item-row" key={item.problem_slug}>
                  <div>
                    <Typography.Text strong>{item.translated_title || item.title}</Typography.Text>
                    <div className="plan-item-reason">{item.recommendation_reason_md}</div>
                    <Typography.Text type="secondary">{item.first_question_hint}</Typography.Text>
                  </div>
                  <Space wrap>
                    <Tag>{item.difficulty}</Tag>
                    {item.weakness_targets.map((target) => (
                      <Tag key={target}>{target}</Tag>
                    ))}
                  </Space>
                </div>
              ))}
            </Space>
            <Button
              type="primary"
              onClick={handleConfirm}
              loading={isConfirming}
              disabled={draft.items.length === 0}
            >
              确认加入当前计划
            </Button>
          </section>
        ) : null}
        {llmRun.isRunning ? <Spin /> : null}
      </Space>
    </Drawer>
  )
}
```

Run the focused frontend test after implementation; if formatting changes are required, apply the formatter already used by the project before committing.

- [ ] **Step 5: Run drawer tests**

Run:

```bash
cd frontend && corepack pnpm vitest run src/pages/ProfilePlanEnrichmentDrawer.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit frontend component**

Run:

```bash
git add frontend/src/api/learning.ts frontend/src/api/llmRuns.ts frontend/src/pages/ProfilePlanEnrichmentDrawer.tsx frontend/src/pages/ProfilePlanEnrichmentDrawer.test.tsx
git commit -m "feat: add profile enrichment drawer"
```

Expected: commit succeeds.

## Task 6: Wire Study Plan Page

**Files:**
- Modify: `frontend/src/pages/StudyPlanPage.tsx`
- Modify: `frontend/src/pages/StudyPlanPage.test.tsx`

- [ ] **Step 1: Write StudyPlanPage test**

Add to `frontend/src/pages/StudyPlanPage.test.tsx`:

```tsx
import userEvent from '@testing-library/user-event'

it('opens profile enrichment drawer from the study plan heading', async () => {
  renderPage()

  expect(await screen.findByText('3 个月 Java 面试冲刺计划')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: '查看画像与补强' }))

  expect(screen.getByText('画像与计划补强')).toBeInTheDocument()
  expect(screen.getByLabelText('这次你希望怎么补强？')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd frontend && corepack pnpm vitest run src/pages/StudyPlanPage.test.tsx
```

Expected: FAIL because button and drawer are not wired.

- [ ] **Step 3: Wire component**

In `frontend/src/pages/StudyPlanPage.tsx`, import state and drawer:

```tsx
import { useState } from 'react'
import { ProfilePlanEnrichmentDrawer } from './ProfilePlanEnrichmentDrawer'
```

Inside `StudyPlanPage`, add:

```tsx
const [enrichmentOpen, setEnrichmentOpen] = useState(false)
```

Add button in heading `Space` before `计划历史`:

```tsx
<Button onClick={() => setEnrichmentOpen(true)}>查看画像与补强</Button>
```

Render drawer near the end of the successful return:

```tsx
<ProfilePlanEnrichmentDrawer
  open={enrichmentOpen}
  plan={data}
  onClose={() => setEnrichmentOpen(false)}
  onPlanUpdated={(updatedPlan) => {
    queryClient.setQueryData(studyPlanQueryKey, updatedPlan)
    void queryClient.invalidateQueries({ queryKey: studyPlanQueryKey })
  }}
/>
```

- [ ] **Step 4: Run page tests**

Run:

```bash
cd frontend && corepack pnpm vitest run src/pages/StudyPlanPage.test.tsx src/pages/ProfilePlanEnrichmentDrawer.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit page wiring**

Run:

```bash
git add frontend/src/pages/StudyPlanPage.tsx frontend/src/pages/StudyPlanPage.test.tsx
git commit -m "feat: surface profile enrichment on study plan"
```

Expected: commit succeeds.

## Task 7: Documentation Updates

**Files:**
- Modify: `docs/index.md`
- Modify: `docs/architecture/foundation.md`
- Modify: `docs/prd/prd.md`
- Modify: `docs/prd/ai-coach-user-profile-prd.md`
- Modify: `docs/project-todolist.md`

- [ ] **Step 1: Update docs/index.md**

Update `backend/app/models/` bullet to include profile plan enrichment draft:

```text
目标校准草稿、学习计划、计划版本、阶段、计划项、变更日志、画像补强计划草稿、训练会话、训练事件、代码快照、LeetCode 回填、教练回合、单题复盘、画像快照和画像增量。
```

Update `backend/app/services/` bullet to include:

```text
画像驱动计划补强生成与确认服务
```

- [ ] **Step 2: Update architecture foundation**

In API list, add:

```text
- `GET /api/study-plans/{plan_id}/profile-enrichments/{draft_id}`
- `POST /api/study-plans/{plan_id}/profile-enrichments/{draft_id}/confirm`
```

In service boundaries, add:

```text
- `backend.app.services.profile_plan_enrichment`：聚合用户意愿、画像、训练事实、当前计划和候选题池，调用大模型生成补强题 draft，并在用户确认后把补强题追加到当前 active 计划。
```

In LLM Run section, add:

```text
`profile_plan_enrichment` run 会选择用户模型资产，读取 active 学习计划、最新画像和最近复盘摘要，先由后端筛出候选题池，再让模型在候选池内生成补强题预览；后端校验通过后保存 draft，用户确认前不修改正式计划。
```

- [ ] **Step 3: Update PRD**

In `docs/prd/prd.md` 学习计划页 section, add:

```text
学习计划页提供“查看画像与补强”入口。用户可以查看当前画像摘要和老师式薄弱点说明，也可以输入本次补强意愿、题目数量和难度倾向，让系统调用大模型生成补强题预览。补强题只有在用户确认后才追加进当前计划。
```

- [ ] **Step 4: Update user profile PRD**

Add a subsection under 第一版边界:

```text
画像还服务学习计划补强：系统可以把最新画像、最近复盘、当前计划和用户本次意愿提供给大模型，让模型生成补强题预览。该能力不允许模型直接改写计划，必须由后端校验并由用户确认后写入正式计划。
```

- [ ] **Step 5: Update project todolist**

Add a new P1 item:

```text
### T11：画像驱动计划补强

| 字段 | 内容 |
| --- | --- |
| 优先级 | P1 |
| 状态 | 已完成 |
| 前置任务 | T7、T10 |
| 主要交付 | 学习计划页画像查看、用户意愿输入、LLM 补强题预览、确认后追加计划题 |
| 完成日期 | 2026-05-26 |

**验证命令**

- `uv run pytest backend/tests/test_profile_plan_enrichment_service.py backend/tests/test_profile_plan_enrichment_flow.py backend/tests/test_learning_api.py backend/tests/test_llm_runs_api.py -q`
- `cd frontend && corepack pnpm vitest run src/pages/ProfilePlanEnrichmentDrawer.test.tsx src/pages/StudyPlanPage.test.tsx`
- `cd frontend && corepack pnpm exec tsc -p tsconfig.app.json --noEmit --pretty false`
```

If implementation is still in progress when docs are updated, set 状态 to `进行中` and completion date to `未完成`.

- [ ] **Step 6: Commit docs**

Run:

```bash
git add docs/index.md docs/architecture/foundation.md docs/prd/prd.md docs/prd/ai-coach-user-profile-prd.md docs/project-todolist.md
git commit -m "docs: document profile plan enrichment"
```

Expected: commit succeeds.

## Task 8: Final Verification

**Files:**
- All files changed by Tasks 1-7.

- [ ] **Step 1: Run backend profile enrichment tests**

Run:

```bash
uv run pytest backend/tests/test_profile_plan_enrichment_service.py backend/tests/test_profile_plan_enrichment_flow.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run backend integration tests touched by registry/API**

Run:

```bash
uv run pytest backend/tests/test_learning_plan_service.py backend/tests/test_learning_api.py backend/tests/test_llm_runs_api.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run frontend focused tests**

Run:

```bash
cd frontend && corepack pnpm vitest run src/pages/ProfilePlanEnrichmentDrawer.test.tsx src/pages/StudyPlanPage.test.tsx
```

Expected: all tests pass.

- [ ] **Step 4: Run frontend type check**

Run:

```bash
cd frontend && corepack pnpm exec tsc -p tsconfig.app.json --noEmit --pretty false
```

Expected: exit code 0.

- [ ] **Step 5: Run lint/type checks for backend**

Run:

```bash
uv run ruff check backend/app backend/tests
uv run mypy backend
```

Expected: both commands exit code 0.

- [ ] **Step 6: Run eval smoke**

Run:

```bash
uv run python -m backend.app.evals.coach_eval_runner
```

Expected: Hint Leakage, Diagnosis, Code Review pass; RAG Grounding remains deferred.

- [ ] **Step 7: Final commit if verification required fixes**

If verification required additional fixes, commit them:

```bash
git add backend frontend docs
git commit -m "fix: stabilize profile plan enrichment"
```

Expected: commit succeeds only when there are verification fixes to commit.

## Self-Review Checklist

- Spec coverage:
  - 用户画像查看：Task 5, Task 6, Task 7.
  - 用户自由意愿 + 数量/难度：Task 1, Task 2, Task 5.
  - 大模型上下文：Task 2, Task 3.
  - 候选题池与后端校验：Task 2, Task 3.
  - 用户确认后追加原计划：Task 4.
  - 文档维护：Task 7.
  - 验证命令：Task 8.
- Type consistency:
  - Backend enum values: `foundational | keep_current | stretch`.
  - Frontend enum values match backend.
  - Run kind is `profile_plan_enrichment` in backend and frontend.
  - Draft ID field is `draft_id` in API and frontend.
- Scope control:
  - No automatic plan rewrite.
  - No deletion or reordering of existing items.
  - No RAG dependency.
  - No direct model write to formal plan before confirm.
