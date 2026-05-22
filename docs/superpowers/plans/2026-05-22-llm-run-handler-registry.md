# LLM Run Handler Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor LLM Run orchestration so `execute_llm_run` owns the generic lifecycle while per-`kind` business logic is delegated through a handler registry.

**Architecture:** Add a new `llm_run_registry` service module containing `RunKindSpec`, `LlmRunContext`, handler protocol/implementations, and payload-to-related-object mapping. Update API creation and orchestrator dispatch to use the registry while keeping the current SSE protocol, DB schema, event hub, and learning flows unchanged.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, pytest, uv.

---

## File Structure

- Create `backend/app/services/llm_run_registry.py`: registry, handler protocol, context dataclass, current handlers for `goal_followup` and `goal_plan_generate`, metadata-only `study_plan_adjustment`, and `related_from_payload`.
- Create `backend/tests/test_llm_run_registry.py`: focused unit tests for registry mapping and handler delegation.
- Modify `backend/app/api/llm_runs.py`: import `related_from_payload` from registry and remove the local hard-coded mapping function.
- Modify `backend/app/services/llm_orchestrator.py`: replace direct learning flow imports and `if/else` dispatch with `handler_for_kind` and `LlmRunContext`.
- Modify `backend/tests/test_llm_runs_api.py`: update orchestrator tests to patch registry handler lookup instead of concrete flow functions.

## Task 1: Add Registry Unit Tests

**Files:**
- Create: `backend/tests/test_llm_run_registry.py`

- [ ] **Step 1: Write failing tests for registry mapping and handler delegation**

Create `backend/tests/test_llm_run_registry.py` with:

```python
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from backend.app.services.llm_run_registry import (
    GoalFollowupHandler,
    GoalPlanGenerateHandler,
    handler_for_kind,
    related_from_payload,
    supported_run_kinds,
)


def test_supported_run_kinds_contains_current_streaming_flows() -> None:
    assert supported_run_kinds() == {"goal_followup", "goal_plan_generate"}


def test_related_from_payload_returns_empty_for_initial_goal_followup() -> None:
    related_type, related_id = related_from_payload(
        "goal_followup",
        {
            "goal_type": "interview_sprint",
            "target_timeline": "within_1_month",
        },
    )

    assert related_type == ""
    assert related_id is None


def test_related_from_payload_maps_goal_followup_answer_to_draft() -> None:
    related_type, related_id = related_from_payload(
        "goal_followup",
        {"draft_id": 15, "question_id": "q1", "answer": "边界条件容易漏"},
    )

    assert related_type == "goal_calibration_draft"
    assert related_id == 15


def test_related_from_payload_maps_goal_plan_generate_to_draft() -> None:
    related_type, related_id = related_from_payload(
        "goal_plan_generate",
        {"draft_id": 15},
    )

    assert related_type == "goal_calibration_draft"
    assert related_id == 15


def test_related_from_payload_maps_study_plan_adjustment_to_plan() -> None:
    related_type, related_id = related_from_payload(
        "study_plan_adjustment",
        {"plan_id": 9},
    )

    assert related_type == "study_plan"
    assert related_id == 9


def test_related_from_payload_rejects_boolean_plan_id() -> None:
    related_type, related_id = related_from_payload(
        "study_plan_adjustment",
        {"plan_id": True},
    )

    assert related_type == ""
    assert related_id is None


def test_handler_for_kind_returns_registered_handler() -> None:
    assert isinstance(handler_for_kind("goal_followup"), GoalFollowupHandler)
    assert isinstance(handler_for_kind("goal_plan_generate"), GoalPlanGenerateHandler)
    assert handler_for_kind("study_plan_adjustment") is None


@pytest.mark.asyncio
async def test_goal_followup_handler_delegates_to_existing_flow(monkeypatch) -> None:
    calls: list[tuple[str, int, str]] = []

    async def fake_flow(
        session: Any,
        *,
        user_id: int,
        run: Any,
        provider: Any,
        model_name: str,
        publish: Any,
    ) -> dict[str, Any]:
        assert session == "session"
        assert run == "run"
        assert provider == "provider"
        assert publish == "publish"
        calls.append(("followup", user_id, model_name))
        return {"draft_id": 15, "status": "asking_followup"}

    monkeypatch.setattr(
        "backend.app.services.llm_run_registry.run_goal_followup",
        fake_flow,
    )
    context = SimpleNamespace(
        session="session",
        user_id=42,
        run="run",
        provider="provider",
        model_name="gpt-test",
        publish="publish",
    )

    result = await GoalFollowupHandler().execute(cast(Any, context))

    assert result == {"draft_id": 15, "status": "asking_followup"}
    assert calls == [("followup", 42, "gpt-test")]


@pytest.mark.asyncio
async def test_goal_plan_handler_delegates_to_existing_flow(monkeypatch) -> None:
    calls: list[tuple[str, int, str]] = []

    async def fake_flow(
        session: Any,
        *,
        user_id: int,
        run: Any,
        provider: Any,
        model_name: str,
        publish: Any,
    ) -> dict[str, Any]:
        assert session == "session"
        assert run == "run"
        assert provider == "provider"
        assert publish == "publish"
        calls.append(("plan", user_id, model_name))
        return {"draft_id": 15, "stage_count": 2, "item_count": 8}

    monkeypatch.setattr(
        "backend.app.services.llm_run_registry.run_goal_plan_generate",
        fake_flow,
    )
    context = SimpleNamespace(
        session="session",
        user_id=42,
        run="run",
        provider="provider",
        model_name="gpt-test",
        publish="publish",
    )

    result = await GoalPlanGenerateHandler().execute(cast(Any, context))

    assert result == {"draft_id": 15, "stage_count": 2, "item_count": 8}
    assert calls == [("plan", 42, "gpt-test")]
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
uv run pytest backend/tests/test_llm_run_registry.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.services.llm_run_registry'`.

