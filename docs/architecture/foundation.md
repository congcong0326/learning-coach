# 项目基座架构

本文档说明当前项目基座的技术选型、服务边界和后续扩展方向。

## 当前目标

当前项目重构为极简 MVP，先保留可持续叠加 AI 能力的核心训练闭环：

- 本地用户注册登录。
- 用户级 OpenAI / OpenAI-compatible API 资产配置。
- 题库导入、题库浏览和题面展示。
- 目标校准、AI 生成学习计划、用户确认当前计划。
- 从当前学习计划进入计划题工作台。
- 工作台 AI 教练完成追问、分层提示、代码 review、LeetCode 反馈分析。
- AC 后生成单题复盘、画像增量和下一题建议。
- Docker Compose、Makefile 和 smoke test 支撑本地开发。

RAG、Trace 页面、备份恢复、学习仪表盘、code-runner、画像驱动计划补强和学习计划历史/版本 UI 已从当前可运行主线移出，作为后续演进能力保留设计参考。

## 总体结构

```text
Browser
  -> Vite dev server / Nginx static frontend
  -> FastAPI backend
  -> PostgreSQL
```

后端是系统的业务和 AI 能力边界。前端只通过 HTTP API 与后端交互，不直接连接数据库、不直接调用 LLM、不直接执行用户代码。

用户身份和模型资产也在后端边界内处理。浏览器只保存后端设置的 HttpOnly session cookie；OpenAI API key 只在创建或覆盖更新时提交给后端，后端加密落库，API 和前端只返回脱敏后的 `api_key_mask`。

用户级 OpenAI API 资产支持多资产列表管理、启用/禁用、首选资产和当前通讯资产。后端 LLM 调用通过统一选择服务使用粘性策略：优先保持当前通讯资产；当连续失败达到 3 次后，切换到其他启用且可用的资产。`is_default` 暂时保留为兼容字段，语义等同 `is_preferred`。

## 前端边界

当前前端使用：

- Vite
- React
- TypeScript
- Ant Design
- React Router
- TanStack Query
- Monaco Editor
- Corepack + pnpm

登录后产品界面使用左侧导航和主内容区。当前页面包括题库、学习计划、工作台、API 设置和复盘；登录和注册作为独立入口。已登录但没有启用首选 API 资产的用户会被引导到 `/settings/api-keys`，已有首选 API 资产的用户默认进入 `/study-plan`。

计划题训练工作台使用 `/workspace/items/:itemId` 路由作为学习计划项入口。前端通过 practice API 创建或恢复同一个训练会话，页面采用上方题面、下方 Chat-first 教练区布局。用户把思路、卡点和代码直接发给教练；非 AC 的 LeetCode 结果也通过聊天输入进入系统。AC 通过明确的“LeetCode 已 AC”动作记录，并触发单题复盘。

AI 教练消息和复盘通过统一 LLM Run SSE 层执行，前端不直接调用模型。run 进行中只展示当前后端状态和流式回复；正式结果由后端持久化后再进入会话历史或复盘页。

## 后端边界

当前后端使用：

- Python 3.12
- uv
- FastAPI
- Pydantic Settings
- SQLAlchemy async
- asyncpg
- Alembic

当前后端公开 API：

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
- `PATCH /api/study-plan/items/{item_id}`
- `POST /api/study-plan/stages/{stage_id}/reorder`
- `POST /api/study-plan/items/{item_id}/practice-session`
- `GET /api/practice-sessions/{session_id}`
- `GET /api/practice-sessions/{session_id}/events`
- `GET /api/practice-sessions/{session_id}/review`
- `POST /api/practice-sessions/{session_id}/messages`
- `POST /api/practice-sessions/{session_id}/code-snapshots`
- `POST /api/practice-sessions/{session_id}/submission-feedback`
- `POST /api/practice-sessions/{session_id}/summary`

当前模块边界：

