# 非 RAG Agent 教练工程化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前 Chat-first AI 教练基座升级为非 RAG 范围内“可恢复、可约束、可追踪、可评估”的 AI Agent 教练系统。

**Architecture:** 以后端结构化 schema、`coach_guard`、LangGraph `CoachGraph`、训练事实、复盘画像、trace 和 eval runner 作为主线。`retrieve_supporting_context` 只返回 `rag_deferred`，不创建 knowledge 表、不导入语料、不做 embedding 或向量检索。

**Tech Stack:** FastAPI、SQLAlchemy async、Pydantic、LangGraph、OpenAI Responses provider、React + TypeScript + Ant Design、TanStack Query、uv、Corepack pnpm。

---

## 文件结构

- Modify: `backend/app/schemas/practice.py`，补齐 `StuckPointDiagnosis`、`CoachAction`、`CodeReviewResult`、提交反馈历史、复盘和 trace schema。
- Modify: `backend/app/services/coach_guard.py`，强化低档位泄题、缺代码、缺提交反馈、缺 AC/终态复盘拒绝规则。
- Modify: `backend/app/services/learning_flows/coach_turn.py`，先接结构化 schema 和 guard，随后切换到 `CoachGraph` 入口。
- Create: `backend/app/agents/coach_graph.py`，实现图状态、节点、checkpoint key 和 `rag_deferred` no-op 检索节点。
- Create: `backend/app/services/agent_trace_service.py`，封装 `agent_trace` 写入和输入输出摘要截断。
- Modify: `backend/app/services/practice_session_service.py`，返回非 AC 提交反馈历史、备注和复盘状态。
- Modify: `backend/app/services/profile_service.py`、`backend/app/services/learning_flows/coach_summary.py`，增强复盘、画像增量和下一题推荐事实。
- Create: `backend/app/services/recommendation_service.py`，实现规则化下一题推荐。
- Create or Modify: `backend/app/api/review.py`、`backend/app/api/trace.py`，提供真实复盘页和 trace 页 API。
- Create: `backend/app/evals/coach_eval_runner.py` 和 `backend/tests/test_coach_eval_runner.py`，实现 Hint Leakage、Diagnosis、Code Review 固定样例规则断言；RAG Grounding 标记 deferred。
- Modify: `frontend/src/api/practice.ts`、`frontend/src/api/review.ts`、`frontend/src/api/trace.ts`，补齐 API 类型。
- Modify: `frontend/src/pages/workspace/CoachPanel.tsx`、`frontend/src/pages/workspace/SubmissionFeedbackModal.tsx`，接入 WA/TLE/RE/MLE/CE/UNKNOWN 反馈入口和历史展示。
- Modify: `frontend/src/pages/ReviewPage.tsx`、`frontend/src/pages/TracePage.tsx`，展示真实复盘和 trace 数据。
- Modify: `Makefile`、`docs/architecture/makefile.md`、`docs/dev-setup.md`，增加 eval 命令和验证说明。
- Modify: `docs/project-todolist.md`、`docs/architecture/foundation.md`、`docs/prd/prd.md`、`docs/prd/ai-coach-workbench-prd.md`、`docs/prd/ai-coach-user-profile-prd.md`，按已落地的非 RAG 范围更新状态和边界。

## Task 1: 结构化教练 schema 和 guard 基线

**Files:**
- Modify: `backend/app/schemas/practice.py`
- Modify: `backend/app/services/coach_guard.py`
- Test: `backend/tests/test_practice_schema.py`
- Test: `backend/tests/test_coach_guard.py`

- [x] **Step 1: Write failing schema tests**

```python
def test_coach_action_requires_stable_non_empty_fields() -> None:
    action = CoachAction(
        phase_after="analyze_feedback",
        diagnosed_stuck_point=StuckPointDiagnosis(
            category="edge_case_missing",
            evidence=["WA 失败用例涉及重复元素"],
            confidence="medium",
        ),
        next_action="analyze_submission_feedback",
        reply_md="先根据失败用例缩小问题区域。",
        should_reveal_solution=False,
    )

    assert action.diagnosed_stuck_point.category == "edge_case_missing"
    assert action.next_action == "analyze_submission_feedback"
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/test_practice_schema.py::test_coach_action_requires_stable_non_empty_fields -q`

