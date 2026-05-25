# 工作台教练聊天简化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 简化做题工作台教练聊天展示，并让 LeetCode 已 AC 后自动展示 Markdown 单题复盘结果。

**Architecture:** 前端移除教练区顶部状态标签，并只在聊天流中渲染真实用户文本和教练回复，系统事件继续由 session payload 保留但不展示成气泡。后端保持 `coach_summary` 自动 run，不新增 API，基于 `session_summary` 组装 Markdown 复盘并更新 assistant event。前端聊天和流式输出统一使用安全 Markdown 渲染。

**Tech Stack:** React + TypeScript + Vitest + Testing Library；FastAPI service 层 + pytest；项目命令通过 `uv run` 和 Corepack pnpm 执行。

---

### Task 1: 前端聊天展示过滤

**Files:**
- Modify: `frontend/src/pages/workspace/CoachPanel.test.tsx`
- Modify: `frontend/src/pages/workspace/CoachPanel.tsx`

- [x] **Step 1: Write the failing test**

在 `CoachPanel.test.tsx` 新增用例，构造包含 `session_started`、`submission_feedback`、`phase_changed`、`user_message` 和 `assistant_message` 的 session，断言只显示真实聊天正文，不显示顶部状态栏、内部事件、阶段和提示档位标签。

- [x] **Step 2: Run test to verify it fails**

Run: `cd frontend && corepack pnpm test -- CoachPanel.test.tsx --run`

Expected: FAIL，因为当前实现会展示顶部 `单题复盘 / summarizing / 追问档` 状态，且会展示 `session_started` 或 `已记录 LeetCode 结果`、阶段/提示档位标签。

- [x] **Step 3: Write minimal implementation**

在 `CoachPanel.tsx` 中移除 `coach-state-bar`，并为 `session.events` 增加过滤：

```ts
const chatEvents = session.events.filter((event) => {
  if (!event.content_md.trim()) {
    return false
  }
  return event.event_type === 'user_message' || event.event_type === 'assistant_message'
})
```

渲染时使用 `chatEvents`，并移除每条消息上的 `phaseLabel(event.phase)` 和 `hintLevelLabel(event.visible_hint_gear)` 标签，仅保留“我 / 教练”身份。

- [x] **Step 4: Run test to verify it passes**

Run: `cd frontend && corepack pnpm test -- CoachPanel.test.tsx --run`

Expected: PASS。

### Task 2: 复盘兜底回复

**Files:**
- Modify: `backend/tests/test_learning_flows.py`
- Modify: `backend/app/services/learning_flows/coach_turn.py`

- [x] **Step 1: Write the failing test**

在 `test_coach_summary_does_not_require_user_event_id` 中断言 `result["reply_md"]` 包含 AC 复盘语境，并不包含 `先说明你的暴力解法`。

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/test_learning_flows.py::test_coach_summary_does_not_require_user_event_id`

Expected: FAIL，因为当前 `coach_summary` fallback 使用普通教练安全话术。

- [x] **Step 3: Write minimal implementation**

在 `coach_turn.py` 中新增 `SUMMARY_SAFE_REPLY`，并让 `_fallback_coach_decision()` 在 `trigger_context["trigger"] == "request_summary"` 或 `trigger_context["next_action"] == "summarize_session"` 时返回该文案。

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest backend/tests/test_learning_flows.py::test_coach_summary_does_not_require_user_event_id`

Expected: PASS。

### Task 3: 集成验证和文档评估

**Files:**
- Test only: `frontend/src/pages/workspace/CoachPanel.test.tsx`
- Test only: `backend/tests/test_learning_flows.py`

- [x] **Step 1: Run focused frontend tests**

Run: `cd frontend && corepack pnpm test -- CoachPanel.test.tsx --run`

Expected: PASS。

- [x] **Step 2: Run focused backend tests**

Run: `uv run pytest backend/tests/test_learning_flows.py::test_coach_summary_does_not_require_user_event_id backend/tests/test_practice_session_service.py::test_ac_submission_feedback_without_code_snapshot_is_allowed`

Expected: PASS。

- [x] **Step 3: Check docs impact**

确认本次代码只落实既有 PRD 行为，不改变 API、目录结构、Docker、Makefile 或系统边界。除本规格和计划外，不需要更新架构或 PRD 文档。

### Task 4: 复盘正文和 Markdown 渲染补齐

**Files:**
- Modify: `backend/tests/test_learning_flows.py`
- Modify: `backend/app/services/learning_flows/coach_summary.py`
- Modify: `frontend/src/pages/workspace/CoachPanel.test.tsx`
- Modify: `frontend/src/pages/workspace/CoachPanel.tsx`
- Modify: `frontend/src/styles/app.css`

- [x] **Step 1: Write failing backend test**

在 `test_coach_summary_does_not_require_user_event_id` 中断言 `assistant.content_md` 以 `## 单题复盘` 开头，包含 `**本题最终结果**：AC`、最高提示档位和 `### 下一步训练建议`。

- [x] **Step 2: Write failing frontend tests**

在 `CoachPanel.test.tsx` 中新增聊天消息 Markdown 渲染测试和流式输出 Markdown 渲染测试，分别断言 `## 单题复盘` 与 `## 正在复盘` 被渲染成 heading。

- [x] **Step 3: Implement backend summary markdown**

在 `coach_summary.py` 中基于 `SessionSummary` 组装 Markdown 复盘，更新 assistant event、coach turn response 和 run display text。

- [x] **Step 4: Implement frontend markdown rendering**

在 `CoachPanel.tsx` 中用 `react-markdown`、`remark-gfm`、`rehype-raw` 和 `rehype-sanitize` 渲染聊天消息与流式输出，并在 CSS 中补充紧凑的 Markdown 样式。

- [x] **Step 5: Verify focused tests**

Run:

```bash
uv run pytest backend/tests/test_learning_flows.py::test_coach_summary_does_not_require_user_event_id
cd frontend && corepack pnpm test -- CoachPanel.test.tsx --run
```

Expected: PASS。
