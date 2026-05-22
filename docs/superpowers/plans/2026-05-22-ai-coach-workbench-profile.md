# AI Coach Workbench Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first coded slice of the profile-driven AI coach workbench: plan-item practice sessions, structured training events, profile snapshots, coach turns, LeetCode feedback, summary, and profile patch persistence.

**Architecture:** Add backend practice/profile tables and services under the existing FastAPI + SQLAlchemy async architecture, reuse the existing `llm_run` streaming layer for coach actions, and expose a plan-item workspace flow to the React frontend. The first slice uses finite-state service orchestration and `ProfileProvider`; LangGraph and RAG remain replaceable later extensions.

**Tech Stack:** Python 3.12, uv, FastAPI, SQLAlchemy async, Alembic, Pydantic, PostgreSQL JSON, React, TypeScript, Ant Design, TanStack Query, existing SSE LLM Run layer.

---

## Reference Documents

- Product PRD: `docs/prd/prd.md`
- Workbench PRD: `docs/prd/ai-coach-workbench-prd.md`
- User profile PRD: `docs/prd/ai-coach-user-profile-prd.md`
- Coding spec: `docs/superpowers/specs/2026-05-22-ai-coach-workbench-profile-coding-spec.md`
- Existing workbench design background: `docs/superpowers/specs/2026-05-22-ai-coach-workbench-engineering-design.md`
- Architecture: `docs/architecture/foundation.md`
- Commands: `docs/architecture/makefile.md`

## File Structure

Backend files to create:

- `backend/app/models/practice.py`: SQLAlchemy models for practice sessions, events, code snapshots, submission feedback, coach turns, session summaries, profile snapshots, and profile deltas.
- `backend/app/schemas/practice.py`: Pydantic request and response schemas for practice APIs.
- `backend/app/services/profile_provider.py`: Stable profile snapshot DTO and provider interface.
- `backend/app/services/profile_service.py`: Initial profile creation, latest snapshot lookup, profile delta validation, and snapshot versioning.
- `backend/app/services/practice_session_service.py`: Session create/restore, event timeline, code snapshot, submission feedback, and response payload assembly.
- `backend/app/services/coach_guard.py`: Finite-state transition and hint-level guard rules.
- `backend/app/services/learning_flows/coach_turn.py`: LLM Run handler for coach messages, code review, and feedback analysis.
- `backend/app/services/learning_flows/coach_summary.py`: LLM Run handler for single-session summaries and profile patch proposal.
- `backend/app/api/practice.py`: Practice HTTP API routes.
- `backend/app/db/migrations/versions/20260522_0007_practice_profile.py`: Alembic migration for new tables.
- `backend/tests/test_practice_models.py`
- `backend/tests/test_profile_provider.py`
- `backend/tests/test_practice_session_service.py`
- `backend/tests/test_practice_api.py`
- `backend/tests/test_coach_guard.py`

Backend files to modify:

- `backend/app/main.py`: Register practice router.
- `backend/app/models/__init__.py`: Import new practice models for Alembic metadata discovery.
- `backend/app/services/llm_run_registry.py`: Add `coach_turn` and `coach_summary` run kinds.
- `backend/app/services/llm_orchestrator.py`: Add `practice_session_not_found`, `coach_output_invalid`, and `coach_state_conflict` to `ERROR_MESSAGES`.
- `backend/app/schemas/learning.py`: Keep unchanged unless implementation changes the existing study plan API response contract; this plan does not require such a change.

Frontend files to create:

- `frontend/src/api/practice.ts`: Practice API client and TypeScript types.
- `frontend/src/pages/workspace/CoachPanel.tsx`
- `frontend/src/pages/workspace/CodePane.tsx`
- `frontend/src/pages/workspace/ProblemPane.tsx`
- `frontend/src/pages/workspace/SubmissionFeedbackModal.tsx`
- `frontend/src/pages/workspace/types.ts`
- `frontend/src/pages/workspace/coachDisplay.ts`
- `frontend/src/pages/workspace/CoachPanel.test.tsx`
- `frontend/src/pages/workspace/SubmissionFeedbackModal.test.tsx`

Frontend files to modify:

- `frontend/src/routes/AppRoutes.tsx`: Add `/workspace/items/:itemId`.
- `frontend/src/pages/WorkspacePage.tsx`: Load plan-item practice sessions and compose workspace panes.
- `frontend/src/pages/StudyPlanPage.tsx`: Link plan items to `/workspace/items/:itemId`.
- `frontend/src/api/learning.ts`: Reuse existing plan item types.
- `frontend/src/styles/app.css`: Add `.workspace-layout`, `.workspace-pane`, `.coach-timeline`, `.coach-state-bar`, and `.code-pane-actions`.