Expected: FAIL because `CoachAction` or nested schema is not defined.

- [x] **Step 3: Implement schema**

Add Pydantic models for `StuckPointDiagnosis`, `CodeReviewResult`, and `CoachAction`. Keep field limits explicit and do not store full code or full solution in these schema objects.

- [x] **Step 4: Write failing guard tests**

```python
def test_guard_rejects_summary_without_ac_or_terminal_feedback() -> None:
    decision = guard_transition(
        phase_before="analyze_feedback",
        proposed_phase_after="summarize",
        has_code=True,
        has_submission_feedback=True,
        has_terminal_result=False,
        hint_level="reflection",
        should_reveal_solution=False,
    )

    assert not decision.accepted
    assert decision.reason == "terminal_result_required_for_summary"
```

- [x] **Step 5: Run guard test to verify it fails**

Run: `uv run pytest backend/tests/test_coach_guard.py::test_guard_rejects_summary_without_ac_or_terminal_feedback -q`

Expected: FAIL because `has_terminal_result` is not accepted or the guard allows the transition.

- [x] **Step 6: Implement guard hardening**

Add `has_terminal_result` to `guard_transition()`, require code for `review_code`, feedback for `analyze_feedback`, terminal AC/equivalent result for formal `summarize`, and low-level solution leak rejection for `questioning` and `direction`.

- [x] **Step 7: Run targeted tests**

Run: `uv run pytest backend/tests/test_practice_schema.py backend/tests/test_coach_guard.py -q`

Expected: PASS.

## Task 2: 非 AC 提交反馈入口、历史和错因归因

**Files:**
- Modify: `backend/app/schemas/practice.py`
- Modify: `backend/app/services/practice_session_service.py`
- Modify: `backend/app/services/learning_flows/coach_turn.py`
- Modify: `frontend/src/api/practice.ts`
- Modify: `frontend/src/pages/workspace/CoachPanel.tsx`
- Modify: `frontend/src/pages/workspace/SubmissionFeedbackModal.tsx`
- Test: `backend/tests/test_practice_session_service.py`
- Test: `backend/tests/test_learning_flows.py`
- Test: `frontend/src/pages/workspace/CoachPanel.test.tsx`

- [x] **Step 1: Write failing backend feedback-history test**

```python
async def test_session_payload_includes_non_ac_feedback_history(db_session, user, practice_session, code_snapshot):
    await record_submission_feedback(
        db_session,
        user,
        practice_session.id,
        SubmissionFeedbackCreate(
            code_snapshot_id=code_snapshot.id,
            result="wa",
            failed_case_text="[3,3], target=6",
            error_message="expected [0,1]",
            note_md="我怀疑是哈希表更新顺序。",
        ),
    )

    payload = await get_session_payload(db_session, user, practice_session.id)

    assert payload.submission_feedbacks[0].result == "wa"
    assert payload.submission_feedbacks[0].note_md == "我怀疑是哈希表更新顺序。"
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/test_practice_session_service.py::test_session_payload_includes_non_ac_feedback_history -q`

Expected: FAIL because payload does not expose `submission_feedbacks` and `note_md`.

- [x] **Step 3: Implement backend feedback history**

Use `SubmissionFeedback.raw_feedback_json["note_md"]` for remarks to avoid a migration unless a dedicated column becomes necessary. Return a sanitized `SubmissionFeedbackHistoryResponse` list in `PracticeSessionResponse`.

- [x] **Step 4: Write failing coach attribution test**

```python
async def test_non_ac_feedback_drives_analyze_feedback_context(session, fake_provider, coach_run_with_wa_feedback):
    result = await run_coach_turn(...)

    assert result["phase_after"] == "analyze_feedback"
    assert result["guard"]["accepted"] is True
```

- [x] **Step 5: Run attribution test to verify it fails**