## Task 2: Implement `llm_run_registry`

**Files:**
- Create: `backend/app/services/llm_run_registry.py`
- Test: `backend/tests/test_llm_run_registry.py`

- [ ] **Step 1: Add the registry module**

Create `backend/app/services/llm_run_registry.py` with:

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.llm_run import LlmRun
from backend.app.services.learning_flows.goal_calibration import run_goal_followup
from backend.app.services.learning_flows.goal_plan import run_goal_plan_generate
from backend.app.services.llm_providers.base import LlmProvider
from backend.app.services.llm_run_events import LlmRunEvent


@dataclass(frozen=True)
class LlmRunContext:
    session: AsyncSession
    user_id: int
    run: LlmRun
    provider: LlmProvider
    model_name: str
    publish: Callable[[LlmRunEvent], Awaitable[None]]


class LlmRunHandler(Protocol):
    async def execute(self, context: LlmRunContext) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class RunKindSpec:
    handler: LlmRunHandler | None
    related_type: str = ""
    related_id_key: str = ""


class GoalFollowupHandler:
    async def execute(self, context: LlmRunContext) -> dict[str, Any]:
        return await run_goal_followup(
            context.session,
            user_id=context.user_id,
            run=context.run,
            provider=context.provider,
            model_name=context.model_name,
            publish=context.publish,
        )


class GoalPlanGenerateHandler:
    async def execute(self, context: LlmRunContext) -> dict[str, Any]:
        return await run_goal_plan_generate(
            context.session,
            user_id=context.user_id,
            run=context.run,
            provider=context.provider,
            model_name=context.model_name,
            publish=context.publish,
        )


RUN_KIND_SPECS: dict[str, RunKindSpec] = {
    "goal_followup": RunKindSpec(
        handler=GoalFollowupHandler(),
        related_type="goal_calibration_draft",
        related_id_key="draft_id",
    ),
    "goal_plan_generate": RunKindSpec(
        handler=GoalPlanGenerateHandler(),
        related_type="goal_calibration_draft",
        related_id_key="draft_id",
    ),
    "study_plan_adjustment": RunKindSpec(
        handler=None,
        related_type="study_plan",
        related_id_key="plan_id",
    ),
}


