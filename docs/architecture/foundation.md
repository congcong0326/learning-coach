# 项目基座架构

本文档说明当前项目基座的技术选型、服务边界和后续扩展方向。

## 目标

项目基座要先解决工程可运行性，而不是一次性实现完整产品功能。当前目标是让以下能力在 WSL Ubuntu 中可重复运行：

- 后端 FastAPI 服务。
- 前端 Vite React 应用。
- PostgreSQL + pgvector 数据库。
- Alembic migration。
- 本地用户注册登录和用户级 OpenAI API 资产配置。
- Docker Compose 开发环境。
- Makefile 一键命令。
- 基础 smoke test。

## 总体结构

```text
Browser
  -> Vite dev server / Nginx static frontend
  -> FastAPI backend
  -> PostgreSQL + pgvector
  -> code-runner container
```

后端是系统的业务边界。前端只通过 HTTP API 与后端交互，不直接连接数据库、不直接调用 LLM、不直接执行用户代码。

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

当前和后续产品功能会放在以下模块边界中：

- `backend.app.api`：HTTP API。
- `backend.app.api.learning`：目标校准、计划草稿、计划确认、当前计划、计划历史、计划项状态、计划重排和版本激活 API。
- `backend.app.core`：配置和基础设施。
- `backend.app.db`：数据库连接、migration 支撑。
- `backend.app.models`：SQLAlchemy 模型。
- `backend.app.models.learning`：目标校准草稿、学习计划、计划版本、阶段、计划项和变更日志。
- `backend.app.schemas`：Pydantic 输入输出模型。
- `backend.app.services.auth_service`：本地用户、Argon2id 密码 hash、session token hash、注册登录退出和当前用户查询。
- `backend.app.services.credential_crypto`：Fernet API key 加密、解密和 mask。
- `backend.app.services.llm_credential_service`：用户级 OpenAI API 资产 CRUD、首选/当前通讯资产处理、粘性路由、连续失败计数和所有权校验。
- `backend.app.services.llm_run_service`：LLM Run 创建、状态迁移、取消、结果落库和终态并发保护。
- `backend.app.services.llm_run_events`：单进程开发环境中的 SSE 事件编码和内存事件 hub。
- `backend.app.services.llm_orchestrator`：统一执行 LLM Run，负责选择模型资产、解密 API key、创建 provider、调度具体学习 flow，并只在 run 成功提交后发布最终 result。
- `backend.app.services.llm_providers`：大模型 provider 适配层，当前封装 OpenAI Responses 流式输出。
- `backend.app.services.learning_flows`：可流式执行的学习业务 flow，当前包含目标校准追问、追问回答和学习计划草稿生成。
- `backend.app.services.learning_plan_llm`：目标校准追问、学习计划草稿生成、OpenAI Responses client 和 LLM repair loop 编排。
- `backend.app.services.learning_plan_validator`：本地题库校验、缺失题目替换、重复题和 paid only 题过滤。
- `backend.app.services.study_plan_service`：目标校准 draft 生命周期、计划确认、唯一 active 计划、版本草稿、版本激活、计划项状态和重排。
- `backend.app.agents`：LangGraph 编排。
- `backend.app.rag`：知识库导入、切块、检索。
- `backend.app.tools`：代码运行、静态分析、错误归因等工具。

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

T1 当前只把学习计划项和题库题目关联起来；真实训练会话、提交历史和代码快照将在 T2 通过稳定的 plan/version/item 标识继续关联。

当前 LLM Run 相关 migration 会：

- 创建 `llm_run`，保存用户、run kind、关联业务对象、输入摘要、阶段、可展示流式文本、最终 result、错误摘要、取消标记、使用的模型资产和时间戳。

### 统一 LLM Run 流式层

大模型调用统一通过后端 LLM Run 层发起。前端先创建 run，再通过 SSE 接收 `started`、`progress`、`delta`、`result`、`error`、`canceled` 和 `done` 事件。API key、模型资产选择、OpenAI Responses 调用、题库校验和 repair 仍在后端边界内完成。

第一版持久化 run 状态、阶段、最终结果、错误摘要和取消状态，不保存完整 token 日志。页面刷新后可以恢复 run 状态和最终结果；未完成的运行在单进程开发环境中通过内存事件 hub 继续推送，后续多 worker 部署再引入外部队列或持久事件表。

目标校准页已经接入该层：首次校准、追问回答和计划草稿生成都通过 `goal_followup` 或 `goal_plan_generate` run 执行。结构化模型输出只作为后端草稿来源，SSE `delta` 面向前端发布安全的用户可读进度文本，不直接展示原始 JSON、题单 schema 或未校验题目 slug。正式计划草稿只在后端校验、repair 和 run 成功提交后通过 `result` 事件暴露给前端；取消或失败时，半截输出只能作为过程文本展示，不能被确认成正式计划。

## Docker Compose 角色

Docker Compose 是本地开发、测试和打包验证的统一入口。

当前服务：

- `postgres`：pgvector PostgreSQL。
- `backend`：FastAPI。
- `frontend`：Vite dev server 或 Nginx 静态服务。
- `code-runner`：隔离的 Python 代码执行容器。

## 代码执行边界

用户代码不在后端主进程里执行。当前基座已经定义独立 `code-runner` 镜像，并在 Compose 中限制：

- 无网络。
- 只读文件系统。
- `no-new-privileges`。
- drop Linux capabilities。
- CPU 和内存限制。

后续产品功能需要在这个边界上继续完善输入协议、超时控制、结果结构化和安全策略。

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

1. 做题工作台的代码编辑与训练会话。
2. 基础 AI 教练闭环。
3. LangGraph 状态机。
4. RAG 教练知识库。
5. 代码执行与错误归因。
6. 复盘、画像和推荐。
7. Trace 和评估。
