# Model Backed Coach Turn Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让工作台 `coach_turn` 使用用户配置的大模型生成教练回复，避免继续输出固定模板。

**Architecture:** `coach_turn` 仍走统一 LLM Run 编排层，由 registry 标记为需要模型资产；flow 内只接受结构化 JSON 输出，先经过后端守卫再持久化 assistant event 和 `coach_turn`。`coach_summary` 暂时保留确定性安全回复，避免把复盘画像合并扩大到同一改动。

**Tech Stack:** Python 3.12, FastAPI service layer, SQLAlchemy async, pytest, uv。

---

### Task 1: 回归测试

**Files:**
- Modify: `backend/tests/test_learning_flows.py`
- Modify: `backend/tests/test_llm_run_registry.py`
- Modify: `backend/tests/test_llm_runs_api.py`

- [x] **Step 1: 写失败测试**

新增一个 fake coach provider，输出：

```json
{
  "phase_after": "define_invariant",
  "diagnosed_stuck_point": "hash_state_needs_precision",
  "next_action": "ask_hash_invariant",
  "reply_md": "你已经给出了哈希表方向，不需要回到暴力解法。下一步说清楚哈希表里存的是值还是下标，以及遍历到当前数时先查还是先写。",
  "should_reveal_solution": false
}
```

并断言 `run_coach_turn()` 持久化这段回复，而不是固定 `SAFE_REPLY`。

- [x] **Step 2: 验证测试失败**

Run: `uv run pytest backend/tests/test_learning_flows.py::test_coach_turn_uses_model_reply_when_user_already_described_hash_idea backend/tests/test_llm_run_registry.py::test_current_coach_turn_requires_model_asset -q`

Expected: FAIL；当前代码忽略 provider，且 registry 仍声明 `coach_turn` 不需要模型资产。

### Task 2: 模型驱动 coach turn

**Files:**
- Modify: `backend/app/services/learning_flows/coach_turn.py`
- Modify: `backend/app/services/llm_run_registry.py`
- Modify: `backend/app/services/llm_orchestrator.py`

- [x] **Step 1: 添加 coach prompt 和 JSON 解析**

在 `coach_turn.py` 中添加中文 coach 指令、允许状态集合、`_stream_coach_decision()`、`_parse_coach_json()` 和 fallback 构造函数。provider 异常或 JSON 不合法时，`coach_turn` 使用安全 fallback，但记录 warning。

- [x] **Step 2: 使用模型输出再过守卫**

`run_coach_turn()` 对 `coach_turn` 调用 provider，拿到模型建议后再调用 `guard_transition()`。如果守卫拒绝状态跳转，回复仍保留模型内容，但状态保持守卫结果；`should_reveal_solution=True` 且低提示档会被守卫拒绝。

- [x] **Step 3: 只切换 `coach_turn` 模型依赖**

`llm_run_registry.py` 将 `coach_turn.requires_model` 改为 `True`，`coach_summary` 暂时保持 `False`。更新 orchestrator 测试，确认 `coach_turn` 会选择模型资产。

### Task 3: 文档和验证

**Files:**
- Modify: `docs/architecture/foundation.md`
- Modify: `docs/project-todolist.md` if the progress table still says coach API has no model config.

- [x] **Step 1: 更新架构文档**

把“工作台教练当前不要求模型资产”的描述改为：`coach_turn` 已接入模型资产和结构化输出，`coach_summary` 暂时保留确定性复盘沉淀。

- [x] **Step 2: 运行验证**

Run:

```bash
uv run pytest backend/tests/test_learning_flows.py backend/tests/test_llm_run_registry.py backend/tests/test_llm_runs_api.py -q
```

Expected: PASS。
