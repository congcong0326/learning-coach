# LLM Streaming Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unified LLM Run layer so goal calibration, study plan generation, study plan adjustment, and later coach chat can show ChatGPT-style streaming text, backend progress, cancellation, and recoverable final status.

**Architecture:** Add `llm_run` as the persistent lifecycle record, expose create/status/cancel/SSE endpoints, and run each LLM scenario through a streaming-first orchestrator. Use an in-process event hub for first-version SSE fan-out, persist run status and final result in PostgreSQL, and keep deterministic plan validation as the gate before any formal study plan result is shown.

**Tech Stack:** FastAPI `StreamingResponse`, SQLAlchemy async, Alembic, OpenAI Responses API streaming, React 19, Ant Design, TanStack Query, Vitest.

---

## Pre-Flight

The current workspace may contain unrelated local edits in:

- `backend/app/api/learning.py`
- `backend/app/services/learning_plan_llm.py`
- `backend/app/services/learning_plan_validator.py`
- `backend/app/services/study_plan_service.py`

Do not revert those edits. At execution time, isolate implementation work with `superpowers:using-git-worktrees` or inspect these files before editing and preserve any user changes.

Reference spec:

- `docs/superpowers/specs/2026-05-21-llm-streaming-experience-design.md`

## File Map

Create backend files:

- `backend/app/models/llm_run.py`: SQLAlchemy model for run lifecycle and persisted final result.
- `backend/app/db/migrations/versions/20260521_0006_llm_runs.py`: Alembic migration for `llm_run`.
- `backend/app/schemas/llm_run.py`: Pydantic request/response/event schemas.
- `backend/app/services/llm_run_events.py`: SSE event dataclass, encoder, in-process subscriber hub.
- `backend/app/services/llm_run_service.py`: create/status/cancel/state transition helpers.
- `backend/app/services/llm_orchestrator.py`: dispatch run kinds to domain flows and publish events.
- `backend/app/services/llm_providers/__init__.py`: provider package exports.
- `backend/app/services/llm_providers/base.py`: provider protocol and chunk types.
- `backend/app/services/llm_providers/openai_responses.py`: OpenAI Responses streaming adapter.
- `backend/app/services/learning_flows/__init__.py`: flow package exports.
- `backend/app/services/learning_flows/goal_calibration.py`: `goal_followup` flow.
- `backend/app/services/learning_flows/goal_plan.py`: `goal_plan_generate` flow.
- `backend/app/services/learning_flows/study_plan_adjustment.py`: `study_plan_adjustment` flow.
- `backend/app/api/llm_runs.py`: LLM Run API routes.

Modify backend files:

- `backend/app/main.py`: register `llm_runs` router.
- `backend/app/models/__init__.py`: export `LlmRun`.
- `backend/app/services/learning_plan_validator.py`: keep deterministic validator public and reusable.
- `backend/app/services/study_plan_service.py`: move or expose small helpers needed by new flows without preserving old sync LLM as the primary path.
- `backend/app/services/learning_plan_llm.py`: migrate constants/schema to flow/provider modules, then shrink to compatibility or remove references after tests migrate.

Create backend tests:

- `backend/tests/test_llm_run_model.py`
- `backend/tests/test_llm_run_events.py`
- `backend/tests/test_llm_run_service.py`
- `backend/tests/test_llm_runs_api.py`
- `backend/tests/test_openai_responses_provider.py`
- `backend/tests/test_learning_flows.py`

Create frontend files:

- `frontend/src/api/llmRuns.ts`
- `frontend/src/hooks/useLlmRun.ts`
- `frontend/src/components/LlmStreamingPanel.tsx`
- `frontend/src/components/LlmStreamingPanel.test.tsx`
- `frontend/src/hooks/useLlmRun.test.tsx`

Modify frontend files:

- `frontend/src/pages/GoalCalibrationPage.tsx`: use run flow for followup and plan generation.
- `frontend/src/pages/StudyPlanPage.tsx`: use run flow for adjustment once adjustment UI is enabled.
- `frontend/src/api/learning.ts`: keep confirm/read/update APIs; remove direct generation calls after page migration.

Modify docs after implementation:

- `docs/index.md`
- `docs/architecture/foundation.md`
- `docs/prd/prd.md`
- `docs/project-todolist.md`

---

### Task 1: Persisted `llm_run` Model And Migration

**Files:**
- Create: `backend/app/models/llm_run.py`
- Create: `backend/app/db/migrations/versions/20260521_0006_llm_runs.py`
- Create: `backend/tests/test_llm_run_model.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write model metadata tests**

Add `backend/tests/test_llm_run_model.py`:

```python
from __future__ import annotations

from sqlalchemy import Table

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
```

- [ ] **Step 2: Run model tests and verify failure**

Run:

```bash
uv run pytest backend/tests/test_llm_run_model.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.models.llm_run'`.

- [ ] **Step 3: Add `LlmRun` model**

Create `backend/app/models/llm_run.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.problem import Base, ID_TYPE


EMPTY_OBJECT = text("'{}'")
EMPTY_TEXT = text("''")


class LlmRun(Base):
    __tablename__ = "llm_run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'canceled')",
            name="ck_llm_run_status",
        ),
        Index("ix_llm_run_user_created", "user_id", "created_at"),
        Index("ix_llm_run_user_kind_status", "user_id", "kind", "status"),
        Index("ix_llm_run_related", "related_type", "related_id"),
        Index("ix_llm_run_credential", "llm_credential_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    stage: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="queued",
        server_default=text("'queued'"),
    )
    display_text_md: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    input_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    result_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=EMPTY_OBJECT,
    )
    error_code: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    error_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    llm_credential_id: Mapped[int | None] = mapped_column(
        ForeignKey("llm_credential.id", ondelete="SET NULL"),
        nullable=True,
    )
    model_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    related_type: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="",
        server_default=EMPTY_TEXT,
    )
    related_id: Mapped[int | None] = mapped_column(ID_TYPE, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
```

- [ ] **Step 4: Export model**

Modify `backend/app/models/__init__.py`:

```python
from backend.app.models.llm_run import LlmRun
```

Add `"LlmRun"` to `__all__`.

- [ ] **Step 5: Add migration**

Create `backend/app/db/migrations/versions/20260521_0006_llm_runs.py`:

```python
"""create llm run table

Revision ID: 20260521_0006
Revises: 20260520_0005
Create Date: 2026-05-21 00:00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260521_0006"
down_revision: str | None = "20260520_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMPTY_JSON_OBJECT = sa.text("'{}'::json")
EMPTY_TEXT = sa.text("''")


def upgrade() -> None:
    op.create_table(
        "llm_run",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "stage",
            sa.String(length=80),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column("display_text_md", sa.Text(), nullable=False, server_default=EMPTY_TEXT),
        sa.Column("input_json", sa.JSON(), nullable=False, server_default=EMPTY_JSON_OBJECT),
        sa.Column("result_json", sa.JSON(), nullable=False, server_default=EMPTY_JSON_OBJECT),
        sa.Column("error_code", sa.String(length=80), nullable=False, server_default=EMPTY_TEXT),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=EMPTY_TEXT),
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "llm_credential_id",
            sa.BigInteger(),
            sa.ForeignKey("llm_credential.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("model_name", sa.String(length=120), nullable=False, server_default=EMPTY_TEXT),
        sa.Column("related_type", sa.String(length=80), nullable=False, server_default=EMPTY_TEXT),
        sa.Column("related_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'canceled')",
            name="ck_llm_run_status",
        ),
    )
    op.create_index("ix_llm_run_user_created", "llm_run", ["user_id", "created_at"])
    op.create_index("ix_llm_run_user_kind_status", "llm_run", ["user_id", "kind", "status"])
    op.create_index("ix_llm_run_related", "llm_run", ["related_type", "related_id"])
    op.create_index("ix_llm_run_credential", "llm_run", ["llm_credential_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_run_credential", table_name="llm_run")
    op.drop_index("ix_llm_run_related", table_name="llm_run")
    op.drop_index("ix_llm_run_user_kind_status", table_name="llm_run")
    op.drop_index("ix_llm_run_user_created", table_name="llm_run")
    op.drop_table("llm_run")
```

- [ ] **Step 6: Run model tests**

Run:

```bash
uv run pytest backend/tests/test_llm_run_model.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/llm_run.py backend/app/models/__init__.py backend/app/db/migrations/versions/20260521_0006_llm_runs.py backend/tests/test_llm_run_model.py
git commit -m "feat: add llm run persistence"
```

---

### Task 2: Run Schemas And SSE Event Utilities

**Files:**
- Create: `backend/app/schemas/llm_run.py`
- Create: `backend/app/services/llm_run_events.py`
- Create: `backend/tests/test_llm_run_events.py`