def supported_run_kinds() -> set[str]:
    return {kind for kind, spec in RUN_KIND_SPECS.items() if spec.handler is not None}


def handler_for_kind(kind: str) -> LlmRunHandler | None:
    spec = RUN_KIND_SPECS.get(kind)
    return spec.handler if spec is not None else None


def related_from_payload(kind: str, payload: dict[str, Any]) -> tuple[str, int | None]:
    spec = RUN_KIND_SPECS.get(kind)
    if spec is None or not spec.related_type or not spec.related_id_key:
        return "", None
    related_id = payload.get(spec.related_id_key)
    if isinstance(related_id, int) and not isinstance(related_id, bool):
        return spec.related_type, related_id
    return "", None
```

Implementation note: `study_plan_adjustment` is metadata-only in this phase. It preserves the existing `study_plan/plan_id` relation at create time, but `handler_for_kind("study_plan_adjustment")` returns `None`, so streaming execution still fails with `run_kind_unsupported` until a real handler is added.

- [ ] **Step 2: Run registry tests and verify they pass**

Run:

```bash
uv run pytest backend/tests/test_llm_run_registry.py -q
```

Expected: PASS.

## Task 3: Move Related Object Mapping Out Of API Layer

**Files:**
- Modify: `backend/app/api/llm_runs.py`
- Test: `backend/tests/test_llm_runs_api.py`

- [ ] **Step 1: Add an API test proving registry mapping is used**

In `backend/tests/test_llm_runs_api.py`, add this test after `test_create_llm_run_returns_stream_url`:

```python
def test_create_llm_run_uses_registry_related_mapping(monkeypatch) -> None:
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
        return type("Run", (), {"id": 10, "kind": kind, "status": "pending", "stage": "queued"})()

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
    assert captured == {
        "kind": "goal_plan_generate",
        "payload": {"draft_id": 3},
        "related_type": "goal_calibration_draft",
        "related_id": 3,
    }
```

- [ ] **Step 2: Run the focused API test**

Run:

```bash
uv run pytest backend/tests/test_llm_runs_api.py::test_create_llm_run_uses_registry_related_mapping -q
```

Expected: PASS before or after the API refactor, proving current behavior.

- [ ] **Step 3: Replace API local mapping with registry import**

In `backend/app/api/llm_runs.py`, add:

```python
from backend.app.services.llm_run_registry import related_from_payload
```

Delete the local `_related_from_payload` function.

In `create_llm_run_route`, replace:

```python
related_type, related_id = _related_from_payload(payload.kind, payload.payload)
```

with:

```python
related_type, related_id = related_from_payload(payload.kind, payload.payload)
```

Keep the existing route comments about `stream_url` and run creation. Do not change response fields.

- [ ] **Step 4: Run API tests**

Run:

```bash
uv run pytest backend/tests/test_llm_runs_api.py::test_create_llm_run_returns_stream_url backend/tests/test_llm_runs_api.py::test_create_llm_run_uses_registry_related_mapping -q
```

Expected: PASS.

## Task 4: Update Orchestrator Tests For Handler Dispatch

**Files:**
- Modify: `backend/tests/test_llm_runs_api.py`

- [ ] **Step 1: Update plan success test to patch `handler_for_kind`**

In `test_orchestrator_goal_plan_success_publishes_result_after_success`, replace the `fake_flow` function with:

```python
    class FakeHandler:
        async def execute(self, context: Any) -> dict[str, Any]:
            assert context.user_id == 42
            assert context.run is run
            assert isinstance(context.provider, FakeProvider)
            assert context.model_name == credential.model_name
            calls.append("flow")
            run.display_text_md = "draft text"
            return {"draft_id": 7, "stage_count": 2, "item_count": 8}

    def fake_handler_for_kind(kind: str) -> Any:
        assert kind == "goal_plan_generate"
        calls.append("handler")
        return FakeHandler()
```

Replace:

```python
    monkeypatch.setattr(llm_orchestrator, "run_goal_plan_generate", fake_flow)
```

with:

```python
    monkeypatch.setattr(llm_orchestrator, "handler_for_kind", fake_handler_for_kind)
