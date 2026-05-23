# 项目基座架构

本文档说明当前项目基座的技术选型、服务边界和后续扩展方向。

## 目标

项目基座要先解决工程可运行性，而不是一次性实现完整产品功能。当前目标是让以下能力在 WSL Ubuntu 中可重复运行：

- 后端 FastAPI 服务。
- 前端 Vite React 应用。
- PostgreSQL + pgvector 数据库。
- Alembic migration。
- 本地用户注册登录和用户级 OpenAI API 资产配置。
- 目标校准、学习计划、计划题训练工作台和基础 AI 教练闭环。
- Docker Compose 开发环境。
- Makefile 一键命令。
- 基础 smoke test。

## 总体结构

```text
Browser
  -> Vite dev server / Nginx static frontend
  -> FastAPI backend
  -> PostgreSQL + pgvector
  -> code-runner container（现有备用基础设施）
```

后端是系统的业务边界。前端只通过 HTTP API 与后端交互，不直接连接数据库、不直接调用 LLM、不直接执行用户代码。

PRD v0.3 第一版不再把本地代码运行纳入核心产品流程。用户最终运行和提交以 LeetCode 官网为准，现有 `code-runner` 仅作为已经搭建好的备用基础设施和后续实验能力保留。

用户身份和模型资产也在后端边界内处理。浏览器只保存后端设置的 HttpOnly session cookie；OpenAI API key 只在创建或覆盖更新时提交给后端，后端加密落库，API 和前端只返回脱敏后的 `api_key_mask`。

用户级 OpenAI API 资产支持多资产列表管理、启用/禁用、首选资产和当前通讯资产。后端后续 LLM 调用不直接读取单个默认资产，而是通过统一选择服务使用粘性策略：优先保持当前通讯资产；当连续失败达到 3 次后，切换到其他启用且可用的资产。`is_default` 暂时保留为兼容字段，语义等同 `is_preferred`。

## 前端选型

当前前端使用：

- Vite
- React
- TypeScript
- Ant Design
- React Router
- TanStack Query
- Monaco Editor
- Corepack + pnpm

选择 Vite SPA 的原因：

- 产品是登录后的训练工作台，不是 SEO 页面。
- 题库、做题工作台、AI 对话、Trace 面板都属于高交互 SPA 场景。
- 后端已经由 FastAPI 承担 API、Agent、RAG、数据库和工具调用职责，不需要 Next.js 提供服务端能力。
- 相比 Create React App，Vite 是更现代的构建链。

Redux Toolkit 当前没有引入。业务请求、缓存、加载态和错误态优先交给 TanStack Query。只有当客户端全局状态明显变复杂时再考虑 Redux。

当前登录后产品界面使用左侧窄导航和主内容区，页面包含题库、学习计划、工作台、API 设置、复盘和 Trace。未登录用户进入登录或注册页；已登录但没有启用的首选 API 资产的用户会被引导到 `/settings/api-keys`，已有首选 API 资产的用户默认进入 `/study-plan`。

计划题训练工作台使用 `/workspace/items/:itemId` 路由作为学习计划项入口。前端会通过 practice API 创建或恢复同一个训练会话，页面采用左侧题面、右侧 Chat-first 教练区的两栏布局；主界面不再维护独立代码草稿。用户把思路、卡点和代码直接发给教练，代码尝试记录由 `review_code` 流程自动提取并通过 session payload 回传，右侧教练区提供代码尝试记录抽屉和“LeetCode 已 AC”动作。AI 教练消息和复盘通过统一 LLM Run SSE 层执行，前端不直接调用模型。

## 后端选型

当前后端使用：

- Python 3.12
- uv
- FastAPI
- Pydantic Settings
- SQLAlchemy async
- asyncpg
- Alembic

后端当前提供：

