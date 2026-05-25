# 做题工作台上下布局与轻量运行状态 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把做题工作台调整为上方自然展开题面、下方 ChatGPT 式教练区，并在 run 进行中只显示一行当前后端执行状态。

**Architecture:** 前端保持现有 `WorkspacePage`、`ProblemPane`、`CoachPanel` 边界，只把页面编排从左右两栏改为上下流式布局。后端继续复用 LLM Run SSE，不新增事件类型，只在 coach flow 内补充更细的 `progress` 事件。测试覆盖布局、状态行、聊天历史不混入系统事件，以及新增后端进度事件。

**Tech Stack:** FastAPI, SQLAlchemy async, React, TypeScript, Ant Design, TanStack Query, Vitest, pytest, uv.

---

## Current Workspace Notes

当前工作区已有未提交改动，包含 coach 聊天 markdown 渲染、隐藏结构化事件、复盘 markdown 回复等内容。执行本计划时必须保留这些改动，不要回滚；后续任务只在这些现有差异上继续叠加上下布局、轻量状态行、后端进度和文档同步。

## File Structure

- Modify: `frontend/src/pages/WorkspacePage.tsx`
  - 负责工作台页面编排，从 AntD `Row/Col` 两栏改成垂直内容流。
- Modify: `frontend/src/pages/WorkspacePage.test.tsx`
  - 覆盖计划题入口的上下布局和题面/教练顺序。
- Modify: `frontend/src/pages/workspace/CoachPanel.tsx`
  - 负责聊天历史、输入框操作和 run 状态行展示。
- Modify: `frontend/src/pages/workspace/CoachPanel.test.tsx`
  - 覆盖轻量状态行、取消按钮和状态不进入聊天历史。
- Modify: `frontend/src/styles/app.css`
  - 负责上下布局、题面自然展开和教练聊天区视觉约束。
- Modify: `backend/app/services/learning_flows/coach_turn.py`
  - 负责 coach turn / summary 共用的训练上下文、模型调用、守卫、保存进度事件。
- Modify: `backend/tests/test_learning_flows.py`
  - 覆盖新增 progress 序列和安全 message。
- Modify: `docs/architecture/foundation.md`
  - 同步当前工作台布局与轻量状态 SSE 行为。
- Modify: `docs/prd/ai-coach-workbench-prd.md`
  - 同步产品体验从左右布局改为上题面、下教练。

## Task 1: 前端上下布局测试

**Files:**
- Modify: `frontend/src/pages/WorkspacePage.test.tsx`

- [ ] **Step 1: 写布局失败测试**

在 `loads planned item workspace as problem and chat coach columns` 用例中改名并替换末尾布局断言：

```tsx
it('loads planned item workspace with problem above the chat coach', async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = input.toString()
    if (url === '/api/study-plan/items/40/practice-session') {
      expect(init?.method).toBe('POST')
      return okJson(stubPracticeSession())
    }
    if (url === '/api/problems/two-sum') {
      return okJson(stubProblemDetail('# Two Sum\n\n## 翻译\n\n计划题题面'))
    }
    return new Response('not found', { status: 404 })
  })
  vi.stubGlobal('fetch', fetchMock)

  const { container } = renderWorkspaceAt('/workspace/items/40', '/workspace/items/:itemId')

  expect(await screen.findByText('计划题题面')).toBeInTheDocument()
  expect(screen.getByText('先复述题意。')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '代码尝试记录' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'LeetCode 已 AC' })).toBeInTheDocument()
  expect(screen.queryByLabelText('代码草稿')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '保存快照' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '提交回填' })).not.toBeInTheDocument()
  expect(screen.queryByText('画像来源')).not.toBeInTheDocument()
  expect(container.querySelectorAll('.workspace-content-column')).toHaveLength(0)
  const panes = container.querySelectorAll('.workspace-vertical-flow > .workspace-pane')
  expect(panes).toHaveLength(2)
  expect(panes[0]).toHaveTextContent('题面')
  expect(panes[1]).toHaveTextContent('教练')
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/study-plan/items/40/practice-session',
    expect.objectContaining({ method: 'POST' }),
  )
})
```