```

Update the expected `calls` list to include `"handler"` before `"select"`:

```python
    assert calls == [
        "publish:started",
        "handler",
        "publish:progress",
        "select",
        "decrypt",
        "mark_running",
        "provider",
        "flow",
        "succeed",
        "publish:result",
        "publish:done",
    ]
```

- [ ] **Step 2: Update followup success test to patch `handler_for_kind`**

In `test_orchestrator_goal_followup_success_publishes_result_after_success`, replace `fake_flow` and `fail_plan_flow` with:

```python
    class FakeHandler:
        async def execute(self, context: Any) -> dict[str, Any]:
            assert context.user_id == 42
            assert context.run is run
            assert isinstance(context.provider, FakeProvider)
            assert context.model_name == credential.model_name
            calls.append("followup_flow")
            run.display_text_md = "followup text"
            return {
                "draft_id": 7,
                "status": "asking_followup",
                "followup_question": "你的面试时间是？",
                "followup_question_id": "q1",
                "remaining_followups": 2,
            }

    def fake_handler_for_kind(kind: str) -> Any:
        assert kind == "goal_followup"
        return FakeHandler()
```

Delete monkeypatches for `run_goal_plan_generate` and `run_goal_followup`.

Add:

```python
    monkeypatch.setattr(llm_orchestrator, "handler_for_kind", fake_handler_for_kind)
```

The existing expected `calls` list remains:

```python
    assert calls == [
        "publish:started",
        "publish:progress",
        "mark_running",
        "provider",
        "followup_flow",
        "succeed",
        "publish:result",
        "publish:done",
    ]
```

- [ ] **Step 3: Update status conflict test to patch `handler_for_kind`**

In `test_orchestrator_status_conflict_rolls_back_without_result`, replace `fake_flow` with:

```python
    class FakeHandler:
        async def execute(self, context: Any) -> dict[str, Any]:
            run.display_text_md = "flushed draft text"
            return {"draft_id": 8}

    def fake_handler_for_kind(kind: str) -> Any:
        assert kind == "goal_plan_generate"
        return FakeHandler()
```

Replace:

```python
    monkeypatch.setattr(llm_orchestrator, "run_goal_plan_generate", fake_flow)
```

with:

```python
    monkeypatch.setattr(llm_orchestrator, "handler_for_kind", fake_handler_for_kind)
```

- [ ] **Step 4: Run modified orchestrator tests and verify failure before implementation**

Run:

```bash
uv run pytest backend/tests/test_llm_runs_api.py::test_orchestrator_goal_plan_success_publishes_result_after_success backend/tests/test_llm_runs_api.py::test_orchestrator_goal_followup_success_publishes_result_after_success backend/tests/test_llm_runs_api.py::test_orchestrator_status_conflict_rolls_back_without_result -q
```

Expected before orchestrator refactor: FAIL because `llm_orchestrator.handler_for_kind` does not exist.

## Task 5: Refactor `execute_llm_run` To Use Registry Handlers

**Files:**
- Modify: `backend/app/services/llm_orchestrator.py`
- Test: `backend/tests/test_llm_runs_api.py`

- [ ] **Step 1: Update imports**

In `backend/app/services/llm_orchestrator.py`, replace:

```python
from backend.app.services.learning_flows.goal_plan import (
    LearningFlowError,
    run_goal_plan_generate,
)
from backend.app.services.learning_flows.goal_calibration import run_goal_followup
```

with:

```python
from backend.app.services.learning_flows.goal_plan import LearningFlowError
from backend.app.services.llm_run_registry import LlmRunContext, handler_for_kind
```

Delete:

```python
SUPPORTED_RUN_KINDS = {"goal_followup", "goal_plan_generate"}
```

- [ ] **Step 2: Replace kind support check and flow dispatch**

In `execute_llm_run`, replace:

```python
            if run.kind not in SUPPORTED_RUN_KINDS:
                await _fail_and_publish(
                    session,
                    run,
                    run_id=run_id,
                    user_id=user_id,
                    error_code="run_kind_unsupported",
                )
                return