Docs to update after implementation:

- `docs/index.md`
- `docs/architecture/foundation.md`
- `docs/prd/prd.md`: No change expected because this plan implements already documented product behavior.

---

### Task 1: Backend Practice And Profile Schemas

**Files:**
- Create: `backend/app/schemas/practice.py`
- Test: `backend/tests/test_practice_schema.py`

- [ ] **Step 1: Write schema tests**

Create `backend/tests/test_practice_schema.py`:

```python
from pydantic import ValidationError

from backend.app.schemas.practice import (
    CodeSnapshotCreate,
    PracticeMessageCreate,
    SubmissionFeedbackCreate,
)


def test_practice_message_accepts_known_intent_and_hint_level() -> None:
    payload = PracticeMessageCreate(
        intent="describe_idea",
        content_md="我先说暴力解法，再说明哈希表优化。",
        requested_hint_level="questioning",
    )

    assert payload.intent == "describe_idea"
    assert payload.requested_hint_level == "questioning"


def test_practice_message_rejects_empty_content() -> None:
    try:
        PracticeMessageCreate(intent="describe_idea", content_md="")
    except ValidationError as exc:
        assert "content_md" in str(exc)
    else:
        raise AssertionError("empty content should be rejected")


def test_code_snapshot_limits_language_to_supported_values() -> None:
    snapshot = CodeSnapshotCreate(
        language="python3",
        code_text="class Solution:\n    pass",
        source="manual_save",
        client_revision=1,
    )

    assert snapshot.language == "python3"


def test_submission_feedback_accepts_structured_wa() -> None:
    feedback = SubmissionFeedbackCreate(
        code_snapshot_id=7,
        result="wa",
        failed_case_text="nums = [3,3], target = 6",
        error_message="",
        runtime_ms=None,
        memory_kb=None,
    )

    assert feedback.result == "wa"
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```bash
uv run pytest backend/tests/test_practice_schema.py -q
```

Expected: FAIL because `backend.app.schemas.practice` does not exist.

- [ ] **Step 3: Implement schemas**

Create `backend/app/schemas/practice.py` with these public types:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


PracticePhase = Literal[
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
PracticeSessionStatus = Literal[
    "active",
    "waiting_user",
    "waiting_leetcode",
    "summarizing",
    "completed",
    "archived",
]
PracticeEventType = Literal[
    "session_started",
    "user_message",
    "assistant_message",
    "code_saved",
    "submission_feedback",
    "phase_changed",
    "summary_generated",
    "profile_updated",
]
PracticeRole = Literal["user", "assistant", "system", "tool"]
UserIntent = Literal[
    "describe_idea",
    "stuck",
    "request_hint",
    "code_review",
    "submit_feedback",
    "request_summary",
    "unknown",
]
SubmissionResult = Literal["ac", "wa", "tle", "re", "mle", "ce", "unknown"]
CodeSnapshotSource = Literal["paste", "manual_save", "before_review", "before_submit", "final"]
ProfileConfidence = Literal["low", "medium", "high"]
ProfileSource = Literal[
    "initial_goal_plan",
    "mock_from_goal_and_plan",
    "summary_patch",
    "manual_repair",
]


class ProfileSnapshotPayload(BaseModel):
    id: int | None = None
    version: str
    source: ProfileSource
    confidence: ProfileConfidence
    overall_level: str
    preferred_training_mode: str
    weak_stuck_points: list[str] = Field(default_factory=list)
    strong_skill_tags: list[str] = Field(default_factory=list)
    weak_skill_tags: list[str] = Field(default_factory=list)
    recent_summary: str = ""
    hint_policy_hint: str = ""
    coach_strategy: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class PracticeMessageCreate(BaseModel):
    intent: UserIntent = "unknown"
    content_md: str = Field(min_length=1, max_length=12000)
    requested_hint_level: HintLevel | None = None


class CodeSnapshotCreate(BaseModel):
    language: Literal["c", "go", "python3", "javascript", "java"]
    code_text: str = Field(min_length=1, max_length=60000)
    source: CodeSnapshotSource = "manual_save"
    client_revision: int = Field(ge=0)


class SubmissionFeedbackCreate(BaseModel):
    code_snapshot_id: int | None = None
    result: SubmissionResult
    failed_case_text: str = Field(default="", max_length=12000)
    error_message: str = Field(default="", max_length=12000)
    runtime_ms: int | None = Field(default=None, ge=0)
    memory_kb: int | None = Field(default=None, ge=0)


class PracticeEventResponse(BaseModel):
    id: int
    event_type: PracticeEventType
    role: PracticeRole
    phase: PracticePhase
    intent: UserIntent | None
    content_md: str
    payload: dict[str, Any]
    hint_level: HintLevel | None
    visible_hint_gear: HintLevel | None
    created_at: datetime


class PracticeSessionResponse(BaseModel):
    id: int
    study_plan_id: int
    problem_id: int
    problem_slug: str
    latest_plan_version_id: int
    latest_plan_item_id: int
    training_mode: str
    phase: PracticePhase
    status: PracticeSessionStatus
    current_hint_level: HintLevel
    visible_hint_gear: HintLevel
    max_hint_level_used: HintLevel | None
    attempt_count: int
    final_result: SubmissionResult | None
    profile_snapshot: ProfileSnapshotPayload
    events: list[PracticeEventResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PracticeMessageResponse(BaseModel):
    event_id: int
    run_id: int
    session_id: int


class CodeSnapshotResponse(BaseModel):
    id: int
    language: str
    source: str
    client_revision: int
    code_hash: str
    created_at: datetime


class SubmissionFeedbackResponse(BaseModel):
    id: int
    result: SubmissionResult
    event_id: int
    code_snapshot_id: int | None
    created_at: datetime
```

