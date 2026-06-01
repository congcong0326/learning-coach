# Coach Chat Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the workspace AI coach from a submission-first practice module into a Chat-first coach module where messages are the user entry point, non-AC LeetCode results are extracted facts, and AC remains the only explicit terminal action.

**Architecture:** Replace the `practice_session` domain with `coach_session`, `coach_message`, `coach_fact`, `code_snapshot`, and `coach_turn` boundaries. Keep LLM Run, RAG, Trace, profile, and summary orchestration, but make them consume coach facts instead of user-submitted feedback forms.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, Pydantic, LangGraph, React, TypeScript, TanStack Query, Ant Design, Vitest, pytest, uv, Corepack pnpm.

---

## Scope And Ground Rules

The implementation follows `docs/superpowers/specs/2026-06-01-coach-chat-refactor-design.md`.

The current worktree already contains unrelated uncommitted changes, especially around RAG, Trace, Docker, and docs. Do not revert or overwrite unrelated work. Commit only files changed for a task when a task asks for a commit.

This plan intentionally does not preserve the old public API:

- Remove workspace use of `/api/practice-sessions/{id}/submission-feedback`.
- Remove workspace use of `/api/practice-sessions/{id}/code-snapshots`.
- Replace `practice` API naming with `coach` naming for the workspace path.

## File Structure

### Backend Models And Migrations

- Create: `backend/app/models/coach.py`
  - Owns `CoachSession`, `CoachMessage`, `CoachFact`, `CodeSnapshot`, `CoachTurn`, `SessionSummary`, `UserProfileSnapshot`, `ProfileDelta`.
- Modify: `backend/app/models/__init__.py`
  - Export coach model names and stop exporting `PracticeSession`, `PracticeEvent`, `SubmissionFeedback`.
- Modify: `backend/app/db/migrations/versions/20260522_0007_practice_profile.py`
  - Keep revision id `20260522_0007`, but create coach tables directly because the project is not online.
- Delete after all imports are migrated: `backend/app/models/practice.py`

### Backend Schemas, API, And Services

- Create: `backend/app/schemas/coach.py`
  - Owns request and response models for coach session, messages, facts, code attempts, review, dashboard, and accepted action.
- Create: `backend/app/api/coach.py`
  - Owns `/api/study-plan/items/{item_id}/coach-session`, `/api/coach-sessions/{session_id}`, `/api/coach-sessions/{session_id}/messages`, `/api/coach-sessions/{session_id}/accepted`, `/api/coach-sessions/{session_id}/review`.
- Modify: `backend/app/main.py`
  - Register `coach_router`; stop registering `practice_router`.
- Create: `backend/app/services/coach_session_service.py`
  - Creates/restores sessions, returns payloads, synchronizes plan item status.
- Create: `backend/app/services/coach_message_service.py`
  - Appends user messages and creates `coach_turn` runs.
- Create: `backend/app/services/coach_fact_service.py`
  - Persists code attempts, LeetCode feedback facts, AC facts, and fact projections.
- Modify: `backend/app/services/code_attempts.py`
  - Uses `CoachSession`, `CoachMessage`, `CoachFact`; no `PracticeEvent`.
- Delete after imports are migrated: `backend/app/api/practice.py`, `backend/app/schemas/practice.py`, `backend/app/services/practice_session_service.py`

### LLM, Graph, Trace, Profile

- Modify: `backend/app/services/learning_flows/coach_turn.py`
  - Load `CoachSession`, `CoachMessage`, latest `CoachFact`; persist assistant `CoachMessage`; persist facts from chat extraction.
- Modify: `backend/app/services/learning_flows/coach_summary.py`
  - Read summary context from `CoachMessage`, `CoachFact`, and `CodeSnapshot`.
- Modify: `backend/app/agents/coach_graph.py`
  - Rename graph state fields from `latest_submission_feedback` to `latest_leetcode_feedback`.
- Modify: `backend/app/services/coach_guard.py`
  - Rename inputs and reasons away from submission terminology.
- Modify: `backend/app/services/profile_service.py`
  - Read summary facts from `CoachMessage` and `CoachFact`.
- Modify: `backend/app/services/recommendation_service.py`
  - Accept `CoachSession` and summary facts.
- Modify: `backend/app/api/trace.py`
  - Authorize traces through `CoachSession`.
- Modify: `backend/app/services/llm_run_registry.py`
  - Set `coach_turn` and `coach_summary` related type to `coach_session`.
- Modify: `backend/app/services/llm_orchestrator.py`
  - Error message should say coach session, not practice session.

### Frontend

- Create: `frontend/src/api/coach.ts`
  - Replaces workspace imports from `frontend/src/api/practice.ts`.
- Modify: `frontend/src/api/llmRuns.ts`
  - Keep `coach_turn` and `coach_summary`; remove unused `coach_message`, `code_review`, `reflection` kinds if no tests rely on them.
- Modify: `frontend/src/hooks/useLlmRun.ts`
  - Add `attachRun(created)` so the accepted endpoint can return an already-created summary run.
- Modify: `frontend/src/pages/WorkspacePage.tsx`
  - Use `createCoachSessionForItem`.
- Modify: `frontend/src/pages/workspace/CoachPanel.tsx`
  - Use coach API, send only `content_md`, call accepted endpoint, attach returned summary run.
- Modify: `frontend/src/pages/workspace/CodeAttemptDrawer.tsx`, `frontend/src/pages/workspace/types.ts`
  - Use coach response types.
- Delete if unused after the workspace refactor: `frontend/src/pages/workspace/CodePane.tsx`

### Tests And Docs

- Create/update backend tests:
  - `backend/tests/test_coach_models.py`
  - `backend/tests/test_coach_session_service.py`
  - `backend/tests/test_coach_api.py`
  - `backend/tests/test_coach_fact_service.py`
  - `backend/tests/test_learning_flows.py`
  - `backend/tests/test_coach_graph.py`
  - `backend/tests/test_coach_guard.py`
  - `backend/tests/test_agent_trace_service.py`
- Create/update frontend tests:
  - `frontend/src/pages/workspace/CoachPanel.test.tsx`
  - `frontend/src/pages/WorkspacePage.test.tsx`
  - `frontend/src/hooks/useLlmRun.test.tsx`
- Modify docs:
  - `docs/index.md`
  - `docs/architecture/foundation.md`
  - `docs/prd/prd.md`
  - `docs/prd/ai-coach-workbench-prd.md`

---

## Task 1: Coach Data Model And Migration

**Files:**
- Create: `backend/app/models/coach.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/db/migrations/versions/20260522_0007_practice_profile.py`
- Create: `backend/tests/test_coach_models.py`

- [ ] **Step 1: Write failing model tests**

Create `backend/tests/test_coach_models.py`:

