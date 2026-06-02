# T6 RAG 教练知识库工程设计

## 1. 文档状态

本文是 T6/RAG 的工程设计草案，用于把 `docs/prd/rag-prd.md` 的产品口径拆成可实施的后端、数据、Agent、Trace 和 Eval 方案。

本文不直接修改业务代码。后续实现应再按实施计划逐步落地，并在每个阶段同步验证命令和文档影响。

## 2. 已参考上下文

- `docs/index.md`
- `docs/prd/prd.md`
- `docs/prd/rag-prd.md`
- `docs/prd/rag-materials.md`
- `docs/prd/ai-coach-workbench-prd.md`
- `docs/prd/ai-coach-user-profile-prd.md`
- `docs/architecture/foundation.md`
- `docs/project-todolist.md`
- `backend/app/agents/coach_graph.py`
- `backend/app/services/learning_flows/coach_turn.py`
- `backend/app/services/agent_trace_service.py`
- `backend/app/models/trace.py`

## 3. 设计目标

T6 第一阶段目标是把当前 `CoachGraph.retrieve_supporting_context=rag_deferred` 升级为真实、可过滤、可追踪、可评估的检索能力。

第一阶段只服务做题工作台 AI 教练：

- 用户卡在题意、题型方向、提示、代码 review、非 AC 反馈或 AC 复盘时，后端可召回 1 到 5 个教练知识片段。
- 检索结果必须遵守提示档位、`has_full_solution`、阶段、题型和质量过滤。
- 检索失败或无高质量命中时，系统回退到非 RAG 教练流程。
- Trace 和 Eval 能证明 RAG 没有绕过 `coach_guard` 或造成低档位泄题。

## 4. 非目标

第一阶段不做以下事情：

- 不做面向用户的资料搜索页。
- 不接入目标校准或学习计划生成主流程。
- 不自动抓取 LeetCode、付费课程或未授权材料。
- 不把完整历史聊天、完整用户代码或完整题解写入向量库。
- 不要求全自动高质量抽卡；允许先用人工整理的教练卡片验证产品效果。
- 不让 RAG 检索结果改变训练状态机的阶段迁移权限。

## 5. 总体架构

```text
本地材料 / 人工教练卡片
  -> source manifest
  -> ingest service
  -> knowledge_doc / knowledge_chunk
  -> embedding provider
  -> pgvector 检索
  -> RetrievalService
  -> CoachGraph.retrieve_supporting_context
  -> coach_turn prompt context
  -> coach_guard
  -> agent_trace / retrieval_trace / eval
```

关键边界：

- `backend.app.rag` 承载 manifest、导入、embedding、检索和过滤逻辑。
- `backend.app.agents.CoachGraph` 只消费检索服务输出，不直接解析材料或调用 embedding provider。
- `coach_turn` 只把经过过滤和摘要化的知识片段注入模型上下文。
- `coach_guard` 仍是最终泄题和阶段跳转守卫。
- `retrieval_trace` 记录检索过程；`agent_trace` 记录图节点摘要和最终注入状态。

## 6. 数据模型

### 6.1 `knowledge_doc`

用于记录一份本地材料或一组人工教练卡片的来源。

建议字段：

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `source_name` | 材料名称，例如 `代码随想录` |
| `source_type` | `book`、`tutorial`、`blog`、`course`、`problem_list`、`repository`、`manual_cards` |
| `source_url` | 来源 URL，可空 |
| `source_locator` | 章节、文件路径或题单位置 |
| `local_path` | 本地材料相对路径，只保存路径摘要，不保存用户目录敏感信息 |
| `language` | `zh`、`en` 或后续扩展 |
| `priority` | `P0`、`P1`、`P2` |
| `main_usage_json` | 主要用途，例如 `pattern_card`、`common_bug_card` |
| `license_note` | 授权或使用说明 |
| `content_hash` | 去重和重导入检测 |
| `metadata_json` | 额外来源信息 |
| `status` | `active`、`disabled`、`ingest_failed` |
| `created_at` / `updated_at` | 时间戳 |

### 6.2 `knowledge_chunk`

用于保存可检索的教练知识片段。第一阶段可以把人工教练卡片和材料切块统一存入该表，通过 `chunk_kind` 区分。

