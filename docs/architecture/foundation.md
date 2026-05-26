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

当前登录后产品界面使用左侧窄导航和主内容区，页面包含题库、学习计划、学习仪表盘、工作台、API 设置、复盘和 Trace。未登录用户进入登录或注册页；已登录但没有启用的首选 API 资产的用户会被引导到 `/settings/api-keys`，已有首选 API 资产的用户默认进入 `/study-plan`。

计划题训练工作台使用 `/workspace/items/:itemId` 路由作为学习计划项入口。前端会通过 practice API 创建或恢复同一个训练会话，页面采用上方题面、下方 Chat-first 教练区的上下布局；主界面不再维护独立代码草稿。用户把思路、卡点和代码直接发给教练，发送后前端先用本地临时消息更新聊天流，后续由后端会话事件接管正式历史。代码尝试记录由 `review_code` 流程自动提取并通过 session payload 回传；后端会先从本轮消息中截取明确代码候选交给教练模型判断，持久化时只保存代码块本身，不保存前后聊天说明；如果模型已经 review 代码并建议去 LeetCode 提交，即使阶段守卫不允许直接快进，也要沉淀本轮代码尝试。教练区提供代码尝试记录居中悬浮框和“LeetCode 已 AC”动作；AC 成功记录后按钮切换为已记录状态并禁止重复点击。非 AC 的 LeetCode 结果不再通过主界面表单回填，用户直接把平台提示、失败用例或错误信息发给教练，后端在 `coach_turn` 中识别并注入安全摘要。悬浮框中的完整代码默认折叠，用户展开单条尝试后查看完整代码。AI 教练消息和复盘通过统一 LLM Run SSE 层执行，前端不直接调用模型；run 进行中只在输入区附近显示一行当前后端状态和已等待时间，并在聊天流里用临时教练气泡展示当前状态或流式回复；AC 触发复盘时，在模型返回前临时气泡明确显示复盘正在生成，不把系统执行步骤写入持久聊天历史。

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
- `GET /api/study-plans/{plan_id}/profile-enrichments/{draft_id}`
- `POST /api/study-plans/{plan_id}/profile-enrichments/{draft_id}/confirm`
- `POST /api/study-plans/{plan_id}/versions/{version_id}/activate`
- `PATCH /api/study-plan/items/{item_id}`
- `POST /api/study-plan/stages/{stage_id}/reorder`
- `POST /api/study-plan/items/{item_id}/practice-session`
- `GET /api/practice-sessions/{session_id}`
- `GET /api/practice-sessions/{session_id}/events`
- `GET /api/practice-dashboard`
- `POST /api/practice-sessions/{session_id}/messages`
- `POST /api/practice-sessions/{session_id}/code-snapshots`
- `POST /api/practice-sessions/{session_id}/submission-feedback`
- `GET /api/practice-sessions/{session_id}/review`
- `POST /api/practice-sessions/{session_id}/summary`
- `GET /api/traces`

当前和后续产品功能会放在以下模块边界中：