Run: `uv run pytest backend/tests/test_learning_flows.py::test_non_ac_feedback_drives_analyze_feedback_context -q`

Expected: FAIL until latest feedback is included in the coach context and terminal summary rules distinguish non-AC from AC.

- [x] **Step 6: Implement attribution context**

Load latest submission feedback summary into `_coach_input_context()` without full code duplication. Let non-AC feedback keep the phase in `analyze_feedback` and produce `next_action` values such as `ask_counterexample_trace`, `suggest_targeted_fix`, or `request_resubmit`.

- [x] **Step 7: Write failing frontend test**

```tsx
it('opens non-AC feedback modal and renders feedback history', async () => {
  render(<CoachPanel session={sessionWithWaFeedback} onSessionRefresh={vi.fn()} />)

  await user.click(screen.getByRole('button', { name: '回填未通过结果' }))

  expect(screen.getByLabelText('LeetCode 结果')).toBeInTheDocument()
  expect(screen.getByText('WA')).toBeInTheDocument()
  expect(screen.getByText('[3,3], target=6')).toBeInTheDocument()
})
```

- [x] **Step 8: Implement frontend modal and history**

Add a secondary “回填未通过结果” button, restrict default modal choices to WA/TLE/RE/MLE/CE/UNKNOWN, add `note_md`, and render recent feedback history below the chat controls.

- [x] **Step 9: Run targeted tests**

Run: `uv run pytest backend/tests/test_practice_session_service.py backend/tests/test_learning_flows.py -q`

Run: `cd frontend && corepack pnpm exec vitest run src/pages/workspace/CoachPanel.test.tsx`

Expected: PASS.

## Task 3: LangGraph CoachGraph 和可恢复状态

**Files:**
- Create: `backend/app/agents/coach_graph.py`
- Modify: `backend/app/services/learning_flows/coach_turn.py`
- Modify: `backend/app/services/practice_session_service.py`
- Test: `backend/tests/test_coach_graph.py`
- Test: `backend/tests/test_learning_flows.py`

- [x] **Step 1: Write failing graph state/node tests**

```python
async def test_retrieve_supporting_context_is_rag_deferred(coach_graph_state):
    graph = CoachGraph()
    next_state = await graph.retrieve_supporting_context(coach_graph_state)

    assert next_state["retrieval_context"]["status"] == "rag_deferred"
    assert next_state["retrieval_context"]["chunks"] == []
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/test_coach_graph.py::test_retrieve_supporting_context_is_rag_deferred -q`

Expected: FAIL because `CoachGraph` does not exist.

- [x] **Step 3: Implement graph state and nodes**

Implement `CoachGraphState` as `TypedDict`, include user/session/plan/item/problem ids, `thread_id`, phase, hint level, profile summary, recent events, latest code attempt, latest submission feedback, run/trace/error summary, and `retrieval_context`.

- [x] **Step 4: Write failing flow-entry test**

```python
async def test_coach_turn_uses_graph_thread_id(session, run, fake_provider):
    result = await run_coach_turn(...)

    assert result["graph"]["thread_id"].startswith("practice-session-")
    assert result["graph"]["retrieval_context"]["status"] == "rag_deferred"
```

- [x] **Step 5: Implement graph entry**

Move the current turn steps behind `CoachGraph.run_turn()`: `load_training_context`, `classify_user_input`, `diagnose_stuck_point`, `retrieve_supporting_context`, `decide_next_action`, `guard_transition`, `generate_coach_reply`, `persist_turn`, `maybe_generate_summary`. Keep SSE progress event names stable.

- [x] **Step 6: Run targeted graph tests**

Run: `uv run pytest backend/tests/test_coach_graph.py backend/tests/test_learning_flows.py -q`

Expected: PASS.

## Task 4: 复盘、画像、下一题推荐和最小仪表盘