- `backend.app.api`：HTTP API。
- `backend.app.api.learning`：目标校准、计划草稿、计划确认、当前计划、计划项状态和计划项重排 API。
- `backend.app.api.practice`：计划题训练会话、事件时间线、用户消息、代码快照、LeetCode 回填和复盘 run 创建 API。
- `backend.app.core`：配置和基础设施。
- `backend.app.db`：数据库连接、migration 支撑。
- `backend.app.models`：SQLAlchemy 模型。
- `backend.app.models.learning`：目标校准草稿、学习计划、计划版本、阶段、计划项和变更日志。
- `backend.app.models.practice`：训练会话、训练事件、代码快照、提交回填、教练回合、单题复盘、长期画像快照和画像增量。
- `backend.app.schemas`：Pydantic 输入输出模型。
- `backend.app.services.auth_service`：本地用户、Argon2id 密码 hash、session token hash、注册登录退出和当前用户查询。
- `backend.app.services.credential_crypto`：Fernet API key 加密、解密和 mask。
- `backend.app.services.llm_credential_service`：用户级 OpenAI API 资产 CRUD、首选/当前通讯资产处理、粘性路由、连续失败计数和所有权校验。
- `backend.app.services.llm_run_service`：LLM Run 创建、状态迁移、取消、结果落库和终态并发保护。
- `backend.app.services.llm_run_events`：单进程开发环境中的 SSE 事件编码和内存事件 hub。
- `backend.app.services.llm_orchestrator`：统一执行 LLM Run，负责选择模型资产、解密 API key、创建 provider、调度手写 loop workflow，并只在 run 成功提交后发布最终 result。
- `backend.app.services.llm_providers`：大模型 provider 适配层，当前通过 factory 支持 OpenAI Responses 流式输出。
- `backend.app.services.learning_flows`：可流式执行的学习业务 flow，当前包含目标校准追问、追问回答、学习计划草稿生成、教练单轮回复和单题复盘。
- `backend.app.services.learning_plan_llm`：目标校准追问、学习计划草稿生成、OpenAI Responses client 和 LLM repair loop 编排。
- `backend.app.services.learning_plan_validator`：本地题库校验、缺失题目替换、重复题和 paid only 题过滤。
- `backend.app.services.study_plan_service`：目标校准 draft 生命周期、计划确认、唯一 active 计划、版本一致性修复、计划项状态和重排。
- `backend.app.services.practice_session_service`：计划题 session 创建/恢复、训练事件、代码快照、提交回填、复盘读取、阶段状态和前端 payload 组装。
- `backend.app.services.code_attempts`：从 `review_code` 阶段聊天消息中提取代码、校验 AI 质量判断，并把代码尝试持久化为 `code_snapshot` 与 `practice_event`。
- `backend.app.services.profile_provider`：面向 AI 教练的安全画像摘要 Provider，隔离长期画像表和 prompt 输入。
- `backend.app.services.profile_service`：初始画像、画像增量校验、画像快照版本化、基于训练事实生成单题复盘，并把复盘安全证据合并为画像增量。
- `backend.app.services.recommendation_service`：基于计划顺序、当前阶段、难度和复盘弱项的规则化下一题推荐。
- `backend.app.services.coach_guard`：教练阶段跳转和提示档位守卫，防止低提示档位输出完整解法或无证据快进。
- `backend.app.prompts`：静态 LLM prompt resource registry，集中声明 prompt key、版本和输出字段契约。
- `backend.app.agents`：手写 Agent loop 内核、workflow registry 和极简 `CoachLoop`。当前 `goal_followup`、`goal_plan_generate`、`coach_turn` 和 `coach_summary` 通过统一 loop 入口桥接到既有业务 flow。
- `backend.app.tools`：后续工具能力目录。当前主线不接入本地代码执行。

## 数据库边界

当前数据库使用 PostgreSQL。MVP 阶段使用一个数据库承载业务数据、训练记录、LLM Run 和用户画像，降低部署和调试复杂度。

当前 migration 链路到 `20260522_0007`。首个 migration 创建 `app_metadata`，不再启用 `vector` extension，也不再创建 RAG/Trace 表。

题库数据使用结构化 seed 文件导入，不在应用运行时解析第三方参考仓库。数据准备流程是：

```text
本地忽略的 data/sources/leetcode-problemset
-> scripts/prepare_problem_seed.py
-> data/seed/*.jsonl
-> make db-seed
-> PostgreSQL problem / problem_category / problem_category_item
```

当前主要表组：

