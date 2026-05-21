# LLM 流式输出体验设计

## 目标

当前目标校准、学习计划生成和计划调整等大模型调用会让用户长时间只看到加载态，无法判断系统是否还在工作、卡在哪个阶段，也看不到模型正在输出。后续做题工作台 AI 教练、代码 review、复盘总结也会遇到同样问题。

本设计的目标是新增一套统一的 LLM Run 流式体验层，让用户获得接近 ChatGPT 的实时输出体验，同时保留当前产品的核心约束：前端不直接调用大模型、不接触 API key；正式学习计划必须经过后端题库校验和 repair 后才能展示为可确认结果。

## 已参考上下文

- `docs/index.md`：确认代码变更后的文档维护映射，以及后端、前端、服务层和文档目录职责。
- `docs/architecture/foundation.md`：确认前端只通过 HTTP API 与后端交互，用户级 OpenAI API 资产由后端加密存储并统一选择。
- `docs/prd/prd.md`：确认 AI Coach、首包时间、可恢复性、SSE / WebSocket 流式输出、trace 和 hint level 安全要求。
- `docs/project-todolist.md`：确认当前项目还在 T2 / T3 前后，AI 教练闭环尚未完成，适合把流式能力设计为后续公共底座。
- `backend/app/services/learning_plan_llm.py`、`backend/app/services/study_plan_service.py`、`backend/app/api/learning.py`：确认现有 LLM 调用集中在学习计划相关流程，当前是同步请求返回最终结果。
- `frontend/src/pages/GoalCalibrationPage.tsx`、`frontend/src/pages/StudyPlanPage.tsx`、`frontend/src/pages/WorkspacePage.tsx`：确认当前前端主要使用按钮 loading 和一次性响应，工作台教练区还未接入。

## 已确认决策

- 采用统一 LLM Run 流式体验层，而不是只给单个页面做局部补丁。
- 用户需要同时看到可展示的流式正文和后台阶段进度。
- 计划生成采用混合展示：生成过程中可以流式展示计划思路、阶段说明和过程摘要；正式题单必须等 validator / repair 完成后才能作为结果展示。
- 支持用户停止生成；取消后的 run 不能确认半截结果，用户可以重新生成。
- 页面刷新后恢复 run 状态和最终结果，不要求回放完整 token。
- 项目仍处早期，采用流式优先的重写方案，不让旧同步 LLM service 阻碍长期架构。
- 第一版使用 SSE 承载服务端到前端的事件流；后续如 LangGraph 或工具调用需要双向实时控制，再评估 WebSocket。

## 非目标

- 第一版不保存每个 token 的完整事件日志。
- 第一版不保证浏览器断线后继续回放完整流式文本。
- 第一版不让前端直接连接 OpenAI 或任何 OpenAI-compatible endpoint。
- 第一版不把 LLM 原始题单作为正式计划展示或确认。
- 第一版不实现跨进程任务队列；如果后续 Docker 多 worker 部署需要更强恢复能力，再引入 Redis、任务队列或持久事件表。

## 总体架构

新增 LLM Run 作为所有大模型调用的主入口。前端先创建 run，再订阅该 run 的 SSE 事件流。后端在 run 内完成用户鉴权、模型资产选择、Provider 调用、业务流程编排、确定性校验、取消检查和最终结果持久化。

```text
React 页面
  -> POST /api/llm-runs
  -> GET /api/llm-runs/{run_id}/stream
  -> POST /api/llm-runs/{run_id}/cancel
  -> GET /api/llm-runs/{run_id}

FastAPI LLM Run API
  -> LLM Run Service
  -> LLM Orchestrator
  -> Domain Flow
  -> LLM Provider Client
  -> Deterministic Validator / Repair
  -> PostgreSQL
```

建议新增模块：

| 模块 | 职责 |
| --- | --- |
| `backend/app/api/llm_runs.py` | 创建 run、订阅 SSE、取消 run、查询 run 状态。 |
| `backend/app/models/llm_run.py` | 保存 run 生命周期、场景、阶段、最终结果、错误摘要和取消请求。 |
| `backend/app/schemas/llm_run.py` | 定义 run 创建、状态查询、事件 payload 和错误响应 schema。 |
| `backend/app/services/llm_run_service.py` | 负责 run 权限、状态迁移、数据库读写和取消语义。 |
| `backend/app/services/llm_orchestrator.py` | 根据 `kind` 分发到具体业务 flow，并统一发出事件。 |
| `backend/app/services/llm_providers/openai_responses.py` | 封装 OpenAI Responses API 的流式和结构化输出调用。 |
| `backend/app/services/learning_flows/` | 承载目标校准追问、计划生成、计划调整等业务流程。 |
| `frontend/src/api/llmRuns.ts` | 封装 create、stream、cancel、status API。 |
| `frontend/src/hooks/useLlmRun.ts` | 管理 run 创建、SSE 连接、事件归并、取消和恢复。 |
| `frontend/src/components/LlmStreamingPanel.tsx` | 展示阶段进度、流式文本、停止按钮、错误和完成态。 |