- [ ] **Step 2: 运行前端单测验证失败**

Run:

```bash
cd frontend && corepack pnpm vitest run src/pages/WorkspacePage.test.tsx
```

Expected: FAIL，原因是当前 DOM 仍存在 `.workspace-content-column` 或缺少 `.workspace-vertical-flow`。

## Task 2: 实现上下布局

**Files:**
- Modify: `frontend/src/pages/WorkspacePage.tsx`
- Modify: `frontend/src/styles/app.css`

- [ ] **Step 1: 修改 WorkspacePage 垂直编排**

把 `Row`、`Col` 从 import 中移除：

```tsx
import { Alert, Button, Space, Tag, Typography } from 'antd'
```

把原 `Row/Col` 内容替换为：

```tsx
<div className="workspace-vertical-flow">
  <ProblemPane markdown={problem?.statement_md} isLoading={isLoading} />
  {sessionQuery.data ? (
    <CoachPanel
      session={sessionQuery.data}
      onSessionRefresh={() => {
        void sessionQuery.refetch()
      }}
    />
  ) : (
    <div className="workspace-pane">
      <h3>教练</h3>
      <Typography.Text type="secondary">从学习计划进入后启用 AI 教练。</Typography.Text>
    </div>
  )}
</div>
```

- [ ] **Step 2: 修改布局 CSS**

在 `frontend/src/styles/app.css` 中保留兼容旧类的基础样式，但新增垂直布局：

```css
.workspace-vertical-flow {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.workspace-vertical-flow > .workspace-pane {
  width: 100%;
}
```

保留 `.workspace-content-row`、`.workspace-content-column` 旧样式，避免影响未检查到的历史页面；`WorkspacePage` 不再渲染这些类。

- [ ] **Step 3: 运行布局测试验证通过**

Run:

```bash
cd frontend && corepack pnpm vitest run src/pages/WorkspacePage.test.tsx
```

Expected: PASS。

- [ ] **Step 4: 提交前端布局改动**

Run:

```bash
git add frontend/src/pages/WorkspacePage.tsx frontend/src/pages/WorkspacePage.test.tsx frontend/src/styles/app.css
git commit -m "feat: stack workspace problem above coach"
```

Expected: commit succeeds，且不包含其他未相关文件。

## Task 3: 教练轻量状态行测试

**Files:**
- Modify: `frontend/src/pages/workspace/CoachPanel.test.tsx`

- [ ] **Step 1: 更新运行状态测试**

把现有 `shows streaming output only while a coach run is active` 用例替换为：

```tsx
it('shows one lightweight backend status line while a coach run is active', () => {
  llmRunState.displayText = '正在生成新的教练回复'
  llmRunState.stage = '正在调用大模型'
  llmRunState.isRunning = true

  const { container, rerender } = render(
    <CoachPanel session={stubSession()} onSessionRefresh={vi.fn()} />,
  )

  expect(screen.getByText('正在调用大模型')).toHaveClass('coach-run-status-text')
  expect(screen.getByRole('button', { name: '取消' })).toBeInTheDocument()
  expect(container.querySelector('.coach-run-output')).toHaveTextContent(
    '正在生成新的教练回复',
  )
  expect(screen.queryByText('状态 正在调用大模型')).not.toBeInTheDocument()

  llmRunState.isRunning = false
  rerender(<CoachPanel session={stubSession()} onSessionRefresh={vi.fn()} />)

  expect(screen.queryByText('正在调用大模型')).not.toBeInTheDocument()
  expect(container.querySelector('.coach-run-output')).toBeNull()
})
```

保留已有 `keeps internal status and structured events out of the chat surface` 用例，确保状态不进入聊天历史。

- [ ] **Step 2: 运行 CoachPanel 测试验证失败**

Run:

```bash
cd frontend && corepack pnpm vitest run src/pages/workspace/CoachPanel.test.tsx
```

Expected: FAIL，原因是当前仍显示 `状态 ${llmRun.stage}`，没有 `.coach-run-status-text`。

## Task 4: 实现教练轻量状态行