- `backend.app.api`：HTTP API。
- `backend.app.api.learning`：目标校准、计划草稿、计划确认、当前计划、计划历史、计划项状态、计划重排和版本激活 API。
- `backend.app.api.practice`：计划题训练会话、事件时间线、用户消息、代码快照、LeetCode 回填和复盘 run 创建 API。
- `backend.app.core`：配置和基础设施。
- `backend.app.db`：数据库连接、migration 支撑。
- `backend.app.models`：SQLAlchemy 模型。
- `backend.app.models.learning`：目标校准草稿、学习计划、计划版本、阶段、计划项、变更日志和画像补强计划草稿。
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
- `backend.app.services.learning_flows`：可流式执行的学习业务 flow，当前包含目标校准追问、追问回答、学习计划草稿生成、画像驱动计划补强、教练单轮回复和单题复盘。
- `backend.app.services.learning_plan_llm`：目标校准追问、学习计划草稿生成、OpenAI Responses client 和 LLM repair loop 编排。
- `backend.app.services.learning_plan_validator`：本地题库校验、缺失题目替换、重复题和 paid only 题过滤。
- `backend.app.services.study_plan_service`：目标校准 draft 生命周期、计划确认、唯一 active 计划、版本草稿、版本激活、计划项状态和重排。
- `backend.app.services.profile_plan_enrichment`：聚合用户意愿、画像、训练事实、当前计划和候选题池，调用大模型生成补强题 draft，并在用户确认后把补强题追加到当前 active 计划。
- `backend.app.services.practice_session_service`：计划题 session 创建/恢复、训练事件、代码快照、提交回填、复盘读取、最小仪表盘指标、阶段状态和前端 payload 组装。
- `backend.app.services.code_attempts`：从 `review_code` 阶段聊天消息中提取代码、校验 AI 质量判断，并把代码尝试持久化为 `code_snapshot` 与 `practice_event`；模型 review 后直接建议提交的本轮代码也要沉淀为代码尝试。
- `backend.app.services.profile_provider`：面向 AI 教练的安全画像摘要 Provider，隔离长期画像表和 prompt 输入。
- `backend.app.services.profile_service`：初始画像、画像增量校验、画像快照版本化、基于训练事实生成单题复盘，并把复盘安全证据合并为画像增量。
- `backend.app.services.recommendation_service`：基于计划顺序、当前阶段、难度和复盘弱项的规则化下一题推荐，输出推荐原因、下一题第一问和 review 重点。
- `backend.app.services.coach_guard`：教练阶段跳转和提示档位守卫，防止低提示档位输出完整解法或无证据快进。
- `backend.app.services.agent_trace_service`：写入和读取 `agent_trace`，对节点输入输出摘要、守卫原因和最终回复进行截断，避免完整用户输入和完整代码进入 trace。
- `backend.app.prompts`：静态 LLM prompt resource registry，使用 package resource 托管提示词正文，并集中声明 prompt key、版本和输出字段契约。学习 flow 只组装动态上下文并通过 registry 读取静态 instructions，避免 prompt 文本散落在业务代码中。
- `backend.app.agents`：LangGraph 编排，当前包含 `CoachGraph` 的非 RAG 状态机，记录 `load_training_context`、输入分类、卡点诊断、`retrieve_supporting_context=rag_deferred`、动作决策、守卫、回复生成、持久化和复盘触发节点，并通过 `practice_session.thread_id` 与图 checkpointer 对齐。
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
- 创建 `profile_plan_enrichment_draft`，保存画像补强题生成时的用户意愿、画像快照引用、候选题池、模型输出、校验报告、确认状态和追加后的计划项引用。

当前 LLM Run 相关 migration 会：

- 创建 `llm_run`，保存用户、run kind、关联业务对象、输入摘要、阶段、可展示流式文本、最终 result、错误摘要、取消标记、使用的模型资产和时间戳。

当前训练工作台和用户画像相关 migration 会：

- 创建 `practice_session`，以 `user_id + study_plan_id + problem_id` 保证同一计划题复用同一个训练会话，并记录 origin/latest 计划版本追溯字段。
- 创建 `practice_event`，保存用户消息、AI 回复、自动代码尝试、LeetCode AC、阶段变化、复盘和画像更新等训练时间线事件。
- 创建 `code_snapshot`，保存用户代码版本和 `code_hash`；第一版代码主要从 `review_code` 聊天流程自动提取，模型 review 后建议提交的本轮代码也会保存为代码尝试。完整代码只在代码快照表中留存，不进入普通日志或长期画像摘要。
- 创建 `submission_feedback`，保存用户确认的 LeetCode 结果；AC 允许不携带运行时间、内存或代码快照。非 AC 事实可以来自聊天识别、高级入口或未来自动接入，主路径不要求用户填写结构化表单。
- 创建 `coach_turn`，保存一次 AI 教练回复的阶段判断、提示档位、守卫结果、上下文快照和 assistant event 关联。
- 创建 `session_summary`，保存单题复盘、阶段轨迹、卡点、提交错因、复杂度/核心思路占位、画像信号和下一题建议，且一个 session 只保留一个 summary。
- 创建 `user_profile_snapshot`，保存面向 AI 教练读取的长期画像版本，不原地覆盖旧版本。
- 创建 `profile_delta`，保存一次复盘对长期画像的增量影响；无证据 delta 会被拒绝，接受后生成新的 `user_profile_snapshot`。