- `GET /health`
- `GET /api/health`
- `GET /api/db/health`
- `GET /api/problems`
- `GET /api/problems/{slug}`
- `GET /api/problem-categories`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/me/llm-credentials`
- `POST /api/me/llm-credentials`
- `PATCH /api/me/llm-credentials/{id}`
- `POST /api/me/llm-credentials/{id}/preferred`
- `POST /api/me/llm-credentials/{id}/default`
- `POST /api/me/llm-credentials/{id}/test`
- `DELETE /api/me/llm-credentials/{id}`
- `POST /api/llm-runs`
- `GET /api/llm-runs/{run_id}`
- `GET /api/llm-runs/{run_id}/stream`
- `POST /api/llm-runs/{run_id}/cancel`
- `POST /api/goal-calibration`
- `POST /api/goal-calibration/{draft_id}/followup`
- `POST /api/goal-calibration/{draft_id}/generate`
- `POST /api/study-plans/confirm`
- `GET /api/study-plan/current`
- `GET /api/study-plans`
- `POST /api/study-plans/{plan_id}/activate`
- `GET /api/study-plans/{plan_id}/versions/{version_id}`
- `POST /api/study-plans/{plan_id}/adjustments`
- `POST /api/study-plans/{plan_id}/versions/{version_id}/activate`
- `PATCH /api/study-plan/items/{item_id}`
- `POST /api/study-plan/stages/{stage_id}/reorder`
- `POST /api/study-plan/items/{item_id}/practice-session`
- `GET /api/practice-sessions/{session_id}`
- `GET /api/practice-sessions/{session_id}/events`
- `POST /api/practice-sessions/{session_id}/messages`
- `POST /api/practice-sessions/{session_id}/code-snapshots`
- `POST /api/practice-sessions/{session_id}/submission-feedback`
- `POST /api/practice-sessions/{session_id}/summary`

当前和后续产品功能会放在以下模块边界中：

- `backend.app.api`：HTTP API。
- `backend.app.api.learning`：目标校准、计划草稿、计划确认、当前计划、计划历史、计划项状态、计划重排和版本激活 API。
- `backend.app.api.practice`：计划题训练会话、事件时间线、用户消息、代码快照、LeetCode 回填和复盘 run 创建 API。
- `backend.app.core`：配置和基础设施。
- `backend.app.db`：数据库连接、migration 支撑。
- `backend.app.models`：SQLAlchemy 模型。
- `backend.app.models.learning`：目标校准草稿、学习计划、计划版本、阶段、计划项和变更日志。
- `backend.app.models.practice`：训练会话、训练事件、代码快照、提交回填、教练回合、单题复盘、长期画像快照和画像增量。
- `backend.app.schemas`：Pydantic 输入输出模型。
- `backend.app.schemas.practice`：训练工作台请求响应、阶段、提示档位、训练事件、画像摘要和提交回填 schema。
- `backend.app.services.auth_service`：本地用户、Argon2id 密码 hash、session token hash、注册登录退出和当前用户查询。
- `backend.app.services.credential_crypto`：Fernet API key 加密、解密和 mask。
- `backend.app.services.llm_credential_service`：用户级 OpenAI API 资产 CRUD、首选/当前通讯资产处理、粘性路由、连续失败计数和所有权校验。
- `backend.app.services.llm_run_service`：LLM Run 创建、状态迁移、取消、结果落库和终态并发保护。
- `backend.app.services.llm_run_events`：单进程开发环境中的 SSE 事件编码和内存事件 hub。
- `backend.app.services.llm_orchestrator`：统一执行 LLM Run，负责选择模型资产、解密 API key、创建 provider、调度具体学习 flow，并只在 run 成功提交后发布最终 result。
- `backend.app.services.llm_providers`：大模型 provider 适配层，当前封装 OpenAI Responses 流式输出。
- `backend.app.services.learning_flows`：可流式执行的学习业务 flow，当前包含目标校准追问、追问回答、学习计划草稿生成、教练单轮回复和单题复盘。
- `backend.app.services.learning_plan_llm`：目标校准追问、学习计划草稿生成、OpenAI Responses client 和 LLM repair loop 编排。
- `backend.app.services.learning_plan_validator`：本地题库校验、缺失题目替换、重复题和 paid only 题过滤。
- `backend.app.services.study_plan_service`：目标校准 draft 生命周期、计划确认、唯一 active 计划、版本草稿、版本激活、计划项状态和重排。
- `backend.app.services.practice_session_service`：计划题 session 创建/恢复、训练事件、代码快照、提交回填、阶段状态和前端 payload 组装。
- `backend.app.services.code_attempts`：从 `review_code` 阶段聊天消息中提取代码、校验 AI 质量判断，并把代码尝试持久化为 `code_snapshot` 与 `practice_event`。
- `backend.app.services.profile_provider`：面向 AI 教练的安全画像摘要 Provider，隔离长期画像表和 prompt 输入。
- `backend.app.services.profile_service`：初始画像、画像增量校验、画像快照版本化、单题复盘到画像更新的合并逻辑。
- `backend.app.services.coach_guard`：教练阶段跳转和提示档位守卫，防止低提示档位输出完整解法或无证据快进。
- `backend.app.agents`：LangGraph 编排。
- `backend.app.rag`：知识库导入、切块、检索。
- `backend.app.tools`：后续工具能力目录。PRD v0.3 第一版优先做 LeetCode 提交结果归因；如后续重新引入本地代码运行，再在此边界内接入。

## 数据库选型

当前数据库使用 PostgreSQL + pgvector。

选择原因：

- PRD 同时需要业务数据、训练记录、Agent trace、RAG 文档和向量检索。
- MVP 阶段使用一个数据库能降低部署和调试复杂度。
- pgvector 可以满足第一版 RAG 检索需求。
- 后续如果检索规模或召回策略变复杂，再评估 Qdrant、Milvus 等专用向量库。

当前首个 migration 会：

- 启用 `vector` extension。
- 创建 `app_metadata`。
- 创建基础 `agent_trace`。
- 创建基础 `retrieval_trace`。

题库数据使用结构化 seed 文件导入，不在应用运行时解析第三方参考仓库。数据准备流程是：

```text
本地忽略的 data/sources/leetcode-problemset
-> scripts/prepare_problem_seed.py
-> data/seed/*.jsonl
-> make db-seed
-> PostgreSQL problem / problem_category / problem_category_item
```

第一版题库浏览只展示题目静态数据，不展示用户训练状态、最近训练时间或平均提示等级。

当前题库相关 migration 会：

- 创建 `problem`。
- 创建 `problem_category`。
- 创建 `problem_category_item`。

当前本地用户和模型资产相关 migration 会：

- 创建 `app_user`。
- 创建 `auth_session`。
- 创建 `llm_credential`。

`app_user` 是后续目标、学习计划、训练记录和画像的用户主键来源。`auth_session` 保存后端 session token hash，浏览器侧只持有 HttpOnly cookie。`llm_credential` 保存用户级 OpenAI API 资产，其中 `api_key_ciphertext` 为 Fernet 密文，`api_key_mask` 用于前端展示；同一用户首选资产和当前通讯资产由服务层保证唯一，数据库当前只提供查询索引，不提供唯一约束。

当前学习计划相关 migration 会：

- 创建 `goal_calibration_draft`，保存结构化输入、LLM 追问记录、草稿计划、校验报告、repair log 和确认后的计划/版本引用。
- 创建 `study_plan`，保存用户级计划容器、计划状态和当前版本号。
- 创建 `study_plan_version`，保存目标快照、生成说明、调整说明、校验报告、repair log 和版本状态。
- 创建 `study_plan_stage`，保存阶段目标、重点标签、验收标准和阶段状态。
- 创建 `study_plan_item`，保存正式题库题目引用、推荐理由、建议训练模式、状态、顺序和锁定标记。
- 创建 `plan_change_log`，记录版本调整中的 preserved、added、removed 和 reordered 变化。

当前 LLM Run 相关 migration 会：

- 创建 `llm_run`，保存用户、run kind、关联业务对象、输入摘要、阶段、可展示流式文本、最终 result、错误摘要、取消标记、使用的模型资产和时间戳。

当前训练工作台和用户画像相关 migration 会：

- 创建 `practice_session`，以 `user_id + study_plan_id + problem_id` 保证同一计划题复用同一个训练会话，并记录 origin/latest 计划版本追溯字段。
- 创建 `practice_event`，保存用户消息、AI 回复、自动代码尝试、LeetCode AC、阶段变化、复盘和画像更新等训练时间线事件。
- 创建 `code_snapshot`，保存用户代码版本和 `code_hash`；第一版代码主要从 `review_code` 聊天流程自动提取，完整代码只在代码快照表中留存，不进入普通日志或长期画像摘要。
- 创建 `submission_feedback`，保存用户确认的 LeetCode 结果；AC 允许不携带运行时间、内存或代码快照，非 AC 反馈仍可关联失败样例摘要、错误信息和代码尝试。
- 创建 `coach_turn`，保存一次 AI 教练回复的阶段判断、提示档位、守卫结果、上下文快照和 assistant event 关联。
- 创建 `session_summary`，保存单题复盘、阶段轨迹、卡点、错因、画像信号和画像更新建议，且一个 session 只保留一个 summary。
- 创建 `user_profile_snapshot`，保存面向 AI 教练读取的长期画像版本，不原地覆盖旧版本。
- 创建 `profile_delta`，保存一次复盘对长期画像的增量影响；无证据 delta 会被拒绝，接受后生成新的 `user_profile_snapshot`。

### 统一 LLM Run 流式层

大模型调用统一通过后端 LLM Run 层发起。前端先创建 run，再通过 SSE 接收 `started`、`progress`、`delta`、`result`、`error`、`canceled` 和 `done` 事件。API key、模型资产选择、OpenAI Responses 调用、题库校验和 repair 仍在后端边界内完成。

第一版持久化 run 状态、阶段、最终结果、错误摘要和取消状态，不保存完整 token 日志。页面刷新后可以恢复 run 状态和最终结果；未完成的运行在单进程开发环境中通过内存事件 hub 继续推送，后续多 worker 部署再引入外部队列或持久事件表。

目标校准页已经接入该层：首次校准、追问回答和计划草稿生成都通过 `goal_followup` 或 `goal_plan_generate` run 执行。结构化模型输出只作为后端草稿来源，SSE `delta` 面向前端发布安全的用户可读进度文本，不直接展示原始 JSON、题单 schema 或未校验题目 slug。正式计划草稿只在后端校验、repair 和 run 成功提交后通过 `result` 事件暴露给前端；取消或失败时，半截输出只能作为过程文本展示，不能被确认成正式计划。

训练工作台也接入该层：`coach_turn` run 持久化 assistant event 和 `coach_turn` 记录，`coach_summary` run 在教练回复后创建或更新 `session_summary`，再生成 `profile_delta` 并经后端校验合并为新的 `user_profile_snapshot`。第一版教练回复仍使用确定性安全回复和后端有限状态编排，因此当前 `coach_turn` 和 `coach_summary` 不要求先选择或解密模型资产；LangGraph、RAG 和更完整的模型结构化输出后续可以在相同 run kind 边界内替换，并在切换到真实模型调用时重新打开模型资产依赖。

## Docker Compose 角色

Docker Compose 是本地开发、测试和打包验证的统一入口。

当前服务：

- `postgres`：pgvector PostgreSQL。
- `backend`：FastAPI。
- `frontend`：Vite dev server 或 Nginx 静态服务。
- `code-runner`：现有备用的隔离 Python 代码执行容器，PRD v0.3 第一版产品主线暂不使用。

## 代码执行边界

PRD v0.3 第一版产品主线不做本地代码运行，用户最终运行和提交以 LeetCode 官网为准。

如后续重新引入本地代码运行，用户代码也不能在后端主进程里执行。当前基座已经定义独立 `code-runner` 镜像，并在 Compose 中限制：

- 无网络。
- 只读文件系统。
- `no-new-privileges`。
- drop Linux capabilities。
- CPU 和内存限制。

后续如重新启用该能力，需要在这个边界上继续完善输入协议、超时控制、结果结构化和安全策略。

## 验证边界

基座可用性的最低验证命令：

```bash
make build
make up
make db-migrate
make smoke
make down
```

`make smoke` 当前会检查：

- 后端健康检查。
- 数据库健康检查。
- pgvector extension。
- 前端页面可访问。
- code-runner 能执行最小 Python 代码。

## 后续里程碑

基座完成后，后续功能应按 PRD 里程碑推进：

1. 将当前确定性 AI 教练回复升级为可校验的结构化模型输出。
2. LangGraph 状态机。
3. RAG 教练知识库。
4. 更完整的 LeetCode 提交错因归因。
5. 画像驱动推荐和画像可视化。
6. Trace 和评估。