- [ ] **Step 1: Write schema and SSE tests**

Create `backend/tests/test_llm_run_events.py`:

```python
from __future__ import annotations

from backend.app.schemas.llm_run import LlmRunCreateRequest
from backend.app.services.llm_run_events import LlmRunEvent, encode_sse


def test_llm_run_create_request_accepts_known_kind() -> None:
    payload = LlmRunCreateRequest(
        kind="goal_plan_generate",
        payload={"draft_id": 3},
    )

    assert payload.kind == "goal_plan_generate"
    assert payload.payload["draft_id"] == 3


def test_encode_sse_formats_named_event() -> None:
    event = LlmRunEvent(
        name="progress",
        data={"run_id": 7, "stage": "validating", "message": "正在校验题库"},
    )

    assert encode_sse(event) == (
        'event: progress\n'
        'data: {"run_id":7,"stage":"validating","message":"正在校验题库"}\n\n'
    )
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest backend/tests/test_llm_run_events.py -q
```

Expected: FAIL with missing schema and event modules.

- [ ] **Step 3: Add schemas**

Create `backend/app/schemas/llm_run.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


LlmRunKind = Literal[
    "goal_followup",
    "goal_plan_generate",
    "study_plan_adjustment",
    "coach_message",
    "code_review",
    "reflection",
]
LlmRunStatus = Literal["pending", "running", "succeeded", "failed", "canceled"]


class LlmRunCreateRequest(BaseModel):
    kind: LlmRunKind
    payload: dict[str, Any] = Field(default_factory=dict)


class LlmRunCreateResponse(BaseModel):
    run_id: int
    kind: LlmRunKind
    status: LlmRunStatus
    stage: str
    stream_url: str


class LlmRunStatusResponse(BaseModel):
    run_id: int
    kind: str
    status: LlmRunStatus
    stage: str
    display_text_md: str
    result: dict[str, Any]
    error_code: str | None
    error_message: str | None
    can_retry: bool
    created_at: str
    started_at: str | None
    finished_at: str | None


class LlmRunCancelResponse(BaseModel):
    run_id: int
    status: LlmRunStatus
    cancel_requested: bool
```

- [ ] **Step 4: Add SSE event utilities**

Create `backend/app/services/llm_run_events.py`:

```python
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LlmRunEvent:
    name: str
    data: dict[str, Any]


def encode_sse(event: LlmRunEvent) -> str:
    payload = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.name}\ndata: {payload}\n\n"


class LlmRunEventHub:
    def __init__(self) -> None:
        self._subscribers: dict[int, set[asyncio.Queue[LlmRunEvent]]] = defaultdict(set)
        self._tasks: dict[int, asyncio.Task[None]] = {}

    def has_task(self, run_id: int) -> bool:
        task = self._tasks.get(run_id)
        return task is not None and not task.done()

    def set_task(self, run_id: int, task: asyncio.Task[None]) -> None:
        self._tasks[run_id] = task

    async def publish(self, run_id: int, event: LlmRunEvent) -> None:
        for queue in list(self._subscribers.get(run_id, set())):
            await queue.put(event)

    async def subscribe(self, run_id: int) -> AsyncIterator[LlmRunEvent]:
        queue: asyncio.Queue[LlmRunEvent] = asyncio.Queue()
        self._subscribers[run_id].add(queue)
        try:
            while True:
                event = await queue.get()
                yield event
                if event.name == "done":
                    break
        finally:
            self._subscribers[run_id].discard(queue)


event_hub = LlmRunEventHub()
```

- [ ] **Step 5: Run event tests**

Run:

```bash
uv run pytest backend/tests/test_llm_run_events.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/llm_run.py backend/app/services/llm_run_events.py backend/tests/test_llm_run_events.py
git commit -m "feat: add llm run event primitives"
```

---

### Task 3: Run Service State Machine

**Files:**
- Create: `backend/app/services/llm_run_service.py`
- Create: `backend/tests/test_llm_run_service.py`

- [ ] **Step 1: Write service tests**

Create `backend/tests/test_llm_run_service.py`:

```python
from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.models.auth import AppUser
from backend.app.models.problem import Base
from backend.app.services.llm_run_service import (
    LlmRunError,
    cancel_llm_run,
    create_llm_run,
    fail_llm_run,
    get_llm_run_for_user,
    mark_llm_run_running,
    succeed_llm_run,
)


@pytest_asyncio.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def create_user(session: AsyncSession) -> AppUser:
    now = datetime.now(UTC)
    unique = uuid4().hex
    user = AppUser(
        username=f"user-{unique}",
        email=f"user-{unique}@example.com",
        password_hash="hash",
        display_name="Learner",
        status="active",
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_create_and_fetch_llm_run(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        run = await create_llm_run(
            session,
            user,
            kind="goal_plan_generate",
            related_type="goal_calibration_draft",
            related_id=9,
        )

        fetched = await get_llm_run_for_user(session, user, run.id)

        assert fetched.id == run.id
        assert fetched.status == "pending"
        assert fetched.stage == "queued"


@pytest.mark.asyncio
async def test_status_transitions(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        run = await create_llm_run(session, user, kind="goal_plan_generate")

        await mark_llm_run_running(session, run, stage="selecting_credential")
        await succeed_llm_run(
            session,
            run,
            result={"draft_id": 12},
            display_text_md="计划生成完成",
        )

        fetched = await get_llm_run_for_user(session, user, run.id)
        assert fetched.status == "succeeded"
        assert fetched.stage == "completed"
        assert fetched.result_json == {"draft_id": 12}
        assert fetched.finished_at is not None


@pytest.mark.asyncio
async def test_cancel_terminal_run_is_rejected(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        user = await create_user(session)
        run = await create_llm_run(session, user, kind="goal_plan_generate")
        await fail_llm_run(session, run, error_code="llm_provider_error", error_message="模型请求失败")

        with pytest.raises(LlmRunError, match="run_status_conflict"):
            await cancel_llm_run(session, user, run.id)
```

- [ ] **Step 2: Run service tests and verify failure**

Run:

```bash
uv run pytest backend/tests/test_llm_run_service.py -q
```

Expected: FAIL with missing `llm_run_service`.

- [ ] **Step 3: Add service implementation**

Create `backend/app/services/llm_run_service.py`:

```python
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.auth import AppUser
from backend.app.models.llm_run import LlmRun


logger = logging.getLogger(__name__)
TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}


class LlmRunError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


async def create_llm_run(
    session: AsyncSession,
    user: AppUser,
    *,
    kind: str,
    payload: dict[str, Any] | None = None,
    related_type: str = "",
    related_id: int | None = None,
) -> LlmRun:
    run = LlmRun(
        user_id=user.id,
        kind=kind,
        input_json=payload or {},
        related_type=related_type,
        related_id=related_id,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    logger.info(
        "llm run created user_id=%s run_id=%s kind=%s related_type=%s related_id=%s",
        user.id,
        run.id,
        kind,
        related_type,
        related_id,
    )
    return run


async def get_llm_run_for_user(
    session: AsyncSession,
    user: AppUser,
    run_id: int,
) -> LlmRun:
    result = await session.execute(
        select(LlmRun).where(LlmRun.id == run_id, LlmRun.user_id == user.id)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise LlmRunError("run_not_found")
    return run


async def mark_llm_run_running(
    session: AsyncSession,
    run: LlmRun,
    *,
    stage: str,
    llm_credential_id: int | None = None,
    model_name: str = "",
) -> LlmRun:
    if run.status in TERMINAL_STATUSES:
        raise LlmRunError("run_status_conflict")
    now = datetime.now(UTC)
    run.status = "running"
    run.stage = stage
    run.started_at = run.started_at or now
    run.updated_at = now
    if llm_credential_id is not None:
        run.llm_credential_id = llm_credential_id
    if model_name:
        run.model_name = model_name
    await session.commit()
    await session.refresh(run)
    logger.info("llm run stage user_id=%s run_id=%s stage=%s", run.user_id, run.id, stage)
    return run


async def update_llm_run_stage(
    session: AsyncSession,
    run: LlmRun,
    *,
    stage: str,
    display_text_md: str | None = None,
) -> LlmRun:
    if run.status in TERMINAL_STATUSES:
        raise LlmRunError("run_status_conflict")
    run.stage = stage
    run.updated_at = datetime.now(UTC)
    if display_text_md is not None:
        run.display_text_md = display_text_md
    await session.commit()
    await session.refresh(run)
    logger.info("llm run stage user_id=%s run_id=%s stage=%s", run.user_id, run.id, stage)
    return run


async def cancel_llm_run(session: AsyncSession, user: AppUser, run_id: int) -> LlmRun:
    run = await get_llm_run_for_user(session, user, run_id)
    if run.status in TERMINAL_STATUSES:
        raise LlmRunError("run_status_conflict")
    run.cancel_requested = True
    run.status = "canceled"
    run.stage = "canceled"
    run.finished_at = datetime.now(UTC)
    run.updated_at = run.finished_at
    await session.commit()
    await session.refresh(run)
    logger.info("llm run canceled user_id=%s run_id=%s stage=%s", user.id, run.id, run.stage)
    return run


async def succeed_llm_run(
    session: AsyncSession,
    run: LlmRun,
    *,
    result: dict[str, Any],
    display_text_md: str,
) -> LlmRun:
    run.status = "succeeded"
    run.stage = "completed"
    run.result_json = result
    run.display_text_md = display_text_md
    run.finished_at = datetime.now(UTC)
    run.updated_at = run.finished_at
    await session.commit()
    await session.refresh(run)
    logger.info("llm run completed user_id=%s run_id=%s status=%s", run.user_id, run.id, run.status)
    return run


async def fail_llm_run(
    session: AsyncSession,
    run: LlmRun,
    *,
    error_code: str,
    error_message: str,
) -> LlmRun:
    run.status = "failed"
    run.stage = "failed"
    run.error_code = error_code
    run.error_message = error_message
    run.finished_at = datetime.now(UTC)
    run.updated_at = run.finished_at
    await session.commit()
    await session.refresh(run)
    logger.warning(
        "llm run failed user_id=%s run_id=%s error_code=%s stage=%s",
        run.user_id,
        run.id,
        error_code,
        run.stage,
    )
    return run
```