学习计划题的展示状态由计划项基础状态和训练事实共同决定。`study_plan_item.status` 继续保存可持久化的计划进度；`practice_session`、`practice_event` 和 `submission_feedback` 是训练事实来源。学习计划 payload 会把已有用户/教练消息、代码尝试或提交反馈投影为 `in_progress`，把 AC 结果投影为 `completed`，以兼容早期只写训练会话但未同步计划项状态的数据。新产生的用户消息、代码尝试和 LeetCode 回填也会同步推进当前计划项状态，避免后续计划调整丢失训练进度。

### 统一 LLM Run 流式层

大模型调用统一通过后端 LLM Run 层发起。前端先创建 run，再通过 SSE 接收 `started`、`progress`、`delta`、`result`、`error`、`canceled` 和 `done` 事件。API key、模型资产选择、OpenAI Responses 调用、题库校验和 repair 仍在后端边界内完成。

第一版持久化 run 状态、阶段、最终结果、错误摘要和取消状态，不保存完整 token 日志。页面刷新后可以恢复 run 状态和最终结果；未完成的运行在单进程开发环境中通过内存事件 hub 继续推送，后续多 worker 部署再引入外部队列或持久事件表。

目标校准页已经接入该层：首次校准、追问回答和计划草稿生成都通过 `goal_followup` 或 `goal_plan_generate` run 执行。结构化模型输出只作为后端草稿来源，SSE `delta` 面向前端发布安全的用户可读进度文本，不直接展示原始 JSON、题单 schema 或未校验题目 slug。正式计划草稿只在后端校验、repair 和 run 成功提交后通过 `result` 事件暴露给前端；取消或失败时，半截输出只能作为过程文本展示，不能被确认成正式计划。

训练工作台也接入该层：`coach_turn` run 会选择用户模型资产，先进入 `CoachGraph` 非 RAG 状态机并绑定 `practice_session.thread_id`，其中 `retrieve_supporting_context` 明确返回 `rag_deferred`，再调用大模型生成结构化教练决策，经后端 `coach_guard` 校验后持久化 assistant event 和 `coach_turn` 记录。`coach_turn` 会从当前学习计划版本的 `target_snapshot.preferred_language` 读取目标训练语言，并以 `session.target_code_language` 注入模型上下文；模型生成代码示例、方法签名或接近代码的伪代码时必须使用该目标语言，不得在用户选择 Java、Go、C 或 JavaScript 时默认输出 Python。模型输出只负责提出 `phase_after`、卡点、下一步动作和用户可见回复；状态跳转、提示升降档、低档位泄题拦截、缺代码 review、缺提交反馈分析和缺 AC/终态复盘仍由后端守卫控制。WA/TLE/RE/MLE/CE/UNKNOWN 等非 AC 信息如果由用户粘贴在聊天中，会被 `coach_turn` 识别为 `chat_extracted` 提交反馈摘要，并进入下一轮模型上下文；`coach_summary` 使用独立 prompt 生成教练式 AC 复盘，重点总结本题优点、缺点、证据、画像变化和下一题训练策略。如果模型调用失败或结构化输出无效，`coach_turn` 会回退到安全追问模板并记录 warning。`coach_turn` 会写入 `agent_trace`，覆盖 LLM run 生命周期、图节点摘要、`rag_deferred`、守卫原因和最终回复摘要，Trace 页通过 `/api/traces` 读取当前用户可访问的真实 trace 数据。

`profile_plan_enrichment` run 会选择用户模型资产，读取 active 学习计划、最新画像和最近复盘摘要，先由后端筛出候选题池，再让模型在候选池内生成补强题预览；后端校验通过后保存 draft，用户确认前不修改正式计划。确认接口会在事务中复核计划版本、候选题、重复题和 paid only 题，并把确认后的补强题追加到当前阶段末尾。

当前复盘页通过 `/api/practice-sessions/{session_id}/review` 读取真实 `session_summary`、`profile_delta` 和下一题推荐；学习仪表盘通过 `/api/practice-dashboard` 展示完成题数、常见卡点、平均/最高提示档位和最近画像摘要。

最小 Eval runner 位于 `backend.app.evals.coach_eval_runner`，可通过 `make eval` 或 `uv run python -m backend.app.evals.coach_eval_runner` 运行。当前固定样例覆盖 Hint Leakage、Diagnosis 和 Code Review；RAG Grounding 因 RAG/T6 延后而报告为 `deferred`，不接真实检索。

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