- [ ] **Step 4: Verify schema tests pass**

Run:

```bash
uv run pytest backend/tests/test_practice_schema.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/practice.py backend/tests/test_practice_schema.py
git commit -m "feat: add practice API schemas"
```

---

### Task 2: Database Models And Migration

**Files:**
- Create: `backend/app/models/practice.py`
- Create: `backend/app/db/migrations/versions/20260522_0007_practice_profile.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_practice_models.py`

- [ ] **Step 1: Write model tests**

Create `backend/tests/test_practice_models.py`:

```python
from backend.app.models.practice import (
    PracticeSession,
    ProfileDelta,
    UserProfileSnapshot,
)


def test_practice_session_identity_columns_are_named_for_plan_problem_reuse() -> None:
    columns = PracticeSession.__table__.columns

    assert "user_id" in columns
    assert "study_plan_id" in columns
    assert "problem_id" in columns


def test_profile_snapshot_has_versioned_json_contract() -> None:
    columns = UserProfileSnapshot.__table__.columns

    assert "version_number" in columns
    assert "ability_profile_json" in columns
    assert "skill_profile_json" in columns
    assert "strategy_json" in columns
    assert "evidence_summary_json" in columns


def test_profile_delta_has_acceptance_and_evidence_fields() -> None:
    columns = ProfileDelta.__table__.columns

    assert "status" in columns
    assert "patch_json" in columns
    assert "evidence_json" in columns
    assert "rejection_reason" in columns
```

- [ ] **Step 2: Run the model tests and verify they fail**

Run:

```bash
uv run pytest backend/tests/test_practice_models.py -q
```

Expected: FAIL because `backend.app.models.practice` does not exist.

- [ ] **Step 3: Implement SQLAlchemy models**

Create `backend/app/models/practice.py` with the eight models defined in the coding spec:

- `PracticeSession`
- `PracticeEvent`
- `CodeSnapshot`
- `SubmissionFeedback`
- `CoachTurn`
- `SessionSummary`
- `UserProfileSnapshot`
- `ProfileDelta`

Use the existing `Base`, `ID_TYPE`, `EMPTY_ARRAY`, `EMPTY_OBJECT`, and `EMPTY_TEXT` patterns from `backend/app/models/learning.py`. Add Chinese comments only for the two non-obvious boundaries:

```python
# 会话身份只绑定 user + study_plan + problem；计划版本只做追溯，避免计划调整后丢失同一道题的训练上下文。
```

```python
# 长期画像保存决策摘要和证据摘要，不保存完整聊天、完整代码或完整题解，避免后续 Prompt 召回放大噪声。
```

Modify `backend/app/models/__init__.py` so Alembic metadata imports the new models:

```python
from backend.app.models import auth, learning, llm_run, practice, problem  # noqa: F401
```

- [ ] **Step 4: Add Alembic migration**

Create `backend/app/db/migrations/versions/20260522_0007_practice_profile.py`.

Migration requirements:

- `revision = "20260522_0007"`
- `down_revision = "20260521_0006"`
- Create all eight tables from the coding spec.
- Add `uq_practice_session_user_plan_problem` on `practice_session(user_id, study_plan_id, problem_id)`.
- Add `uq_user_profile_snapshot_user_version` on `user_profile_snapshot(user_id, version_number)`.
- Add `uq_session_summary_session` on `session_summary(session_id)`.
- Add indexes listed in the coding spec sections 4.2 through 4.9.
- Drop indexes and tables in reverse dependency order in `downgrade()`.

- [ ] **Step 5: Verify model tests pass**

Run:

```bash
uv run pytest backend/tests/test_practice_models.py -q
```

Expected: PASS.

- [ ] **Step 6: Verify migration imports**