```python
from __future__ import annotations

from sqlalchemy import inspect

from backend.app.models.coach import CoachFact, CoachMessage, CoachSession
from backend.app.models.problem import Base


def test_coach_tables_are_registered() -> None:
    table_names = set(Base.metadata.tables)

    assert "coach_session" in table_names
    assert "coach_message" in table_names
    assert "coach_fact" in table_names
    assert "submission_feedback" not in table_names
    assert "practice_session" not in table_names


def test_coach_session_identity_constraint() -> None:
    table = CoachSession.__table__

    constraints = {
        constraint.name
        for constraint in table.constraints
        if constraint.name is not None
    }

    assert "uq_coach_session_user_plan_problem" in constraints
    assert "uq_coach_session_id_user" in constraints


def test_coach_fact_indexes_support_session_and_result_queries() -> None:
    indexes = {index.name: tuple(index.columns.keys()) for index in CoachFact.__table__.indexes}

    assert indexes["ix_coach_fact_session_created"] == ("session_id", "created_at")
    assert indexes["ix_coach_fact_user_type_result_created"] == (
        "user_id",
        "fact_type",
        "result",
        "created_at",
    )


def test_coach_message_has_no_user_intent_column() -> None:
    mapper = inspect(CoachMessage)

    assert "intent" not in mapper.columns
```

- [ ] **Step 2: Run the failing model tests**

Run:

```bash
uv run pytest backend/tests/test_coach_models.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'backend.app.models.coach'`.

- [ ] **Step 3: Create `backend/app/models/coach.py`**

Move the practice/profile models into coach terminology. The model file must define these classes and table names:

```python
class CoachSession(Base):
    __tablename__ = "coach_session"


class CoachMessage(Base):
    __tablename__ = "coach_message"


class CoachFact(Base):
    __tablename__ = "coach_fact"


class CodeSnapshot(Base):
    __tablename__ = "code_snapshot"


class CoachTurn(Base):
    __tablename__ = "coach_turn"


class SessionSummary(Base):
    __tablename__ = "session_summary"


class UserProfileSnapshot(Base):
    __tablename__ = "user_profile_snapshot"


class ProfileDelta(Base):
    __tablename__ = "profile_delta"
```

Use these concrete changes while porting fields:

- `PracticeSession` -> `CoachSession`
- `PracticeEvent` -> `CoachMessage`
- `SubmissionFeedback` -> `CoachFact`
- `CoachMessage.content_md` remains the chat text field.
- Remove `CoachMessage.intent`.
- `CoachFact.fact_type` is `String(40)`, non-null.
- `CoachFact.source` is `String(40)`, non-null, default `"system"`.
- `CoachFact.result` is `String(20)`, non-null, default `""`.
- `CoachFact.payload_json` is JSON, non-null, default `{}`.
- `CoachFact.message_id` references `coach_message.id`.
- `CoachFact.code_snapshot_id` references `code_snapshot.id`.
- `CodeSnapshot.session_id`, `CoachTurn.session_id`, `SessionSummary.session_id`, and `ProfileDelta.session_id` reference `coach_session.id`.
- `CoachTurn.user_message_id` and `CoachTurn.assistant_message_id` reference `coach_message.id`.

Keep existing Chinese comments where they explain safety boundaries, and update them to coach terminology.

- [ ] **Step 4: Update model exports**

Modify `backend/app/models/__init__.py` so imports look like this:

```python
from backend.app.models import auth, coach, learning, llm_run, problem, rag, trace  # noqa: F401
from backend.app.models.coach import (
    CoachFact,
    CoachMessage,
    CoachSession,
    CoachTurn,
    CodeSnapshot,
    ProfileDelta,
    SessionSummary,
    UserProfileSnapshot,
)
```

Update `__all__` to include:

```python
"CoachFact",
"CoachMessage",
"CoachSession",
"CoachTurn",
"CodeSnapshot",
"ProfileDelta",
"SessionSummary",
"UserProfileSnapshot",
```

Remove:

```python
"PracticeEvent",
"PracticeSession",
"SubmissionFeedback",
```

- [ ] **Step 5: Update the existing practice/profile migration in place**

Modify `backend/app/db/migrations/versions/20260522_0007_practice_profile.py`:

- Keep `revision = "20260522_0007"`.
- Change table names and constraint/index names from `practice_session` to `coach_session`.
- Change `practice_event` to `coach_message`.
- Change `submission_feedback` to `coach_fact`.
- Remove the `intent` column from `coach_message`.
- Add `fact_type`, `source`, `result`, `payload_json`, `message_id`, `code_snapshot_id` to `coach_fact`.
- Update all foreign key names and references to `coach_session` and `coach_message`.

The migration should create a fresh database directly in the new structure. Do not add a data-copy migration.

- [ ] **Step 6: Run the model tests**

Run:

```bash
uv run pytest backend/tests/test_coach_models.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/coach.py backend/app/models/__init__.py backend/app/db/migrations/versions/20260522_0007_practice_profile.py backend/tests/test_coach_models.py
git commit -m "refactor: introduce coach data model"
```

---

## Task 2: Coach Schemas

**Files:**
- Create: `backend/app/schemas/coach.py`
- Create: `backend/tests/test_coach_schema.py`

- [ ] **Step 1: Write failing schema tests**

Create `backend/tests/test_coach_schema.py`:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.schemas.coach import (
    CoachAcceptedResponse,
    CoachMessageCreate,
    CoachSessionResponse,
)


def test_coach_message_create_only_requires_content() -> None:
    payload = CoachMessageCreate(content_md="这版 WA，失败用例是 nums=[3,3], target=6")

    assert payload.content_md.startswith("这版 WA")


def test_coach_message_create_rejects_intent() -> None:
    with pytest.raises(ValidationError):
        CoachMessageCreate(content_md="我卡住了", intent="stuck")  # type: ignore[call-arg]


def test_accepted_response_contains_summary_run() -> None:
    response = CoachAcceptedResponse(
        fact_id=1,
        session_id=2,
        result="ac",
        run_id=3,
        kind="coach_summary",
        status="pending",
        stage="queued",
        stream_url="/api/llm-runs/3/stream",
    )

    assert response.result == "ac"
    assert response.stream_url == "/api/llm-runs/3/stream"


def test_session_response_uses_messages_and_facts() -> None:
    fields = set(CoachSessionResponse.model_fields)

    assert "messages" in fields
    assert "facts" in fields
    assert "events" not in fields
    assert "submission_feedbacks" not in fields
```

- [ ] **Step 2: Run the failing schema tests**

Run:

```bash
uv run pytest backend/tests/test_coach_schema.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'backend.app.schemas.coach'`.

- [ ] **Step 3: Create `backend/app/schemas/coach.py`**

Define these aliases:

```python
CoachPhase = Literal[
    "understand_problem",
    "propose_bruteforce",
    "optimize_solution",
    "define_invariant",
    "write_code",
    "review_code",
    "submit_to_leetcode",
    "analyze_feedback",
    "summarize",
]
HintLevel = Literal["questioning", "direction", "key_hint", "reflection"]
CoachSessionStatus = Literal["active", "waiting_user", "waiting_leetcode", "summarizing", "completed", "archived"]
CoachFactType = Literal["code_attempt", "leetcode_feedback", "leetcode_accepted", "phase_transition", "summary_generated", "profile_updated"]
CoachFactSource = Literal["chat_extracted", "explicit_action", "coach_decision", "system"]
LeetCodeResult = Literal["ac", "wa", "tle", "re", "mle", "ce", "unknown"]
```

Define request and response models with `extra="forbid"` on request models:

```python
class CoachMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_md: str = Field(min_length=1, max_length=12000)
    requested_hint_level: HintLevel | None = None


