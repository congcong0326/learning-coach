# 项目基座架构

本文档说明当前代码真正提供的技术选型、服务边界、数据边界和验证边界。产品需求见 `docs/prd/prd.md`。

## 当前目标

项目当前收敛为题库与本地登录极简版，优先保证一个可运行、可测试、可继续扩展的全栈基座：

- 本地用户注册登录。
- 题库 seed 导入。
- 题库列表和题面详情查询。
- 最小题库问答 Agent loop 实验入口。
- 前端登录态保护、题库列表和题面详情页面。
- Docker Compose、Makefile 和 smoke test 支撑本地开发。

完整 AI 教练、学习计划、训练工作台、复盘、画像、推荐、RAG、Trace 和 code-runner 已从当前代码中移除。当前只保留一个后端最小 Agent loop，用受限题库工具连接 OpenAI Responses API，不恢复旧版 LLM Run 或训练闭环。

## 总体结构

```text
Browser
  -> Vite dev server / Nginx static frontend
  -> FastAPI backend
  -> PostgreSQL
```

后端是认证和题库数据边界。前端只通过 HTTP API 与后端交互，不直接连接数据库。

浏览器只保存后端设置的 HttpOnly session cookie；密码 hash 只保存在数据库中，原始密码和原始 session token 不落库、不写日志。

## 前端边界

当前前端使用：

- Vite
- React
- TypeScript
- Ant Design
- React Router
- TanStack Query
- React Markdown
- Corepack + pnpm

当前页面：

- `/login`：登录。
- `/register`：注册。
- `/problems`：题库列表。
- `/problems/:slug`：题面详情。

未登录用户访问受保护页面会跳转到 `/login`。已登录用户访问 `/` 会跳转到 `/problems`。

## 后端边界

当前后端使用：

- Python 3.12
- uv
- FastAPI
- Pydantic Settings
- SQLAlchemy async
- asyncpg
- Alembic

当前公开 API：

- `GET /health`
- `GET /api/health`
- `GET /api/db/health`
- `GET /api/problems`
- `GET /api/problems/{slug}`
- `GET /api/problem-categories`
- `POST /api/coach/chat`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`

主要模块边界：

- `backend.app.api`：HTTP API。
- `backend.app.core`：配置入口。
- `backend.app.db`：数据库连接、健康检查和 migration 支撑。
- `backend.app.models`：SQLAlchemy 模型，当前只有题库、用户和 session。
- `backend.app.schemas`：Pydantic 输入输出模型。
- `backend.app.services.auth_service`：本地用户、密码 hash、session token hash 和登录态。
- `backend.app.services.problem_service`：题库列表、详情和分类查询。
- `backend.app.services.problem_seed`：题库 seed 解析和 upsert。
- `backend.app.llm`：模型决策引擎适配器，当前包含 OpenAI Responses API 适配器。
- `backend.app.agents.types`：模型无关的 agent 历史、工具和决策协议。
- `backend.app.agents.problem_agent`：题库问答 loop 编排。
- `backend.app.agents.problem_tools`：只允许查询题库的安全工具集合。

## Agent loop 边界

当前 Agent loop 只服务题库问答：

- 决策引擎协议位于 `backend.app.agents.types`，业务 loop 不直接依赖 OpenAI SDK 或 LLM 专用类型。
- Agent loop 维护 agent-native 的本次对话历史，决策引擎负责把历史映射到模型、规则引擎或自身 API；OpenAI 的 response id、`previous_response_id` 等状态续接细节不得进入业务 loop。
- OpenAI 适配器位于 `backend.app.llm.openai_responses`，使用 Responses API。
- 工具只允许查询题库列表、题面详情和题库分类。
- 不开放 bash、文件读写、本地代码执行、在线判题或外部网页访问。
- 不持久化 LLM Run、trace、token、费用或跨请求对话历史。
- 本地 OpenAI 配置第一版位于 `backend/app/llm/local_openai_config.py`，真实密钥可放入已忽略的 `backend/app/llm/local_openai_config_local.py`。

## 数据库边界

当前数据库使用 PostgreSQL。当前 Alembic head 是 `20260519_0003`。

题库数据使用结构化 seed 文件导入：

```text
本地忽略的 data/sources/leetcode-problemset
-> scripts/prepare_problem_seed.py
-> data/seed/*.jsonl
-> make db-seed
-> PostgreSQL problem / problem_category / problem_category_item
```

当前主要表：

- 基础元数据：`app_metadata`。
- 题库：`problem`、`problem_category`、`problem_category_item`。
- 本地用户：`app_user`、`auth_session`。

题库 seed 不包含题解内容。题面 Markdown 允许包含题面所需的文本、代码块、表格和图片引用。

如果本地开发数据库曾运行旧版 AI 教练迁移，数据库内可能保留已删除表和旧 Alembic 版本号。当前代码不再依赖这些表；需要完全匹配当前 schema 时，应在确认数据可丢弃后重建开发数据库 volume。

## Docker Compose 角色

Docker Compose 是本地开发、测试和打包验证入口。当前服务：

- `postgres`：PostgreSQL 16。
- `backend`：FastAPI。
- `frontend`：Vite dev server 或 Nginx 静态服务。

详细说明见 `docs/architecture/docker.md`。

## 验证边界

最低本地验证：

```bash
make build
docker compose -f infra/compose/docker-compose.dev.yml config
```

运行环境 smoke 验证：

```bash
make up
make db-migrate
make smoke
make down
```

`make smoke` 检查后端健康检查、数据库健康检查、PostgreSQL 基本 schema 查询和前端页面可访问。

## 后续恢复池

后续如需恢复 AI 教练、学习计划、工作台、复盘、画像、推荐、RAG、Trace 或 code-runner，需要先重新定义当前版本产品范围、数据边界和安全边界。