- 题库：`problem`、`problem_category`、`problem_category_item`。
- 本地用户和模型资产：`app_user`、`auth_session`、`llm_credential`。
- 学习计划：`goal_calibration_draft`、`study_plan`、`study_plan_version`、`study_plan_stage`、`study_plan_item`、`plan_change_log`。
- LLM Run：`llm_run`。
- 训练工作台和用户画像：`practice_session`、`practice_event`、`code_snapshot`、`submission_feedback`、`coach_turn`、`session_summary`、`user_profile_snapshot`、`profile_delta`。

学习计划题的展示状态由计划项基础状态和训练事实共同决定。`study_plan_item.status` 保存可持久化的计划进度；`practice_session`、`practice_event` 和 `submission_feedback` 是训练事实来源。学习计划 payload 会把已有用户/教练消息、代码尝试或提交反馈投影为 `in_progress`，把 AC 结果投影为 `completed`。

## 统一 LLM Run 流式层

大模型调用统一通过后端 LLM Run 层发起。前端先创建 run，再通过 SSE 接收 `started`、`progress`、`delta`、`result`、`error`、`canceled` 和 `done` 事件。API key、模型资产选择、OpenAI Responses 调用、题库校验和 repair 都在后端边界内完成。

第一版持久化 run 状态、阶段、最终结果、错误摘要和取消状态，不保存完整 token 日志。页面刷新后可以恢复 run 状态和最终结果；未完成的运行在单进程开发环境中通过内存事件 hub 继续推送，后续多 worker 部署再引入外部队列或持久事件表。

目标校准页接入该层：首次校准、追问回答和计划草稿生成都通过 `goal_followup` 或 `goal_plan_generate` run 执行。正式计划草稿只在后端校验、repair 和 run 成功提交后通过 `result` 事件暴露给前端。

训练工作台也接入该层：`coach_turn` run 会选择用户模型资产，经手写 loop workflow 进入 `CoachLoop` 预处理编排并绑定 `practice_session.thread_id`。`coach_turn` 会从当前学习计划版本的 `target_snapshot.preferred_language` 读取目标训练语言，并以 `session.target_code_language` 注入模型上下文。模型输出只负责提出 `phase_after`、卡点、下一步动作和用户可见回复；状态跳转、提示升降档、低提示档位泄题拦截、缺代码 review、缺提交反馈分析和缺 AC/终态复盘仍由后端守卫控制。

WA/TLE/RE/MLE/CE/UNKNOWN 等非 AC 信息如果由用户粘贴在聊天中，会被 `coach_turn` 识别为 `chat_extracted` 提交反馈摘要，并进入下一轮模型上下文。`coach_summary` 使用独立 prompt 生成教练式 AC 复盘，重点总结本题优点、缺点、证据、画像变化和下一题训练策略。如果模型调用失败或结构化输出无效，`coach_turn` 会回退到安全追问模板并记录 warning。

最小 Eval runner 位于 `backend.app.evals.coach_eval_runner`，可通过 `make eval` 或 `uv run python -m backend.app.evals.coach_eval_runner` 运行。当前固定样例覆盖 Hint Leakage、Diagnosis 和 Code Review。

## Docker Compose 角色

Docker Compose 是本地开发、测试和打包验证的统一入口。

当前服务：

- `postgres`：标准 PostgreSQL 16。
- `backend`：FastAPI。
- `frontend`：Vite dev server 或 Nginx 静态服务。

## 代码执行边界

当前 MVP 不做本地代码运行，用户最终运行和提交以 LeetCode 官网为准。

如后续重新引入本地代码运行，用户代码不能在后端主进程里执行，需要重新设计隔离容器、输入协议、超时控制、结果结构化和安全策略。

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
- 数据库健康检查和基本 schema 查询。
- 前端页面可访问。

## 后续里程碑

极简 MVP 稳定后，后续功能应按价值逐步恢复：

1. 扩大 AI 教练评估集，覆盖更多真实做题对话。
2. 更完整的 LeetCode 提交错因归因。
3. 更细的用户画像和个性化训练推荐。
4. RAG 教练知识库。
5. 面向研发验证的 Trace、评估集和提示泄露检查。
6. 学习仪表盘、画像驱动计划补强、学习计划历史/版本 UI。
7. 本地代码执行工具和更完整的工具层。