class CoachMessageResponse(BaseModel):
    id: int
    role: Literal["user", "assistant", "system", "tool"]
    phase: CoachPhase
    content_md: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    hint_level: HintLevel | None
    visible_hint_gear: HintLevel | None
    created_at: datetime


class CoachFactResponse(BaseModel):
    id: int
    fact_type: CoachFactType
    source: CoachFactSource
    result: LeetCodeResult | None
    message_id: int | None
    code_snapshot_id: int | None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class CoachMessageCreateResponse(BaseModel):
    message_id: int
    run_id: int
    session_id: int
    kind: str
    status: str
    stage: str
    stream_url: str


class CoachAcceptedResponse(BaseModel):
    fact_id: int
    session_id: int
    result: Literal["ac"]
    run_id: int
    kind: str
    status: str
    stage: str
    stream_url: str
```

Port existing profile, code attempt, review, and dashboard response models from `backend/app/schemas/practice.py`, renaming:

- `PracticeSessionResponse` -> `CoachSessionResponse`
- `PracticeSessionReviewResponse` -> `CoachSessionReviewResponse`
- `PracticeDashboardResponse` -> `CoachDashboardResponse`
- `PracticeMessageResponse` -> `CoachMessageCreateResponse`
- `SubmissionFeedbackHistoryResponse` -> `CoachFactResponse`

- [ ] **Step 4: Run schema tests**

Run:

```bash
uv run pytest backend/tests/test_coach_schema.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/coach.py backend/tests/test_coach_schema.py
git commit -m "refactor: add coach schemas"
```

---

## Task 3: Coach Session, Message, And Fact Services

**Files:**
- Create: `backend/app/services/coach_session_service.py`
- Create: `backend/app/services/coach_message_service.py`
- Create: `backend/app/services/coach_fact_service.py`
- Modify: `backend/app/services/code_attempts.py`
- Create: `backend/tests/test_coach_session_service.py`
- Create: `backend/tests/test_coach_fact_service.py`

- [ ] **Step 1: Write service tests for session creation and messaging**

Create `backend/tests/test_coach_session_service.py` by copying the fixture setup from `backend/tests/test_practice_session_service.py`, then update imports to coach names.

Add these tests:

```python
@pytest.mark.asyncio
async def test_same_plan_problem_reuses_coach_session(db_session, user, study_plan_item) -> None:
    from backend.app.services.coach_session_service import get_or_create_session_for_plan_item

    first = await get_or_create_session_for_plan_item(db_session, user, study_plan_item.id)
    second = await get_or_create_session_for_plan_item(db_session, user, study_plan_item.id)

    assert first.id == second.id
    assert first.thread_id == f"coach-session-{first.id}"


@pytest.mark.asyncio
async def test_user_message_creates_message_and_run(db_session, user, coach_session, monkeypatch) -> None:
    from backend.app.schemas.coach import CoachMessageCreate
    from backend.app.services import coach_message_service

    async def fake_create_llm_run(session, selected_user, *, kind, payload, related_type="", related_id=None):
        assert kind == "coach_turn"
        assert payload["session_id"] == coach_session.id
        assert payload["trigger"] == "user_message"
        return type(
            "Run",
            (),
            {
                "id": 88,
                "kind": kind,
                "status": "pending",
                "stage": "queued",
            },
        )()

    monkeypatch.setattr(coach_message_service, "create_llm_run", fake_create_llm_run)

    response = await coach_message_service.append_user_message(
        db_session,
        user,
        coach_session.id,
        CoachMessageCreate(content_md="我先说暴力解法。"),
    )

    assert response.message_id > 0
    assert response.run_id == 88
    assert response.stream_url == "/api/llm-runs/88/stream"
```

- [ ] **Step 2: Write service tests for facts**

Create `backend/tests/test_coach_fact_service.py`:

```python
@pytest.mark.asyncio
async def test_record_explicit_ac_fact_updates_session_and_plan_item(db_session, user, coach_session, study_plan_item, monkeypatch) -> None:
    from backend.app.services import coach_fact_service

    async def fake_create_llm_run(session, selected_user, *, kind, payload, related_type="", related_id=None):
        assert kind == "coach_summary"
        assert payload["trigger"] == "accepted"
        return type("Run", (), {"id": 99, "kind": kind, "status": "pending", "stage": "queued"})()

    monkeypatch.setattr(coach_fact_service, "create_llm_run", fake_create_llm_run)

    response = await coach_fact_service.record_accepted(
        db_session,
        user,
        coach_session.id,
    )

    await db_session.refresh(coach_session)
    await db_session.refresh(study_plan_item)
    assert response.result == "ac"
    assert response.run_id == 99
    assert coach_session.final_result == "ac"
    assert coach_session.status == "summarizing"
    assert study_plan_item.status == "completed"