Run:

```bash
uv run alembic heads
```

Expected: command succeeds and includes `20260522_0007`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/practice.py backend/app/models/__init__.py backend/app/db/migrations/versions/20260522_0007_practice_profile.py backend/tests/test_practice_models.py
git commit -m "feat: add practice and profile persistence models"
```

---

### Task 3: Profile Provider And Snapshot Service

**Files:**
- Create: `backend/app/services/profile_provider.py`
- Create: `backend/app/services/profile_service.py`
- Test: `backend/tests/test_profile_provider.py`

- [ ] **Step 1: Write provider tests**

Create `backend/tests/test_profile_provider.py`:

```python
import pytest

from backend.app.services.profile_provider import ProfileSnapshot


def test_profile_snapshot_excludes_sensitive_long_form_content() -> None:
    snapshot = ProfileSnapshot(
        id=None,
        version="profile-snapshot-v1",
        source="mock_from_goal_and_plan",
        confidence="low",
        overall_level="beginner",
        preferred_training_mode="guided",
        weak_stuck_points=["edge_case"],
        strong_skill_tags=[],
        weak_skill_tags=["hash-table"],
        recent_summary="最近需要先确认边界。",
        hint_policy_hint="先追问边界，不直接给完整流程。",
        coach_strategy={"start_phase": "understand_problem"},
        evidence=[{"source": "study_plan", "summary": "计划项聚焦哈希表"}],
    )

    payload = snapshot.to_prompt_payload()

    assert payload["source"] == "mock_from_goal_and_plan"
    assert "完整代码" not in str(payload)
    assert "完整题解" not in str(payload)


@pytest.mark.asyncio
async def test_empty_profile_provider_returns_low_confidence_snapshot() -> None:
    from backend.app.services.profile_provider import EmptyProfileProvider

    provider = EmptyProfileProvider()
    snapshot = await provider.get_snapshot(
        user_id=1,
        problem_id=2,
        study_plan_id=3,
        plan_item_id=4,
    )

    assert snapshot.confidence == "low"
    assert snapshot.source == "mock_from_goal_and_plan"
```

- [ ] **Step 2: Run provider tests and verify they fail**

Run:

```bash
uv run pytest backend/tests/test_profile_provider.py -q
```

Expected: FAIL because `profile_provider.py` does not exist.

- [ ] **Step 3: Implement provider DTO and empty provider**

Create `backend/app/services/profile_provider.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession


ProfileSource = Literal[
    "initial_goal_plan",
    "mock_from_goal_and_plan",
    "summary_patch",
    "manual_repair",
]
ProfileConfidence = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ProfileSnapshot:
    id: int | None
    version: str
    source: ProfileSource
    confidence: ProfileConfidence
    overall_level: str
    preferred_training_mode: str
    weak_stuck_points: list[str] = field(default_factory=list)
    strong_skill_tags: list[str] = field(default_factory=list)
    weak_skill_tags: list[str] = field(default_factory=list)
    recent_summary: str = ""
    hint_policy_hint: str = ""
    coach_strategy: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "source": self.source,
            "confidence": self.confidence,
            "overall_level": self.overall_level,
            "preferred_training_mode": self.preferred_training_mode,
            "weak_stuck_points": self.weak_stuck_points,
            "strong_skill_tags": self.strong_skill_tags,
            "weak_skill_tags": self.weak_skill_tags,
            "recent_summary": self.recent_summary[:800],
            "hint_policy_hint": self.hint_policy_hint[:400],
            "coach_strategy": self.coach_strategy,
            "evidence": self.evidence[:8],
        }


class ProfileProvider(Protocol):
    async def get_snapshot(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        problem_id: int,
        study_plan_id: int,
        plan_item_id: int | None = None,
    ) -> ProfileSnapshot:
        ...


class EmptyProfileProvider:
    async def get_snapshot(
        self,
        session: AsyncSession | None = None,
        *,
        user_id: int,
        problem_id: int,
        study_plan_id: int,
        plan_item_id: int | None = None,
    ) -> ProfileSnapshot:
        return ProfileSnapshot(
            id=None,
            version="profile-snapshot-v1",
            source="mock_from_goal_and_plan",
            confidence="low",
            overall_level="unknown",
            preferred_training_mode="independent",
            hint_policy_hint="画像置信度低，先根据用户本轮输入判断训练阶段。",
            coach_strategy={"start_phase": "understand_problem"},
            evidence=[
                {
                    "source": "fallback",
                    "summary": "尚无长期画像，使用保守起手策略。",
                }
            ],
        )
