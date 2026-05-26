# Prompt Resource Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将后端静态 LLM prompt 正文迁移到 package resource 文件中，并用 Python registry 统一管理 key、版本和输出契约。

**Architecture:** Prompt 正文放在 `backend/app/prompts/resources/*.md`，通过 `importlib.resources` 读取，避免依赖当前工作目录。`backend.app.prompts.registry` 暴露 `get_prompt()` 和常用常量，业务 flow 只负责动态上下文组装和 provider 调用。现有 LLM Run、SSE、数据库字段和前端 API 不变。

**Tech Stack:** Python 3.12, `importlib.resources`, pytest, FastAPI 后端现有 LLM provider 抽象。

---

### Task 1: Prompt Registry 基础能力

**Files:**
- Create: `backend/app/prompts/__init__.py`
- Create: `backend/app/prompts/types.py`
- Create: `backend/app/prompts/registry.py`
- Create: `backend/app/prompts/resources/__init__.py`
- Create: `backend/app/prompts/resources/*.md`
- Test: `backend/tests/test_prompt_registry.py`

- [ ] **Step 1: Write the failing registry tests**

Create `backend/tests/test_prompt_registry.py` with tests that require:

```python
from backend.app.prompts import get_prompt


def test_get_prompt_loads_resource_text() -> None:
    prompt = get_prompt("coach_turn")

    assert prompt.key == "coach_turn"
    assert prompt.version == "coach-turn-v2-structured"
    assert "单题 AI 教练" in prompt.instructions
    assert "reply_md" in prompt.instructions


def test_prompt_registry_exposes_goal_plan_prompt_contracts() -> None:
    draft = get_prompt("goal_plan_draft")
    followup = get_prompt("goal_followup")

    assert draft.version == "goal-plan-v3-streaming"
    assert "默认语言语境：简体中文" in draft.instructions
    assert "problem_slug" in draft.instructions
    assert followup.version == "goal-plan-v3-streaming"
    assert "目标校准教练" in followup.instructions


def test_get_prompt_rejects_unknown_key() -> None:
    try:
        get_prompt("missing")
    except KeyError as exc:
        assert "unknown prompt key" in str(exc)
    else:
        raise AssertionError("unknown prompt key should fail")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest backend/tests/test_prompt_registry.py -q
```

Expected: fail because `backend.app.prompts` does not exist.

- [ ] **Step 3: Implement registry and resources**

Add immutable `PromptSpec`, resource loading via `importlib.resources.files`, and `.md` resource files for `goal_followup`, `goal_plan_draft`, `goal_plan_repair`, `legacy_learning_followup`, `legacy_learning_plan_draft`, `legacy_learning_plan_repair`, and `coach_turn`.

- [ ] **Step 4: Run registry tests**

Run:

```bash
uv run pytest backend/tests/test_prompt_registry.py -q
```

Expected: pass.

### Task 2: Migrate LLM flows to registry

**Files:**
- Modify: `backend/app/services/learning_flows/goal_calibration.py`
- Modify: `backend/app/services/learning_flows/goal_plan.py`
- Modify: `backend/app/services/learning_flows/coach_turn.py`
- Modify: `backend/app/services/learning_plan_llm.py`
- Test: `backend/tests/test_learning_flows.py`
- Test: `backend/tests/test_learning_llm_generation.py`

- [ ] **Step 1: Write flow-level assertions**

Extend existing tests so provider calls still receive prompt text containing key phrases from resources, and `learning_plan_llm` prompt constants still include default Chinese language context.

- [ ] **Step 2: Run targeted tests to verify current behavior**

Run:

```bash
uv run pytest backend/tests/test_learning_flows.py backend/tests/test_learning_llm_generation.py -q
```

Expected: pass before migration, proving existing behavior is covered.

- [ ] **Step 3: Replace inline prompt strings**

Import prompt specs from `backend.app.prompts` and replace inline prompt constants with `prompt.instructions` and `prompt.version`. Keep compatibility exports (`PROMPT_VERSION`, `PLAN_DRAFT_INSTRUCTIONS`, `FOLLOWUP_INSTRUCTIONS`, `REPAIR_PLAN_INSTRUCTIONS`, `COACH_REPLY_INSTRUCTIONS`) where tests or older services import them.

- [ ] **Step 4: Run targeted tests again**

Run:

```bash
uv run pytest backend/tests/test_prompt_registry.py backend/tests/test_learning_flows.py backend/tests/test_learning_llm_generation.py -q
```

Expected: pass.

### Task 3: Documentation impact

**Files:**
- Modify: `docs/index.md`
- Modify: `docs/architecture/foundation.md`

- [ ] **Step 1: Document the new module boundary**

Add `backend/app/prompts/` to `docs/index.md` and `docs/architecture/foundation.md` as the central static prompt resource registry.

- [ ] **Step 2: Run final verification**

Run:

```bash
uv run pytest backend/tests/test_prompt_registry.py backend/tests/test_learning_flows.py backend/tests/test_learning_llm_generation.py -q
```

Expected: pass.