**Files:**
- Modify: `backend/app/services/profile_service.py`
- Modify: `backend/app/services/learning_flows/coach_summary.py`
- Create: `backend/app/services/recommendation_service.py`
- Create or Modify: `backend/app/api/review.py`
- Modify: `frontend/src/pages/ReviewPage.tsx`
- Create: `frontend/src/api/review.ts`
- Test: `backend/tests/test_practice_session_service.py`
- Test: `backend/tests/test_recommendation_service.py`
- Test: `frontend/src/pages/ReviewPage.test.tsx`

- [x] **Step 1: Write failing summary detail test**

```python
async def test_summary_contains_required_training_facts(db_session, user, completed_session):
    result = await persist_session_summary_profile_update(db_session, user_id=user.id, session_id=completed_session.id)
    summary = await db_session.get(SessionSummary, result.summary_id)

    assert summary.final_submission_result == "ac"
    assert summary.next_recommendation_json["reason"]
    assert summary.profile_signals_json["evidence"]
```

- [x] **Step 2: Implement richer deterministic summary**

Populate final result, phase track, main stuck points, highest hint level, code/submission error types, complexity placeholders based on user facts, profile signals, and recommendation reason. Never copy full user input, full code, full solution, API keys, or tokens into profile fields.

- [x] **Step 3: Write failing recommendation test**

```python
def test_recommendation_prefers_same_weak_tag_next_pending_item(plan_payload, summary):
    recommendation = recommend_next_plan_item(plan_payload, summary)

    assert recommendation["item_id"] == 12
    assert "边界" in recommendation["reason"]
```

- [x] **Step 4: Implement rules recommendation service**

Pick next pending/in_progress plan item by weak tag overlap, current stage order, difficulty step-up, and recent stuck point. Return item id, problem slug/title, reason, first-question hint, and review focus.

- [x] **Step 5: Implement review API/page**

Expose session summary and recommendation through `/api/practice-sessions/{session_id}/review` or a dedicated review router. Update `ReviewPage` to read a `sessionId` query param and render real fields.

- [x] **Step 6: Run targeted tests**

Run: `uv run pytest backend/tests/test_practice_session_service.py backend/tests/test_recommendation_service.py -q`

Run: `cd frontend && corepack pnpm exec vitest run src/pages/ReviewPage.test.tsx`

Expected: PASS.

## Task 5: Trace 写入、Trace 页和 Eval runner

**Files:**
- Create: `backend/app/models/trace.py` if model mapping is absent.
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/services/agent_trace_service.py`
- Create: `backend/app/api/trace.py`
- Modify: `backend/app/main.py`
- Modify: `frontend/src/pages/TracePage.tsx`
- Create: `frontend/src/api/trace.ts`
- Create: `backend/app/evals/coach_eval_runner.py`
- Create: `backend/tests/test_agent_trace_service.py`
- Create: `backend/tests/test_coach_eval_runner.py`
- Modify: `Makefile`

- [x] **Step 1: Write failing trace service test**

```python
async def test_trace_service_writes_node_summary_without_full_user_input(db_session):
    trace = await append_agent_trace(db_session, session_id="1", thread_id="practice-session-1", node_name="guard_transition", input_summary={"content_md": "x" * 2000}, output_summary={"reason": "accepted"})

    assert trace.node_name == "guard_transition"
    assert "x" * 1000 not in trace.tool_calls["input_summary"]
```

- [x] **Step 2: Implement trace model/service/API**

Map existing `agent_trace`, write node lifecycle summaries, guard reasons, final reply summary, phase transitions and error summaries. Keep RAG trace deferred and do not write retrieval chunks.

- [x] **Step 3: Write failing frontend trace test**

```tsx
it('renders trace rows from API', async () => {
  render(<TracePage />)

  expect(await screen.findByText('guard_transition')).toBeInTheDocument()
  expect(screen.getByText('accepted')).toBeInTheDocument()
})
```

- [x] **Step 4: Implement Trace page**

Fetch `/api/traces`, show node, phase, hint level, guard status/reason, model, latency and created time. Add filters only if the data contract stays small.

- [x] **Step 5: Write failing eval tests**

```python
def test_hint_leakage_eval_fails_low_level_solution_reveal():
    result = run_eval_suite(["hint_leakage"])

    assert result.failed == 0
    assert result.cases[0].name == "low_hint_blocks_full_solution"