```

- [ ] **Step 4: Implement profile service**

Create `backend/app/services/profile_service.py` with:

- `latest_profile_snapshot`
- `snapshot_payload`
- `ensure_initial_profile_snapshot`
- `validate_profile_patch`
- `apply_profile_delta`

Rules from coding spec section 4.9 must be enforced:

- no evidence means rejected delta;
- accepted delta creates a new `UserProfileSnapshot`;
- old snapshots are never updated in place.

- [ ] **Step 5: Verify provider tests pass**

Run:

```bash
uv run pytest backend/tests/test_profile_provider.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/profile_provider.py backend/app/services/profile_service.py backend/tests/test_profile_provider.py
git commit -m "feat: add AI coach profile provider"
```

---

### Task 4: Practice Session Service

**Files:**
- Create: `backend/app/services/practice_session_service.py`
- Test: `backend/tests/test_practice_session_service.py`

- [ ] **Step 1: Write service tests**

Create tests for these behaviors:

```python
import pytest


@pytest.mark.asyncio
async def test_same_plan_problem_reuses_practice_session(db_session, user, study_plan_item):
    from backend.app.services.practice_session_service import get_or_create_session_for_plan_item

    first = await get_or_create_session_for_plan_item(db_session, user, study_plan_item.id)
    second = await get_or_create_session_for_plan_item(db_session, user, study_plan_item.id)

    assert first.id == second.id


@pytest.mark.asyncio
async def test_user_message_creates_practice_event(db_session, user, practice_session):
    from backend.app.schemas.practice import PracticeMessageCreate
    from backend.app.services.practice_session_service import append_user_message

    result = await append_user_message(
        db_session,
        user,
        practice_session.id,
        PracticeMessageCreate(intent="describe_idea", content_md="我先讲暴力解法。"),
    )

    assert result.event_id > 0
    assert result.session_id == practice_session.id
```

Reuse the authenticated user, study plan, version, stage, item, and problem fixture construction style from `backend/tests/test_learning_api.py` and `backend/tests/test_learning_plan_service.py`; keep fixture names local to this test file if shared fixtures do not already exist.

- [ ] **Step 2: Run service tests and verify they fail**

Run:

```bash
uv run pytest backend/tests/test_practice_session_service.py -q
```

Expected: FAIL because the service does not exist.

- [ ] **Step 3: Implement service functions**

Create `backend/app/services/practice_session_service.py` with:

```text
PracticeSessionError
get_or_create_session_for_plan_item
get_session_payload
list_session_events
append_user_message
save_code_snapshot
record_submission_feedback
```

Implementation constraints:

- Look up `StudyPlanItem`, `StudyPlanVersion`, `StudyPlan`, and `Problem`.
- Verify all loaded objects belong to the current user through the plan relationship.
- Reuse session by `user_id + study_plan_id + problem_id`.
- Update `latest_plan_version_id`, `latest_plan_item_id`, `last_activity_at`, and `profile_snapshot_json` on every plan-item entry.
- Create `session_started` event only on first creation.
- Compute `code_hash` with SHA-256 for code snapshots.
- Submission result `ac` sets phase to `summarize`; other concrete results set phase to `analyze_feedback`.

- [ ] **Step 4: Verify service tests pass**

Run:

```bash
uv run pytest backend/tests/test_practice_session_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/practice_session_service.py backend/tests/test_practice_session_service.py
git commit -m "feat: add practice session service"
```

---

### Task 5: Practice API Routes

**Files:**
- Create: `backend/app/api/practice.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_practice_api.py`

- [ ] **Step 1: Write API tests**

Create `backend/tests/test_practice_api.py` with tests for:

```python
def test_plan_item_entry_requires_login(client, study_plan_item):
    response = client.post(f"/api/study-plan/items/{study_plan_item.id}/practice-session")

    assert response.status_code in {401, 403}


def test_plan_item_entry_returns_session(authenticated_client, study_plan_item):
    response = authenticated_client.post(
        f"/api/study-plan/items/{study_plan_item.id}/practice-session"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] > 0
    assert body["latest_plan_item_id"] == study_plan_item.id