现有 `learning_plan_validator.py` 的确定性校验继续保留。现有 `learning_plan_llm.py` 不再作为长期基础，可以迁移其中 prompt、schema 和 repair 策略到新的 flow / provider 层后删除或收缩为兼容壳。

## Run 类型

第一版支持：

| `kind` | 用途 | 结果写入 |
| --- | --- | --- |
| `goal_followup` | 根据目标校准输入或已有 draft 的追问回答生成最多一个追问，或判断信息足够。 | 首次提交时创建 `goal_calibration_draft`；后续回答时更新 `followup_messages_json` 和状态。 |
| `goal_plan_generate` | 根据目标校准草稿生成学习计划草稿。 | 更新 `goal_calibration_draft.draft_plan_json`、`validation_report_json`、`repair_log_json` 和状态。 |
| `study_plan_adjustment` | 根据用户调整原因生成新版本草稿。 | 创建或更新 draft 版本，并写入 change log。 |

后续复用：

| `kind` | 用途 |
| --- | --- |
| `coach_message` | 做题工作台 AI 教练对话。 |
| `code_review` | 用户代码 review。 |
| `reflection` | 单题复盘总结和画像更新。 |

## API 设计

### 创建 Run

`POST /api/llm-runs`

请求：

```json
{
  "kind": "goal_plan_generate",
  "payload": {
    "draft_id": 123
  }
}
```

响应：

```json
{
  "run_id": 456,
  "kind": "goal_plan_generate",
  "status": "pending",
  "stage": "queued",
  "stream_url": "/api/llm-runs/456/stream"
}
```

创建时只接受当前登录用户有权访问的业务对象。比如 `draft_id` 必须属于当前用户，否则返回 404 或 403，避免暴露其他用户资源是否存在。

### 订阅 Run

`GET /api/llm-runs/{run_id}/stream`

返回 `text/event-stream`。事件名使用统一集合：

| 事件 | 用途 |
| --- | --- |
| `started` | run 进入执行，返回 `run_id`、`kind`、脱敏模型信息和初始阶段。 |
| `progress` | 后台阶段变化，如选择模型资产、请求模型、解析输出、校验题库、repair、写入草稿。 |
| `delta` | 可展示给用户的流式文本片段。 |
| `result` | 最终结构化结果。 |
| `error` | 失败，返回稳定错误码和用户可读提示。 |
| `canceled` | 用户停止生成。 |
| `done` | 事件流结束。 |

示例：

```text
event: progress
data: {"run_id":456,"stage":"validating_problem_library","message":"正在校验题库和过滤不可用题目"}

event: delta
data: {"run_id":456,"text":"我会先把训练拆成题型识别、Medium 稳定性和面试表达三个阶段。"}

event: result
data: {"run_id":456,"status":"succeeded","result":{"draft_id":123,"stage_count":3,"item_count":18}}
```

### 取消 Run

`POST /api/llm-runs/{run_id}/cancel`

行为：

- 当前用户只能取消自己的 run。
- 后端设置 `cancel_requested = true`。
- flow 在模型调用前后、validator 前后、repair 前后和 DB 写入前检查取消状态。
- 如果底层 provider 请求无法立即终止，也必须尽快关闭前端事件流，并把 run 标记为 `canceled`。
- canceled run 不允许确认计划或写入正式计划版本。

### 查询 Run

`GET /api/llm-runs/{run_id}`

用于刷新页面后的恢复。返回：

```json
{
  "run_id": 456,
  "kind": "goal_plan_generate",
  "status": "succeeded",
  "stage": "completed",
  "display_text_md": "本次计划按三个阶段组织...",
  "result": {
    "draft_id": 123
  },
  "error_code": null,
  "error_message": null,
  "can_retry": false,
  "created_at": "2026-05-21T10:00:00Z",
  "finished_at": "2026-05-21T10:00:20Z"
}
```

## 数据模型

新增 `llm_run` 表：

```text
llm_run
- id
- user_id
- kind
- status                  # pending / running / succeeded / failed / canceled
- stage                   # queued / selecting_credential / streaming_model / validating / repairing / completed 等
- display_text_md          # 可恢复展示的过程摘要，不保存完整 token 日志
- result_json              # 最终结构化结果
- error_code
- error_message            # 脱敏后的用户可读错误摘要
- cancel_requested
- llm_credential_id
- model_name
- related_type             # goal_calibration_draft / study_plan / study_plan_version / practice_session 等
- related_id
- created_at
- started_at
- finished_at
- updated_at
```

