# T6 RAG 教练知识库实施计划

> **For agentic workers:** Implement this plan task-by-task. Keep each task independently testable. Do not start by importing large third-party materials; use small local fixtures first.

**Goal:** 将当前 `CoachGraph.retrieve_supporting_context=rag_deferred` 升级为第一阶段 RAG 工作台闭环：本地教练卡片入库、pgvector 检索、提示档位过滤、`CoachGraph` 接入、Trace 记录和 RAG Grounding Eval。

**Architecture:** 以后端 `backend.app.rag` 为核心，新增 knowledge 数据模型、manifest loader、ingest service、embedding provider、retrieval service，并把检索摘要接入 `CoachGraph` 和 `coach_turn`。RAG 只作为教练知识增强，不能绕过 `coach_guard`。

**Tech Stack:** FastAPI、SQLAlchemy async、PostgreSQL + pgvector、Pydantic、LangGraph、OpenAI-compatible embedding provider、uv、pytest、mypy、ruff。前端只在 Trace 页需要展示新增字段时修改。

---

## 文件结构

- Create: `backend/app/models/rag.py`
- Create: `backend/app/rag/manifest.py`
- Create: `backend/app/rag/ingest.py`
- Create: `backend/app/rag/embedding.py`
- Create: `backend/app/rag/retrieval.py`
- Create: `backend/app/rag/tracing.py`
- Create: `backend/app/cli/rag_ingest.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/db/migrations/versions/20260531_0009_rag_knowledge.py`
- Modify: `backend/app/agents/coach_graph.py`
- Modify: `backend/app/services/learning_flows/coach_turn.py`
- Modify: `backend/app/services/agent_trace_service.py`
- Modify: `backend/app/evals/coach_eval_runner.py`
- Modify: `backend/tests/test_coach_eval_runner.py`
- Create: `backend/tests/test_rag_manifest.py`
- Create: `backend/tests/test_rag_ingest.py`
- Create: `backend/tests/test_rag_retrieval.py`
- Modify: `backend/tests/test_coach_graph.py`
- Modify: `backend/tests/test_learning_flows.py`
- Optional Modify: `frontend/src/pages/TracePage.tsx`
- Optional Modify: `frontend/src/pages/TracePage.test.tsx`
- Modify as needed: `Makefile`
- Modify as needed: `docs/index.md`
- Modify as needed: `docs/architecture/foundation.md`
- Modify as needed: `docs/architecture/makefile.md`
- Modify as needed: `docs/dev-setup.md`
- Modify: `docs/project-todolist.md`

## Task 1: knowledge 数据模型和 migration

**Files:**
- Create: `backend/app/models/rag.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/db/migrations/versions/20260531_0009_rag_knowledge.py`
- Test: `backend/tests/test_rag_models.py`

- [ ] **Step 1: Write failing model tests**

Test that `KnowledgeDoc` and `KnowledgeChunk` can be constructed with required metadata, `hint_level_min/max`, `has_full_solution`, `quality_score`, and stable `chunk_uid`.

- [ ] **Step 2: Run model test to verify it fails**

Run: `uv run pytest backend/tests/test_rag_models.py -q`

Expected: FAIL because models and migration do not exist.

- [ ] **Step 3: Implement models**

Create `KnowledgeDoc` and `KnowledgeChunk` using existing `Base` and `ID_TYPE`. Add indexes for `source_name`, `chunk_uid`, `knowledge_type`, `problem_slug`, `hint_level`, `quality_score`, and `has_full_solution`.

- [ ] **Step 4: Implement migration**

Create `knowledge_doc` and `knowledge_chunk`. Use pgvector for `embedding`. If using the Python `pgvector` SQLAlchemy type, add the dependency with `uv add pgvector`; otherwise use raw SQL for `vector(n)`.

- [ ] **Step 5: Run targeted tests**

Run: `uv run pytest backend/tests/test_rag_models.py -q`

Expected: PASS.

## Task 2: source manifest 和人工卡片 loader

**Files:**
- Create: `backend/app/rag/manifest.py`
- Create: `backend/app/rag/ingest.py`
- Create: `backend/tests/test_rag_manifest.py`
- Create: `backend/tests/test_rag_ingest.py`

- [ ] **Step 1: Write failing manifest tests**

Cover valid manifest, missing `license_note`, unsupported `source_type`, and ignored absolute path leakage.

- [ ] **Step 2: Run manifest tests**

Run: `uv run pytest backend/tests/test_rag_manifest.py -q`