```

Match the repository's existing async test client fixture style.

- [ ] **Step 2: Run API tests and verify they fail**

Run:

```bash
uv run pytest backend/tests/test_practice_api.py -q
```

Expected: FAIL because the route is not registered.

- [ ] **Step 3: Implement route file**

Create `backend/app/api/practice.py` with routes:

```text
POST /api/study-plan/items/{item_id}/practice-session
GET /api/practice-sessions/{session_id}
GET /api/practice-sessions/{session_id}/events
POST /api/practice-sessions/{session_id}/messages
POST /api/practice-sessions/{session_id}/code-snapshots
POST /api/practice-sessions/{session_id}/submission-feedback
POST /api/practice-sessions/{session_id}/summary
```

Route rules:

- Use `current_user_dependency`.
- Use `get_session`.
- Map service errors containing `not_found` to 404.
- Map ownership and state conflicts to 400 or 409 with stable `detail`.
- Do not log full user input or code.

- [ ] **Step 4: Register router**

Modify `backend/app/main.py` to include:

```python
from backend.app.api import practice
```

and:

```python
app.include_router(practice.router, prefix="/api")
```

- [ ] **Step 5: Verify API tests pass**

Run:

```bash
uv run pytest backend/tests/test_practice_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/practice.py backend/app/main.py backend/tests/test_practice_api.py
git commit -m "feat: add practice session API"
```

---

### Task 6: Coach Guard And LLM Run Registry

**Files:**
- Create: `backend/app/services/coach_guard.py`
- Create: `backend/app/services/learning_flows/coach_turn.py`
- Create: `backend/app/services/learning_flows/coach_summary.py`
- Modify: `backend/app/services/llm_run_registry.py`
- Modify: `backend/app/services/llm_orchestrator.py`
- Test: `backend/tests/test_coach_guard.py`

- [ ] **Step 1: Write guard tests**

Create `backend/tests/test_coach_guard.py`:

```python
from backend.app.services.coach_guard import guard_transition


def test_rejects_feedback_analysis_without_submission_feedback() -> None:
    result = guard_transition(
        phase_before="review_code",
        proposed_phase_after="analyze_feedback",
        has_code=True,
        has_submission_feedback=False,
        hint_level="questioning",
        should_reveal_solution=False,
    )

    assert result.accepted is False
    assert result.phase_after == "review_code"


def test_ac_feedback_can_enter_summary() -> None:
    result = guard_transition(
        phase_before="analyze_feedback",
        proposed_phase_after="summarize",
        has_code=True,
        has_submission_feedback=True,
        hint_level="reflection",
        should_reveal_solution=False,
    )

    assert result.accepted is True
    assert result.phase_after == "summarize"


def test_low_hint_rejects_solution_reveal() -> None:
    result = guard_transition(
        phase_before="optimize_solution",
        proposed_phase_after="optimize_solution",
        has_code=False,
        has_submission_feedback=False,
        hint_level="questioning",
        should_reveal_solution=True,
    )

    assert result.accepted is False
    assert "hint" in result.reason
```

- [ ] **Step 2: Run guard tests and verify they fail**

Run:

```bash
uv run pytest backend/tests/test_coach_guard.py -q
```

Expected: FAIL because `coach_guard.py` does not exist.

- [ ] **Step 3: Implement guard**

Create `backend/app/services/coach_guard.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass


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
    return GuardDecision(
        accepted=True,
        phase_after=proposed_phase_after,
        hint_level_after=hint_level,
        reason="accepted",
    )
```

- [ ] **Step 4: Add LLM run handlers**

Create minimal handlers:

- `backend/app/services/learning_flows/coach_turn.py`
- `backend/app/services/learning_flows/coach_summary.py`

The first implementation returns this deterministic safe reply while prompt wiring is completed in the same task:

```text
我已经记录你的输入。先说明你的暴力解法、你准备维护的关键状态，以及你认为必须覆盖的边界用例。
```

It must still:

- load session context;
- load profile snapshot;
- persist assistant event;
- persist coach turn;
- publish `progress`, `delta`, and `result` events through existing `publish`.

- [ ] **Step 5: Register run kinds**

Modify `backend/app/services/llm_run_registry.py`:

```python
from backend.app.services.learning_flows.coach_summary import CoachSummaryHandler
from backend.app.services.learning_flows.coach_turn import CoachTurnHandler
```

Add specs:

```python
"coach_turn": RunKindSpec(
    handler=CoachTurnHandler(),
    related_type="practice_session",
    related_id_key="session_id",
),
"coach_summary": RunKindSpec(
    handler=CoachSummaryHandler(),
    related_type="practice_session",
    related_id_key="session_id",
),
```

- [ ] **Step 6: Verify guard tests pass**

Run:

```bash
uv run pytest backend/tests/test_coach_guard.py -q
```

Expected: PASS.

- [ ] **Step 7: Run LLM registry tests**

Run:

```bash
uv run pytest backend/tests/test_learning_flows.py backend/tests/test_learning_api.py -q
```

Expected: PASS. Existing goal calibration run kinds must remain registered and working.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/coach_guard.py backend/app/services/learning_flows/coach_turn.py backend/app/services/learning_flows/coach_summary.py backend/app/services/llm_run_registry.py backend/app/services/llm_orchestrator.py backend/tests/test_coach_guard.py
git commit -m "feat: add coach guard and run handlers"
```

---

### Task 7: Frontend Practice API And Routing