```

with:

```python
            handler = handler_for_kind(run.kind)
            if handler is None:
                await _fail_and_publish(
                    session,
                    run,
                    run_id=run_id,
                    user_id=user_id,
                    error_code="run_kind_unsupported",
                )
                return
```

Replace:

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
            else:
                result = await run_goal_plan_generate(
                    session,
                    user_id=user_id,
                    run=run,
                    provider=provider,
                    model_name=credential.model_name,
                    publish=lambda event: event_hub.publish(run_id, event),
                )
```

with:

```python
            result = await handler.execute(
                LlmRunContext(
                    session=session,
                    user_id=user_id,
                    run=run,
                    provider=provider,
                    model_name=credential.model_name,
                    publish=lambda event: event_hub.publish(run_id, event),
                )
            )
```

Keep credential selection, provider construction, `succeed_llm_run`, and final `result/done` publishing unchanged.

- [ ] **Step 3: Run orchestrator tests**

Run:

```bash
uv run pytest backend/tests/test_llm_runs_api.py::test_orchestrator_goal_plan_success_publishes_result_after_success backend/tests/test_llm_runs_api.py::test_orchestrator_goal_followup_success_publishes_result_after_success backend/tests/test_llm_runs_api.py::test_orchestrator_unsupported_kind_fails_and_publishes_error backend/tests/test_llm_runs_api.py::test_orchestrator_unsupported_kind_real_session_finishes_stream backend/tests/test_llm_runs_api.py::test_orchestrator_status_conflict_rolls_back_without_result -q
```

Expected: PASS.

## Task 6: Run Focused Regression Suite

**Files:**
- Verify only.

- [ ] **Step 1: Run LLM Run and learning flow tests**

Run:

```bash
uv run pytest backend/tests/test_llm_run_events.py backend/tests/test_llm_run_service.py backend/tests/test_llm_run_registry.py backend/tests/test_llm_runs_api.py backend/tests/test_learning_flows.py -q
```

Expected: PASS.

- [ ] **Step 2: Run syntax checks for changed modules**

Run:

```bash
uv run python -m py_compile backend/app/api/llm_runs.py backend/app/services/llm_orchestrator.py backend/app/services/llm_run_registry.py
```

Expected: exit 0.

- [ ] **Step 3: Check diffs for whitespace errors in touched files**

Run:

```bash
git diff --check -- backend/app/api/llm_runs.py backend/app/services/llm_orchestrator.py backend/app/services/llm_run_registry.py backend/tests/test_llm_run_registry.py backend/tests/test_llm_runs_api.py
```

Expected: exit 0.

## Task 7: Documentation Impact Check

**Files:**
- Inspect: `docs/index.md`
- Inspect: `docs/architecture/foundation.md`
- Inspect: `docs/data-flow.md`
- Inspect: `docs/superpowers/specs/2026-05-22-llm-run-handler-registry-design.md`

- [ ] **Step 1: Decide whether architecture docs need updates**

Check whether the implementation changes external API, SSE event names, DB schema, Docker, Makefile, or product behavior.

Expected result for this refactor:

```text
No architecture or product docs need updates because this is an internal orchestrator dispatch refactor.
docs/data-flow.md still accurately describes the runtime data flow.
The new design spec remains the detailed explanation for the registry pattern.
```

- [ ] **Step 2: Record final verification in the agent response**

Final response must include:

```text
已参考的文档：
- docs/index.md
- docs/architecture/foundation.md
- docs/data-flow.md
- docs/superpowers/specs/2026-05-22-llm-run-handler-registry-design.md

修改的代码文件：
- backend/app/services/llm_run_registry.py
- backend/app/api/llm_runs.py
- backend/app/services/llm_orchestrator.py
- backend/tests/test_llm_run_registry.py
- backend/tests/test_llm_runs_api.py

修改的文档文件：
- docs/superpowers/plans/2026-05-22-llm-run-handler-registry.md

不需要更新架构/产品文档的理由：
- API、SSE 事件协议、DB schema、Docker、Makefile 和产品行为不变；只是内部 handler 分发重构。

执行过的验证命令：
- uv run pytest ...
- uv run python -m py_compile ...
- git diff --check ...
```