Expected: FAIL because manifest parser does not exist.

- [ ] **Step 3: Implement manifest parser**

Use Pydantic models. Required fields: `source_name`, `source_type`, `language`, `priority`, `main_usage`, `local_path`, `license_note`.

- [ ] **Step 4: Write failing card ingest tests**

Use a tiny JSONL fixture with 2-3 cards: one safe `pattern_card`, one `common_bug_card`, and one `has_full_solution=true` card. Assert upsert idempotency and metadata preservation.

- [ ] **Step 5: Implement manual card loader**

Validate each card, compute `content_hash`, upsert `knowledge_doc`, upsert `knowledge_chunk`, and keep full material out of logs.

- [ ] **Step 6: Run targeted tests**

Run: `uv run pytest backend/tests/test_rag_manifest.py backend/tests/test_rag_ingest.py -q`

Expected: PASS.

## Task 3: Markdown/txt 基础导入和切块

**Files:**
- Modify: `backend/app/rag/ingest.py`
- Create or Modify: `backend/tests/test_rag_ingest.py`

- [ ] **Step 1: Write failing text ingest tests**

Use a short Markdown fixture with headings and code blocks. Assert heading locator, chunk count, sanitized content, and default metadata.

- [ ] **Step 2: Implement cleaner and heading parser**

Support Markdown headings and plain text fallback. Preserve source locator and strip excessive whitespace. Do not attempt full automatic card extraction in this task.

- [ ] **Step 3: Implement chunker**

Create bounded text chunks with stable `chunk_uid`. Keep chunk size conservative so prompt injection later uses summaries, not large original sections.

- [ ] **Step 4: Run targeted tests**

Run: `uv run pytest backend/tests/test_rag_ingest.py -q`

Expected: PASS.

## Task 4: embedding provider 和 pgvector 检索

**Files:**
- Create: `backend/app/rag/embedding.py`
- Create: `backend/app/rag/retrieval.py`
- Create: `backend/tests/test_rag_retrieval.py`

- [ ] **Step 1: Write failing fake embedding tests**

Assert deterministic fake embeddings return stable dimensions and can be used in retrieval tests without network.

- [ ] **Step 2: Implement embedding provider interface**

Create `EmbeddingProvider` protocol, fake provider for tests, and OpenAI-compatible provider skeleton. Do not log API keys or raw large text.

- [ ] **Step 3: Write failing retrieval filter tests**

Cases:

- Current hint level is `questioning`; `has_full_solution=true` chunk is filtered.
- `review_code` phase prefers `common_bug_card`.
- Current problem slug exact match outranks tag-only match.
- No high-quality match returns `no_match` or `filtered_empty`.

- [ ] **Step 4: Implement retrieval service**

Apply metadata filters before final selection. Use vector similarity where available, with a deterministic fallback path for SQLite/tests.

- [ ] **Step 5: Run targeted tests**

Run: `uv run pytest backend/tests/test_rag_retrieval.py -q`

Expected: PASS.

## Task 5: retrieval_trace 和 agent_trace 接入

**Files:**
- Create: `backend/app/rag/tracing.py`
- Modify: `backend/app/models/trace.py` if a mapped `RetrievalTrace` model is needed
- Modify: `backend/app/services/agent_trace_service.py`
- Create or Modify: `backend/tests/test_rag_retrieval.py`
- Modify: `backend/tests/test_agent_trace_service.py`

- [ ] **Step 1: Write failing trace tests**

Assert retrieval trace stores query summary, intent, hint level, selected ids, filtered reasons, and `used_in_prompt`, without storing full user input or full code.

- [ ] **Step 2: Implement retrieval trace writer**

Reuse existing `retrieval_trace` table. Store filtered reasons as structured JSON in `filtered_out_chunk_ids`.

- [ ] **Step 3: Extend agent trace helper**

Allow `append_agent_trace()` to accept final `retrieved_chunk_ids`. Keep sanitizer limits unchanged.

- [ ] **Step 4: Run targeted tests**

Run: `uv run pytest backend/tests/test_rag_retrieval.py backend/tests/test_agent_trace_service.py -q`

Expected: PASS.

## Task 6: CoachGraph 和 coach_turn 接入

**Files:**
- Modify: `backend/app/agents/coach_graph.py`
- Modify: `backend/app/services/learning_flows/coach_turn.py`
- Modify: `backend/tests/test_coach_graph.py`
- Modify: `backend/tests/test_learning_flows.py`