**Files:**
- Create: `frontend/src/api/practice.ts`
- Modify: `frontend/src/routes/AppRoutes.tsx`
- Modify: `frontend/src/pages/StudyPlanPage.tsx`
- Test: `frontend/src/pages/StudyPlanPage.test.tsx`

- [ ] **Step 1: Write route/link test**

Extend `frontend/src/pages/StudyPlanPage.test.tsx` with an assertion that a plan item links to:

```text
/workspace/items/{itemId}
```

- [ ] **Step 2: Run frontend test and verify it fails**

Run:

```bash
cd frontend && corepack pnpm test -- StudyPlanPage.test.tsx
```

Expected: FAIL because the link is still `/workspace/:slug` or absent.

- [ ] **Step 3: Add practice API client**

Create `frontend/src/api/practice.ts` with exported functions:

```typescript
import { requestJson } from './client'

export type HintLevel = 'questioning' | 'direction' | 'key_hint' | 'reflection'
export type UserIntent =
  | 'describe_idea'
  | 'stuck'
  | 'request_hint'
  | 'code_review'
  | 'submit_feedback'
  | 'request_summary'
  | 'unknown'

export type PracticeSession = {
  id: number
  study_plan_id: number
  problem_id: number
  problem_slug: string
  latest_plan_version_id: number
  latest_plan_item_id: number
  training_mode: string
  phase: string
  status: string
  current_hint_level: HintLevel
  visible_hint_gear: HintLevel
  max_hint_level_used: HintLevel | null
  attempt_count: number
  final_result: string | null
  profile_snapshot: {
    version: string
    source: string
    confidence: string
    overall_level: string
    preferred_training_mode: string
    weak_stuck_points: string[]
    strong_skill_tags: string[]
    weak_skill_tags: string[]
    recent_summary: string
    hint_policy_hint: string
  }
  events: PracticeEvent[]
}

export type PracticeEvent = {
  id: number
  event_type: string
  role: string
  phase: string
  intent: UserIntent | null
  content_md: string
  payload: Record<string, unknown>
  hint_level: HintLevel | null
  visible_hint_gear: HintLevel | null
  created_at: string
}

export function createPracticeSessionForItem(itemId: number) {
  return requestJson<PracticeSession>(`/api/study-plan/items/${itemId}/practice-session`, {
    method: 'POST',
  })
}
```

Add the remaining API functions listed in the coding spec section 9.3 in the same file.

- [ ] **Step 4: Add route**

Modify `frontend/src/routes/AppRoutes.tsx`:

```tsx
<Route path="/workspace/items/:itemId" element={<WorkspacePage />} />
```

- [ ] **Step 5: Update study plan links**

In `StudyPlanPage.tsx`, make plan item primary action navigate to:

```typescript
`/workspace/items/${item.id}`
```

- [ ] **Step 6: Verify frontend route/link test passes**

Run:

```bash
cd frontend && corepack pnpm test -- StudyPlanPage.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/practice.ts frontend/src/routes/AppRoutes.tsx frontend/src/pages/StudyPlanPage.tsx frontend/src/pages/StudyPlanPage.test.tsx
git commit -m "feat: add practice workspace route"
```

---

### Task 8: Workspace UI Composition

**Files:**
- Create: `frontend/src/pages/workspace/CoachPanel.tsx`
- Create: `frontend/src/pages/workspace/CodePane.tsx`
- Create: `frontend/src/pages/workspace/ProblemPane.tsx`
- Create: `frontend/src/pages/workspace/SubmissionFeedbackModal.tsx`
- Create: `frontend/src/pages/workspace/types.ts`
- Create: `frontend/src/pages/workspace/coachDisplay.ts`
- Modify: `frontend/src/pages/WorkspacePage.tsx`
- Test: `frontend/src/pages/WorkspacePage.test.tsx`
- Test: `frontend/src/pages/workspace/CoachPanel.test.tsx`

- [ ] **Step 1: Write UI tests**

Add tests that verify:

```text
计划题入口加载 practice session
教练面板展示画像来源和置信度
提交回填按钮存在
```

- [ ] **Step 2: Run UI tests and verify they fail**

Run:

```bash
cd frontend && corepack pnpm test -- WorkspacePage.test.tsx CoachPanel.test.tsx
```

Expected: FAIL because the new panels do not exist.

- [ ] **Step 3: Implement panel components**

Component responsibilities:

- `ProblemPane`: receive problem markdown and render the existing sanitized markdown path.
- `CodePane`: local code draft, language selector, save button, calls `saveCodeSnapshot`.
- `CoachPanel`: show session state, profile snapshot, event timeline, message input, hint request controls, and SSE result state through existing `useLlmRun`.
- `SubmissionFeedbackModal`: structured result form for AC/WA/TLE/RE/MLE/CE/Unknown.
- `coachDisplay.ts`: map phases and hint levels to Chinese labels.