建议字段：

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `doc_id` | 外键，指向 `knowledge_doc` |
| `chunk_uid` | 稳定唯一标识，便于重导入幂等 |
| `chunk_kind` | `coach_card` 或 `source_chunk` |
| `knowledge_type` | `concept_card`、`pattern_card`、`invariant_card`、`common_bug_card`、`hint_card`、`problem_coach_card`、`interview_expression_card`、`plan_path_card` |
| `title` | 片段标题 |
| `summary_md` | 注入 prompt 的优先摘要 |
| `content_md` | 清洗后的正文或卡片内容 |
| `source_locator` | 原始章节、文件或题目位置 |
| `problem_slug` | 可空，单题卡片使用 |
| `problem_tags_json` | 题型标签 |
| `difficulty` | 可空，`easy`、`medium`、`hard` |
| `phases_json` | 可用阶段，例如 `understand_problem`、`review_code` |
| `stuck_points_json` | 适用卡点 |
| `hint_level_min` / `hint_level_max` | 可用提示档位，使用 0-3 映射 |
| `has_full_solution` | 是否包含完整解法风险 |
| `language` | 片段语言 |
| `quality_score` | 质量评分，第一阶段可使用 0-100 |
| `embedding` | pgvector 向量列 |
| `embedding_model` | 生成 embedding 的模型名 |
| `content_hash` | 去重检测 |
| `metadata_json` | 额外结构化信息 |
| `created_at` / `updated_at` | 时间戳 |

第一阶段建议引入 `pgvector` Python 包映射向量列；如果实现时不希望新增依赖，也可以在 migration 中使用原生 `vector(n)` 列并在检索 SQL 中显式处理。

### 6.3 复用 `retrieval_trace`

现有 migration 已创建 `retrieval_trace` 表，第一阶段优先复用，不急于扩表。

字段使用约定：

| 字段 | 第一阶段用途 |
| --- | --- |
| `session_id` | `practice_session.id` |
| `problem_slug` | 当前题目 slug |
| `query` | 脱敏 query 摘要，不保存完整用户输入 |
| `retrieved_doc_ids` | 初始候选 doc/chunk id |
| `selected_chunk_ids` | 最终注入片段 id |
| `current_hint_level` | 当前提示档位 0-3 |
| `retrieval_intent` | `pattern_direction`、`code_review` 等 |
| `filtered_out_chunk_ids` | 对象数组，包含 `chunk_id` 和 `reason` |
| `used_in_prompt` | 是否注入模型上下文 |

## 7. Source Manifest

第一阶段 manifest 推荐使用 JSON 文件，便于测试和跨平台运行。

示例：

```json
{
  "source_name": "manual-two-sum-cards",
  "source_type": "manual_cards",
  "language": "zh",
  "priority": "P0",
  "main_usage": ["pattern_card", "common_bug_card", "hint_card"],
  "local_path": "data/sources/rag/manual-two-sum-cards.jsonl",
  "license_note": "本地人工整理，用于产品验证",
  "notes": "Two Sum 和哈希表基础卡片"
}
```

实际第三方材料继续放在已忽略的 `data/sources/` 下。仓库可提交示例 manifest 和示例卡片，但不得提交受限原始材料或大段受版权保护内容。

## 8. 入库流程

第一阶段支持两条路径。

路径 A：人工教练卡片 JSONL

```text
manifest
  -> JSONL card loader
  -> metadata validation
  -> knowledge_doc / knowledge_chunk upsert
  -> embedding
```

路径 B：Markdown/txt 材料

```text
manifest
  -> raw text loader
  -> clean
  -> heading parser
  -> chunker
  -> metadata heuristics
  -> knowledge_doc / knowledge_chunk upsert
  -> embedding
```

第一阶段优先实现路径 A，再实现路径 B 的基础能力。自动抽取高质量教练卡片可以延后。

## 9. Embedding Provider

设计为可替换接口：

```text
EmbeddingProvider.embed(texts: list[str]) -> list[list[float]]
```

实现要求：

- 测试使用 deterministic fake provider，不访问网络。
- 真实 provider 可以复用 OpenAI-compatible 能力，但必须明确模型名和维度。
- 失败时记录 warning，不写入半成品 active chunk。
- 不把 API key、完整材料内容或完整用户输入写入日志。

第一阶段可以先使用固定 embedding 模型配置，例如 `text-embedding-3-small`。如果后续支持用户级 embedding 资产，需要再设计用户隔离和成本归属。

## 10. 检索服务

`RetrievalService.retrieve_for_coach()` 建议输入：

| 字段 | 说明 |
| --- | --- |
| `user_id` | 当前用户，用于日志和后续权限扩展 |
| `session_id` | 当前训练会话 |
| `problem_slug` | 当前题目 |
| `problem_tags` | 当前题型标签 |
| `phase` | 当前训练阶段 |
| `hint_level` | 当前提示档位 |
| `stuck_point` | 当前卡点 |
| `retrieval_intent` | 检索意图 |
| `query_summary` | 脱敏后的 query 摘要 |
| `top_k` | 候选数量 |

输出：

| 字段 | 说明 |
| --- | --- |
| `status` | `used`、`no_match`、`filtered_empty`、`error` |
| `selected_chunks` | 最终注入片段，最多 3-5 个 |
| `candidate_chunk_ids` | 初始候选 |
| `filtered_chunks` | 被过滤片段和原因 |
| `trace_id` | `retrieval_trace.id` |
| `prompt_context_md` | 给模型的摘要化上下文 |

过滤顺序建议：