- [ ] **Step 1: Write failing CoachGraph tests**

Replace or extend the current `rag_deferred` test with a fixture-backed retrieval service. Assert `retrieve_supporting_context` returns `status=used`, selected chunks, filtered reasons, and trace id.

- [ ] **Step 2: Implement retrieval service injection**

Avoid hard-coding global service construction where tests need a fake. Keep default behavior safe: if retrieval service is unavailable or errors, return `status=error` and continue.

- [ ] **Step 3: Write failing coach prompt context tests**

Assert `coach_turn` prompt context includes only chunk summaries and ids, not full source material or filtered full-solution chunks.

- [ ] **Step 4: Implement prompt context injection**

Add a clear RAG context section to coach input: knowledge is guidance only, must obey current hint level and guard.

- [ ] **Step 5: Run targeted tests**

Run: `uv run pytest backend/tests/test_coach_graph.py backend/tests/test_learning_flows.py -q`

Expected: PASS.

## Task 7: RAG Eval 从 deferred 升级为真实检查

**Files:**
- Modify: `backend/app/evals/coach_eval_runner.py`
- Modify: `backend/tests/test_coach_eval_runner.py`

- [ ] **Step 1: Write failing eval tests**

Assert there is no `rag_grounding_deferred` case once RAG is enabled. Add cases for low-hint full-solution filtering, common bug grounding, and non-AC feedback grounding.

- [ ] **Step 2: Implement eval fixtures**

Use fixed local chunks and deterministic retrieval results. Do not call real LLM or network.

- [ ] **Step 3: Update eval runner output**

RAG cases should report `passed` or `failed`, not `deferred`, once retrieval implementation is active.

- [ ] **Step 4: Run eval tests and runner**

Run: `uv run pytest backend/tests/test_coach_eval_runner.py -q`

Run: `uv run python -m backend.app.evals.coach_eval_runner`

Expected: PASS, with no RAG deferred line.

## Task 8: CLI、Makefile 和文档回填

**Files:**
- Create: `backend/app/cli/rag_ingest.py`
- Modify as needed: `Makefile`
- Modify as needed: `docs/index.md`
- Modify as needed: `docs/architecture/foundation.md`
- Modify as needed: `docs/architecture/makefile.md`
- Modify as needed: `docs/dev-setup.md`
- Modify: `docs/project-todolist.md`

- [ ] **Step 1: Implement CLI**

Add `uv run python -m backend.app.cli.rag_ingest --manifest <path>`. CLI may print final summary, but ingest internals must use `logging`.

- [ ] **Step 2: Add Makefile target if useful**

Potential target:

```make
rag-ingest: ## Import local RAG materials from MANIFEST
	uv run python -m backend.app.cli.rag_ingest --manifest $(MANIFEST)
```

- [ ] **Step 3: Update docs**

Update docs only for contracts that changed: directory duties, architecture, commands, environment variables, and T6 completion status.

- [ ] **Step 4: Run final verification**

Run:

- `uv run ruff check .`
- `uv run mypy backend`
- `uv run pytest backend/tests/test_rag_manifest.py backend/tests/test_rag_ingest.py backend/tests/test_rag_retrieval.py backend/tests/test_coach_graph.py backend/tests/test_learning_flows.py backend/tests/test_coach_eval_runner.py -q`
- `uv run python -m backend.app.evals.coach_eval_runner`
- If frontend Trace changes: `cd frontend && corepack pnpm exec vitest run src/pages/TracePage.test.tsx`
- If frontend Trace changes: `cd frontend && corepack pnpm exec tsc -p tsconfig.app.json --noEmit --pretty false`

Expected: PASS.

## Rollout Order

1. Land model, manifest, manual card ingest and deterministic tests.
2. Land retrieval filtering and trace writing with fake embeddings.
3. Connect `CoachGraph` using fixtures and fallback behavior.
4. Upgrade eval from deferred to real RAG checks.
5. Add CLI and docs.
6. Only after the minimal loop passes, import a tiny local P0 material sample.

## Completion Criteria

- `CoachGraph.retrieve_supporting_context` no longer returns `rag_deferred` in normal configured runs.
- Low hint levels filter full-solution chunks.
- RAG context injected into `coach_turn` contains summaries and ids only.
- `retrieval_trace` and `agent_trace` show selected chunk ids and filter reasons.
- Eval runner has real RAG Grounding checks.
- `docs/project-todolist.md` marks T6 engineering implementation complete with verification commands.