- [ ] **Step 4: Modify WorkspacePage**

`WorkspacePage` behavior:

- If `itemId` route param exists, call `createPracticeSessionForItem(Number(itemId))`.
- If `slug` route param exists and no itemId exists, keep current problem-only behavior.
- Render plan-item workbench only after session payload is loaded.
- Preserve existing Chinese题面 extraction.

- [ ] **Step 5: Verify UI tests pass**

Run:

```bash
cd frontend && corepack pnpm test -- WorkspacePage.test.tsx CoachPanel.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/WorkspacePage.tsx frontend/src/pages/workspace frontend/src/pages/WorkspacePage.test.tsx
git commit -m "feat: build profile-driven workspace UI"
```

---

### Task 9: Summary And Profile Delta Flow

**Files:**
- Modify: `backend/app/services/profile_service.py`
- Modify: `backend/app/services/learning_flows/coach_summary.py`
- Test: `backend/tests/test_profile_provider.py`
- Test: `backend/tests/test_practice_session_service.py`

- [ ] **Step 1: Add summary/profile tests**

Add tests for:

```text
summary generation creates session_summary
profile_delta with evidence is accepted
profile_delta without evidence is rejected
accepted delta creates new user_profile_snapshot version
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run pytest backend/tests/test_profile_provider.py backend/tests/test_practice_session_service.py -q
```

Expected: FAIL for missing summary/profile merge behavior.

- [ ] **Step 3: Implement merge behavior**

Rules:

- `coach_summary` creates or updates one `session_summary` per session.
- `profile_update_suggestion_json` from summary is converted to `profile_delta.patch_json`.
- `profile_delta.evidence_json` must include at least one evidence item with `source` and `summary`.
- Accepted delta creates a new `user_profile_snapshot`.
- Rejected delta keeps `next_snapshot_id` empty and records `rejection_reason`.

- [ ] **Step 4: Verify summary/profile tests pass**

Run:

```bash
uv run pytest backend/tests/test_profile_provider.py backend/tests/test_practice_session_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/profile_service.py backend/app/services/learning_flows/coach_summary.py backend/tests/test_profile_provider.py backend/tests/test_practice_session_service.py
git commit -m "feat: persist practice summary profile updates"
```

---

### Task 10: Documentation And Full Verification

**Files:**
- Modify: `docs/index.md`
- Modify: `docs/architecture/foundation.md`
- Modify: `docs/architecture/makefile.md` when verification commands change; this plan expects no command changes.
- Modify: `docs/prd/prd.md` when shipped behavior differs from PRD; this plan expects no product scope changes.

- [ ] **Step 1: Update docs impacted by implementation**

Required updates:

- `docs/index.md`: add new backend and frontend modules.
- `docs/architecture/foundation.md`: add practice/profile tables, APIs, and service boundaries.
- `docs/architecture/makefile.md`: no change unless commands changed.

- [ ] **Step 2: Run backend verification**

Run:

```bash
uv run ruff check .
uv run mypy backend
uv run pytest -q
```

Expected: all commands exit 0.

- [ ] **Step 3: Run frontend verification**

Run:

```bash
cd frontend && corepack pnpm lint
cd frontend && corepack pnpm test
cd frontend && corepack pnpm build
```

Expected: all commands exit 0. Vite chunk size warnings are acceptable if build exits 0.

- [ ] **Step 4: Run migration smoke check**

Run:

```bash
uv run alembic upgrade head
```

Expected: database migrates through `20260522_0007`.

- [ ] **Step 5: Commit docs and final verification fixes**

```bash
git add docs/index.md docs/architecture/foundation.md docs/architecture/makefile.md docs/prd/prd.md
git commit -m "docs: document practice profile implementation"
```

If only `docs/index.md` and `docs/architecture/foundation.md` changed, add only those files.

---

## Self-Review

Spec coverage:

- Workbench session identity is covered by Tasks 2, 4, and 5.
- Profile snapshot and profile delta are covered by Tasks 2, 3, and 9.
- AI coach guardrails are covered by Task 6.
- Frontend plan-item workbench is covered by Tasks 7 and 8.
- Summary and profile update loop is covered by Task 9.
- Documentation and verification are covered by Task 10.

Placeholder scan:

- This plan avoids open-ended placeholder steps. Implementation details that are larger than a snippet are anchored to the exact coding spec sections and exact file paths.

Type consistency:

- Backend schemas use `questioning | direction | key_hint | reflection` for hint levels.
- Practice phase names match both PRDs and the coding spec.
- Frontend route `/workspace/items/:itemId` matches the backend plan-item entry route.

Plan complete. Execute tasks in order and commit after each task.