索引：

- `(user_id, created_at)`
- `(user_id, kind, status)`
- `(related_type, related_id)`
- `(llm_credential_id)`

状态迁移：

```text
pending -> running -> succeeded
pending -> running -> failed
pending -> running -> canceled
pending -> canceled
```

任何终态 run 不允许再次进入 running。重试应创建新的 run，并通过 `related_type` / `related_id` 关联同一个业务对象。

## 后端 Flow 设计

### `goal_followup`

流程：

1. 如果 payload 是首次目标校准输入，先创建 `goal_calibration_draft`，保存结构化输入并绑定当前用户。
2. 如果 payload 是追问回答，校验 draft 属于当前用户且状态允许继续追问。
3. 选择用户当前可用 LLM 资产。
4. 发出 `started` 和 `progress: selecting_credential`。
5. 调用 provider 流式生成追问或 `null` 判断。
6. 只将可展示的追问生成过程作为 `delta` 输出。
7. 解析最终输出。
8. 更新 draft 的追问历史和状态。
9. 发出 `result`，结果包含 `draft_id`、正式追问、剩余追问次数或“信息足够”的状态。

### `goal_plan_generate`

流程：

1. 校验 draft 属于当前用户，且状态允许生成计划。
2. 选择用户当前可用 LLM 资产。
3. 发出 `progress: generating_plan_outline`，流式展示计划思路和阶段摘要。
4. 获取结构化草稿 JSON。
5. 发出 `progress: validating_problem_library`。
6. 调用 `learning_plan_validator` 做本地题库校验、paid only 过滤、重复题处理和确定性 repair。
7. 如果仍不合法，发出 `progress: repairing_plan_draft`，把校验报告交给模型生成修复草稿。
8. 每轮 repair 后重新校验。
9. 最终合法时写入 `goal_calibration_draft.draft_plan_json`、`validation_report_json`、`repair_log_json`。
10. 发出 `result`，前端此时才渲染正式题单和“确认创建计划”按钮。

### `study_plan_adjustment`

流程：

1. 校验 plan 属于当前用户。
2. 读取 active version 和已有进度题目。
3. 发出 `progress: preserving_existing_progress`。
4. 调用模型生成调整草稿。
5. 用 validator 修复题目合法性。
6. 合并 locked / in_progress / completed / skipped 题目，避免用户已投入训练被静默丢弃。
7. 写入 draft version 和 change log。
8. 发出 `result`。

## Provider 设计

第一版 provider 只实现 OpenAI Responses API，并保持 OpenAI-compatible base URL 能力。

Provider 层职责：

- 从 `llm_credential` 获取 `model_name`、`base_url` 和解密后的 API key。
- 发起流式请求。
- 将 provider 原始事件转换为内部 `delta`。
- 提供结构化输出解析。
- 捕获 provider 错误并返回统一错误码。

Provider 层不处理业务对象、不写学习计划、不做题库校验。

为了避免把未校验题单暴露给用户，计划生成应区分两类输出：

- 面向用户的 `delta`：计划思路、阶段摘要、生成说明。
- 面向后端的 structured payload：题目 slug、阶段、推荐理由等，必须经过 validator 后才进入 `result`。

## 前端体验

### 通用组件

`LlmStreamingPanel` 展示：

- 标题和当前状态。
- 当前阶段 `stage` 和用户可读说明。
- 流式正文区域。
- 停止生成按钮。
- 错误提示和重试入口。
- 完成后根据 `result` 渲染业务结果。

`useLlmRun` 负责：

- 创建 run。
- 建立 SSE 连接。
- 归并 `delta` 到显示文本。
- 维护 `stage`、`status`、`result`、`error`。
- 调用 cancel。
- 页面恢复时查询 run 状态。

### 目标校准页

用户提交目标校准表单后：

- 页面进入“教练正在校准目标”状态。
- 显示分析目标、判断追问必要性等阶段。
- 完成后展示正式追问，或展示“信息足够，可以生成计划”。

### 计划生成页

用户点击生成计划后：

- 页面显示阶段进度：生成计划思路、生成结构化草稿、校验题库、修复草稿、完成。
- 流式正文只展示过程摘要和计划思路。
- 正式题单只在 `result` 到达后展示。
- canceled / failed 状态不展示确认按钮。

### 学习计划调整

用户提交调整原因后：