- [ ] **Step 4: Run service tests**

Run:

```bash
uv run pytest backend/tests/test_llm_run_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/llm_run_service.py backend/tests/test_llm_run_service.py
git commit -m "feat: add llm run state service"
```

---

### Task 4: LLM Run API Routes And Streaming Shell

**Files:**
- Create: `backend/app/api/llm_runs.py`
- Create: `backend/tests/test_llm_runs_api.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write API tests**

Create `backend/tests/test_llm_runs_api.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from backend.app.api.auth import current_user_dependency
from backend.app.main import app
from backend.app.models.auth import AppUser


def fake_user() -> AppUser:
    now = datetime.now(UTC)
    return AppUser(
        id=42,
        username="alice",
        email="alice@example.com",
        password_hash="hash",
        display_name="Alice",
        status="active",
        created_at=now,
        updated_at=now,
    )


def test_create_llm_run_requires_authentication() -> None:
    client = TestClient(app)

    response = client.post("/api/llm-runs", json={"kind": "goal_plan_generate", "payload": {}})

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


def test_create_llm_run_returns_stream_url(monkeypatch) -> None:
    async def fake_create(
        session: Any,
        user: AppUser,
        *,
        kind: str,
        payload: dict[str, Any] | None = None,
        related_type: str = "",
        related_id: int | None = None,
    ):
        return type("Run", (), {"id": 9, "kind": kind, "status": "pending", "stage": "queued"})()

    monkeypatch.setattr("backend.app.api.llm_runs.create_llm_run", fake_create)
    app.dependency_overrides[current_user_dependency] = fake_user
    try:
        client = TestClient(app)
        response = client.post(
            "/api/llm-runs",
            json={"kind": "goal_plan_generate", "payload": {"draft_id": 3}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "run_id": 9,
        "kind": "goal_plan_generate",
        "status": "pending",
        "stage": "queued",
        "stream_url": "/api/llm-runs/9/stream",
    }


def test_cancel_llm_run_maps_status_conflict(monkeypatch) -> None:
    from backend.app.services.llm_run_service import LlmRunError

    async def fake_cancel(session: Any, user: AppUser, run_id: int):
        raise LlmRunError("run_status_conflict")

    monkeypatch.setattr("backend.app.api.llm_runs.cancel_llm_run", fake_cancel)
    app.dependency_overrides[current_user_dependency] = fake_user
    try:
        client = TestClient(app)
        response = client.post("/api/llm-runs/7/cancel")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"] == "run_status_conflict"
```

- [ ] **Step 2: Run API tests and verify failure**

Run:

```bash
uv run pytest backend/tests/test_llm_runs_api.py -q
```

Expected: FAIL because `/api/llm-runs` is not registered.

- [ ] **Step 3: Add route module**

Create `backend/app/api/llm_runs.py`:

```python
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.auth import current_user_dependency
from backend.app.db.session import async_session_factory, get_session
from backend.app.models.auth import AppUser
from backend.app.schemas.llm_run import (
    LlmRunCancelResponse,
    LlmRunCreateRequest,
    LlmRunCreateResponse,
    LlmRunStatusResponse,
)
from backend.app.services.llm_orchestrator import execute_llm_run
from backend.app.services.llm_run_events import LlmRunEvent, encode_sse, event_hub
from backend.app.services.llm_run_service import (
    LlmRunError,
    cancel_llm_run,
    create_llm_run,
    get_llm_run_for_user,
)


router = APIRouter(prefix="/llm-runs", tags=["llm-runs"])


def _http_error(exc: LlmRunError) -> HTTPException:
    status_code = 404 if exc.detail == "run_not_found" else 400
    if exc.detail == "run_status_conflict":
        status_code = 409
    return HTTPException(status_code=status_code, detail=exc.detail)


def _related_from_payload(payload: LlmRunCreateRequest) -> tuple[str, int | None]:
    if payload.kind in {"goal_plan_generate", "goal_followup"} and "draft_id" in payload.payload:
        return "goal_calibration_draft", int(payload.payload["draft_id"])
    if payload.kind == "study_plan_adjustment" and "plan_id" in payload.payload:
        return "study_plan", int(payload.payload["plan_id"])
    return "", None


@router.post("", response_model=LlmRunCreateResponse)
async def create_llm_run_route(
    payload: LlmRunCreateRequest,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    related_type, related_id = _related_from_payload(payload)
    run = await create_llm_run(
        session,
        user,
        kind=payload.kind,
        payload=payload.payload,
        related_type=related_type,
        related_id=related_id,
    )
    return {
        "run_id": run.id,
        "kind": run.kind,
        "status": run.status,
        "stage": run.stage,
        "stream_url": f"/api/llm-runs/{run.id}/stream",
    }


@router.get("/{run_id}", response_model=LlmRunStatusResponse)
async def llm_run_status_route(
    run_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        run = await get_llm_run_for_user(session, user, run_id)
    except LlmRunError as exc:
        raise _http_error(exc) from exc
    return {
        "run_id": run.id,
        "kind": run.kind,
        "status": run.status,
        "stage": run.stage,
        "display_text_md": run.display_text_md,
        "result": run.result_json,
        "error_code": run.error_code or None,
        "error_message": run.error_message or None,
        "can_retry": run.status in {"failed", "canceled"},
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


@router.post("/{run_id}/cancel", response_model=LlmRunCancelResponse)
async def cancel_llm_run_route(
    run_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        run = await cancel_llm_run(session, user, run_id)
    except LlmRunError as exc:
        raise _http_error(exc) from exc
    await event_hub.publish(run_id, LlmRunEvent("canceled", {"run_id": run_id, "status": "canceled"}))
    await event_hub.publish(run_id, LlmRunEvent("done", {"run_id": run_id}))
    return {"run_id": run.id, "status": run.status, "cancel_requested": run.cancel_requested}


@router.get("/{run_id}/stream")
async def stream_llm_run_route(
    run_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    try:
        run = await get_llm_run_for_user(session, user, run_id)
    except LlmRunError as exc:
        raise _http_error(exc) from exc

    if run.status == "pending" and not event_hub.has_task(run_id):
        task = asyncio.create_task(execute_llm_run(async_session_factory, run_id, user.id))
        event_hub.set_task(run_id, task)

    async def event_stream() -> AsyncIterator[str]:
        async for event in event_hub.subscribe(run_id):
            yield encode_sse(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 4: Add temporary orchestrator shell**

Create `backend/app/services/llm_orchestrator.py` with a shell so API tests import:

```python
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.services.llm_run_events import LlmRunEvent, event_hub


async def execute_llm_run(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: int,
    user_id: int,
) -> None:
    await event_hub.publish(run_id, LlmRunEvent("error", {"run_id": run_id, "error_code": "flow_not_implemented"}))
    await event_hub.publish(run_id, LlmRunEvent("done", {"run_id": run_id}))
```

This shell is replaced in Task 7 after provider and flows exist.

- [ ] **Step 5: Register router**

Modify `backend/app/main.py`:

```python
from backend.app.api.llm_runs import router as llm_runs_router
```

Inside `create_app()`:

```python
application.include_router(llm_runs_router, prefix=settings.api_prefix)
```

- [ ] **Step 6: Run API tests**

Run:

```bash
uv run pytest backend/tests/test_llm_runs_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/llm_runs.py backend/app/main.py backend/app/services/llm_orchestrator.py backend/tests/test_llm_runs_api.py
git commit -m "feat: add llm run api shell"
```

---

### Task 5: OpenAI Responses Provider Interface

**Files:**
- Create: `backend/app/services/llm_providers/__init__.py`
- Create: `backend/app/services/llm_providers/base.py`
- Create: `backend/app/services/llm_providers/openai_responses.py`
- Create: `backend/tests/test_openai_responses_provider.py`

- [ ] **Step 1: Write provider tests**

Create `backend/tests/test_openai_responses_provider.py`:

```python
from __future__ import annotations

from types import SimpleNamespace

from backend.app.services.llm_providers.openai_responses import event_to_text_delta


def test_event_to_text_delta_reads_response_text_delta() -> None:
    event = SimpleNamespace(type="response.output_text.delta", delta="你好")

    assert event_to_text_delta(event) == "你好"


def test_event_to_text_delta_ignores_non_text_events() -> None:
    event = SimpleNamespace(type="response.created")

    assert event_to_text_delta(event) == ""
```

- [ ] **Step 2: Run provider tests and verify failure**

Run:

```bash
uv run pytest backend/tests/test_openai_responses_provider.py -q
```

Expected: FAIL with missing provider module.

- [ ] **Step 3: Add provider base types**

Create `backend/app/services/llm_providers/base.py`:

```python
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderChunk:
    text_delta: str = ""
    final_text: str = ""


class LlmProvider(Protocol):
    async def stream_text(
        self,
        *,
        model: str,
        instructions: str,
        input_text: str,
    ) -> AsyncIterator[ProviderChunk]: ...
```

- [ ] **Step 4: Add OpenAI Responses adapter**

Create `backend/app/services/llm_providers/openai_responses.py`:

```python
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from backend.app.services.llm_providers.base import ProviderChunk


def event_to_text_delta(event: Any) -> str:
    if getattr(event, "type", "") == "response.output_text.delta":
        return str(getattr(event, "delta", ""))
    return ""


class OpenAIResponsesProvider:
    def __init__(self, *, api_key: str, base_url: str) -> None:
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def stream_text(
        self,
        *,
        model: str,
        instructions: str,
        input_text: str,
    ) -> AsyncIterator[ProviderChunk]:
        stream = await self.client.responses.create(
            model=model,
            instructions=instructions,
            input=input_text,
            stream=True,
        )
        final_parts: list[str] = []
        async for event in stream:
            delta = event_to_text_delta(event)
            if not delta:
                continue
            final_parts.append(delta)
            yield ProviderChunk(text_delta=delta)
        yield ProviderChunk(final_text="".join(final_parts))
```

- [ ] **Step 5: Export provider types**

Create `backend/app/services/llm_providers/__init__.py`:

```python
from backend.app.services.llm_providers.base import LlmProvider, ProviderChunk
from backend.app.services.llm_providers.openai_responses import OpenAIResponsesProvider

__all__ = ["LlmProvider", "OpenAIResponsesProvider", "ProviderChunk"]
```

- [ ] **Step 6: Run provider tests**

Run:

```bash
uv run pytest backend/tests/test_openai_responses_provider.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/llm_providers backend/tests/test_openai_responses_provider.py
git commit -m "feat: add openai responses stream provider"
```

---

### Task 6: Learning Flows With Fake Provider Tests

**Files:**
- Create: `backend/app/services/learning_flows/__init__.py`
- Create: `backend/app/services/learning_flows/goal_calibration.py`
- Create: `backend/app/services/learning_flows/goal_plan.py`
- Create: `backend/app/services/learning_flows/study_plan_adjustment.py`
- Create: `backend/tests/test_learning_flows.py`
- Modify: `backend/app/services/learning_plan_llm.py`
- Modify: `backend/app/services/study_plan_service.py`

- [ ] **Step 1: Write flow tests**

Create `backend/tests/test_learning_flows.py`:

```python
from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.models.auth import AppUser
from backend.app.models.learning import GoalCalibrationDraft
from backend.app.models.llm_run import LlmRun
from backend.app.models.problem import Base, Problem
from backend.app.services.learning_flows.goal_plan import run_goal_plan_generate
from backend.app.services.llm_providers.base import ProviderChunk
from backend.app.services.llm_run_events import LlmRunEvent


class FakeProvider:
    async def stream_text(self, *, model: str, instructions: str, input_text: str):
        yield ProviderChunk(text_delta="我会按三个阶段生成计划。")
        yield ProviderChunk(
            final_text=json.dumps(
                {
                    "title": "面试冲刺计划",
                    "target_snapshot": {"goal_type": "interview_sprint"},
                    "generation_summary_md": "按三个阶段训练。",
                    "stages": [
                        {
                            "title": "数组基础",
                            "objective_md": "巩固基础题型。",
                            "focus_tags": ["array"],
                            "assessment_criteria": ["能讲清思路"],
                            "items": [
                                {
                                    "problem_slug": "two-sum",
                                    "difficulty": "Easy",
                                    "skill_tags": ["array"],
                                    "suggested_mode": "guided",
                                    "recommendation_reason": "训练哈希表入门",
                                }
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
            )
        )


@pytest_asyncio.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def create_user_problem_draft(session: AsyncSession) -> tuple[AppUser, GoalCalibrationDraft, LlmRun]:
    now = datetime.now(UTC)
    unique = uuid4().hex
    user = AppUser(
        username=f"user-{unique}",
        email=f"user-{unique}@example.com",
        password_hash="hash",
        display_name="Learner",
        status="active",
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    await session.flush()
    session.add(
        Problem(
            frontend_id="1",
            slug="two-sum",
            title="Two Sum",
            translated_title="两数之和",
            difficulty="Easy",
            statement_md="# Two Sum",
            metadata_json={"topic_tags": [{"slug": "array", "name": "Array"}]},
            leetcode_url="https://leetcode.cn/problems/two-sum/",
            is_paid_only=False,
            created_at=now,
            updated_at=now,
        )
    )
    draft = GoalCalibrationDraft(
        user_id=user.id,
        input_json={"goal_type": "interview_sprint"},
        status="collecting_input",
    )
    session.add(draft)
    await session.flush()
    run = LlmRun(user_id=user.id, kind="goal_plan_generate", related_type="goal_calibration_draft", related_id=draft.id)
    session.add(run)
    await session.commit()
    await session.refresh(user)
    await session.refresh(draft)
    await session.refresh(run)
    return user, draft, run


@pytest.mark.asyncio
async def test_goal_plan_generate_flow_updates_draft_and_emits_result(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user, draft, run = await create_user_problem_draft(session)
        events: list[LlmRunEvent] = []

        async def publish(event: LlmRunEvent) -> None:
            events.append(event)

        result = await run_goal_plan_generate(
            session,
            user_id=user.id,
            run=run,
            provider=FakeProvider(),
            model_name="gpt-test",
            publish=publish,
        )

        await session.refresh(draft)
        assert result["draft_id"] == draft.id
        assert draft.draft_plan_json["stages"][0]["items"][0]["problem_slug"] == "two-sum"
        assert any(event.name == "delta" for event in events)
        assert any(event.name == "result" for event in events)
```

- [ ] **Step 2: Run flow tests and verify failure**

Run:

```bash
uv run pytest backend/tests/test_learning_flows.py -q
```

Expected: FAIL with missing `learning_flows`.

- [ ] **Step 3: Add shared prompt/schema module content**

Move the current prompt/schema constants from `backend/app/services/learning_plan_llm.py` into `backend/app/services/learning_flows/goal_plan.py` or a small sibling module. Keep these exact names available for tests during migration:

```python
PROMPT_VERSION = "goal-plan-v3-streaming"
PLAN_DRAFT_INSTRUCTIONS = "默认语言语境：简体中文。根据用户目标生成阶段化学习计划。只输出 JSON。"
REPAIR_PLAN_INSTRUCTIONS = "默认语言语境：简体中文。根据 validation_report 修复学习计划。只输出 JSON。"
```

If existing tests still import `PROMPT_VERSION` from `learning_plan_llm.py`, re-export it there:

```python
from backend.app.services.learning_flows.goal_plan import PROMPT_VERSION
```

- [ ] **Step 4: Add `goal_plan` flow**

Create `backend/app/services/learning_flows/goal_plan.py`:

```python
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.learning import GoalCalibrationDraft
from backend.app.models.llm_run import LlmRun
from backend.app.services.learning_plan_validator import validate_and_repair_plan_draft
from backend.app.services.llm_providers.base import LlmProvider
from backend.app.services.llm_run_events import LlmRunEvent


PROMPT_VERSION = "goal-plan-v3-streaming"
PLAN_DRAFT_INSTRUCTIONS = (
    "默认语言语境：简体中文。根据用户目标生成阶段化学习计划。"
    "返回 JSON，且 stages 至少包含 1 个阶段；正式题单会由后端校验。"
)


async def _draft_for_run(session: AsyncSession, user_id: int, run: LlmRun) -> GoalCalibrationDraft:
    result = await session.execute(
        select(GoalCalibrationDraft).where(
            GoalCalibrationDraft.id == run.related_id,
            GoalCalibrationDraft.user_id == user_id,
        )
    )
    draft = result.scalar_one_or_none()
    if draft is None:
        raise ValueError("goal_draft_not_found")
    return draft


async def run_goal_plan_generate(
    session: AsyncSession,
    *,
    user_id: int,
    run: LlmRun,
    provider: LlmProvider,
    model_name: str,
    publish: Callable[[LlmRunEvent], Awaitable[None]],
) -> dict[str, Any]:
    draft = await _draft_for_run(session, user_id, run)
    await publish(LlmRunEvent("progress", {"run_id": run.id, "stage": "generating_plan_outline", "message": "正在生成计划思路"}))

    display_parts: list[str] = []
    final_text = ""
    async for chunk in provider.stream_text(
        model=model_name,
        instructions=PLAN_DRAFT_INSTRUCTIONS,
        input_text=json.dumps({"payload": draft.input_json, "history": draft.followup_messages_json}, ensure_ascii=False),
    ):
        if chunk.text_delta:
            display_parts.append(chunk.text_delta)
            await publish(LlmRunEvent("delta", {"run_id": run.id, "text": chunk.text_delta}))
        if chunk.final_text:
            final_text = chunk.final_text

    raw_plan = json.loads(final_text)
    await publish(LlmRunEvent("progress", {"run_id": run.id, "stage": "validating_problem_library", "message": "正在校验题库和修复不可用题目"}))
    repaired, report, repair_log = await validate_and_repair_plan_draft(session, raw_plan)

    if not report.get("valid"):
        raise ValueError("plan_validation_failed")

    draft.draft_plan_json = repaired
    draft.validation_report_json = report
    draft.repair_log_json = repair_log
    draft.prompt_version = PROMPT_VERSION
    draft.model_name = model_name
    draft.status = "draft_ready"
    await session.commit()
    await session.refresh(draft)

    result = {
        "draft_id": draft.id,
        "status": draft.status,
        "stage_count": len(repaired.get("stages", [])),
        "item_count": sum(len(stage.get("items", [])) for stage in repaired.get("stages", [])),
    }
    await publish(LlmRunEvent("result", {"run_id": run.id, "status": "succeeded", "result": result}))
    return result
```

- [ ] **Step 5: Add flow package shells**

Create `backend/app/services/learning_flows/goal_calibration.py`:

```python
from __future__ import annotations


class GoalFollowupFlowUnavailable(Exception):
    pass
```

Create `backend/app/services/learning_flows/study_plan_adjustment.py`:

```python
from __future__ import annotations


class StudyPlanAdjustmentFlowUnavailable(Exception):
    pass
```

Create `backend/app/services/learning_flows/__init__.py`:

```python
from backend.app.services.learning_flows.goal_plan import run_goal_plan_generate

__all__ = ["run_goal_plan_generate"]
```

- [ ] **Step 6: Run flow tests**

Run:

```bash
uv run pytest backend/tests/test_learning_flows.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/learning_flows backend/app/services/learning_plan_llm.py backend/app/services/study_plan_service.py backend/tests/test_learning_flows.py
git commit -m "feat: add streaming learning plan flow"
```

---

### Task 7: Orchestrator Execution And Credential Selection

**Files:**
- Modify: `backend/app/services/llm_orchestrator.py`
- Modify: `backend/tests/test_llm_runs_api.py`

- [ ] **Step 1: Add orchestrator unit test**

Append to `backend/tests/test_llm_runs_api.py`:

```python
def test_stream_route_starts_pending_run(monkeypatch) -> None:
    started: list[int] = []

    async def fake_get(session: Any, user: AppUser, run_id: int):
        return type("Run", (), {"id": run_id, "user_id": user.id, "status": "pending", "kind": "goal_plan_generate"})()

    from backend.app.services.llm_run_events import LlmRunEvent, event_hub

    async def fake_execute(session_factory: Any, run_id: int, user_id: int):
        started.append(run_id)
        await event_hub.publish(run_id, LlmRunEvent("done", {"run_id": run_id}))

    monkeypatch.setattr("backend.app.api.llm_runs.get_llm_run_for_user", fake_get)
    monkeypatch.setattr("backend.app.api.llm_runs.execute_llm_run", fake_execute)
    app.dependency_overrides[current_user_dependency] = fake_user
    try:
        client = TestClient(app)
        with client.stream("GET", "/api/llm-runs/99/stream") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
    finally:
        app.dependency_overrides.clear()

    assert started == [99]
```

- [ ] **Step 2: Run route test and verify behavior**

Run:

```bash
uv run pytest backend/tests/test_llm_runs_api.py::test_stream_route_starts_pending_run -q
```

Expected: PASS after the stream route starts the fake executor and the fake executor publishes `done`.

- [ ] **Step 3: Replace orchestrator shell**

Modify `backend/app/services/llm_orchestrator.py`:

```python
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core.config import settings
from backend.app.models.auth import AppUser
from backend.app.models.llm_run import LlmRun
from backend.app.services.credential_crypto import decrypt_api_key
from backend.app.services.learning_flows.goal_plan import run_goal_plan_generate
from backend.app.services.llm_credential_service import select_llm_credential_for_user
from backend.app.services.llm_providers.openai_responses import OpenAIResponsesProvider
from backend.app.services.llm_run_events import LlmRunEvent, event_hub
from backend.app.services.llm_run_service import (
    fail_llm_run,
    mark_llm_run_running,
    succeed_llm_run,
)


logger = logging.getLogger(__name__)


async def _load_run_and_user(
    session: AsyncSession,
    run_id: int,
    user_id: int,
) -> tuple[LlmRun, AppUser]:
    run_result = await session.execute(select(LlmRun).where(LlmRun.id == run_id, LlmRun.user_id == user_id))
    run = run_result.scalar_one()
    user_result = await session.execute(select(AppUser).where(AppUser.id == user_id))
    user = user_result.scalar_one()
    return run, user


async def execute_llm_run(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: int,
    user_id: int,
) -> None:
    async with session_factory() as session:
        run, user = await _load_run_and_user(session, run_id, user_id)
        try:
            await event_hub.publish(run_id, LlmRunEvent("started", {"run_id": run_id, "kind": run.kind}))
            await event_hub.publish(run_id, LlmRunEvent("progress", {"run_id": run_id, "stage": "selecting_credential", "message": "正在选择模型资产"}))
            credential = await select_llm_credential_for_user(session, user)
            api_key = decrypt_api_key(credential.api_key_ciphertext, settings.credential_encryption_key)
            await mark_llm_run_running(
                session,
                run,
                stage="selecting_credential",
                llm_credential_id=credential.id,
                model_name=credential.model_name,
            )
            provider = OpenAIResponsesProvider(api_key=api_key, base_url=credential.base_url)

            if run.kind == "goal_plan_generate":
                result = await run_goal_plan_generate(
                    session,
                    user_id=user_id,
                    run=run,
                    provider=provider,
                    model_name=credential.model_name,
                    publish=lambda event: event_hub.publish(run_id, event),
                )
                await succeed_llm_run(session, run, result=result, display_text_md=run.display_text_md)
                await event_hub.publish(run_id, LlmRunEvent("done", {"run_id": run_id}))
                return

            await fail_llm_run(session, run, error_code="run_kind_unsupported", error_message="当前生成类型暂未接入")
            await event_hub.publish(run_id, LlmRunEvent("error", {"run_id": run_id, "error_code": "run_kind_unsupported", "message": "当前生成类型暂未接入"}))
            await event_hub.publish(run_id, LlmRunEvent("done", {"run_id": run_id}))
        except Exception as exc:
            logger.exception("llm run crashed user_id=%s run_id=%s reason=%s", user_id, run_id, type(exc).__name__)
            await fail_llm_run(session, run, error_code="llm_provider_error", error_message="模型生成失败")
            await event_hub.publish(run_id, LlmRunEvent("error", {"run_id": run_id, "error_code": "llm_provider_error", "message": "模型生成失败"}))
            await event_hub.publish(run_id, LlmRunEvent("done", {"run_id": run_id}))
```

- [ ] **Step 4: Fix display text persistence**

In `run_goal_plan_generate`, whenever a `delta` is emitted, update `run.display_text_md` before final success:

```python
run.display_text_md = "".join(display_parts)
```

Commit it through the same session before `result`:

```python
await session.flush()
```

- [ ] **Step 5: Run backend streaming shell tests**

Run:

```bash
uv run pytest backend/tests/test_llm_runs_api.py backend/tests/test_learning_flows.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/llm_orchestrator.py backend/app/services/learning_flows/goal_plan.py backend/tests/test_llm_runs_api.py
git commit -m "feat: execute llm run through orchestrator"
```

---

### Task 8: Frontend LLM Run API And Hook

**Files:**
- Create: `frontend/src/api/llmRuns.ts`
- Create: `frontend/src/hooks/useLlmRun.ts`
- Create: `frontend/src/hooks/useLlmRun.test.tsx`

- [ ] **Step 1: Write hook tests**

Create `frontend/src/hooks/useLlmRun.test.tsx`:

```tsx
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useLlmRun } from './useLlmRun'

class FakeEventSource {
  static instances: FakeEventSource[] = []
  listeners: Record<string, Array<(event: MessageEvent) => void>> = {}
  url: string

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(name: string, listener: (event: MessageEvent) => void) {
    this.listeners[name] = [...(this.listeners[name] ?? []), listener]
  }

  close() {}

  emit(name: string, payload: unknown) {
    for (const listener of this.listeners[name] ?? []) {
      listener({ data: JSON.stringify(payload) } as MessageEvent)
    }
  }
}

function okJson(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('useLlmRun', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    FakeEventSource.instances = []
  })

  it('creates a run and accumulates delta events', async () => {
    vi.stubGlobal('EventSource', FakeEventSource)
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        okJson({
          run_id: 5,
          kind: 'goal_plan_generate',
          status: 'pending',
          stage: 'queued',
          stream_url: '/api/llm-runs/5/stream',
        }),
      ),
    )

    const { result } = renderHook(() => useLlmRun())

    await act(async () => {
      await result.current.startRun('goal_plan_generate', { draft_id: 3 })
    })

    act(() => {
      FakeEventSource.instances[0].emit('progress', { stage: 'validating', message: '正在校验题库' })
      FakeEventSource.instances[0].emit('delta', { text: '计划生成中' })
      FakeEventSource.instances[0].emit('result', { result: { draft_id: 3 } })
    })

    await waitFor(() => expect(result.current.displayText).toBe('计划生成中'))
    expect(result.current.stage).toBe('validating')
    expect(result.current.result).toEqual({ draft_id: 3 })
  })
})
```

- [ ] **Step 2: Run hook test and verify failure**

Run:

```bash
cd frontend && corepack pnpm test -- useLlmRun.test.tsx
```

Expected: FAIL with missing hook.

- [ ] **Step 3: Add API client**

Create `frontend/src/api/llmRuns.ts`:

```ts
import { requestJson } from './client'

export type LlmRunKind =
  | 'goal_followup'
  | 'goal_plan_generate'
  | 'study_plan_adjustment'
  | 'coach_message'
  | 'code_review'
  | 'reflection'

export type LlmRunStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'canceled'

export type LlmRunCreateResponse = {
  run_id: number
  kind: LlmRunKind
  status: LlmRunStatus
  stage: string
  stream_url: string
}

export type LlmRunStatusResponse = {
  run_id: number
  kind: LlmRunKind
  status: LlmRunStatus
  stage: string
  display_text_md: string
  result: Record<string, unknown>
  error_code: string | null
  error_message: string | null
  can_retry: boolean
}

export function createLlmRun(kind: LlmRunKind, payload: Record<string, unknown>) {
  return requestJson<LlmRunCreateResponse>('/api/llm-runs', {
    method: 'POST',
    body: { kind, payload },
  })
}

export function getLlmRun(runId: number) {
  return requestJson<LlmRunStatusResponse>(`/api/llm-runs/${runId}`)
}

export function cancelLlmRun(runId: number) {
  return requestJson<{ run_id: number; status: LlmRunStatus; cancel_requested: boolean }>(
    `/api/llm-runs/${runId}/cancel`,
    { method: 'POST' },
  )
}
```

- [ ] **Step 4: Add hook**

Create `frontend/src/hooks/useLlmRun.ts`:

```ts
import { useRef, useState } from 'react'

import { cancelLlmRun, createLlmRun, type LlmRunKind, type LlmRunStatus } from '../api/llmRuns'

type LlmRunResult = Record<string, unknown> | null

export function useLlmRun() {
  const [runId, setRunId] = useState<number | null>(null)
  const [status, setStatus] = useState<LlmRunStatus>('pending')
  const [stage, setStage] = useState('idle')
  const [displayText, setDisplayText] = useState('')
  const [result, setResult] = useState<LlmRunResult>(null)
  const [error, setError] = useState<string | null>(null)
  const sourceRef = useRef<EventSource | null>(null)

  function connect(streamUrl: string) {
    sourceRef.current?.close()
    const source = new EventSource(streamUrl)
    sourceRef.current = source

    source.addEventListener('started', () => setStatus('running'))
    source.addEventListener('progress', (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as { stage?: string }
      setStage(payload.stage ?? 'running')
    })
    source.addEventListener('delta', (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as { text?: string }
      setDisplayText((current) => `${current}${payload.text ?? ''}`)
    })
    source.addEventListener('result', (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as { result?: Record<string, unknown> }
      setStatus('succeeded')
      setResult(payload.result ?? null)
    })
    source.addEventListener('error', (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as { error_code?: string; message?: string }
      setStatus('failed')
      setError(payload.message ?? payload.error_code ?? 'request_failed')
    })
    source.addEventListener('canceled', () => {
      setStatus('canceled')
    })
    source.addEventListener('done', () => {
      source.close()
    })
  }

  async function startRun(kind: LlmRunKind, payload: Record<string, unknown>) {
    setDisplayText('')
    setResult(null)
    setError(null)
    const run = await createLlmRun(kind, payload)
    setRunId(run.run_id)
    setStatus(run.status)
    setStage(run.stage)
    connect(run.stream_url)
  }

  async function cancelRun() {
    if (runId === null) {
      return
    }
    await cancelLlmRun(runId)
    setStatus('canceled')
    sourceRef.current?.close()
  }

  return { runId, status, stage, displayText, result, error, startRun, cancelRun }
}
```

- [ ] **Step 5: Run hook test**

Run:

```bash
cd frontend && corepack pnpm test -- useLlmRun.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/llmRuns.ts frontend/src/hooks/useLlmRun.ts frontend/src/hooks/useLlmRun.test.tsx
git commit -m "feat: add frontend llm run hook"
```

---

### Task 9: Streaming Panel Component

**Files:**
- Create: `frontend/src/components/LlmStreamingPanel.tsx`
- Create: `frontend/src/components/LlmStreamingPanel.test.tsx`

- [ ] **Step 1: Write component tests**

Create `frontend/src/components/LlmStreamingPanel.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { LlmStreamingPanel } from './LlmStreamingPanel'

describe('LlmStreamingPanel', () => {
  it('shows progress text and cancel button while running', () => {
    const cancel = vi.fn()

    render(
      <LlmStreamingPanel
        title="正在生成计划"
        status="running"
        stage="validating_problem_library"
        displayText="我会按三个阶段训练。"
        error={null}
        onCancel={cancel}
      />,
    )

    expect(screen.getByText('正在生成计划')).toBeInTheDocument()
    expect(screen.getByText('validating_problem_library')).toBeInTheDocument()
    expect(screen.getByText('我会按三个阶段训练。')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '停止生成' }))
    expect(cancel).toHaveBeenCalledTimes(1)
  })

  it('hides cancel button after success', () => {
    render(
      <LlmStreamingPanel
        title="计划已完成"
        status="succeeded"
        stage="completed"
        displayText=""
        error={null}
        onCancel={() => undefined}
      />,
    )

    expect(screen.queryByRole('button', { name: '停止生成' })).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run component test and verify failure**

Run:

```bash
cd frontend && corepack pnpm test -- LlmStreamingPanel.test.tsx
```

Expected: FAIL with missing component.

- [ ] **Step 3: Add component**

Create `frontend/src/components/LlmStreamingPanel.tsx`:

```tsx
import { Alert, Button, Space, Spin, Typography } from 'antd'

import type { LlmRunStatus } from '../api/llmRuns'

type Props = {
  title: string
  status: LlmRunStatus
  stage: string
  displayText: string
  error: string | null
  onCancel: () => void
  children?: React.ReactNode
}

export function LlmStreamingPanel({
  title,
  status,
  stage,
  displayText,
  error,
  onCancel,
  children,
}: Props) {
  const running = status === 'pending' || status === 'running'

  return (
    <div className="workflow-panel">
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Space align="center">
          {running ? <Spin size="small" /> : null}
          <Typography.Title level={3} style={{ margin: 0 }}>
            {title}
          </Typography.Title>
        </Space>
        <Typography.Text type="secondary">{stage}</Typography.Text>
        {displayText ? (
          <Typography.Paragraph>{displayText}</Typography.Paragraph>
        ) : null}
        {error ? <Alert showIcon type="error" message={error} /> : null}
        {children}
        {running ? <Button onClick={onCancel}>停止生成</Button> : null}
      </Space>
    </div>
  )
}
```

- [ ] **Step 4: Run component test**

Run:

```bash
cd frontend && corepack pnpm test -- LlmStreamingPanel.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/LlmStreamingPanel.tsx frontend/src/components/LlmStreamingPanel.test.tsx
git commit -m "feat: add llm streaming panel"
```

---

### Task 10: Migrate Goal Calibration Page To Run Flow

**Files:**
- Modify: `frontend/src/pages/GoalCalibrationPage.tsx`
- Modify: `frontend/src/pages/GoalCalibrationPage.test.tsx`
- Modify: `frontend/src/api/learning.ts`

- [ ] **Step 1: Update page test to expect run API**

Modify the first test in `frontend/src/pages/GoalCalibrationPage.test.tsx` so fetch responds to run creation:

```tsx
it('starts calibration through llm run and shows streaming text', async () => {
  class FakeEventSource {
    static instance: FakeEventSource
    listeners: Record<string, Array<(event: MessageEvent) => void>> = {}

    constructor() {
      FakeEventSource.instance = this
    }

    addEventListener(name: string, listener: (event: MessageEvent) => void) {
      this.listeners[name] = [...(this.listeners[name] ?? []), listener]
    }

    close() {}

    emit(name: string, payload: unknown) {
      for (const listener of this.listeners[name] ?? []) {
        listener({ data: JSON.stringify(payload) } as MessageEvent)
      }
    }
  }

  vi.stubGlobal('EventSource', FakeEventSource)
  const fetchMock = vi.fn(async () =>
    okJson({
      run_id: 3,
      kind: 'goal_followup',
      status: 'pending',
      stage: 'queued',
      stream_url: '/api/llm-runs/3/stream',
    }),
  )
  vi.stubGlobal('fetch', fetchMock)

  renderPage()

  fireEvent.click(screen.getByLabelText('面试冲刺'))
  fireEvent.click(screen.getByLabelText('1 到 3 个月'))
  fireEvent.click(screen.getByLabelText('Python3'))
  fireEvent.click(screen.getByRole('button', { name: '开始校准' }))

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/llm-runs',
      expect.objectContaining({ method: 'POST' }),
    ),
  )

  fireEvent.click(screen.getByText('目标校准'))
  FakeEventSource.instance.emit('delta', { text: '正在分析目标。' })

  expect(await screen.findByText('正在分析目标。')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run page test and verify failure**

Run:

```bash
cd frontend && corepack pnpm test -- GoalCalibrationPage.test.tsx
```

Expected: FAIL because page still calls `/api/goal-calibration`.

- [ ] **Step 3: Update page imports and hook usage**

Modify `frontend/src/pages/GoalCalibrationPage.tsx`:

```tsx
import { LlmStreamingPanel } from '../components/LlmStreamingPanel'
import { useLlmRun } from '../hooks/useLlmRun'
```

Inside component:

```tsx
const calibrationRun = useLlmRun()
const planRun = useLlmRun()
```

Replace start mutation usage in `submit`:

```tsx
function submit(values: GoalCalibrationPayload) {
  void calibrationRun.startRun('goal_followup', normalisePayload(values))
}
```

Render streaming panel when calibration is running:

```tsx
{calibrationRun.runId ? (
  <LlmStreamingPanel
    title="目标校准"
    status={calibrationRun.status}
    stage={calibrationRun.stage}
    displayText={calibrationRun.displayText}
    error={calibrationRun.error}
    onCancel={calibrationRun.cancelRun}
  />
) : null}
```

For plan generation button:

```tsx
<Button
  type="primary"
  onClick={() => {
    const draftId = Number(calibrationRun.result?.draft_id ?? draft?.draft_id ?? 0)
    void planRun.startRun('goal_plan_generate', { draft_id: draftId })
  }}
  disabled={!calibrationRun.result?.draft_id && !draft?.draft_id}
>
  生成计划草稿
</Button>
```

When `planRun.result` arrives, fetch the draft payload using an existing read endpoint if added during backend implementation, or use the `result` payload if it already includes the renderable plan draft. The first implementation should make `result` include the same shape as `PlanDraftResponse` so `setPlanDraft(planRun.result as PlanDraftResponse)` is safe:

```tsx
useEffect(() => {
  if (planRun.status === 'succeeded' && planRun.result) {
    setPlanDraft(planRun.result as PlanDraftResponse)
  }
}, [planRun.status, planRun.result])
```

- [ ] **Step 4: Remove obsolete generation calls from this page**

Keep `confirmPlan` from `frontend/src/api/learning.ts`. Stop using:

```tsx
startGoalCalibration
answerGoalFollowup
generatePlanDraft
```

Do not delete these API functions until backend compatibility tests are migrated.

- [ ] **Step 5: Run page test**

Run:

```bash
cd frontend && corepack pnpm test -- GoalCalibrationPage.test.tsx useLlmRun.test.tsx LlmStreamingPanel.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/GoalCalibrationPage.tsx frontend/src/pages/GoalCalibrationPage.test.tsx frontend/src/api/learning.ts
git commit -m "feat: stream goal calibration page"
```

---

### Task 11: Complete Backend Result Payloads For Goal Calibration And Plan Generation

**Files:**
- Modify: `backend/app/services/learning_flows/goal_calibration.py`
- Modify: `backend/app/services/learning_flows/goal_plan.py`
- Modify: `backend/app/services/llm_orchestrator.py`
- Modify: `backend/tests/test_learning_flows.py`

- [ ] **Step 1: Add followup flow test**

Append to `backend/tests/test_learning_flows.py`:

```python
@pytest.mark.asyncio
async def test_goal_followup_flow_creates_draft_from_payload(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from backend.app.services.learning_flows.goal_calibration import run_goal_followup

    async with session_factory() as session:
        now = datetime.now(UTC)
        user = AppUser(
            username="followup-user",
            email="followup@example.com",
            password_hash="hash",
            display_name="Learner",
            status="active",
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        run = LlmRun(
            user_id=user.id,
            kind="goal_followup",
            input_json={"goal_type": "interview_sprint"},
            related_type="",
            related_id=None,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        events: list[LlmRunEvent] = []

        async def publish(event: LlmRunEvent) -> None:
            events.append(event)

        result = await run_goal_followup(
            session,
            user_id=user.id,
            run=run,
            provider=FakeProvider(),
            model_name="gpt-test",
            publish=publish,
        )

        assert result["draft_id"] > 0
        assert "followup_question" in result
```

- [ ] **Step 2: Run followup test and verify failure**

Run:

```bash
uv run pytest backend/tests/test_learning_flows.py::test_goal_followup_flow_creates_draft_from_payload -q
```

Expected: FAIL because `run_goal_followup` is not implemented.

- [ ] **Step 3: Implement followup flow**

Replace `backend/app/services/learning_flows/goal_calibration.py`:

```python
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.learning import GoalCalibrationDraft
from backend.app.models.llm_run import LlmRun
from backend.app.services.llm_providers.base import LlmProvider
from backend.app.services.llm_run_events import LlmRunEvent


FOLLOWUP_INSTRUCTIONS = (
    "默认语言语境：简体中文。你是目标校准教练。"
    "只在必要时返回一个 JSON 问题；信息足够时返回 null。"
)


async def run_goal_followup(
    session: AsyncSession,
    *,
    user_id: int,
    run: LlmRun,
    provider: LlmProvider,
    model_name: str,
    publish: Callable[[LlmRunEvent], Awaitable[None]],
) -> dict[str, Any]:
    payload = run.input_json
    draft = GoalCalibrationDraft(user_id=user_id, input_json=payload, status="collecting_input")
    session.add(draft)
    await session.flush()
    await publish(LlmRunEvent("progress", {"run_id": run.id, "stage": "calibrating_goal", "message": "正在分析目标并判断是否需要追问"}))

    final_text = ""
    async for chunk in provider.stream_text(
        model=model_name,
        instructions=FOLLOWUP_INSTRUCTIONS,
        input_text=json.dumps({"payload": payload, "history": []}, ensure_ascii=False),
    ):
        if chunk.text_delta:
            await publish(LlmRunEvent("delta", {"run_id": run.id, "text": chunk.text_delta}))
        if chunk.final_text:
            final_text = chunk.final_text

    parsed = None if final_text.strip() == "null" else json.loads(final_text)
    if isinstance(parsed, dict):
        question = {
            "role": "assistant",
            "question_id": str(parsed.get("question_id", "q1")),
            "question": str(parsed.get("question", "")),
        }
        draft.followup_messages_json = [question]
        draft.status = "asking_followup"
        result = {
            "draft_id": draft.id,
            "status": draft.status,
            "followup_question": question["question"],
            "followup_question_id": question["question_id"],
            "remaining_followups": 2,
        }
    else:
        draft.status = "collecting_input"
        result = {
            "draft_id": draft.id,
            "status": draft.status,
            "followup_question": None,
            "followup_question_id": None,
            "remaining_followups": 3,
        }
    await session.commit()
    await session.refresh(draft)
    await publish(LlmRunEvent("result", {"run_id": run.id, "status": "succeeded", "result": result}))
    return result
```

- [ ] **Step 4: Make plan result renderable**

In `backend/app/services/learning_flows/goal_plan.py`, replace the summary-only `result` with a payload matching `PlanDraftResponse`:

```python
result = {
    "draft_id": draft.id,
    "status": draft.status,
    "target_snapshot": repaired.get("target_snapshot", draft.input_json),
    "generation_summary_md": repaired.get("generation_summary_md", ""),
    "stages": repaired.get("stages", []),
    "validation_report": report,
    "repair_log": repair_log,
    "uncertainty_notes": [],
}
```

- [ ] **Step 5: Dispatch followup kind in orchestrator**

In `backend/app/services/llm_orchestrator.py`, import:

```python
from backend.app.services.learning_flows.goal_calibration import run_goal_followup
```

Add before the plan branch:

```python
if run.kind == "goal_followup":
    result = await run_goal_followup(
        session,
        user_id=user_id,
        run=run,
        provider=provider,
        model_name=credential.model_name,
        publish=lambda event: event_hub.publish(run_id, event),
    )
    await succeed_llm_run(session, run, result=result, display_text_md=run.display_text_md)
    await event_hub.publish(run_id, LlmRunEvent("done", {"run_id": run_id}))
    return
```

The `create_llm_run` signature from Task 3 already accepts `payload: dict[str, Any] | None = None`. The route must pass `payload.payload`, and `LlmRun.input_json` must be the only place where pending input is stored.

- [ ] **Step 6: Run flow tests**

Run:

```bash
uv run pytest backend/tests/test_learning_flows.py backend/tests/test_llm_run_service.py backend/tests/test_llm_runs_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/learning_flows backend/app/services/llm_orchestrator.py backend/app/services/llm_run_service.py backend/app/api/llm_runs.py backend/tests/test_learning_flows.py backend/tests/test_llm_run_service.py backend/tests/test_llm_runs_api.py
git commit -m "feat: return streaming learning results"
```

---

### Task 12: Documentation Updates And Full Verification

**Files:**
- Modify: `docs/index.md`
- Modify: `docs/architecture/foundation.md`
- Modify: `docs/prd/prd.md`
- Modify: `docs/project-todolist.md`

- [ ] **Step 1: Update `docs/index.md`**

Add or adjust directory responsibilities:

```markdown
- `backend/app/api/llm_runs.py`：统一 LLM Run API，负责创建流式任务、SSE 订阅、取消和状态查询。
- `backend/app/services/llm_providers/`：大模型 provider 适配层，当前封装 OpenAI Responses 流式调用。
- `backend/app/services/learning_flows/`：学习场景 LLM 业务流程，负责目标校准、计划生成和计划调整的事件化编排。
- `frontend/src/hooks/useLlmRun.ts`：前端 LLM Run 状态和 SSE 事件管理 hook。
- `frontend/src/components/LlmStreamingPanel.tsx`：通用流式输出和阶段进度展示组件。
```

- [ ] **Step 2: Update `docs/architecture/foundation.md`**

Add a section under backend services:

```markdown
### 统一 LLM Run 流式层

大模型调用统一通过后端 LLM Run 层发起。前端先创建 run，再通过 SSE 接收 `started`、`progress`、`delta`、`result`、`error`、`canceled` 和 `done` 事件。API key、模型资产选择、OpenAI Responses 调用、题库校验和 repair 仍在后端边界内完成。

第一版持久化 run 状态、阶段、最终结果、错误摘要和取消状态，不保存完整 token 日志。页面刷新后可以恢复 run 状态和最终结果；未完成的运行在单进程开发环境中通过内存事件 hub 继续推送，后续多 worker 部署再引入外部队列或持久事件表。
```

- [ ] **Step 3: Update `docs/prd/prd.md`**

In non-functional requirements and page behavior, add:

```markdown
- 大模型调用应提供 ChatGPT 式流式反馈：用户可以看到可展示的输出片段和后台阶段进度。
- 长耗时生成必须支持停止生成；停止后的半截结果不能被确认成正式计划或训练结果。
- 学习计划生成过程中，未经过本地题库校验和 repair 的题单不得作为正式题单展示。
- 页面刷新后应能恢复 run 状态和已完成的最终结果，不要求回放完整 token。
```

- [ ] **Step 4: Update `docs/project-todolist.md`**

Add a task between T1/T2/T3 or as T3 prerequisite:

```markdown
### T2.5：统一 LLM Run 流式体验层

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 已完成 |
| 主要交付 | LLM Run 状态表、SSE 事件协议、停止生成、目标校准和计划生成流式体验 |
| 完成日期 | 2026-05-21 |

**验证命令**

- `uv run pytest backend/tests/test_llm_run_model.py backend/tests/test_llm_run_events.py backend/tests/test_llm_run_service.py backend/tests/test_llm_runs_api.py backend/tests/test_openai_responses_provider.py backend/tests/test_learning_flows.py -q`
- `cd frontend && corepack pnpm test -- useLlmRun.test.tsx LlmStreamingPanel.test.tsx GoalCalibrationPage.test.tsx`
- `make build`
```

- [ ] **Step 5: Run backend verification**

Run:

```bash
uv run pytest backend/tests/test_llm_run_model.py backend/tests/test_llm_run_events.py backend/tests/test_llm_run_service.py backend/tests/test_llm_runs_api.py backend/tests/test_openai_responses_provider.py backend/tests/test_learning_flows.py -q
```

Expected: PASS.

- [ ] **Step 6: Run frontend verification**

Run:

```bash
cd frontend && corepack pnpm test -- useLlmRun.test.tsx LlmStreamingPanel.test.tsx GoalCalibrationPage.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Run build verification**

Run:

```bash
make build
```

Expected: PASS.

- [ ] **Step 8: Commit docs and final verification**

```bash
git add docs/index.md docs/architecture/foundation.md docs/prd/prd.md docs/project-todolist.md
git commit -m "docs: document llm streaming run layer"
```

---

## Final Verification Checklist

- [x] `uv run pytest backend/tests/test_llm_run_model.py backend/tests/test_llm_run_events.py backend/tests/test_llm_run_service.py backend/tests/test_llm_runs_api.py backend/tests/test_openai_responses_provider.py backend/tests/test_learning_flows.py -q`
- [x] `cd frontend && corepack pnpm test -- useLlmRun.test.tsx LlmStreamingPanel.test.tsx GoalCalibrationPage.test.tsx`
- [x] `cd frontend && corepack pnpm exec tsc -b`
- [x] `make build`
- [x] `git status --short` shows only intentional changes.

## Execution Notes

- Do not log full user input, full model output, code submissions, session tokens, API keys, or Fernet keys.
- Keep the old synchronous learning APIs only as temporary compatibility until the migrated frontend and backend tests no longer use them.
- Do not display model-generated problem slugs as formal plan items until `learning_plan_validator` has accepted or repaired them.
- If SSE behavior becomes unreliable under multi-worker deployment, stop after this version and design a persistent event table or queue rather than adding ad hoc polling.
- 2026-05-21 实施结果：目标校准、追问回答和计划草稿生成均已接入统一 LLM Run；正式 `result` 只在 orchestrator 成功提交后发布，取消或失败时前端只展示过程文本。
- 2026-05-21 验证结果：后端专项 39 个测试通过，前端专项 33 个测试通过，`make build` 通过；Vite 仍提示主 bundle 超过 500 kB，属于现有打包体积提示，不影响本次功能验收。