```

- [x] **Step 6: Implement eval runner and Makefile target**

Add fixed rule-based cases for Hint Leakage, Diagnosis and Code Review. Return non-zero on failures. RAG Grounding case must be reported as `deferred` because T6/RAG is explicitly out of scope.

- [x] **Step 7: Run targeted tests and eval**

Run: `uv run pytest backend/tests/test_agent_trace_service.py backend/tests/test_coach_eval_runner.py -q`

Run: `uv run python -m backend.app.evals.coach_eval_runner`

Expected: PASS and eval summary lists RAG Grounding as deferred.

## Task 6: 文档、端到端路径和最终验证

**Files:**
- Modify: `docs/project-todolist.md`
- Modify: `docs/architecture/foundation.md`
- Modify: `docs/architecture/makefile.md`
- Modify: `docs/dev-setup.md`
- Modify: `docs/prd/prd.md`
- Modify: `docs/prd/ai-coach-workbench-prd.md`
- Modify: `docs/prd/ai-coach-user-profile-prd.md`

- [x] **Step 1: Update docs against implementation**

Document the non-RAG Agent path, Graph node list, `rag_deferred`, non-AC feedback flow, review/profile/recommendation flow, trace API, eval runner and `make eval`.

- [x] **Step 2: Update todolist statuses**

Mark completed subitems for T3, T5, T4, T7, T9 and T10 based on actual tests and files. Keep T6/RAG as deferred, not completed.

- [x] **Step 3: Run final verification**

Run:

```bash
uv run pytest backend/tests/test_practice_schema.py backend/tests/test_coach_guard.py backend/tests/test_practice_session_service.py backend/tests/test_learning_flows.py backend/tests/test_coach_graph.py backend/tests/test_agent_trace_service.py backend/tests/test_coach_eval_runner.py -q
```

Run:

```bash
cd frontend && corepack pnpm exec vitest run src/pages/workspace/CoachPanel.test.tsx src/pages/ReviewPage.test.tsx src/pages/TracePage.test.tsx
```

Run:

```bash
cd frontend && corepack pnpm exec tsc -p tsconfig.app.json --noEmit --pretty false
```

Run:

```bash
uv run python -m backend.app.evals.coach_eval_runner
```

Expected: all tests pass, eval exits zero, RAG Grounding is reported as deferred.

Actual 2026-05-26:

- `uv run ruff check .`：通过。
- `uv run mypy backend`：通过。
- `uv run pytest backend/tests/test_practice_schema.py backend/tests/test_coach_guard.py backend/tests/test_practice_session_service.py backend/tests/test_learning_flows.py backend/tests/test_coach_graph.py backend/tests/test_agent_trace_service.py backend/tests/test_coach_eval_runner.py backend/tests/test_recommendation_service.py -q`：85 passed。
- `cd frontend && corepack pnpm exec vitest run src/pages/workspace/CoachPanel.test.tsx src/pages/workspace/CodeAttemptDrawer.test.tsx src/pages/ReviewPage.test.tsx src/pages/TracePage.test.tsx src/pages/DashboardPage.test.tsx`：5 files / 22 tests passed。
- `cd frontend && corepack pnpm exec tsc -p tsconfig.app.json --noEmit --pretty false`：通过。
- `uv run python -m backend.app.evals.coach_eval_runner`：passed=3 failed=0 deferred=1，RAG Grounding deferred。
- `make eval`：passed=3 failed=0 deferred=1，RAG Grounding deferred。

## Self-Review Notes

- This plan intentionally excludes `knowledge_doc`, `knowledge_chunk`, corpus import, embedding, vector retrieval, retrieval API and RAG Grounding implementation.
- `retrieve_supporting_context` must keep a no-op `rag_deferred` output so graph state and trace are future-compatible without violating the non-RAG scope.
- Existing modified files in the worktree must be preserved; tasks should adapt to current code rather than reverting unrelated changes.
