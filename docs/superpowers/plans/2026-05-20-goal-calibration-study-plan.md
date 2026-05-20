# Goal Calibration Study Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build T1 goal calibration and versioned study plan management from the approved PRD: structured calibration, LLM follow-up, validated plan drafts, one active plan per user, plan versions, current-stage tasks, and frontend pages.

**Architecture:** Backend owns all user-private learning state, LLM routing, draft validation, plan activation, and version cloning. Frontend is a typed React client that displays calibration, plan review, active plan, history, and version details through HTTP APIs only. T1 stores traceable plan/version/stage/item records and reserves training-history linkage through stable IDs; full practice-session implementation remains outside this plan.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic v2, OpenAI Responses API via the installed `openai` package, PostgreSQL/SQLite-compatible tests, React, TypeScript, Ant Design, TanStack Query, React Router, Vitest.

---

## Scope Check

This plan implements the T1 vertical slice:

- Structured goal calibration form.
- LLM follow-up questions capped at three.
- LLM-generated plan draft using the current user's LLM asset.
- Backend validation and repair loop against the local problem library.
- User confirmation that creates `StudyPlan` v1 and makes it the only active plan.
- Multiple study plans with active/paused/completed/archived statuses.
- Study plan versions with stages, current-stage detailed items, and change logs.
- User-triggered plan adjustment that clones a new draft version and preserves already-started items.
- Frontend routes for goal calibration, current plan, plan history, and version review.

The plan does not implement T2 practice sessions, code snapshots, code-runner multi-language execution, AI coach chat, RAG, profile updates, or real submission history tables. Where the PRD requires future traceability, this plan creates stable plan/version/item identifiers and enforces item preservation based on current plan-item status. T2 will attach `practice_session` and `submission_history` to these identifiers.

## File Structure

Backend files:

- Create `backend/app/models/learning.py`: SQLAlchemy models for calibration drafts, plans, versions, stages, items, and change logs.
- Modify `backend/app/models/__init__.py`: export learning models.
- Create `backend/app/db/migrations/versions/20260520_0005_goal_calibration_study_plan.py`: Alembic migration for learning tables.
- Create `backend/app/schemas/learning.py`: Pydantic request/response schemas and enums.
- Create `backend/app/services/learning_plan_validator.py`: local problem-library validation and fallback replacement.
- Create `backend/app/services/learning_plan_llm.py`: LLM client interface, OpenAI implementation, JSON schema, and repair loop orchestration.
- Create `backend/app/services/study_plan_service.py`: draft lifecycle, plan confirmation, active-plan switching, item status changes, reorder, adjustment drafts, and version activation.
- Create `backend/app/api/learning.py`: authenticated learning-plan HTTP API.
- Modify `backend/app/main.py`: include learning router.
- Create `backend/tests/test_learning_plan_validator.py`.
- Create `backend/tests/test_learning_plan_service.py`.
- Create `backend/tests/test_learning_llm_generation.py`.
- Create `backend/tests/test_learning_api.py`.

Frontend files:

- Create `frontend/src/api/learning.ts`: typed API client for calibration and study plans.
- Create `frontend/src/pages/GoalCalibrationPage.tsx`.
- Create `frontend/src/pages/GoalCalibrationPage.test.tsx`.
- Create `frontend/src/pages/StudyPlanPage.tsx`.
- Create `frontend/src/pages/StudyPlanPage.test.tsx`.
- Create `frontend/src/pages/StudyPlanHistoryPage.tsx`.
- Create `frontend/src/pages/StudyPlanHistoryPage.test.tsx`.
- Modify `frontend/src/App.tsx`: add 学习计划 nav item.
- Modify `frontend/src/routes/AppRoutes.tsx`: add `/goal-calibration`, `/study-plan`, `/study-plans`, `/study-plans/:planId/versions/:versionId`.
- Modify `frontend/src/routes/AuthRedirect.tsx`: redirect users with API assets to `/study-plan`, falling back to `/goal-calibration` when no active plan exists.
- Modify `frontend/src/styles/app.css`: add plan page layout styles.

Documentation files:

- Modify `docs/prd/prd.md`: align T1 product text with the approved PRD.
- Modify `docs/project-todolist.md`: update T1 task definition.
- Modify `docs/architecture/foundation.md`: describe learning-plan service boundaries after implementation.
- Modify `docs/index.md`: add new learning modules and pages if needed.

---

### Task 1: Backend Learning Data Model And Migration

**Files:**
- Create: `backend/app/models/learning.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/db/migrations/versions/20260520_0005_goal_calibration_study_plan.py`
- Test: `backend/tests/test_learning_plan_service.py`

- [ ] **Step 1: Write the failing model metadata test**

Add this test to `backend/tests/test_learning_plan_service.py`:

```python
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
```

- [ ] **Step 2: Run the model test and verify it fails**

Run:

```bash
uv run pytest backend/tests/test_learning_plan_service.py::test_learning_tables_are_registered_in_metadata -q
```

Expected: fail with `ModuleNotFoundError: No module named 'backend.app.models.learning'`.

- [ ] **Step 3: Create SQLAlchemy learning models**

Create `backend/app/models/learning.py` with these model boundaries:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.problem import Base, ID_TYPE, Problem


