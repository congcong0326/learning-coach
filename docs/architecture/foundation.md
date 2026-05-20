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

当前登录后产品界面使用左侧窄导航和主内容区，页面包含题库、工作台、API 设置、复盘和 Trace。未登录用户进入登录或注册页；已登录但没有启用的首选 API 资产的用户会被引导到 `/settings/api-keys`。

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

后续产品功能会放在以下模块边界中：

- `backend.app.api`：HTTP API。
- `backend.app.core`：配置和基础设施。
- `backend.app.db`：数据库连接、migration 支撑。
- `backend.app.models`：SQLAlchemy 模型。
- `backend.app.schemas`：Pydantic 输入输出模型。
- `backend.app.services.auth_service`：本地用户、Argon2id 密码 hash、session token hash、注册登录退出和当前用户查询。
- `backend.app.services.credential_crypto`：Fernet API key 加密、解密和 mask。
- `backend.app.services.llm_credential_service`：用户级 OpenAI API 资产 CRUD、首选/当前通讯资产处理、粘性路由、连续失败计数和所有权校验。
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