1. 只查 `status=active` 且 `quality_score` 达标的片段。
2. 过滤 `hint_level_min <= current <= hint_level_max`。
3. 低提示档位过滤 `has_full_solution=true`。
4. 优先匹配当前 `problem_slug`，再匹配题型标签。
5. 优先匹配当前 `phase` 和 `stuck_point`。
6. 向量相似度排序，必要时叠加 metadata 加分。
7. 最终只返回摘要化内容，不返回大段原文。

## 11. CoachGraph 接入

当前 `retrieve_supporting_context` 返回：

```json
{
  "status": "rag_deferred",
  "chunks": [],
  "reason": "RAG/T6 延后，当前非 RAG 图节点不做检索。"
}
```

T6 后应返回：

```json
{
  "status": "used",
  "retrieval_intent": "code_review",
  "trace_id": 123,
  "chunks": [
    {
      "chunk_id": 10,
      "knowledge_type": "common_bug_card",
      "title": "哈希表查询和写入顺序",
      "summary_md": "Two Sum 中应先查询 complement，再写入当前元素，避免重复使用同一位置。",
      "source_name": "manual-two-sum-cards"
    }
  ],
  "filtered": [
    {"chunk_id": 9, "reason": "full_solution_blocked"}
  ]
}
```

接入原则：

- `CoachGraph` 只放检索摘要和 chunk id，不放完整材料原文。
- `coach_turn` prompt 中新增 RAG 上下文区块，但必须声明“这些知识只能作为教练提示依据，不能绕过当前提示档位”。
- `coach_guard` 继续检查 `should_reveal_solution` 和阶段迁移，不信任模型因为 RAG 命中而快进。
- 检索异常时，`retrieval_context.status=error`，教练仍继续非 RAG 流程。

## 12. Trace 与 Eval

Trace 写入：

- `retrieval_trace`：保存检索 query 摘要、候选、过滤、最终注入状态。
- `agent_trace`：在 `retrieve_supporting_context` 节点摘要中记录 `retrieval_status`、`selected_chunk_ids`、`filtered_reasons`。
- `agent_trace.retrieved_chunk_ids` 应写入最终注入 chunk id，便于 Trace 页展示。

Eval 更新：

- 取消当前固定 `rag_grounding_deferred`。
- 增加低档位命中完整解法但被过滤的样例。
- 增加 `common_bug_card` 能辅助 Two Sum 代码 review 的样例。
- 增加非 AC 反馈结合错误类型和题型卡片的样例。
- Eval 不调用真实 OpenAI，可以使用固定检索 fixture 和规则断言。

## 13. API 与 CLI

第一阶段不做用户可见搜索页，但需要开发入口：

- CLI：`uv run python -m backend.app.cli.rag_ingest --manifest <path>`，用于本地导入。
- Python service API：`RetrievalService.retrieve_for_coach()`，供 `CoachGraph` 调用。
- 可选调试 HTTP API：仅在后续需要 Trace 调试时增加，必须要求登录并避免返回大段原文。

如果新增 Makefile 目标，建议：

```text
make rag-ingest MANIFEST=...
make eval
```

## 14. 测试策略

后端测试优先：

- manifest schema 和 loader。
- 人工卡片 JSONL 入库幂等。
- Markdown/txt 基础切块。
- fake embedding provider。
- hint level / full solution / phase / tag 过滤。
- retrieval trace 写入和脱敏。
- `CoachGraph.retrieve_supporting_context` 从 `rag_deferred` 升级为真实检索。
- `coach_turn` prompt 只注入摘要化 RAG 上下文。
- eval runner 的 RAG Grounding 从 deferred 升级为 passed/failed。

前端测试只在 Trace 页展示字段变化时补充。

## 15. 风险与控制

| 风险 | 控制 |
| --- | --- |
| 低提示档位泄露完整解法 | `has_full_solution` 过滤 + `coach_guard` + eval |
| 材料版权或授权不清 | manifest 必填 `license_note`，实际材料放本地忽略目录 |
| 检索片段质量低导致教练跑偏 | `quality_score`、metadata 过滤、无命中回退 |
| 向量维度或模型切换导致旧数据不可用 | `embedding_model` 和维度写入 chunk，切换模型时重建 embedding |
| Trace 泄露用户代码或材料原文 | 只写摘要、id 和过滤原因，沿用 trace sanitizer |
| RAG 变成通用资料问答 | 第一阶段不做搜索页，只接工作台状态机 |

## 16. 文档影响

实现 T6 时需要同步检查：

- `docs/index.md`：如新增 `backend/app/rag/` 具体模块职责或 CLI，需要更新目录说明。
- `docs/architecture/foundation.md`：如新增 knowledge 表、RAG 服务和 CoachGraph 接入，需要更新架构边界。
- `docs/architecture/makefile.md`、`docs/dev-setup.md`：如新增 `make rag-ingest` 或环境变量，需要更新命令说明。
- `docs/project-todolist.md`：按任务完成情况更新 T6 状态和验证命令。