**Files:**
- Modify: `frontend/src/pages/workspace/CoachPanel.tsx`
- Modify: `frontend/src/styles/app.css`

- [ ] **Step 1: 修改 CoachPanel 状态展示**

在 `CoachPanel` 中新增：

```tsx
const runStatusText = llmRun.isRunning && llmRun.stage ? llmRun.stage : ''
```

把按钮区里这段：

```tsx
{llmRun.isRunning && llmRun.stage ? (
  <Typography.Text type="secondary">状态 {llmRun.stage}</Typography.Text>
) : null}
```

替换为：

```tsx
{runStatusText ? (
  <Typography.Text type="secondary" className="coach-run-status-text">
    {runStatusText}
  </Typography.Text>
) : null}
```

- [ ] **Step 2: 增加状态行 CSS**

在 `frontend/src/styles/app.css` 中加入：

```css
.coach-run-status-text {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  color: #586158;
}
```

- [ ] **Step 3: 运行 CoachPanel 测试验证通过**

Run:

```bash
cd frontend && corepack pnpm vitest run src/pages/workspace/CoachPanel.test.tsx
```

Expected: PASS。

- [ ] **Step 4: 提交状态行改动**

Run:

```bash
git add frontend/src/pages/workspace/CoachPanel.tsx frontend/src/pages/workspace/CoachPanel.test.tsx frontend/src/styles/app.css
git commit -m "feat: show lightweight coach run status"
```

Expected: commit succeeds，且不回滚已有 markdown/chat cleanup 改动。

## Task 5: 后端 coach progress 测试

**Files:**
- Modify: `backend/tests/test_learning_flows.py`

- [ ] **Step 1: 新增 progress message 断言 helper**

在测试文件中新增 helper：

```python
def progress_messages(events: list[LlmRunEvent]) -> list[str]:
    return [
        str(event.data.get("message", ""))
        for event in events
        if event.name == "progress"
    ]
```

- [ ] **Step 2: 更新普通 coach turn 事件断言**

在 `test_coach_turn_uses_model_reply_when_user_already_described_hash_idea` 中，把事件序列断言改为：

```python
assert [event.name for event in events] == [
    "progress",
    "progress",
    "progress",
    "delta",
    "progress",
]
assert progress_messages(events) == [
    "正在准备训练上下文",
    "正在调用大模型",
    "正在校验教练阶段",
    "正在保存教练回复",
]
```

- [ ] **Step 3: 更新 coach summary 事件断言**

在 `test_coach_summary_does_not_require_user_event_id` 中改为同样的 progress 序列：

```python
assert [event.name for event in events] == [
    "progress",
    "progress",
    "progress",
    "delta",
    "progress",
]
assert progress_messages(events) == [
    "正在准备训练上下文",
    "正在调用大模型",
    "正在校验教练阶段",
    "正在保存教练回复",
]
```

- [ ] **Step 4: 运行后端 flow 测试验证失败**

Run:

```bash
uv run pytest backend/tests/test_learning_flows.py -k "coach_turn or coach_summary" -q
```

Expected: FAIL，原因是后端尚未发布新增 progress 事件。

## Task 6: 实现后端 coach progress

**Files:**
- Modify: `backend/app/services/learning_flows/coach_turn.py`

- [ ] **Step 1: 在 run_coach_turn 起始发布准备上下文状态**

在完成 `trigger_context` 后、日志前加入：

```python
    await _publish_progress(
        publish,
        run_id=run.id,
        stage="loading_context",
        message="正在准备训练上下文",
    )
```

- [ ] **Step 2: 把原生成状态改为调用模型**

将原先 `stage="coach_turn", message="正在生成教练回复"` 改为：

```python
    await _publish_progress(
        publish,
        run_id=run.id,
        stage="calling_model",
        message="正在调用大模型",
    )
```

- [ ] **Step 3: 在 guard_transition 前发布校验阶段**

在 `coach_decision = await _coach_decision(...)` 后、调用 `guard_transition(...)` 前加入：

```python
    await _publish_progress(
        publish,
        run_id=run.id,
        stage="guarding_transition",
        message="正在校验教练阶段",
    )
```