class GoalCalibrationDraft(Base):
    __tablename__ = "goal_calibration_draft"
    __table_args__ = (
        Index("ix_goal_calibration_draft_user_status", "user_id", "status"),
        Index("ix_goal_calibration_draft_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False)
    llm_credential_id: Mapped[int | None] = mapped_column(ForeignKey("llm_credential.id", ondelete="SET NULL"), nullable=True)
    input_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    followup_messages_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    draft_goal_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    draft_plan_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    validation_report_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    repair_log_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False, default="goal-plan-v1")
    model_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'collecting_input'"))
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confirmed_plan_id: Mapped[int | None] = mapped_column(ForeignKey("study_plan.id", ondelete="SET NULL"), nullable=True)
    confirmed_version_id: Mapped[int | None] = mapped_column(ForeignKey("study_plan_version.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StudyPlan(Base):
    __tablename__ = "study_plan"
    __table_args__ = (
        Index("ix_study_plan_user_status", "user_id", "status"),
        Index("ix_study_plan_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'active'"))
    active_version_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    versions: Mapped[list[StudyPlanVersion]] = relationship(back_populates="plan", cascade="all, delete-orphan")


class StudyPlanVersion(Base):
    __tablename__ = "study_plan_version"
    __table_args__ = (
        UniqueConstraint("plan_id", "version_number", name="uq_study_plan_version_plan_number"),
        Index("ix_study_plan_version_plan_status", "plan_id", "status"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("study_plan.id", ondelete="CASCADE"), nullable=False)
    source_draft_id: Mapped[int | None] = mapped_column(ForeignKey("goal_calibration_draft.id", ondelete="SET NULL"), nullable=True)
    cloned_from_version_id: Mapped[int | None] = mapped_column(ForeignKey("study_plan_version.id", ondelete="SET NULL"), nullable=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'draft'"))
    target_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generation_summary_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    adjustment_summary_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    validation_report_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    repair_log_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    plan: Mapped[StudyPlan] = relationship(back_populates="versions", foreign_keys=[plan_id])
    stages: Mapped[list[StudyPlanStage]] = relationship(back_populates="version", cascade="all, delete-orphan")
    items: Mapped[list[StudyPlanItem]] = relationship(back_populates="version", cascade="all, delete-orphan")


class StudyPlanStage(Base):
    __tablename__ = "study_plan_stage"
    __table_args__ = (
        UniqueConstraint("version_id", "stage_index", name="uq_study_plan_stage_version_index"),
        Index("ix_study_plan_stage_version", "version_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("study_plan_version.id", ondelete="CASCADE"), nullable=False)
    stage_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    objective_md: Mapped[str] = mapped_column(Text, nullable=False)
    focus_tags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    assessment_criteria_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'not_started'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    version: Mapped[StudyPlanVersion] = relationship(back_populates="stages")
    items: Mapped[list[StudyPlanItem]] = relationship(back_populates="stage")


class StudyPlanItem(Base):
    __tablename__ = "study_plan_item"
    __table_args__ = (
        UniqueConstraint("version_id", "problem_id", name="uq_study_plan_item_version_problem"),
        UniqueConstraint("stage_id", "order_index", name="uq_study_plan_item_stage_order"),
        Index("ix_study_plan_item_version_status", "version_id", "status"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("study_plan_version.id", ondelete="CASCADE"), nullable=False)
    stage_id: Mapped[int] = mapped_column(ForeignKey("study_plan_stage.id", ondelete="CASCADE"), nullable=False)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problem.id", ondelete="RESTRICT"), nullable=False)
    problem_slug: Mapped[str] = mapped_column(String(180), nullable=False)
    skill_tags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    suggested_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    recommendation_reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'pending'"))
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    version: Mapped[StudyPlanVersion] = relationship(back_populates="items")
    stage: Mapped[StudyPlanStage] = relationship(back_populates="items")
    problem: Mapped[Problem] = relationship()


class PlanChangeLog(Base):
    __tablename__ = "plan_change_log"
    __table_args__ = (Index("ix_plan_change_log_version", "version_id"),)

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("study_plan_version.id", ondelete="CASCADE"), nullable=False)
    change_type: Mapped[str] = mapped_column(String(40), nullable=False)
    problem_id: Mapped[int | None] = mapped_column(ForeignKey("problem.id", ondelete="SET NULL"), nullable=True)
    detail_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    reason_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
```

- [ ] **Step 4: Export learning models**

Modify `backend/app/models/__init__.py` to import and export the new classes:

```python
from backend.app.models.learning import (
    GoalCalibrationDraft,
    PlanChangeLog,
    StudyPlan,
    StudyPlanItem,
    StudyPlanStage,
    StudyPlanVersion,
)
```

Add those names to `__all__`.

- [ ] **Step 5: Add Alembic migration**

Create `backend/app/db/migrations/versions/20260520_0005_goal_calibration_study_plan.py`.

Use `down_revision = "20260519_0004"`. Create the six tables in dependency order:

1. `study_plan`
2. `goal_calibration_draft`
3. `study_plan_version`
4. `study_plan_stage`
5. `study_plan_item`
6. `plan_change_log`

Use the exact columns and indexes from the model code above. In downgrade, drop indexes and tables in reverse dependency order.

- [ ] **Step 6: Run the model test and migration check**

Run:

```bash
uv run pytest backend/tests/test_learning_plan_service.py::test_learning_tables_are_registered_in_metadata -q
uv run alembic upgrade head
uv run alembic downgrade 20260519_0004
uv run alembic upgrade head
```

Expected: pytest passes; Alembic commands exit 0.

- [ ] **Step 7: Commit Task 1**

```bash
git add backend/app/models/learning.py backend/app/models/__init__.py backend/app/db/migrations/versions/20260520_0005_goal_calibration_study_plan.py backend/tests/test_learning_plan_service.py
git commit -m "feat: add learning plan data model"
```

---

### Task 2: Backend Learning Schemas And Enums

**Files:**
- Create: `backend/app/schemas/learning.py`
- Test: `backend/tests/test_learning_plan_service.py`

- [ ] **Step 1: Write failing schema validation tests**

Append to `backend/tests/test_learning_plan_service.py`:

```python
import pytest
from pydantic import ValidationError

from backend.app.schemas.learning import GoalCalibrationInput


def test_goal_calibration_accepts_supported_languages() -> None:
    for language in ["c", "go", "python3", "javascript", "java"]:
        payload = GoalCalibrationInput(
            goal_type="interview_sprint",
            target_timeline="one_to_three_months",
            weekly_days=4,
            session_minutes=60,
            current_level="medium_partial",
            preferred_language=language,
            self_reported_weaknesses=["pattern", "edge_case"],
            extra_notes="3 months until interview",
            training_preference="independent_first",
        )
        assert payload.preferred_language == language


def test_goal_calibration_rejects_unsupported_language() -> None:
    with pytest.raises(ValidationError):
        GoalCalibrationInput(
            goal_type="interview_sprint",
            target_timeline="one_to_three_months",
            weekly_days=4,
            session_minutes=60,
            current_level="medium_partial",
            preferred_language="ruby",
            self_reported_weaknesses=[],
            training_preference="guided",
        )
```

- [ ] **Step 2: Run schema tests and verify they fail**

Run:

```bash
uv run pytest backend/tests/test_learning_plan_service.py::test_goal_calibration_accepts_supported_languages backend/tests/test_learning_plan_service.py::test_goal_calibration_rejects_unsupported_language -q
```

Expected: fail because `backend.app.schemas.learning` does not exist.

- [ ] **Step 3: Create learning schemas**

Create `backend/app/schemas/learning.py` with:

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


GoalType = Literal["beginner", "interview_sprint", "strengthen_weakness", "maintain"]
TargetTimeline = Literal["none", "within_1_month", "one_to_three_months", "over_three_months"]
CurrentLevel = Literal["new", "easy_started", "medium_partial", "round_done_unstable"]
PreferredLanguage = Literal["c", "go", "python3", "javascript", "java"]
Weakness = Literal[
    "problem_understanding",
    "pattern",
    "complexity",
    "implementation",
    "edge_case",
    "interview_expression",
]
TrainingPreference = Literal["guided", "independent_first", "interviewer_style"]
TrainingMode = Literal["guided", "independent", "mock_interview"]
PlanStatus = Literal["active", "paused", "completed", "archived"]
VersionStatus = Literal["draft", "active", "superseded"]
StageStatus = Literal["not_started", "in_progress", "completed"]
PlanItemStatus = Literal["pending", "in_progress", "completed", "skipped", "locked_completed"]
DraftStatus = Literal[
    "collecting_input",
    "asking_followup",
    "generating",
    "validating",
    "needs_repair",
    "ready_for_review",
    "confirmed",
    "failed",
    "discarded",
]


class GoalCalibrationInput(BaseModel):
    goal_type: GoalType
    target_timeline: TargetTimeline
    weekly_days: int = Field(ge=1, le=7)
    session_minutes: int = Field(ge=15, le=180)
    current_level: CurrentLevel
    preferred_language: PreferredLanguage
    self_reported_weaknesses: list[Weakness] = Field(default_factory=list)
    extra_notes: str = Field(default="", max_length=2000)
    training_preference: TrainingPreference


class FollowupAnswer(BaseModel):
    question_id: str
    answer: str = Field(max_length=1000)


class GoalCalibrationStartResponse(BaseModel):
    draft_id: int
    status: DraftStatus
    followup_question: str | None = None
    followup_question_id: str | None = None
    remaining_followups: int


class PlanDraftItem(BaseModel):
    problem_slug: str
    title: str = ""
    difficulty: str
    skill_tags: list[str] = Field(default_factory=list)
    suggested_mode: TrainingMode
    recommendation_reason: str
    order_index: int


class PlanDraftStage(BaseModel):
    title: str
    objective_md: str
    focus_tags: list[str] = Field(default_factory=list)
    assessment_criteria: list[str] = Field(default_factory=list)
    items: list[PlanDraftItem] = Field(default_factory=list)


class PlanDraftResponse(BaseModel):
    draft_id: int
    status: DraftStatus
    target_snapshot: dict
    generation_summary_md: str
    stages: list[PlanDraftStage]
    validation_report: dict
    repair_log: list[dict]
    uncertainty_notes: list[str] = Field(default_factory=list)


class ConfirmPlanRequest(BaseModel):
    draft_id: int


class StudyPlanItemResponse(BaseModel):
    id: int
    problem_id: int
    problem_slug: str
    frontend_id: str
    title: str
    translated_title: str
    difficulty: str
    skill_tags: list[str]
    suggested_mode: str
    recommendation_reason: str
    status: str
    order_index: int
    locked: bool


class StudyPlanStageResponse(BaseModel):
    id: int
    stage_index: int
    title: str
    objective_md: str
    focus_tags: list[str]
    assessment_criteria: list[str]
    status: str
    items: list[StudyPlanItemResponse]


class StudyPlanVersionResponse(BaseModel):
    id: int
    version_number: int
    status: str
    target_snapshot: dict
    generation_summary_md: str
    adjustment_summary_md: str
    validation_report: dict
    repair_log: list[dict]
    stages: list[StudyPlanStageResponse]
    created_at: datetime
    activated_at: datetime | None


class StudyPlanResponse(BaseModel):
    id: int
    title: str
    status: str
    active_version_number: int
    created_at: datetime
    updated_at: datetime
    active_version: StudyPlanVersionResponse


class StudyPlanListItem(BaseModel):
    id: int
    title: str
    status: str
    active_version_number: int
    created_at: datetime
    updated_at: datetime


class StudyPlanListResponse(BaseModel):
    items: list[StudyPlanListItem]


class PlanItemStatusUpdateRequest(BaseModel):
    status: Literal["pending", "skipped"]


class PlanItemReorderRequest(BaseModel):
    item_ids: list[int] = Field(min_length=1)


class PlanAdjustmentRequest(BaseModel):
    reason: Literal[
        "time_change",
        "interview_date_change",
        "too_hard",
        "too_easy",
        "strengthen_topic",
        "reduce_topic",
        "language_change",
        "other",
    ]
    notes: str = Field(default="", max_length=2000)
    preferred_language: PreferredLanguage | None = None
```

- [ ] **Step 4: Run schema tests**

Run:

```bash
uv run pytest backend/tests/test_learning_plan_service.py::test_goal_calibration_accepts_supported_languages backend/tests/test_learning_plan_service.py::test_goal_calibration_rejects_unsupported_language -q
```

Expected: both tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add backend/app/schemas/learning.py backend/tests/test_learning_plan_service.py
git commit -m "feat: add learning plan schemas"
```

---

### Task 3: Plan Validator And Local Problem Matching

**Files:**
- Create: `backend/app/services/learning_plan_validator.py`
- Test: `backend/tests/test_learning_plan_validator.py`

- [ ] **Step 1: Write failing validator tests**

Create `backend/tests/test_learning_plan_validator.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.models.auth import AppUser
from backend.app.models.problem import Base, Problem
from backend.app.services.learning_plan_validator import (
    ValidationIssue,
    validate_and_repair_plan_draft,
)


@pytest_asyncio.fixture
async def validator_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def problem(slug: str, *, paid: bool = False) -> Problem:
    now = datetime.now(UTC)
    return Problem(
        frontend_id=slug,
        slug=slug,
        title=slug.replace("-", " ").title(),
        translated_title=slug,
        difficulty="Easy",
        statement_md="# statement",
        metadata_json={"topic_tags": [{"slug": "array", "name": "Array", "translated_name": "数组"}]},
        leetcode_url=f"https://leetcode.cn/problems/{slug}/",
        is_paid_only=paid,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_validator_replaces_missing_problem_with_same_tag_candidate(validator_session_factory) -> None:
    async with validator_session_factory() as session:
        session.add(problem("two-sum"))
        await session.commit()

        draft = {
            "stages": [
                {
                    "title": "基础",
                    "objective_md": "练数组",
                    "focus_tags": ["array"],
                    "assessment_criteria": ["能讲清 complement"],
                    "items": [
                        {
                            "problem_slug": "missing-problem",
                            "difficulty": "Easy",
                            "skill_tags": ["array"],
                            "suggested_mode": "guided",
                            "recommendation_reason": "练数组",
                            "order_index": 1,
                        }
                    ],
                }
            ]
        }

        repaired, report, repair_log = await validate_and_repair_plan_draft(session, draft)

        assert repaired["stages"][0]["items"][0]["problem_slug"] == "two-sum"
        assert report["valid"] is True
        assert repair_log[0]["reason"] == "problem_not_found"


@pytest.mark.asyncio
async def test_validator_reports_empty_problem_library(validator_session_factory) -> None:
    async with validator_session_factory() as session:
        repaired, report, repair_log = await validate_and_repair_plan_draft(session, {"stages": []})

        assert repaired == {"stages": []}
        assert report["valid"] is False
        assert ValidationIssue.EMPTY_PROBLEM_LIBRARY.value in report["issues"]
        assert repair_log == []
```

- [ ] **Step 2: Run validator tests and verify they fail**

Run:

```bash
uv run pytest backend/tests/test_learning_plan_validator.py -q
```

Expected: fail because `learning_plan_validator.py` does not exist.

- [ ] **Step 3: Implement validator**

Create `backend/app/services/learning_plan_validator.py`:

```python
from __future__ import annotations

from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.problem import Problem


class ValidationIssue(str, Enum):
    EMPTY_PROBLEM_LIBRARY = "empty_problem_library"
    PROBLEM_NOT_FOUND = "problem_not_found"
    PAID_ONLY_PROBLEM = "paid_only_problem"
    DUPLICATE_PROBLEM = "duplicate_problem"


def _problem_tags(problem: Problem) -> set[str]:
    return {
        item.get("slug", "")
        for item in problem.metadata_json.get("topic_tags", [])
        if item.get("slug")
    }


async def _load_available_problems(session: AsyncSession) -> list[Problem]:
    result = await session.execute(
        select(Problem)
        .where(Problem.is_paid_only.is_(False))
        .order_by(Problem.difficulty.asc(), Problem.frontend_id.asc())
    )
    return list(result.scalars().all())


def _candidate_for_tags(candidates: list[Problem], wanted_tags: list[str], used: set[str]) -> Problem | None:
    wanted = set(wanted_tags)
    for candidate in candidates:
        if candidate.slug in used:
            continue
        if wanted and wanted.intersection(_problem_tags(candidate)):
            return candidate
    for candidate in candidates:
        if candidate.slug not in used:
            return candidate
    return None


def _item_from_problem(problem: Problem, original: dict[str, Any], order_index: int) -> dict[str, Any]:
    return {
        **original,
        "problem_slug": problem.slug,
        "title": problem.title,
        "difficulty": problem.difficulty,
        "skill_tags": [tag.get("slug", "") for tag in problem.metadata_json.get("topic_tags", []) if tag.get("slug")],
        "order_index": order_index,
    }


async def validate_and_repair_plan_draft(
    session: AsyncSession,
    draft: dict[str, Any],
    *,
    locked_problem_slugs: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    candidates = await _load_available_problems(session)
    if not candidates:
        return draft, {"valid": False, "issues": [ValidationIssue.EMPTY_PROBLEM_LIBRARY.value]}, []

    by_slug = {problem.slug: problem for problem in candidates}
    used: set[str] = set()
    repair_log: list[dict[str, Any]] = []
    issues: list[str] = []
    locked = locked_problem_slugs or set()
    repaired = {**draft, "stages": []}

    for stage in draft.get("stages", []):
        repaired_stage = {**stage, "items": []}
        for index, item in enumerate(stage.get("items", []), start=1):
            slug = item.get("problem_slug", "")
            problem = by_slug.get(slug)
            reason = ""
            if slug in used:
                reason = ValidationIssue.DUPLICATE_PROBLEM.value
                problem = None
            elif problem is None:
                reason = ValidationIssue.PROBLEM_NOT_FOUND.value

            if problem is None:
                replacement = _candidate_for_tags(candidates, item.get("skill_tags", []), used | locked)
                if replacement is None:
                    issues.append(reason)
                    continue
                repair_log.append(
                    {
                        "reason": reason,
                        "original_problem_slug": slug,
                        "replacement_problem_slug": replacement.slug,
                    }
                )
                problem = replacement

            used.add(problem.slug)
            repaired_stage["items"].append(_item_from_problem(problem, item, index))
        repaired["stages"].append(repaired_stage)

    report = {
        "valid": len(issues) == 0 and any(stage.get("items") for stage in repaired["stages"]),
        "issues": issues,
        "item_count": sum(len(stage.get("items", [])) for stage in repaired["stages"]),
    }
    return repaired, report, repair_log
```

- [ ] **Step 4: Run validator tests**

Run:

```bash
uv run pytest backend/tests/test_learning_plan_validator.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add backend/app/services/learning_plan_validator.py backend/tests/test_learning_plan_validator.py
git commit -m "feat: validate learning plan drafts"
```

---

### Task 4: Study Plan Service Without LLM Network Calls

**Files:**
- Create: `backend/app/services/study_plan_service.py`
- Test: `backend/tests/test_learning_plan_service.py`

- [ ] **Step 1: Write failing service tests**

Append service tests that use a deterministic draft. Include these cases:

```python
@pytest.mark.asyncio
async def test_confirm_draft_creates_unique_active_plan(learning_session_factory) -> None:
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        first_draft = await create_ready_draft(session, user, title="第一计划")
        first_plan = await confirm_plan_draft(session, user, first_draft.id)

        second_draft = await create_ready_draft(session, user, title="第二计划")
        second_plan = await confirm_plan_draft(session, user, second_draft.id)

        await session.refresh(first_plan)
        assert first_plan.status == "paused"
        assert second_plan.status == "active"


@pytest.mark.asyncio
async def test_adjustment_clone_preserves_completed_items(learning_session_factory) -> None:
    async with learning_session_factory() as session:
        user = await create_learning_user(session)
        draft = await create_ready_draft(session, user, title="原计划")
        plan = await confirm_plan_draft(session, user, draft.id)
        version = await get_active_plan_version(session, user, plan.id)
        version.items[0].status = "completed"
        version.items[0].locked = True
        await session.commit()

        new_version = await clone_adjusted_version(
            session,
            user,
            plan.id,
            adjustment_summary_md="完成题保留，补充数组题",
            draft_plan_json=draft.draft_plan_json,
            validation_report_json={"valid": True},
            repair_log_json=[],
        )

        assert any(item.problem_slug == version.items[0].problem_slug for item in new_version.items)
        assert new_version.version_number == 2
```

Use helper functions in the same test file:

```python
async def create_learning_user(session: AsyncSession) -> AppUser:
    now = datetime.now(UTC)
    user = AppUser(
        username=f"user-{now.timestamp()}",
        email=f"user-{now.timestamp()}@example.com",
        password_hash="hash",
        display_name="learner",
        status="active",
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    await session.flush()
    session.add(problem("two-sum"))
    session.add(problem("valid-parentheses"))
    await session.commit()
    await session.refresh(user)
    return user
```

- [ ] **Step 2: Run service tests and verify they fail**

Run:

```bash
uv run pytest backend/tests/test_learning_plan_service.py -q
```

Expected: fail because service functions are not defined.

- [ ] **Step 3: Implement service functions**

Create `backend/app/services/study_plan_service.py` with these functions:

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.auth import AppUser
from backend.app.models.learning import (
    GoalCalibrationDraft,
    PlanChangeLog,
    StudyPlan,
    StudyPlanItem,
    StudyPlanStage,
    StudyPlanVersion,
)
from backend.app.models.problem import Problem


class StudyPlanError(RuntimeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


async def pause_other_active_plans(db: AsyncSession, user: AppUser, keep_plan_id: int | None = None) -> None:
    query = update(StudyPlan).where(StudyPlan.user_id == user.id, StudyPlan.status == "active")
    if keep_plan_id is not None:
        query = query.where(StudyPlan.id != keep_plan_id)
    await db.execute(query.values(status="paused", updated_at=datetime.now(UTC)))


async def get_active_plan_version(db: AsyncSession, user: AppUser, plan_id: int) -> StudyPlanVersion:
    result = await db.execute(
        select(StudyPlanVersion)
        .join(StudyPlan)
        .options(
            selectinload(StudyPlanVersion.stages).selectinload(StudyPlanStage.items).selectinload(StudyPlanItem.problem),
            selectinload(StudyPlanVersion.items).selectinload(StudyPlanItem.problem),
        )
        .where(
            StudyPlan.id == plan_id,
            StudyPlan.user_id == user.id,
            StudyPlanVersion.status == "active",
        )
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise StudyPlanError("active_study_plan_version_not_found")
    return version


async def _problem_by_slug(db: AsyncSession, slug: str) -> Problem:
    result = await db.execute(select(Problem).where(Problem.slug == slug))
    problem = result.scalar_one_or_none()
    if problem is None:
        raise StudyPlanError("validated_problem_not_found")
    return problem


async def _write_version_content(
    db: AsyncSession,
    version: StudyPlanVersion,
    draft_plan_json: dict[str, Any],
) -> None:
    for stage_index, stage_payload in enumerate(draft_plan_json.get("stages", []), start=1):
        stage = StudyPlanStage(
            version_id=version.id,
            stage_index=stage_index,
            title=stage_payload["title"],
            objective_md=stage_payload["objective_md"],
            focus_tags_json=stage_payload.get("focus_tags", []),
            assessment_criteria_json=stage_payload.get("assessment_criteria", []),
            status="in_progress" if stage_index == 1 else "not_started",
        )
        db.add(stage)
        await db.flush()
        for order_index, item_payload in enumerate(stage_payload.get("items", []), start=1):
            problem = await _problem_by_slug(db, item_payload["problem_slug"])
            db.add(
                StudyPlanItem(
                    version_id=version.id,
                    stage_id=stage.id,
                    problem_id=problem.id,
                    problem_slug=problem.slug,
                    skill_tags_json=item_payload.get("skill_tags", []),
                    difficulty=problem.difficulty,
                    suggested_mode=item_payload["suggested_mode"],
                    recommendation_reason=item_payload["recommendation_reason"],
                    status="pending",
                    order_index=order_index,
                    locked=False,
                )
            )


async def confirm_plan_draft(db: AsyncSession, user: AppUser, draft_id: int) -> StudyPlan:
    result = await db.execute(
        select(GoalCalibrationDraft).where(
            GoalCalibrationDraft.id == draft_id,
            GoalCalibrationDraft.user_id == user.id,
            GoalCalibrationDraft.status == "ready_for_review",
        )
    )
    draft = result.scalar_one_or_none()
    if draft is None:
        raise StudyPlanError("plan_draft_not_ready")

    await pause_other_active_plans(db, user)
    now = datetime.now(UTC)
    plan = StudyPlan(
        user_id=user.id,
        title=draft.draft_plan_json.get("title", "学习计划"),
        status="active",
        active_version_number=1,
        created_at=now,
        updated_at=now,
    )
    db.add(plan)
    await db.flush()
    version = StudyPlanVersion(
        plan_id=plan.id,
        source_draft_id=draft.id,
        version_number=1,
        status="active",
        target_snapshot_json=draft.draft_goal_json,
        generation_summary_md=draft.draft_plan_json.get("generation_summary_md", ""),
        adjustment_summary_md="",
        validation_report_json=draft.validation_report_json,
        repair_log_json=draft.repair_log_json,
        created_at=now,
        activated_at=now,
    )
    db.add(version)
    await db.flush()
    await _write_version_content(db, version, draft.draft_plan_json)
    draft.status = "confirmed"
    draft.confirmed_plan_id = plan.id
    draft.confirmed_version_id = version.id
    draft.confirmed_at = now
    await db.commit()
    await db.refresh(plan)
    return plan
```

Add `clone_adjusted_version`, `activate_plan`, `list_study_plans`, `get_active_study_plan`, `update_plan_item_status`, and `reorder_stage_items` in the same file. `clone_adjusted_version` must:

- Load the active version.
- Mark the old version `superseded`.
- Create version number `old.version_number + 1`.
- Copy completed, in-progress, skipped, or locked old items into the new version even when the adjustment draft omits them.
- Create `PlanChangeLog` rows for `preserved`, `added`, `removed`, and `reordered` changes.
- Commit atomically.

- [ ] **Step 4: Run service tests**

Run:

```bash
uv run pytest backend/tests/test_learning_plan_service.py -q
```

Expected: all service tests pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add backend/app/services/study_plan_service.py backend/tests/test_learning_plan_service.py
git commit -m "feat: manage study plan lifecycle"
```

---

### Task 5: LLM Client, Follow-Up Questions, And Repair Loop

**Files:**
- Create: `backend/app/services/learning_plan_llm.py`
- Test: `backend/tests/test_learning_llm_generation.py`

- [ ] **Step 1: Write failing LLM orchestration tests**

Create `backend/tests/test_learning_llm_generation.py` with a fake client:

```python
from __future__ import annotations

import pytest

from backend.app.services.learning_plan_llm import LearningPlanLlmClient, generate_plan_with_repair


class FakeLearningPlanClient(LearningPlanLlmClient):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def followup_question(self, payload: dict, history: list[dict]) -> dict:
        return {"question_id": "q1", "question": "你的面试时间是？"}

    async def plan_draft(self, payload: dict, history: list[dict]) -> dict:
        self.calls.append("plan")
        return {
            "title": "面试冲刺计划",
            "target_snapshot": payload,
            "generation_summary_md": "按面试冲刺生成。",
            "stages": [
                {
                    "title": "数组基础",
                    "objective_md": "补齐数组基础。",
                    "focus_tags": ["array"],
                    "assessment_criteria": ["能讲清哈希表"],
                    "items": [
                        {
                            "problem_slug": "missing",
                            "difficulty": "Easy",
                            "skill_tags": ["array"],
                            "suggested_mode": "guided",
                            "recommendation_reason": "练数组",
                            "order_index": 1,
                        }
                    ],
                }
            ],
        }

    async def repair_plan_draft(self, payload: dict, report: dict, repair_log: list[dict]) -> dict:
        self.calls.append("repair")
        repaired = await self.plan_draft(payload, [])
        repaired["stages"][0]["items"][0]["problem_slug"] = "two-sum"
        return repaired


@pytest.mark.asyncio
async def test_generate_plan_with_repair_uses_repair_when_validation_fails(monkeypatch) -> None:
    async def fake_validate(session, draft, *, locked_problem_slugs=None):
        if draft["stages"][0]["items"][0]["problem_slug"] == "two-sum":
            return draft, {"valid": True, "issues": []}, []
        return draft, {"valid": False, "issues": ["problem_not_found"]}, []

    monkeypatch.setattr(
        "backend.app.services.learning_plan_llm.validate_and_repair_plan_draft",
        fake_validate,
    )

    client = FakeLearningPlanClient()
    draft, report, repair_log = await generate_plan_with_repair(
        session=None,
        client=client,
        payload={"goal_type": "interview_sprint"},
        history=[],
        max_repairs=2,
    )

    assert draft["stages"][0]["items"][0]["problem_slug"] == "two-sum"
    assert report["valid"] is True
    assert client.calls == ["plan", "repair", "plan"]
```

- [ ] **Step 2: Run LLM tests and verify they fail**

Run:

```bash
uv run pytest backend/tests/test_learning_llm_generation.py -q
```

Expected: fail because `learning_plan_llm.py` does not exist.

- [ ] **Step 3: Implement LLM interface and OpenAI client**

Create `backend/app/services/learning_plan_llm.py`:

```python
from __future__ import annotations

import json
from typing import Any, Protocol

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.models.auth import AppUser, LlmCredential
from backend.app.services.credential_crypto import decrypt_api_key
from backend.app.services.learning_plan_validator import validate_and_repair_plan_draft
from backend.app.services.llm_credential_service import select_llm_credential_for_user


PROMPT_VERSION = "goal-plan-v1"

PLAN_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "target_snapshot", "generation_summary_md", "stages"],
    "properties": {
        "title": {"type": "string"},
        "target_snapshot": {"type": "object"},
        "generation_summary_md": {"type": "string"},
        "stages": {"type": "array"},
    },
}


class LearningPlanLlmClient(Protocol):
    async def followup_question(self, payload: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any] | None:
        ...

    async def plan_draft(self, payload: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
        ...

    async def repair_plan_draft(self, payload: dict[str, Any], report: dict[str, Any], repair_log: list[dict[str, Any]]) -> dict[str, Any]:
        ...


class OpenAILearningPlanClient:
    def __init__(self, credential: LlmCredential, api_key: str) -> None:
        self.credential = credential
        self.client = AsyncOpenAI(api_key=api_key, base_url=credential.base_url)

    async def _json_response(self, instructions: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self.client.responses.create(
            model=self.credential.model_name,
            instructions=instructions,
            input=json.dumps(payload, ensure_ascii=False),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "learning_plan_payload",
                    "schema": PLAN_JSON_SCHEMA,
                    "strict": False,
                }
            },
        )
        return json.loads(response.output_text)

    async def followup_question(self, payload: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any] | None:
        if len(history) >= 3:
            return None
        prompt = "你是目标校准教练。只在必要时返回一个 JSON 问题；信息足够时返回 null。"
        response = await self.client.responses.create(
            model=self.credential.model_name,
            instructions=prompt,
            input=json.dumps({"payload": payload, "history": history}, ensure_ascii=False),
        )
        text = response.output_text.strip()
        return None if text == "null" else json.loads(text)

    async def plan_draft(self, payload: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
        return await self._json_response(
            "根据用户目标生成阶段化学习计划。当前阶段必须包含 LeetCode 题目 slug。",
            {"payload": payload, "history": history},
        )

    async def repair_plan_draft(self, payload: dict[str, Any], report: dict[str, Any], repair_log: list[dict[str, Any]]) -> dict[str, Any]:
        return await self._json_response(
            "根据校验失败原因修复学习计划，只替换无效题目。",
            {"payload": payload, "validation_report": report, "repair_log": repair_log},
        )


async def client_for_user(db: AsyncSession, user: AppUser) -> tuple[LearningPlanLlmClient, LlmCredential]:
    credential = await select_llm_credential_for_user(db, user)
    api_key = decrypt_api_key(credential.api_key_ciphertext, settings.credential_encryption_key)
    return OpenAILearningPlanClient(credential, api_key), credential


async def generate_plan_with_repair(
    session: AsyncSession,
    client: LearningPlanLlmClient,
    payload: dict[str, Any],
    history: list[dict[str, Any]],
    *,
    max_repairs: int = 2,
    locked_problem_slugs: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    draft = await client.plan_draft(payload, history)
    combined_repair_log: list[dict[str, Any]] = []
    for attempt in range(max_repairs + 1):
        repaired, report, repair_log = await validate_and_repair_plan_draft(
            session,
            draft,
            locked_problem_slugs=locked_problem_slugs,
        )
        combined_repair_log.extend(repair_log)
        if report.get("valid"):
            return repaired, report, combined_repair_log
        if attempt == max_repairs:
            return repaired, report, combined_repair_log
        draft = await client.repair_plan_draft(payload, report, combined_repair_log)
    return draft, {"valid": False, "issues": ["repair_loop_exhausted"]}, combined_repair_log
```

- [ ] **Step 4: Run LLM tests**

Run:

```bash
uv run pytest backend/tests/test_learning_llm_generation.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 5**

```bash
git add backend/app/services/learning_plan_llm.py backend/tests/test_learning_llm_generation.py
git commit -m "feat: generate learning plan drafts with llm"
```

---

### Task 6: Learning API Routes

**Files:**
- Create: `backend/app/api/learning.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_learning_api.py`

- [ ] **Step 1: Write failing API tests**

Create `backend/tests/test_learning_api.py` with tests that monkeypatch services:

```python
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.api.auth import current_user_dependency
from backend.app.main import app
from backend.app.models.auth import AppUser


def fake_user() -> AppUser:
    return AppUser(
        id=42,
        username="alice",
        email="alice@example.com",
        password_hash="hash",
        display_name="Alice",
        status="active",
    )


def test_learning_routes_require_authentication() -> None:
    client = TestClient(app)

    response = client.get("/api/study-plan/current")

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


def test_start_goal_calibration_returns_draft(monkeypatch) -> None:
    async def fake_start(*args, **kwargs):
        return {
            "draft_id": 1,
            "status": "asking_followup",
            "followup_question": "你的面试时间是？",
            "followup_question_id": "q1",
            "remaining_followups": 2,
        }

    monkeypatch.setattr(
        "backend.app.services.study_plan_service.start_goal_calibration",
        fake_start,
        raising=False,
    )
    app.dependency_overrides[current_user_dependency] = fake_user
    try:
        client = TestClient(app)
        response = client.post(
            "/api/goal-calibration",
            json={
                "goal_type": "interview_sprint",
                "target_timeline": "one_to_three_months",
                "weekly_days": 4,
                "session_minutes": 60,
                "current_level": "medium_partial",
                "preferred_language": "python3",
                "self_reported_weaknesses": ["pattern"],
                "extra_notes": "",
                "training_preference": "independent_first",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["followup_question"] == "你的面试时间是？"
```

- [ ] **Step 2: Run API tests and verify they fail**

Run:

```bash
uv run pytest backend/tests/test_learning_api.py -q
```

Expected: fail because `backend.app.api.learning` is not registered.

- [ ] **Step 3: Implement API routes**

Create `backend/app/api/learning.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.auth import current_user_dependency
from backend.app.db.session import get_session
from backend.app.models.auth import AppUser
from backend.app.schemas.learning import (
    ConfirmPlanRequest,
    FollowupAnswer,
    GoalCalibrationInput,
    GoalCalibrationStartResponse,
    PlanAdjustmentRequest,
    PlanDraftResponse,
    PlanItemReorderRequest,
    PlanItemStatusUpdateRequest,
    StudyPlanListResponse,
    StudyPlanResponse,
)
from backend.app.services.study_plan_service import StudyPlanError


router = APIRouter(tags=["learning"])


def _http_error(exc: StudyPlanError) -> HTTPException:
    status = 404 if "not_found" in exc.detail else 400
    if exc.detail in {"llm_credential_unavailable", "empty_problem_library"}:
        status = 409
    return HTTPException(status_code=status, detail=exc.detail)


@router.post("/goal-calibration", response_model=GoalCalibrationStartResponse)
async def start_goal_calibration_route(
    payload: GoalCalibrationInput,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        from backend.app.services.study_plan_service import start_goal_calibration

        return await start_goal_calibration(session, user, payload)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.post("/goal-calibration/{draft_id}/followup", response_model=GoalCalibrationStartResponse)
async def answer_followup_route(
    draft_id: int,
    payload: FollowupAnswer,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        from backend.app.services.study_plan_service import answer_goal_followup

        return await answer_goal_followup(session, user, draft_id, payload)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.post("/goal-calibration/{draft_id}/generate", response_model=PlanDraftResponse)
async def generate_plan_draft_route(
    draft_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        from backend.app.services.study_plan_service import generate_goal_plan_draft

        return await generate_goal_plan_draft(session, user, draft_id)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.post("/study-plans/confirm", response_model=StudyPlanResponse)
async def confirm_plan_route(
    payload: ConfirmPlanRequest,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        from backend.app.services.study_plan_service import confirm_plan_draft, study_plan_payload

        plan = await confirm_plan_draft(session, user, payload.draft_id)
        return await study_plan_payload(session, user, plan.id)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc
```

Continue `backend/app/api/learning.py` with the remaining route skeletons:

```python
@router.get("/study-plan/current", response_model=StudyPlanResponse)
async def current_plan_route(
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        from backend.app.services.study_plan_service import get_current_study_plan_payload

        return await get_current_study_plan_payload(session, user)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.get("/study-plans", response_model=StudyPlanListResponse)
async def study_plan_list_route(
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from backend.app.services.study_plan_service import list_study_plan_payloads

    return await list_study_plan_payloads(session, user)


@router.post("/study-plans/{plan_id}/activate", response_model=StudyPlanResponse)
async def activate_plan_route(
    plan_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        from backend.app.services.study_plan_service import activate_plan, study_plan_payload

        plan = await activate_plan(session, user, plan_id)
        return await study_plan_payload(session, user, plan.id)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.get("/study-plans/{plan_id}/versions/{version_id}", response_model=StudyPlanResponse)
async def plan_version_route(
    plan_id: int,
    version_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        from backend.app.services.study_plan_service import study_plan_payload

        return await study_plan_payload(session, user, plan_id, version_id=version_id)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.post("/study-plans/{plan_id}/adjustments", response_model=PlanDraftResponse)
async def create_adjustment_route(
    plan_id: int,
    payload: PlanAdjustmentRequest,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        from backend.app.services.study_plan_service import create_adjustment_draft

        return await create_adjustment_draft(session, user, plan_id, payload)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.post("/study-plans/{plan_id}/versions/{version_id}/activate", response_model=StudyPlanResponse)
async def activate_version_route(
    plan_id: int,
    version_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        from backend.app.services.study_plan_service import activate_plan_version, study_plan_payload

        await activate_plan_version(session, user, plan_id, version_id)
        return await study_plan_payload(session, user, plan_id)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.patch("/study-plan/items/{item_id}", response_model=StudyPlanResponse)
async def update_item_status_route(
    item_id: int,
    payload: PlanItemStatusUpdateRequest,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        from backend.app.services.study_plan_service import study_plan_payload, update_plan_item_status

        plan_id = await update_plan_item_status(session, user, item_id, payload.status)
        return await study_plan_payload(session, user, plan_id)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc


@router.post("/study-plan/stages/{stage_id}/reorder", response_model=StudyPlanResponse)
async def reorder_stage_route(
    stage_id: int,
    payload: PlanItemReorderRequest,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        from backend.app.services.study_plan_service import reorder_stage_items, study_plan_payload

        plan_id = await reorder_stage_items(session, user, stage_id, payload.item_ids)
        return await study_plan_payload(session, user, plan_id)
    except StudyPlanError as exc:
        raise _http_error(exc) from exc
```

- [ ] **Step 4: Register router**

Modify `backend/app/main.py`:

```python
from backend.app.api.learning import router as learning_router
```

Inside `create_app()`:

```python
application.include_router(learning_router, prefix=settings.api_prefix)
```

- [ ] **Step 5: Run API tests**

Run:

```bash
uv run pytest backend/tests/test_learning_api.py -q
```

Expected: all API tests pass.

- [ ] **Step 6: Commit Task 6**

```bash
git add backend/app/api/learning.py backend/app/main.py backend/tests/test_learning_api.py
git commit -m "feat: expose learning plan api"
```

---

### Task 7: Frontend Learning API, Routes, And Navigation

**Files:**
- Create: `frontend/src/api/learning.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/routes/AppRoutes.tsx`
- Modify: `frontend/src/routes/AuthRedirect.tsx`
- Test: `frontend/src/App.test.tsx`

- [ ] **Step 1: Write failing route/nav test**

Modify `frontend/src/App.test.tsx` to assert the app has a study-plan navigation item:

```tsx
expect(await screen.findByText('学习计划')).toBeInTheDocument()
```

Stub `/api/auth/me` as authenticated with `has_default_llm_credential: true`, `/api/health` as ok, and `/api/study-plan/current` as 404 for no active plan.

- [ ] **Step 2: Run frontend app test and verify it fails**

Run:

```bash
cd frontend && corepack pnpm test -- App.test.tsx
```

Expected: fail because the navigation does not include 学习计划.

- [ ] **Step 3: Add typed learning API client**

Create `frontend/src/api/learning.ts` with:

```ts
import { requestJson } from './client'

export type PreferredLanguage = 'c' | 'go' | 'python3' | 'javascript' | 'java'
export type GoalType = 'beginner' | 'interview_sprint' | 'strengthen_weakness' | 'maintain'
export type TargetTimeline = 'none' | 'within_1_month' | 'one_to_three_months' | 'over_three_months'
export type CurrentLevel = 'new' | 'easy_started' | 'medium_partial' | 'round_done_unstable'
export type TrainingPreference = 'guided' | 'independent_first' | 'interviewer_style'

export type GoalCalibrationPayload = {
  goal_type: GoalType
  target_timeline: TargetTimeline
  weekly_days: number
  session_minutes: number
  current_level: CurrentLevel
  preferred_language: PreferredLanguage
  self_reported_weaknesses: string[]
  extra_notes: string
  training_preference: TrainingPreference
}

export type GoalCalibrationStartResponse = {
  draft_id: number
  status: string
  followup_question: string | null
  followup_question_id: string | null
  remaining_followups: number
}

export type PlanDraftResponse = {
  draft_id: number
  status: string
  target_snapshot: Record<string, unknown>
  generation_summary_md: string
  stages: Array<{
    title: string
    objective_md: string
    focus_tags: string[]
    assessment_criteria: string[]
    items: Array<{
      problem_slug: string
      title: string
      difficulty: string
      skill_tags: string[]
      suggested_mode: string
      recommendation_reason: string
      order_index: number
    }>
  }>
  validation_report: Record<string, unknown>
  repair_log: Array<Record<string, unknown>>
  uncertainty_notes: string[]
}

export type StudyPlan = {
  id: number
  title: string
  status: string
  active_version_number: number
  active_version: StudyPlanVersion
}

export type StudyPlanVersion = {
  id: number
  version_number: number
  status: string
  target_snapshot: Record<string, unknown>
  generation_summary_md: string
  adjustment_summary_md: string
  stages: StudyPlanStage[]
}

export type StudyPlanStage = {
  id: number
  stage_index: number
  title: string
  objective_md: string
  focus_tags: string[]
  assessment_criteria: string[]
  status: string
  items: StudyPlanItem[]
}

export type StudyPlanItem = {
  id: number
  problem_slug: string
  frontend_id: string
  title: string
  translated_title: string
  difficulty: string
  skill_tags: string[]
  suggested_mode: string
  recommendation_reason: string
  status: string
  order_index: number
  locked: boolean
}

export function startGoalCalibration(payload: GoalCalibrationPayload) {
  return requestJson<GoalCalibrationStartResponse>('/api/goal-calibration', {
    method: 'POST',
    body: payload,
  })
}

export function answerGoalFollowup(draftId: number, questionId: string, answer: string) {
  return requestJson<GoalCalibrationStartResponse>(`/api/goal-calibration/${draftId}/followup`, {
    method: 'POST',
    body: { question_id: questionId, answer },
  })
}

export function generatePlanDraft(draftId: number) {
  return requestJson<PlanDraftResponse>(`/api/goal-calibration/${draftId}/generate`, {
    method: 'POST',
  })
}

export function confirmPlan(draftId: number) {
  return requestJson<StudyPlan>('/api/study-plans/confirm', {
    method: 'POST',
    body: { draft_id: draftId },
  })
}

export function getCurrentStudyPlan() {
  return requestJson<StudyPlan>('/api/study-plan/current')
}

export function listStudyPlans() {
  return requestJson<{ items: Array<{ id: number; title: string; status: string; active_version_number: number }> }>('/api/study-plans')
}
```

- [ ] **Step 4: Add routes and nav**

Modify `frontend/src/App.tsx`:

```tsx
import { CalendarOutlined } from '@ant-design/icons'
```

Add nav item after 题库:

```tsx
{ to: '/study-plan', label: '学习计划', icon: <CalendarOutlined aria-hidden="true" /> },
```

Modify `frontend/src/routes/AppRoutes.tsx`:

```tsx
import { GoalCalibrationPage } from '../pages/GoalCalibrationPage'
import { StudyPlanHistoryPage } from '../pages/StudyPlanHistoryPage'
import { StudyPlanPage } from '../pages/StudyPlanPage'
```

Add:

```tsx
<Route path="/goal-calibration" element={<GoalCalibrationPage />} />
<Route path="/study-plan" element={<StudyPlanPage />} />
<Route path="/study-plans" element={<StudyPlanHistoryPage />} />
<Route path="/study-plans/:planId/versions/:versionId" element={<StudyPlanPage />} />
```

Modify `AuthRedirect.tsx` so authenticated users with LLM assets go to `/study-plan`.

- [ ] **Step 5: Run frontend app test**

Run:

```bash
cd frontend && corepack pnpm test -- App.test.tsx
```

Expected: App route/nav tests pass.

- [ ] **Step 6: Commit Task 7**

```bash
git add frontend/src/api/learning.ts frontend/src/App.tsx frontend/src/routes/AppRoutes.tsx frontend/src/routes/AuthRedirect.tsx frontend/src/App.test.tsx
git commit -m "feat: add learning plan frontend routes"
```

---

### Task 8: Goal Calibration Page

**Files:**
- Create: `frontend/src/pages/GoalCalibrationPage.tsx`
- Create: `frontend/src/pages/GoalCalibrationPage.test.tsx`

- [ ] **Step 1: Write failing page tests**

Create `frontend/src/pages/GoalCalibrationPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { GoalCalibrationPage } from './GoalCalibrationPage'

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <GoalCalibrationPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function okJson(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('GoalCalibrationPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('submits calibration and shows followup question', async () => {
    const fetchMock = vi.fn(async () =>
      okJson({
        draft_id: 3,
        status: 'asking_followup',
        followup_question: '你的面试时间是？',
        followup_question_id: 'q1',
        remaining_followups: 2,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    fireEvent.click(screen.getByLabelText('面试冲刺'))
    fireEvent.click(screen.getByLabelText('1 到 3 个月'))
    fireEvent.click(screen.getByLabelText('Python3'))
    fireEvent.click(screen.getByRole('button', { name: '开始校准' }))

    expect(await screen.findByText('你的面试时间是？')).toBeInTheDocument()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/goal-calibration', expect.objectContaining({ method: 'POST' })))
  })
})
```

- [ ] **Step 2: Run page test and verify it fails**

Run:

```bash
cd frontend && corepack pnpm test -- GoalCalibrationPage.test.tsx
```

Expected: fail because the page does not exist.

- [ ] **Step 3: Implement `GoalCalibrationPage`**

Create a form-based page with Ant Design:

```tsx
import { useMutation } from '@tanstack/react-query'
import { Alert, Button, Card, Checkbox, Form, Input, InputNumber, Radio, Space, Typography } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  answerGoalFollowup,
  confirmPlan,
  generatePlanDraft,
  startGoalCalibration,
  type GoalCalibrationPayload,
  type GoalCalibrationStartResponse,
  type PlanDraftResponse,
} from '../api/learning'

export function GoalCalibrationPage() {
  const [draft, setDraft] = useState<GoalCalibrationStartResponse | null>(null)
  const [planDraft, setPlanDraft] = useState<PlanDraftResponse | null>(null)
  const [followupAnswer, setFollowupAnswer] = useState('')
  const navigate = useNavigate()

  const startMutation = useMutation({
    mutationFn: startGoalCalibration,
    onSuccess: setDraft,
  })
  const answerMutation = useMutation({
    mutationFn: () => answerGoalFollowup(draft!.draft_id, draft!.followup_question_id!, followupAnswer),
    onSuccess: setDraft,
  })
  const generateMutation = useMutation({
    mutationFn: () => generatePlanDraft(draft!.draft_id),
    onSuccess: setPlanDraft,
  })
  const confirmMutation = useMutation({
    mutationFn: () => confirmPlan(planDraft!.draft_id),
    onSuccess: () => navigate('/study-plan'),
  })

  function submit(values: GoalCalibrationPayload) {
    startMutation.mutate({
      ...values,
      self_reported_weaknesses: values.self_reported_weaknesses ?? [],
      extra_notes: values.extra_notes ?? '',
    })
  }

  return (
    <section className="page-section">
      <div className="page-heading">
        <Typography.Title level={2}>目标校准</Typography.Title>
      </div>

      {startMutation.isError || answerMutation.isError || generateMutation.isError ? (
        <Alert showIcon type="error" message="目标校准失败" className="page-alert" />
      ) : null}

      {!draft ? (
        <Form layout="vertical" initialValues={{ weekly_days: 4, session_minutes: 60, preferred_language: 'python3', training_preference: 'independent_first' }} onFinish={submit}>
          <Form.Item name="goal_type" label="学习目标" rules={[{ required: true }]}>
            <Radio.Group>
              <Radio value="beginner">刷题入门</Radio>
              <Radio value="interview_sprint">面试冲刺</Radio>
              <Radio value="strengthen_weakness">专项补弱</Radio>
              <Radio value="maintain">保持手感</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="target_timeline" label="时间线" rules={[{ required: true }]}>
            <Radio.Group>
              <Radio value="none">无明确时间</Radio>
              <Radio value="within_1_month">1 个月内</Radio>
              <Radio value="one_to_three_months">1 到 3 个月</Radio>
              <Radio value="over_three_months">3 个月以上</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="preferred_language" label="默认训练语言" rules={[{ required: true }]}>
            <Radio.Group>
              <Radio value="c">C</Radio>
              <Radio value="go">Go</Radio>
              <Radio value="python3">Python3</Radio>
              <Radio value="javascript">JavaScript</Radio>
              <Radio value="java">Java</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="weekly_days" label="每周训练天数"><InputNumber min={1} max={7} /></Form.Item>
          <Form.Item name="session_minutes" label="单次训练分钟"><InputNumber min={15} max={180} /></Form.Item>
          <Form.Item name="current_level" label="当前水平" rules={[{ required: true }]}>
            <Radio.Group>
              <Radio value="new">没系统刷过</Radio>
              <Radio value="easy_started">做过少量 Easy</Radio>
              <Radio value="medium_partial">能做部分 Medium</Radio>
              <Radio value="round_done_unstable">刷过一轮但不稳定</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="self_reported_weaknesses" label="自评弱项">
            <Checkbox.Group options={[
              { label: '题意理解', value: 'problem_understanding' },
              { label: '题型识别', value: 'pattern' },
              { label: '复杂度优化', value: 'complexity' },
              { label: '代码实现', value: 'implementation' },
              { label: '边界条件', value: 'edge_case' },
              { label: '面试表达', value: 'interview_expression' },
            ]} />
          </Form.Item>
          <Form.Item name="training_preference" label="训练偏好">
            <Radio.Group>
              <Radio value="guided">更希望被引导</Radio>
              <Radio value="independent_first">先独立思考再提示</Radio>
              <Radio value="interviewer_style">偏面试官追问</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="extra_notes" label="补充说明"><Input.TextArea rows={4} /></Form.Item>
          <Button type="primary" htmlType="submit" loading={startMutation.isPending}>开始校准</Button>
        </Form>
      ) : null}

      {draft?.followup_question ? (
        <Card title="追问">
          <Typography.Paragraph>{draft.followup_question}</Typography.Paragraph>
          <Input.TextArea value={followupAnswer} onChange={(event) => setFollowupAnswer(event.target.value)} rows={3} />
          <Space>
            <Button type="primary" onClick={() => answerMutation.mutate()} loading={answerMutation.isPending}>提交回答</Button>
            <Button onClick={() => generateMutation.mutate()} loading={generateMutation.isPending}>跳过并生成计划</Button>
          </Space>
        </Card>
      ) : null}

      {draft && !draft.followup_question && !planDraft ? (
        <Button type="primary" onClick={() => generateMutation.mutate()} loading={generateMutation.isPending}>生成计划草稿</Button>
      ) : null}

      {planDraft ? (
        <Card title="计划草稿">
          <Typography.Paragraph>{planDraft.generation_summary_md}</Typography.Paragraph>
          {planDraft.stages.map((stage) => (
            <Card key={stage.title} type="inner" title={stage.title}>
              <Typography.Paragraph>{stage.objective_md}</Typography.Paragraph>
              {stage.items.map((item) => (
                <div key={item.problem_slug}>{item.order_index}. {item.title || item.problem_slug} · {item.difficulty}</div>
              ))}
            </Card>
          ))}
          <Button type="primary" onClick={() => confirmMutation.mutate()} loading={confirmMutation.isPending}>确认创建计划</Button>
        </Card>
      ) : null}
    </section>
  )
}
```

- [ ] **Step 4: Run page tests**

Run:

```bash
cd frontend && corepack pnpm test -- GoalCalibrationPage.test.tsx
```

Expected: test passes.

- [ ] **Step 5: Commit Task 8**

```bash
git add frontend/src/pages/GoalCalibrationPage.tsx frontend/src/pages/GoalCalibrationPage.test.tsx
git commit -m "feat: add goal calibration page"
```

---

### Task 9: Study Plan Pages

**Files:**
- Create: `frontend/src/pages/StudyPlanPage.tsx`
- Create: `frontend/src/pages/StudyPlanPage.test.tsx`
- Create: `frontend/src/pages/StudyPlanHistoryPage.tsx`
- Create: `frontend/src/pages/StudyPlanHistoryPage.test.tsx`
- Modify: `frontend/src/api/learning.ts`
- Modify: `frontend/src/styles/app.css`

- [ ] **Step 1: Write failing current plan page test**

Create `frontend/src/pages/StudyPlanPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { StudyPlanPage } from './StudyPlanPage'

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StudyPlanPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function okJson(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('StudyPlanPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders active plan stages and current-stage items', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        okJson({
          id: 10,
          title: '3 个月 Java 面试冲刺计划',
          status: 'active',
          active_version_number: 1,
          active_version: {
            id: 20,
            version_number: 1,
            status: 'active',
            target_snapshot: { preferred_language: 'java' },
            generation_summary_md: '基于面试冲刺生成。',
            adjustment_summary_md: '',
            stages: [
              {
                id: 30,
                stage_index: 1,
                title: '数组基础',
                objective_md: '补齐数组基础。',
                focus_tags: ['array'],
                assessment_criteria: ['能讲清哈希表'],
                status: 'in_progress',
                items: [
                  {
                    id: 40,
                    problem_slug: 'two-sum',
                    frontend_id: '1',
                    title: 'Two Sum',
                    translated_title: '两数之和',
                    difficulty: 'Easy',
                    skill_tags: ['array'],
                    suggested_mode: 'guided',
                    recommendation_reason: '练 complement 查找。',
                    status: 'pending',
                    order_index: 1,
                    locked: false,
                  },
                ],
              },
            ],
          },
        }),
      ),
    )

    renderPage()

    expect(await screen.findByText('3 个月 Java 面试冲刺计划')).toBeInTheDocument()
    expect(screen.getByText('数组基础')).toBeInTheDocument()
    expect(screen.getByText('Two Sum')).toBeInTheDocument()
    expect(screen.getByText('练 complement 查找。')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run page tests and verify they fail**

Run:

```bash
cd frontend && corepack pnpm test -- StudyPlanPage.test.tsx
```

Expected: fail because the page does not exist.

- [ ] **Step 3: Add remaining API functions**

Extend `frontend/src/api/learning.ts`:

```ts
export function updatePlanItemStatus(itemId: number, status: 'pending' | 'skipped') {
  return requestJson<StudyPlanItem>(`/api/study-plan/items/${itemId}`, {
    method: 'PATCH',
    body: { status },
  })
}

export function reorderStageItems(stageId: number, itemIds: number[]) {
  return requestJson<StudyPlan>(`/api/study-plan/stages/${stageId}/reorder`, {
    method: 'POST',
    body: { item_ids: itemIds },
  })
}

export function activateStudyPlan(planId: number) {
  return requestJson<StudyPlan>(`/api/study-plans/${planId}/activate`, {
    method: 'POST',
  })
}

export function createPlanAdjustment(planId: number, payload: { reason: string; notes: string; preferred_language?: PreferredLanguage }) {
  return requestJson<PlanDraftResponse>(`/api/study-plans/${planId}/adjustments`, {
    method: 'POST',
    body: payload,
  })
}
```

- [ ] **Step 4: Implement current study plan page**

Create `frontend/src/pages/StudyPlanPage.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Space, Tag, Typography } from 'antd'
import { Link } from 'react-router-dom'

import { getCurrentStudyPlan, updatePlanItemStatus, type StudyPlanItem } from '../api/learning'

const studyPlanQueryKey = ['study-plan', 'current']

function statusLabel(status: string) {
  return {
    pending: '未开始',
    in_progress: '训练中',
    completed: '已完成',
    skipped: '已跳过',
    locked_completed: '已完成',
  }[status] ?? status
}

export function StudyPlanPage() {
  const queryClient = useQueryClient()
  const { data, isError, isLoading, error } = useQuery({
    queryKey: studyPlanQueryKey,
    queryFn: getCurrentStudyPlan,
    retry: false,
  })
  const itemStatusMutation = useMutation({
    mutationFn: ({ item, status }: { item: StudyPlanItem; status: 'pending' | 'skipped' }) =>
      updatePlanItemStatus(item.id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: studyPlanQueryKey }),
  })

  if (isLoading) {
    return <section className="page-section">学习计划加载中</section>
  }

  if (isError) {
    return (
      <section className="page-section">
        <Alert showIcon type="info" message="还没有学习计划" description="请先完成目标校准。" />
        <Link to="/goal-calibration"><Button type="primary">开始目标校准</Button></Link>
      </section>
    )
  }

  return (
    <section className="page-section study-plan-page">
      <div className="page-heading">
        <Space direction="vertical" size={2}>
          <Typography.Title level={2}>{data.title}</Typography.Title>
          <Space wrap>
            <Tag color="green">{data.status}</Tag>
            <Tag>v{data.active_version.version_number}</Tag>
            <Tag>{String(data.active_version.target_snapshot.preferred_language ?? '')}</Tag>
          </Space>
        </Space>
        <Space>
          <Link to="/study-plans"><Button>计划历史</Button></Link>
          <Button>调整计划</Button>
        </Space>
      </div>

      <Typography.Paragraph>{data.active_version.generation_summary_md}</Typography.Paragraph>

      {data.active_version.stages.map((stage) => (
        <Card key={stage.id} title={stage.title} className="plan-stage">
          <Typography.Paragraph>{stage.objective_md}</Typography.Paragraph>
          <div className="plan-items">
            {stage.items.map((item) => (
              <div key={item.id} className="plan-item-row">
                <div>
                  <Link to={`/workspace/${item.problem_slug}`}>
                    {item.frontend_id}. {item.title}
                  </Link>
                  <Typography.Text type="secondary"> {item.translated_title}</Typography.Text>
                  <div>{item.recommendation_reason}</div>
                </div>
                <Space>
                  <Tag>{item.difficulty}</Tag>
                  <Tag>{statusLabel(item.status)}</Tag>
                  {item.status === 'pending' ? (
                    <Button onClick={() => itemStatusMutation.mutate({ item, status: 'skipped' })}>跳过</Button>
                  ) : null}
                  {item.status === 'skipped' ? (
                    <Button onClick={() => itemStatusMutation.mutate({ item, status: 'pending' })}>取消跳过</Button>
                  ) : null}
                </Space>
              </div>
            ))}
          </div>
        </Card>
      ))}
    </section>
  )
}
```

- [ ] **Step 5: Implement plan history page**

Create `frontend/src/pages/StudyPlanHistoryPage.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Space, Table, Tag, Typography } from 'antd'
import { Link } from 'react-router-dom'

import { activateStudyPlan, listStudyPlans } from '../api/learning'

const studyPlanListQueryKey = ['study-plans']

export function StudyPlanHistoryPage() {
  const queryClient = useQueryClient()
  const { data, isError, isLoading } = useQuery({
    queryKey: studyPlanListQueryKey,
    queryFn: listStudyPlans,
  })
  const activateMutation = useMutation({
    mutationFn: activateStudyPlan,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: studyPlanListQueryKey }),
  })

  return (
    <section className="page-section">
      <div className="page-heading">
        <Typography.Title level={2}>学习计划历史</Typography.Title>
        <Link to="/goal-calibration"><Button type="primary">新建计划</Button></Link>
      </div>
      {isError ? <Alert showIcon type="error" message="计划列表加载失败" className="page-alert" /> : null}
      <Table
        rowKey="id"
        loading={isLoading}
        dataSource={data?.items ?? []}
        columns={[
          { title: '计划名称', dataIndex: 'title' },
          { title: '状态', dataIndex: 'status', render: (status: string) => <Tag>{status}</Tag> },
          { title: '当前版本', dataIndex: 'active_version_number', render: (value: number) => `v${value}` },
          {
            title: '操作',
            render: (_, row) => (
              <Space>
                <Link to={`/study-plan`}><Button>查看</Button></Link>
                {row.status === 'paused' || row.status === 'completed' ? (
                  <Button
                    type="primary"
                    onClick={() => activateMutation.mutate(row.id)}
                    loading={activateMutation.isPending && activateMutation.variables === row.id}
                  >
                    激活
                  </Button>
                ) : null}
              </Space>
            ),
          },
        ]}
      />
    </section>
  )
}
```

Create `frontend/src/pages/StudyPlanHistoryPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { StudyPlanHistoryPage } from './StudyPlanHistoryPage'

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StudyPlanHistoryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function okJson(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('StudyPlanHistoryPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders plans and activates a paused plan', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/study-plans/2/activate' && init?.method === 'POST') {
        return okJson({ id: 2, title: '动态规划专项', status: 'active', active_version_number: 1, active_version: { stages: [] } })
      }
      return okJson({
        items: [
          { id: 1, title: '面试冲刺', status: 'active', active_version_number: 1 },
          { id: 2, title: '动态规划专项', status: 'paused', active_version_number: 2 },
        ],
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    expect(await screen.findByText('面试冲刺')).toBeInTheDocument()
    expect(screen.getByText('动态规划专项')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '激活' }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/study-plans/2/activate',
        expect.objectContaining({ method: 'POST', credentials: 'include' }),
      ),
    )
  })
})
```

- [ ] **Step 6: Add CSS**

Append to `frontend/src/styles/app.css`:

```css
.study-plan-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.plan-stage {
  border-radius: 8px;
}

.plan-items {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.plan-item-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  padding: 12px 0;
  border-top: 1px solid #f0f0f0;
}
```

- [ ] **Step 7: Run frontend page tests**

Run:

```bash
cd frontend && corepack pnpm test -- StudyPlanPage.test.tsx StudyPlanHistoryPage.test.tsx
```

Expected: both test files pass.

- [ ] **Step 8: Commit Task 9**

```bash
git add frontend/src/api/learning.ts frontend/src/pages/StudyPlanPage.tsx frontend/src/pages/StudyPlanPage.test.tsx frontend/src/pages/StudyPlanHistoryPage.tsx frontend/src/pages/StudyPlanHistoryPage.test.tsx frontend/src/styles/app.css
git commit -m "feat: add study plan pages"
```

---

### Task 10: Documentation And End-To-End Verification

**Files:**
- Modify: `docs/prd/prd.md`
- Modify: `docs/project-todolist.md`
- Modify: `docs/architecture/foundation.md`
- Modify: `docs/index.md`

- [ ] **Step 1: Update product and architecture docs**

Update `docs/prd/prd.md` sections for:

- Goal calibration uses structured form plus up to 3 LLM follow-ups.
- Supported default training languages: C, Go, Python3, JavaScript, Java.
- Study plans are multi-plan, active-exclusive, stage-based, and versioned.
- Plan adjustment is user-triggered and creates a new version.

Update `docs/project-todolist.md` T1 task list so it matches this implementation.

Update `docs/architecture/foundation.md` with the new backend boundaries:

- `backend.app.models.learning`
- `backend.app.services.study_plan_service`
- `backend.app.services.learning_plan_llm`
- `backend.app.services.learning_plan_validator`
- `backend.app.api.learning`

Update `docs/index.md` directory responsibilities if new files or pages are not already covered.

- [ ] **Step 2: Run backend tests**

Run:

```bash
uv run pytest backend/tests/test_learning_plan_validator.py backend/tests/test_learning_plan_service.py backend/tests/test_learning_llm_generation.py backend/tests/test_learning_api.py -q
```

Expected: all listed backend tests pass.

- [ ] **Step 3: Run frontend tests**

Run:

```bash
cd frontend && corepack pnpm test -- GoalCalibrationPage.test.tsx StudyPlanPage.test.tsx StudyPlanHistoryPage.test.tsx App.test.tsx
```

Expected: all listed frontend tests pass.

- [ ] **Step 4: Run build**

Run:

```bash
make build
```

Expected: backend and frontend build checks complete with exit code 0.

- [ ] **Step 5: Run full smoke if local services are available**

Run:

```bash
make up
make db-migrate
make smoke
make down
```

Expected: smoke test exits 0. If Docker services cannot start in the current environment, record the exact failing command and error in the final implementation summary.

- [ ] **Step 6: Commit Task 10**

```bash
git add docs/prd/prd.md docs/project-todolist.md docs/architecture/foundation.md docs/index.md
git commit -m "docs: document learning plan implementation"
```

---

## Self-Review Checklist

- Spec coverage: The tasks cover structured calibration, LLM follow-up, LLM planning, backend validation, repair loop, multi-plan active exclusivity, version cloning, current-stage items, user-triggered adjustment, frontend calibration, plan display, history, docs, and verification.
- Scope boundary: T2 practice sessions, code-runner, RAG, AI coach chat, and real submission history are not implemented here; T1 stores identifiers and status needed for those features.
- Type consistency: Backend schemas use lowercase language values `c`, `go`, `python3`, `javascript`, `java`; frontend uses the same union type.
- Status consistency: Plan, version, stage, item, and draft statuses match the approved PRD.
- Verification commands: Backend tests, frontend tests, build, and optional smoke are listed with exact commands.