@pytest.mark.asyncio
async def test_extract_chat_feedback_fact_from_message(db_session, user, coach_session) -> None:
    from backend.app.models.coach import CoachMessage
    from backend.app.services.coach_fact_service import persist_leetcode_feedback_fact

    message = CoachMessage(
        session_id=coach_session.id,
        user_id=user.id,
        role="user",
        phase=coach_session.phase,
        content_md="LeetCode WA，失败用例 nums=[3,3], target=6，expected [0,1], got []",
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    db_session.add(message)
    await db_session.flush()

    fact = await persist_leetcode_feedback_fact(
        db_session,
        user_id=user.id,
        coach_session=coach_session,
        message=message,
        result="wa",
        text_excerpt=message.content_md,
        code_snapshot_id=None,
    )

    assert fact.fact_type == "leetcode_feedback"
    assert fact.source == "chat_extracted"
    assert fact.result == "wa"
    assert fact.payload_json["has_failed_case"] is True
```

- [ ] **Step 3: Run failing service tests**

Run:

```bash
uv run pytest backend/tests/test_coach_session_service.py backend/tests/test_coach_fact_service.py -q
```

Expected: fail because services do not exist.

- [ ] **Step 4: Implement `coach_session_service.py`**

Port session logic from `practice_session_service.py` and expose these exact functions:

```python
class CoachSessionError(RuntimeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail
```

Required function signatures:

- `async def get_or_create_session_for_plan_item(db: AsyncSession, user: AppUser, plan_item_id: int) -> CoachSession`
- `async def get_session_payload(db: AsyncSession, user: AppUser, session_id: int) -> CoachSessionResponse`
- `async def get_session_review(db: AsyncSession, user: AppUser, session_id: int) -> CoachSessionReviewResponse`
- `async def get_coach_dashboard(db: AsyncSession, user: AppUser) -> CoachDashboardResponse`
- `async def list_session_messages(db: AsyncSession, user: AppUser, session_id: int) -> list[CoachMessageResponse]`
- `async def sync_latest_plan_item_status(db: AsyncSession, coach_session: CoachSession, *, status: str, now: datetime) -> None`

Set new sessions with:

```python
coach_session.thread_id = f"coach-session-{coach_session.id}"
coach_session.phase = "understand_problem"
coach_session.status = "active"
coach_session.current_hint_level = "questioning"
coach_session.visible_hint_gear = 0
```

Return payloads with:

```python
messages = await list_session_messages(db, user, coach_session.id)
facts = await list_session_facts(db, user, coach_session.id)
code_attempts = await list_code_attempts(db, user, coach_session.id)

CoachSessionResponse(
    id=coach_session.id,
    study_plan_id=coach_session.study_plan_id,
    problem_id=coach_session.problem_id,
    problem_slug=coach_session.problem_slug,
    latest_plan_version_id=coach_session.latest_plan_version_id,
    latest_plan_item_id=coach_session.latest_plan_item_id,
    training_mode=coach_session.training_mode,
    phase=coach_session.phase,
    status=coach_session.status,
    current_hint_level=coach_session.current_hint_level,
    visible_hint_gear=_hint_gear_label(coach_session.visible_hint_gear),
    max_hint_level_used=coach_session.max_hint_level_used,
    final_result=coach_session.final_result or None,
    profile_snapshot=ProfileSnapshotPayload.model_validate(coach_session.profile_snapshot_json),
    messages=messages,
    facts=facts,
    code_attempts=code_attempts,
    created_at=coach_session.created_at,
    updated_at=coach_session.updated_at,
)
```

- [ ] **Step 5: Implement `coach_message_service.py`**

Implement:

```python
async def append_user_message(
    db: AsyncSession,
    user: AppUser,
    session_id: int,
    payload: CoachMessageCreate,
) -> CoachMessageCreateResponse:
    coach_session = await load_session_for_update(db, user, session_id)
    now = datetime.now(UTC)
    message = CoachMessage(
        session_id=coach_session.id,
        user_id=user.id,
        role="user",
        phase=coach_session.phase,
        content_md=payload.content_md,
        metadata_json={
            "requested_hint_level": payload.requested_hint_level,
            "content_length": len(payload.content_md),
        },
        hint_level=payload.requested_hint_level,
        visible_hint_gear=coach_session.visible_hint_gear,
        created_at=now,
    )
    db.add(message)
    coach_session.last_activity_at = now
    coach_session.updated_at = now
    await sync_latest_plan_item_status(db, coach_session, status="in_progress", now=now)
    await db.flush()
    run = await create_llm_run(
        db,
        user,
        kind="coach_turn",
        payload={
            "session_id": coach_session.id,
            "user_message_id": message.id,
            "trigger": "user_message",
        },
        related_type="coach_session",
        related_id=coach_session.id,
    )
    await db.commit()
    return CoachMessageCreateResponse(
        message_id=message.id,
        run_id=run.id,
        session_id=coach_session.id,
        kind=run.kind,
        status=run.status,
        stage=run.stage,
        stream_url=f"/api/llm-runs/{run.id}/stream",
    )
```

Log `coach_user_message_appended user_id=%s session_id=%s message_id=%s run_id=%s content_length=%s`.

- [ ] **Step 6: Implement `coach_fact_service.py`**

Expose these exact functions:

- `async def list_session_facts(db: AsyncSession, user: AppUser, session_id: int) -> list[CoachFactResponse]`
- `async def latest_leetcode_feedback_fact(db: AsyncSession, *, user_id: int, session_id: int) -> CoachFact | None`
- `async def latest_accepted_fact(db: AsyncSession, *, user_id: int, session_id: int) -> CoachFact | None`
- `async def persist_leetcode_feedback_fact(db: AsyncSession, *, user_id: int, coach_session: CoachSession, message: CoachMessage, result: str, text_excerpt: str, code_snapshot_id: int | None) -> CoachFact`
- `async def persist_code_attempt_fact(db: AsyncSession, *, user_id: int, coach_session: CoachSession, message: CoachMessage, code_snapshot: CodeSnapshot, quality_status: str, quality_comment: str) -> CoachFact`
- `async def record_accepted(db: AsyncSession, user: AppUser, session_id: int) -> CoachAcceptedResponse`

`record_accepted()` must:

- Lock the session.
- Refuse duplicate AC with `CoachSessionError("accepted_already_recorded")`.
- Create `CoachFact(fact_type="leetcode_accepted", source="explicit_action", result="ac")`.
- Set `final_result="ac"`, `phase="summarize"`, `status="summarizing"`, `completed_at=now`.
- Synchronize plan item status to `completed`.
- Create `coach_summary` LLM Run with related type `coach_session`.
- Commit once at the end.

- [ ] **Step 7: Update `code_attempts.py`**

Change imports:

```python
from backend.app.models.coach import CodeSnapshot, CoachFact, CoachMessage, CoachSession
```

Change `persist_review_code_attempt()` signature to:

```python
async def persist_review_code_attempt(
    db: AsyncSession,
    *,
    user_id: int,
    coach_session: CoachSession,
    user_message: CoachMessage,
    extracted_code: ExtractedCode,
    quality_status: str,
    quality_comment: str,
    client_revision: int,
    now: datetime,
) -> tuple[CodeSnapshot, CoachFact]:
```

Persist `CodeSnapshot` and a `CoachFact(fact_type="code_attempt", source="coach_decision")`. Store quality fields in `CoachFact.payload_json`, not in a message payload.

- [ ] **Step 8: Run service tests**

Run:

```bash
uv run pytest backend/tests/test_coach_session_service.py backend/tests/test_coach_fact_service.py -q
```

Expected: all tests pass.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/coach_session_service.py backend/app/services/coach_message_service.py backend/app/services/coach_fact_service.py backend/app/services/code_attempts.py backend/tests/test_coach_session_service.py backend/tests/test_coach_fact_service.py
git commit -m "refactor: add coach session message fact services"
```

---

## Task 4: Coach API Routes

**Files:**
- Create: `backend/app/api/coach.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/llm_run_registry.py`
- Create: `backend/tests/test_coach_api.py`

- [ ] **Step 1: Write failing API tests**

Create `backend/tests/test_coach_api.py` using the fixture pattern from `backend/tests/test_practice_api.py`.

Add:

```python
def test_plan_item_entry_returns_coach_session(authenticated_client, study_plan_item):
    response = authenticated_client.post(
        f"/api/study-plan/items/{study_plan_item.id}/coach-session"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] > 0
    assert body["latest_plan_item_id"] == study_plan_item.id
    assert "messages" in body
    assert "facts" in body


def test_message_route_rejects_intent(authenticated_client, study_plan_item):
    session_response = authenticated_client.post(
        f"/api/study-plan/items/{study_plan_item.id}/coach-session"
    )
    session_id = session_response.json()["id"]

    response = authenticated_client.post(
        f"/api/coach-sessions/{session_id}/messages",
        json={"content_md": "我卡住了", "intent": "stuck"},
    )

    assert response.status_code == 422


def test_old_submission_feedback_route_is_gone(authenticated_client, study_plan_item):
    session_response = authenticated_client.post(
        f"/api/study-plan/items/{study_plan_item.id}/coach-session"
    )
    session_id = session_response.json()["id"]

    response = authenticated_client.post(
        f"/api/practice-sessions/{session_id}/submission-feedback",
        json={"result": "wa"},
    )

    assert response.status_code == 404
```

- [ ] **Step 2: Run failing API tests**

Run:

```bash
uv run pytest backend/tests/test_coach_api.py -q
```

Expected: fail with 404 for new routes.

- [ ] **Step 3: Implement `backend/app/api/coach.py`**

Routes:

```python
@router.post("/study-plan/items/{item_id}/coach-session", response_model=CoachSessionResponse)
async def create_coach_session_from_plan_item_route(
    item_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> CoachSessionResponse:
    try:
        coach_session = await get_or_create_session_for_plan_item(session, user, item_id)
        return await get_session_payload(session, user, coach_session.id)
    except CoachSessionError as exc:
        raise _http_error(exc) from exc

@router.get("/coach-sessions/{session_id}", response_model=CoachSessionResponse)
async def coach_session_detail_route(
    session_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> CoachSessionResponse:
    try:
        return await get_session_payload(session, user, session_id)
    except CoachSessionError as exc:
        raise _http_error(exc) from exc

@router.post("/coach-sessions/{session_id}/messages", response_model=CoachMessageCreateResponse)
async def append_coach_message_route(
    session_id: int,
    payload: CoachMessageCreate,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> CoachMessageCreateResponse:
    try:
        return await append_user_message(session, user, session_id, payload)
    except CoachSessionError as exc:
        raise _http_error(exc) from exc

@router.post("/coach-sessions/{session_id}/accepted", response_model=CoachAcceptedResponse)
async def record_coach_accepted_route(
    session_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> CoachAcceptedResponse:
    try:
        return await record_accepted(session, user, session_id)
    except CoachSessionError as exc:
        raise _http_error(exc) from exc

@router.get("/coach-sessions/{session_id}/review", response_model=CoachSessionReviewResponse)
async def coach_session_review_route(
    session_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> CoachSessionReviewResponse:
    try:
        return await get_session_review(session, user, session_id)
    except CoachSessionError as exc:
        raise _http_error(exc) from exc
```

Translate `CoachSessionError`:

```python
def _http_error(exc: CoachSessionError) -> HTTPException:
    status = 400
    if "not_found" in exc.detail:
        status = 404
    if exc.detail in {"accepted_already_recorded"}:
        status = 409
    return HTTPException(status_code=status, detail=exc.detail)
```

- [ ] **Step 4: Register coach routes and remove practice routes**

In `backend/app/main.py`:

```python
from backend.app.api.coach import router as coach_router
```

Register:

```python
application.include_router(coach_router, prefix=settings.api_prefix)
```

Remove:

```python
from backend.app.api.practice import router as practice_router
application.include_router(practice_router, prefix=settings.api_prefix)
```

- [ ] **Step 5: Update LLM run registry related type**

In `backend/app/services/llm_run_registry.py`, change:

```python
"coach_turn": RunKindSpec(
    handler=CoachTurnHandler(),
    related_type="coach_session",
    related_id_key="session_id",
    requires_model=True,
),
"coach_summary": RunKindSpec(
    handler=CoachSummaryHandler(),
    related_type="coach_session",
    related_id_key="session_id",
    requires_model=True,
),
```

- [ ] **Step 6: Run API tests**

Run:

```bash
uv run pytest backend/tests/test_coach_api.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/coach.py backend/app/main.py backend/app/services/llm_run_registry.py backend/tests/test_coach_api.py
git commit -m "refactor: expose coach api routes"
```

---

## Task 5: Coach Turn Flow And Graph Refactor

**Files:**
- Modify: `backend/app/services/learning_flows/coach_turn.py`
- Modify: `backend/app/agents/coach_graph.py`
- Modify: `backend/app/services/coach_guard.py`
- Modify: `backend/app/prompts/resources/coach_turn.v2.md`
- Modify: `backend/tests/test_learning_flows.py`
- Modify: `backend/tests/test_coach_graph.py`
- Modify: `backend/tests/test_coach_guard.py`

- [ ] **Step 1: Update guard tests first**

In `backend/tests/test_coach_guard.py`, rename argument names and expected reasons:

```python
def test_feedback_analysis_requires_leetcode_feedback() -> None:
    from backend.app.services.coach_guard import guard_transition

    decision = guard_transition(
        phase_before="review_code",
        proposed_phase_after="analyze_feedback",
        has_code=True,
        has_leetcode_feedback=False,
        has_terminal_result=False,
        hint_level="questioning",
        should_reveal_solution=False,
    )

    assert decision.accepted is False
    assert decision.reason == "leetcode_feedback_required"
```

- [ ] **Step 2: Run failing guard tests**

Run:

```bash
uv run pytest backend/tests/test_coach_guard.py -q
```

Expected: fail because `has_leetcode_feedback` does not exist.

- [ ] **Step 3: Update `coach_guard.py`**

Change signature:

```python
def guard_transition(
    *,
    phase_before: str,
    proposed_phase_after: str,
    has_code: bool,
    has_leetcode_feedback: bool,
    has_terminal_result: bool = False,
    hint_level: str,
    should_reveal_solution: bool,
) -> GuardDecision:
```

Replace reasons:

- `submission_feedback_required` -> `leetcode_feedback_required`
- `terminal_result_required_for_summary` remains valid.

- [ ] **Step 4: Update graph tests**

In `backend/tests/test_coach_graph.py`, update graph state factory keys:

```python
"latest_leetcode_feedback": {"result": "wa", "source": "chat_extracted"},
```

Assert:

```python
assert result["input_classification"]["kind"] == "leetcode_feedback"
assert result["action_summary"]["next_action"] == "analyze_leetcode_feedback"
```

- [ ] **Step 5: Update `coach_graph.py`**

Rename state field and graph summaries:

- `latest_submission_feedback` -> `latest_leetcode_feedback`
- `submission_feedback` classification -> `leetcode_feedback`
- `analyze_submission_feedback` -> `analyze_leetcode_feedback`
- `submission_feedback_required_for_analysis` -> `leetcode_feedback_required_for_analysis`
- `_retrieval_intent()` returns `"leetcode_feedback"` for non-AC facts.

Keep RAG retrieval compatible by mapping `"leetcode_feedback"` to existing retrieval filters if `backend/app/rag/retrieval.py` still expects old values. The adapter can be:

```python
def _retrieval_intent(state: CoachGraphState) -> str:
    feedback_result = _feedback_result(state["latest_leetcode_feedback"])
    if feedback_result in _NON_AC_RESULTS:
        return "leetcode_feedback"
```

- [ ] **Step 6: Update learning flow tests**

In `backend/tests/test_learning_flows.py`, update fixtures from `PracticeSession`, `PracticeEvent`, `SubmissionFeedback` to `CoachSession`, `CoachMessage`, `CoachFact`.

Add a focused test:

```python
@pytest.mark.asyncio
async def test_coach_turn_persists_chat_extracted_leetcode_feedback_fact(db_session, user, coach_session, provider) -> None:
    from sqlalchemy import select

    from backend.app.models.coach import CoachFact
    from backend.app.models.llm_run import LlmRun
    from backend.app.services.coach_message_service import append_user_message
    from backend.app.schemas.coach import CoachMessageCreate
    from backend.app.services.learning_flows.coach_turn import run_coach_turn
    from backend.app.services.llm_run_events import LlmRunEvent

    response = await append_user_message(
        db_session,
        user,
        coach_session.id,
        CoachMessageCreate(content_md="LeetCode WA，失败用例 nums=[3,3], target=6"),
    )

    run = await db_session.get(LlmRun, response.run_id)
    assert run is not None
    published: list[LlmRunEvent] = []

    async def publish(event: LlmRunEvent) -> None:
        published.append(event)

    await run_coach_turn(
        db_session,
        user_id=user.id,
        run=run,
        provider=provider,
        model_name="test-model",
        publish=publish,
    )

    facts = (await db_session.execute(select(CoachFact).where(CoachFact.session_id == coach_session.id))).scalars().all()
    assert any(fact.fact_type == "leetcode_feedback" and fact.result == "wa" for fact in facts)
    assert any(event.event == "delta" for event in published)
```

- [ ] **Step 7: Refactor `coach_turn.py`**

Make these concrete changes:

- Import from `backend.app.models.coach`.
- Load `user_message_id` instead of `user_event_id`.
- `_load_user_message()` only accepts `CoachMessage.role == "user"`.
- Load latest LeetCode feedback through `coach_fact_service.latest_leetcode_feedback_fact()`.
- Convert a `CoachFact` to prompt context through:

```python
def _leetcode_feedback_context(fact: CoachFact | None, chat_feedback_context: dict[str, Any] | None) -> dict[str, Any] | None:
    if chat_feedback_context is not None:
        return chat_feedback_context
    if fact is None:
        return None
    payload = fact.payload_json if isinstance(fact.payload_json, dict) else {}
    return {
        "source": fact.source,
        "result": fact.result,
        "code_snapshot_id": fact.code_snapshot_id,
        "has_failed_case": bool(payload.get("has_failed_case")),
        "has_error_message": bool(payload.get("has_error_message")),
        "text_excerpt": payload.get("text_excerpt", ""),
    }
```

- Persist assistant reply as `CoachMessage`.
- Persist chat-extracted WA/TLE/RE/MLE/CE as `CoachFact(fact_type="leetcode_feedback")`.
- Persist code attempts through updated `persist_review_code_attempt()`.
- Return result keys with `user_message_id`, `assistant_message_id`, `coach_fact_ids`.

Log `coach_turn_flow_started` and `coach_turn_flow_completed` with `session_id`, `run_id`, `phase_before`, `phase_after`, `facts_created`.

- [ ] **Step 8: Update prompt wording**

In `backend/app/prompts/resources/coach_turn.v2.md`, replace:

```text
latest_submission_feedback.source 为 chat_extracted
```

with:

```text
latest_leetcode_feedback.source 为 chat_extracted
```

Replace “回填表单” with “额外表单”.

- [ ] **Step 9: Run flow and graph tests**

Run:

```bash
uv run pytest backend/tests/test_coach_guard.py backend/tests/test_coach_graph.py backend/tests/test_learning_flows.py -q
```

Expected: all tests pass.

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/learning_flows/coach_turn.py backend/app/agents/coach_graph.py backend/app/services/coach_guard.py backend/app/prompts/resources/coach_turn.v2.md backend/tests/test_learning_flows.py backend/tests/test_coach_graph.py backend/tests/test_coach_guard.py
git commit -m "refactor: make coach turn consume messages and facts"
```

---

## Task 6: Summary, Profile, Recommendation, Trace

**Files:**
- Modify: `backend/app/services/learning_flows/coach_summary.py`
- Modify: `backend/app/services/profile_service.py`
- Modify: `backend/app/services/recommendation_service.py`
- Modify: `backend/app/api/trace.py`
- Modify: `backend/app/services/agent_trace_service.py`
- Modify: `backend/app/evals/coach_eval_runner.py`
- Modify: `backend/tests/test_agent_trace_service.py`
- Modify: `backend/tests/test_coach_eval_runner.py`
- Modify: `backend/tests/test_profile_provider.py`
- Modify: `backend/tests/test_recommendation_service.py`

- [ ] **Step 1: Update summary/profile tests**

In existing summary/profile tests, change object creation:

```python
CoachMessage(
    session_id=coach_session.id,
    user_id=user.id,
    role="user",
    phase="review_code",
    content_md="我的代码如下：class Solution:\n    pass",
    metadata_json={},
)
CoachFact(
    session_id=coach_session.id,
    user_id=user.id,
    fact_type="leetcode_feedback",
    source="chat_extracted",
    result="wa",
    payload_json={"has_failed_case": True, "text_excerpt": "nums=[3,3]"},
)
```

Assert summary context contains `"leetcode_feedbacks"` rather than `"submission_feedbacks"`.

- [ ] **Step 2: Run failing summary/profile tests**

Run:

```bash
uv run pytest backend/tests/test_profile_provider.py backend/tests/test_recommendation_service.py backend/tests/test_agent_trace_service.py -q
```

Expected: fail on old model imports or old field names.

- [ ] **Step 3: Refactor `coach_summary.py`**

Concrete replacements:

- `PracticeSession` -> `CoachSession`
- `PracticeEvent` -> `CoachMessage`
- `SubmissionFeedback` -> `CoachFact`
- `_summary_practice_session()` -> `_summary_coach_session()`
- `_summary_event_context()` -> `_summary_message_context()`
- `_summary_feedback_context()` -> `_summary_leetcode_feedback_context()`
- response context key `"submission_feedbacks"` -> `"leetcode_feedbacks"`

Only include `CoachFact.fact_type.in_(("leetcode_feedback", "leetcode_accepted"))` in feedback context.

- [ ] **Step 4: Refactor `profile_service.py`**

Concrete replacements:

- `_load_practice_session_for_summary()` -> `_load_coach_session_for_summary()`
- `_session_events()` -> `_session_messages()`
- `_session_feedbacks()` -> `_session_facts()`
- `facts["final_submission_result"]` may remain as summary output naming, but source it from `coach_session.final_result` and `CoachFact(fact_type="leetcode_accepted")`.

In `_summary_facts()`, compute:

```python
leetcode_feedbacks = [
    fact for fact in facts
    if fact.fact_type == "leetcode_feedback" and fact.result
]
accepted_facts = [
    fact for fact in facts
    if fact.fact_type == "leetcode_accepted" and fact.result == "ac"
]
```

Use `leetcode_feedbacks` for error types and `accepted_facts` for terminal result.

- [ ] **Step 5: Refactor recommendation and trace**

In `backend/app/services/recommendation_service.py`, update type imports to `CoachSession`.

In `backend/app/api/trace.py`, authorize with:

```python
from backend.app.models.coach import CoachSession
```

and return 404 detail:

```python
"coach_session_not_found"
```

In `backend/app/evals/coach_eval_runner.py`, rename retrieval intent `"submission_feedback"` to `"leetcode_feedback"` and update fixture expectations.

- [ ] **Step 6: Run affected backend tests**

Run:

```bash
uv run pytest backend/tests/test_agent_trace_service.py backend/tests/test_coach_eval_runner.py backend/tests/test_profile_provider.py backend/tests/test_recommendation_service.py backend/tests/test_learning_flows.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/learning_flows/coach_summary.py backend/app/services/profile_service.py backend/app/services/recommendation_service.py backend/app/api/trace.py backend/app/services/agent_trace_service.py backend/app/evals/coach_eval_runner.py backend/tests/test_agent_trace_service.py backend/tests/test_coach_eval_runner.py backend/tests/test_profile_provider.py backend/tests/test_recommendation_service.py backend/tests/test_learning_flows.py
git commit -m "refactor: update summary profile trace for coach facts"
```

---

## Task 7: Frontend Coach API And Workspace UI

**Files:**
- Create: `frontend/src/api/coach.ts`
- Modify: `frontend/src/api/llmRuns.ts`
- Modify: `frontend/src/hooks/useLlmRun.ts`
- Modify: `frontend/src/hooks/useLlmRun.test.tsx`
- Modify: `frontend/src/pages/WorkspacePage.tsx`
- Modify: `frontend/src/pages/WorkspacePage.test.tsx`
- Modify: `frontend/src/pages/workspace/CoachPanel.tsx`
- Modify: `frontend/src/pages/workspace/CoachPanel.test.tsx`
- Modify: `frontend/src/pages/workspace/CodeAttemptDrawer.tsx`
- Modify: `frontend/src/pages/workspace/types.ts`

- [ ] **Step 1: Write frontend API and hook tests**

In `frontend/src/hooks/useLlmRun.test.tsx`, add:

```tsx
it('can attach to a run created by another API endpoint', async () => {
  const { result } = renderHook(() => useLlmRun())

  await act(async () => {
    result.current.attachRun({
      run_id: 42,
      kind: 'coach_summary',
      status: 'pending',
      stage: 'queued',
      stream_url: '/api/llm-runs/42/stream',
    })
  })

  expect(result.current.runId).toBe(42)
  expect(result.current.status).toBe('pending')
})
```

In `frontend/src/pages/workspace/CoachPanel.test.tsx`, update expectations:

Update the hook mock first:

```tsx
const llmRunMock = vi.hoisted(() => ({
  startRun: vi.fn(),
  attachRun: vi.fn(),
  cancelRun: vi.fn(),
}))
```

```tsx
expect(coachApiMock.sendCoachMessage).toHaveBeenCalledWith(10, {
  content_md: '我卡住了',
  requested_hint_level: null,
})
```

Add:

```tsx
it('records accepted through the coach accepted endpoint and attaches the returned summary run', async () => {
  const acceptedRun = {
    fact_id: 91,
    session_id: 10,
    result: 'ac' as const,
    run_id: 42,
    kind: 'coach_summary' as const,
    status: 'pending' as const,
    stage: 'queued',
    stream_url: '/api/llm-runs/42/stream',
  }
  coachApiMock.recordCoachAccepted.mockResolvedValue(acceptedRun)
  const onSessionRefresh = vi.fn()

  render(<CoachPanel session={{ ...stubSession(), facts: [] }} onSessionRefresh={onSessionRefresh} />)
  fireEvent.click(screen.getByRole('button', { name: 'LeetCode 已 AC' }))

  await waitFor(() => expect(coachApiMock.recordCoachAccepted).toHaveBeenCalledWith(10))
  expect(onSessionRefresh).toHaveBeenCalled()
  expect(llmRunMock.attachRun).toHaveBeenCalledWith(acceptedRun)
})
```

- [ ] **Step 2: Run failing frontend tests**

Run:

```bash
cd frontend && corepack pnpm test -- CoachPanel.test.tsx useLlmRun.test.tsx
```

Expected: fail because `attachRun` and coach API calls do not exist.

- [ ] **Step 3: Create `frontend/src/api/coach.ts`**

Port from `practice.ts` and rename:

```ts
export type CoachMessagePayload = {
  content_md: string
  requested_hint_level?: HintLevel | null
}

export function createCoachSessionForItem(itemId: number) {
  return requestJson<CoachSession>(`/api/study-plan/items/${itemId}/coach-session`, {
    method: 'POST',
  })
}

export function getCoachSession(sessionId: number) {
  return requestJson<CoachSession>(`/api/coach-sessions/${sessionId}`)
}

export function sendCoachMessage(sessionId: number, payload: CoachMessagePayload) {
  return requestJson<CoachMessageCreateResponse>(`/api/coach-sessions/${sessionId}/messages`, {
    method: 'POST',
    body: payload,
  })
}

export function recordCoachAccepted(sessionId: number) {
  return requestJson<CreateLlmRunResponse & { fact_id: number; session_id: number; result: 'ac' }>(
    `/api/coach-sessions/${sessionId}/accepted`,
    { method: 'POST' },
  )
}
```

Use response fields `messages` and `facts`, not `events` and `submission_feedbacks`.

- [ ] **Step 4: Add `attachRun` to `useLlmRun.ts`**

Import `CreateLlmRunResponse` and add:

```ts
const attachRun = useCallback(
  (created: CreateLlmRunResponse) => {
    const requestSeq = requestSeqRef.current + 1
    requestSeqRef.current = requestSeq
    closeSource()
    runIdRef.current = created.run_id
    setState({
      runId: created.run_id,
      status: created.status,
      stage: created.stage,
      displayText: '',
      result: null,
      error: null,
    })
    openStream(created.stream_url, created.run_id, requestSeq)
  },
  [closeSource, openStream],
)
```

Return `attachRun` from the hook.

- [ ] **Step 5: Update WorkspacePage and CoachPanel**

In `WorkspacePage.tsx`:

```ts
import { createCoachSessionForItem } from '../api/coach'
```

Use query key:

```ts
queryKey: ['coach-session', 'plan-item', itemIdNumber]
```

In `CoachPanel.tsx`:

- Import `sendCoachMessage` and `recordCoachAccepted` from `../../api/coach`.
- Remove `UserIntent`.
- Change `sendCoachMessage(messageIntent, messageContent)` to `sendCoachMessage(messageContent, requestedHintLevel)`.
- Send body:

```ts
{
  content_md: trimmedContent,
  requested_hint_level: requestedHintLevel,
}
```

- For normal send, call `sendCoachMessage(content, null)`.
- For hint, call `sendCoachMessage(content.trim() || REQUEST_HINT_MESSAGE, session.current_hint_level)`.
- For AC:

```ts
const accepted = await recordCoachAccepted(session.id)
setLocalAcceptedSessionId(session.id)
onSessionRefresh()
setActiveRunPurpose('summary')
setRunStartedAtMs(Date.now())
llmRun.attachRun(accepted)
```

Compute `acceptedResult` from `session.final_result === 'ac'` or `facts.some(fact => fact.fact_type === 'leetcode_accepted' && fact.result === 'ac')`.

- [ ] **Step 6: Run frontend tests**

Run:

```bash
cd frontend && corepack pnpm test -- CoachPanel.test.tsx WorkspacePage.test.tsx useLlmRun.test.tsx
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/coach.ts frontend/src/api/llmRuns.ts frontend/src/hooks/useLlmRun.ts frontend/src/hooks/useLlmRun.test.tsx frontend/src/pages/WorkspacePage.tsx frontend/src/pages/WorkspacePage.test.tsx frontend/src/pages/workspace/CoachPanel.tsx frontend/src/pages/workspace/CoachPanel.test.tsx frontend/src/pages/workspace/CodeAttemptDrawer.tsx frontend/src/pages/workspace/types.ts
git commit -m "refactor: switch workspace frontend to coach api"
```

---

## Task 8: Remove Legacy Practice Module References

**Files:**
- Delete: `backend/app/api/practice.py`
- Delete: `backend/app/schemas/practice.py`
- Delete: `backend/app/services/practice_session_service.py`
- Delete: `backend/app/models/practice.py`
- Delete or update: `backend/tests/test_practice_api.py`
- Delete or update: `backend/tests/test_practice_models.py`
- Delete or update: `backend/tests/test_practice_schema.py`
- Delete or update: `backend/tests/test_practice_session_service.py`
- Modify: every remaining backend/frontend import found by grep.

- [ ] **Step 1: Run legacy reference scan**

Run:

```bash
grep -RInE "backend\\.app\\.models\\.practice|schemas\\.practice|api/practice|practice_session_service|PracticeSession|PracticeEvent|SubmissionFeedback|submission-feedback|code-snapshots|submit_feedback" backend/app backend/tests frontend/src
```

Expected before cleanup: output contains old references.

- [ ] **Step 2: Delete or rename legacy tests**

For tests that still cover valid behavior, rename them:

- `test_practice_api.py` -> `test_coach_api.py` if not already migrated.
- `test_practice_schema.py` -> `test_coach_schema.py` if not already migrated.
- `test_practice_session_service.py` -> `test_coach_session_service.py` if not already migrated.
- `test_practice_models.py` -> `test_coach_models.py` if not already migrated.

Delete duplicate legacy tests after their coach equivalents pass.

- [ ] **Step 3: Delete legacy module files**

Run:

```bash
git rm backend/app/api/practice.py backend/app/schemas/practice.py backend/app/services/practice_session_service.py backend/app/models/practice.py
```

- [ ] **Step 4: Fix remaining imports**

Run the scan from Step 1 again. For each remaining match:

- Use `backend.app.models.coach`.
- Use `backend.app.schemas.coach`.
- Use `backend.app.services.coach_session_service`.
- Replace public API strings with `/api/coach-sessions`.
- Replace `related_type="practice_session"` with `related_type="coach_session"`.

- [ ] **Step 5: Verify no legacy references remain in code**

Run:

```bash
grep -RInE "backend\\.app\\.models\\.practice|schemas\\.practice|api/practice|practice_session_service|PracticeSession|PracticeEvent|SubmissionFeedback|submission-feedback|code-snapshots|submit_feedback" backend/app backend/tests frontend/src
```

Expected: no output.

- [ ] **Step 6: Run broad backend tests**

Run:

```bash
uv run pytest backend/tests -q
```

Expected: all backend tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app backend/tests frontend/src
git commit -m "refactor: remove legacy practice module"
```

---

## Task 9: Documentation Updates

**Files:**
- Modify: `docs/index.md`
- Modify: `docs/architecture/foundation.md`
- Modify: `docs/prd/prd.md`
- Modify: `docs/prd/ai-coach-workbench-prd.md`
- Modify: `docs/project-todolist.md` if status wording references old practice API names.

- [ ] **Step 1: Update docs terminology**

Apply these replacements where they describe current implementation, not historical plans:

- `practice_session` -> `coach_session`
- `practice_event` -> `coach_message`
- `submission_feedback` -> `coach_fact`
- `PracticeSession` -> `CoachSession`
- “提交反馈表单” -> “聊天抽取的 LeetCode 反馈事实”
- “LeetCode 回填” -> “LeetCode AC 显式动作与非 AC 聊天识别”

- [ ] **Step 2: Update API lists**

In `docs/architecture/foundation.md`, replace old endpoints:

```text
POST /api/study-plan/items/{item_id}/practice-session
GET /api/practice-sessions/{session_id}
GET /api/practice-sessions/{session_id}/events
POST /api/practice-sessions/{session_id}/messages
POST /api/practice-sessions/{session_id}/code-snapshots
POST /api/practice-sessions/{session_id}/submission-feedback
POST /api/practice-sessions/{session_id}/summary
```

with:

```text
POST /api/study-plan/items/{item_id}/coach-session
GET /api/coach-sessions/{session_id}
POST /api/coach-sessions/{session_id}/messages
POST /api/coach-sessions/{session_id}/accepted
GET /api/coach-sessions/{session_id}/review
```

- [ ] **Step 3: Update module responsibilities**

In `docs/index.md`, describe:

```text
backend/app/api/coach.py：计划题教练会话、聊天消息、AC 终态动作和复盘读取 API。
backend/app/models/coach.py：教练会话、聊天消息、训练事实、代码快照、教练回合、复盘和画像模型。
backend/app/services/coach_*：教练会话、消息和训练事实服务。
```

- [ ] **Step 4: Run docs grep**

Run:

```bash
grep -RInE "practice-sessions|submission-feedback|code-snapshots|practice_session|practice_event|submission_feedback" docs
```

Expected: no matches for current implementation sections. Historical plan/spec files under `docs/superpowers/` may still contain old terms if they describe old work; leave those unchanged unless they describe the new refactor.

- [ ] **Step 5: Commit**

```bash
git add docs/index.md docs/architecture/foundation.md docs/prd/prd.md docs/prd/ai-coach-workbench-prd.md docs/project-todolist.md
git commit -m "docs: update coach chat architecture"
```

---

## Task 10: Final Verification

**Files:**
- No new files.
- May modify files only if verification exposes defects from earlier tasks.

- [ ] **Step 1: Run backend unit tests**

Run:

```bash
uv run pytest backend/tests -q
```

Expected: all tests pass.

- [ ] **Step 2: Run backend eval smoke**

Run:

```bash
uv run python -m backend.app.evals.coach_eval_runner
```

Expected: eval runner completes without failures and reports all fixed samples passing.

- [ ] **Step 3: Run frontend tests**

Run:

```bash
cd frontend && corepack pnpm test
```

Expected: all frontend tests pass.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend && corepack pnpm build
```

Expected: TypeScript build and Vite production build complete successfully.

- [ ] **Step 5: Run global legacy reference scan**

Run:

```bash
grep -RInE "backend\\.app\\.models\\.practice|schemas\\.practice|api/practice|practice_session_service|PracticeSession|PracticeEvent|SubmissionFeedback|submission-feedback|code-snapshots|submit_feedback" backend/app backend/tests frontend/src
```

Expected: no output.

- [ ] **Step 6: Check git status**

Run:

```bash
git status --short
```

Expected: only unrelated pre-existing worktree changes remain, or no output if the implementation branch contains only committed task changes.

- [ ] **Step 7: Commit verification fixes**

If verification required fixes, commit them:

```bash
git add backend frontend docs
git commit -m "fix: complete coach chat refactor verification"
```

If no fixes were needed, do not create an empty commit.

---

## Self-Review

Spec coverage:

- Chat-first entry point: Task 3, Task 4, Task 7.
- AC as explicit terminal action: Task 3, Task 4, Task 7.
- Non-AC as chat-extracted fact: Task 3, Task 5, Task 6.
- Remove submission-first public API: Task 4, Task 8.
- Clear backend boundaries: Task 1, Task 2, Task 3.
- RAG/Trace/Profile/Summary continuity: Task 5, Task 6.
- Docs maintenance: Task 9.
- Verification: Task 10.

Placeholder scan:

- No deferred-work markers or undefined task references are intentionally present.
- Code snippets define the names introduced in each task before later tasks rely on them.

Type consistency:

- Public backend names use `CoachSession`, `CoachMessage`, `CoachFact`.
- Public frontend names use `CoachSession`, `CoachMessagePayload`, `recordCoachAccepted`.
- LLM Run payload uses `session_id`, `user_message_id`, and `trigger`.