- [ ] **Step 4: 在保存 assistant event 前发布保存状态**

在 `await publish(LlmRunEvent("delta", ...))` 后、创建 `now = datetime.now(UTC)` 前加入：

```python
    await _publish_progress(
        publish,
        run_id=run.id,
        stage="saving_reply",
        message="正在保存教练回复",
    )
```

- [ ] **Step 5: 运行后端 flow 测试验证通过**

Run:

```bash
uv run pytest backend/tests/test_learning_flows.py -k "coach_turn or coach_summary" -q
```

Expected: PASS。

- [ ] **Step 6: 提交后端进度改动**

Run:

```bash
git add backend/app/services/learning_flows/coach_turn.py backend/tests/test_learning_flows.py
git commit -m "feat: stream coach run progress"
```

Expected: commit succeeds。

## Task 7: 文档同步

**Files:**
- Modify: `docs/architecture/foundation.md`
- Modify: `docs/prd/ai-coach-workbench-prd.md`

- [ ] **Step 1: 更新 foundation 工作台说明**

把 `docs/architecture/foundation.md` 中训练工作台布局描述改为：

```md
计划题训练工作台使用 `/workspace/items/:itemId` 路由作为学习计划项入口。前端会通过 practice API 创建或恢复同一个训练会话，页面采用上方题面、下方 Chat-first 教练区的上下布局；主界面不再维护独立代码草稿。用户把思路、卡点和代码直接发给教练，代码尝试记录由 `review_code` 流程自动提取并通过 session payload 回传，教练区提供代码尝试记录抽屉和“LeetCode 已 AC”动作。AI 教练消息和复盘通过统一 LLM Run SSE 层执行，前端不直接调用模型；run 进行中只在输入区附近显示一行当前后端状态，不把系统执行步骤写入聊天历史。
```

- [ ] **Step 2: 更新 PRD 进入工作台体验**

把 `docs/prd/ai-coach-workbench-prd.md` 的 4.1 第一段改为：

```md
用户从学习计划点击一道题进入工作台。

页面上方自然展开题面，下方展示 ChatGPT 式 AI 教练区。第一版不再在主界面放独立代码卡片；用户把思路、卡点和代码直接发给教练，系统只在进入 `review_code` 流程时自动提取代码并沉淀为代码尝试记录。AI 教练区不是空白聊天框，而是直接展示当前训练上下文：
```

在 5.1 主流程的用户发送后补充：

```md
-> 前端通过一行轻量状态展示后端当前步骤，例如准备上下文、调用大模型、校验阶段或保存回复
```

- [ ] **Step 3: 提交文档同步**

Run:

```bash
git add docs/architecture/foundation.md docs/prd/ai-coach-workbench-prd.md
git commit -m "docs: sync vertical workspace experience"
```

Expected: commit succeeds。

## Task 8: 全量验证

**Files:**
- No code changes unless verification exposes a failure.

- [ ] **Step 1: 运行前端相关测试**

Run:

```bash
cd frontend && corepack pnpm vitest run src/pages/WorkspacePage.test.tsx src/pages/workspace/CoachPanel.test.tsx
```

Expected: PASS。

- [ ] **Step 2: 运行后端相关测试**

Run:

```bash
uv run pytest backend/tests/test_learning_flows.py -k "coach_turn or coach_summary" -q
```

Expected: PASS。

- [ ] **Step 3: 运行格式和类型检查中与当前改动相关的项目命令**

Run:

```bash
uv run pytest backend/tests/test_llm_runs_api.py -q
cd frontend && corepack pnpm vitest run src/pages/WorkspacePage.test.tsx src/pages/workspace/CoachPanel.test.tsx src/hooks/useLlmRun.test.tsx
```

Expected: PASS。失败时先记录失败用例、错误摘要和涉及文件；只修复由本计划改动直接引入的断言、类型或渲染问题，不改无关文件。

- [ ] **Step 4: 最终检查 git diff**

Run:

```bash
git status --short
git diff --stat
```

Expected: 只剩用户已有未提交改动或本计划中尚未提交的改动；最终回复明确列出修改文件、文档文件和验证命令。