- 页面显示保留已有进度、生成调整草稿、校验题库、合并锁定题目、写入草稿等阶段。
- 完成后展示新版本草稿和激活入口。

### 后续工作台 AI 教练

工作台右侧教练区直接复用 `delta` 做 ChatGPT 式逐段输出。`progress` 可用于展示诊断卡点、选择提示档位、生成回复、记录 trace 等内部阶段。教练对话的泄题检查和 hint level 控制仍应在后端 flow 内完成。

## 错误处理

统一错误码：

| 错误码 | 含义 |
| --- | --- |
| `llm_credential_unavailable` | 当前用户没有可用模型资产。 |
| `llm_provider_error` | Provider 请求失败或返回错误。 |
| `llm_output_parse_failed` | 模型输出无法解析为后端需要的结构。 |
| `plan_validation_failed` | repair 后仍无法得到合法计划草稿。 |
| `run_canceled` | 用户主动停止生成。 |
| `run_not_found` | run 不存在或不属于当前用户。 |
| `run_status_conflict` | 当前 run 状态不允许执行该操作。 |

错误事件只返回稳定错误码和简短可读提示，不返回完整 provider 异常、完整 prompt、完整用户输入或完整模型输出。

## 日志与安全

关键日志使用标准 `logging` 和稳定 key：

```text
llm run created user_id=%s run_id=%s kind=%s related_type=%s related_id=%s
llm run started user_id=%s run_id=%s kind=%s credential_id=%s model=%s
llm run stage user_id=%s run_id=%s stage=%s
llm run canceled user_id=%s run_id=%s stage=%s
llm run completed user_id=%s run_id=%s status=%s duration_ms=%s
llm run failed user_id=%s run_id=%s error_code=%s stage=%s
```

不得记录：

- API key、session token、加密密钥。
- 完整用户输入。
- 完整题解、完整代码、完整模型输出。
- provider 原始错误中的敏感请求内容。

## 测试策略

后端测试：

- run 创建、权限隔离和状态迁移。
- SSE 事件序列：`started -> progress/delta -> result -> done`。
- 取消 run 后进入 `canceled`，且不能确认半截结果。
- fake provider stream，不依赖真实 OpenAI。
- `goal_plan_generate` flow：模型草稿、validator、repair、最终 result。
- provider 报错、JSON 解析失败、校验失败的错误映射。
- 用户级 LLM 资产路由仍被调用，API key 不出后端边界。

前端测试：

- `useLlmRun` 正确处理 `started/progress/delta/result/error/canceled/done`。
- `LlmStreamingPanel` 显示阶段、流式文本、停止按钮、错误态和完成态。
- `GoalCalibrationPage` 使用 run 完成追问和计划生成。
- 计划生成未完成、失败或取消时不显示确认按钮。
- 刷新后通过 status API 恢复最终结果。

建议验证命令：

```bash
uv run pytest backend/tests/test_llm_runs_api.py backend/tests/test_llm_run_service.py backend/tests/test_learning_flows.py -q
cd frontend && corepack pnpm test -- LlmStreamingPanel.test.tsx useLlmRun.test.tsx GoalCalibrationPage.test.tsx
make build
```

## 文档影响

实现时需要同步维护：

- `docs/index.md`：新增 `llm_run`、provider、learning flows、前端 streaming hook / component 的目录职责。
- `docs/architecture/foundation.md`：补充统一 LLM Run 流式调用层、SSE 边界、取消和刷新恢复语义。
- `docs/prd/prd.md`：补充 ChatGPT 式流式输出、后台阶段进度、停止生成、刷新恢复状态。
- `docs/project-todolist.md`：把 LLM Run 流式体验层作为 T3 基础 AI 教练闭环的前置底座或 T2 / T3 之间的独立任务。

如果实现只新增内部模块但不改变 Docker、端口、环境变量、Makefile 命令，则不需要更新 `docs/architecture/docker.md`、`docs/architecture/makefile.md` 和 `docs/dev-setup.md`。

## 验收标准

- 目标校准追问、计划生成和计划调整不再只有 loading，用户能看到阶段进度和可展示的流式文本。
- 计划生成过程中的未校验题单不会作为正式题单展示。
- 计划生成完成后，`result` 返回通过后端 validator / repair 的正式草稿。
- 用户点击停止后，run 进入 `canceled`，不允许确认半截结果，并可以重新生成。
- 页面刷新后可查询 run 状态；已完成 run 能恢复最终结果。
- 所有 LLM 调用仍通过用户级 API 资产池和粘性路由，不把 API key 暴露给前端。
- 日志满足项目规则，不记录完整用户输入、完整模型输出、API key 或其他敏感信息。
