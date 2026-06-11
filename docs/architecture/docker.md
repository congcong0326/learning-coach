# Docker 设计

本文档说明当前 Docker 镜像、Compose 文件、端口、数据卷和 smoke test。实际行为以 `infra/` 下文件为准。

## 文件结构

```text
infra/
  docker/
    backend.Dockerfile
    frontend.Dockerfile
    nginx.conf
  compose/
    docker-compose.dev.yml
    docker-compose.test.yml
    docker-compose.prod.yml
```

## 镜像

### backend

文件：`infra/docker/backend.Dockerfile`

职责：

- 使用 Python 3.12 slim。
- 使用 uv 安装 Python 依赖。
- 安装基础证书以支持 HTTPS 调用。
- 运行 FastAPI 应用。
- 打包 `scripts/` 和 `data/seed/`，用于本地或私有镜像中的题库 seed 导入。

默认启动命令：

```bash
uv run --no-sync uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

开发 compose 会追加 `--reload`，并把本地 `backend/` 和 `alembic.ini` 挂载进容器。

题库原始参考仓库不进入镜像。`data/seed/` 可能包含完整题面，打包镜像默认面向本地或私有环境，不应公开分发。

### frontend

文件：`infra/docker/frontend.Dockerfile`

职责：

- dev 阶段运行 Vite dev server。
- build 阶段构建 `frontend/dist`。
- runtime 阶段用 Nginx 托管静态文件。

生产 runtime 使用 `infra/docker/nginx.conf`：

- `/api/` 代理到 `backend:8000/api/`。
- `/health` 代理到后端 `/health`。
- 其他路径 fallback 到 `index.html`。

## Compose 文件

### 开发环境

文件：`infra/compose/docker-compose.dev.yml`

服务：

- `postgres`
- `backend`
- `frontend`

默认端口：

- 后端：`8000`
- 前端：`5173`
- PostgreSQL 宿主机端口：`15432`

启动和停止：

```bash
make up
make down
```

开发数据库 volume：

- `learning-coach-dev_postgres_data`

前端依赖 volume：

- `learning-coach-dev_frontend_node_modules`

前端容器启动时会先执行 `CI=true pnpm install --frozen-lockfile`，再启动 Vite dev server。这样 `package.json` 或 `pnpm-lock.yaml` 变化时，容器内依赖 volume 会以非交互方式同步。

### 测试环境

文件：`infra/compose/docker-compose.test.yml`

服务：

- `postgres`
- `backend-test`

数据库使用 tmpfs，不保留测试数据。

运行：

```bash
docker compose -f infra/compose/docker-compose.test.yml run --rm backend-test
```

### 生产/打包环境

文件：`infra/compose/docker-compose.prod.yml`

服务：

- `postgres`
- `backend`
- `frontend`

前端默认暴露端口：

- `8080`

启动示例：

```bash
docker compose -f infra/compose/docker-compose.prod.yml up -d --build
```

## 环境变量

参考 `.env.example`。

常用变量：

- `APP_ENV`
- `BACKEND_PORT`
- `FRONTEND_PORT`
- `FRONTEND_HTTP_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST_PORT`
- `DATABASE_URL`
- `DOCKER_DATABASE_URL`
- `CREDENTIAL_ENCRYPTION_KEY`
- `OPENAI_API_KEY`
- `LLM_API_KEY`
- `LLM_MODEL_ID`
- `LLM_BASE_URL`

本机直接运行后端时，数据库地址应指向 `localhost:15432`。容器内后端运行时，数据库地址应指向 `postgres:5432`。

`CREDENTIAL_ENCRYPTION_KEY` 是后端加密用户 OpenAI API key 的 Fernet key。开发和生产 compose 会从宿主机环境或 `.env` 传入该变量；为空时，登录注册可用，但 API 资产创建、覆盖更新和测试连接会失败。测试 compose 使用固定测试 key。

题库推荐使用显式 seed 命令：

```bash
make prepare-problem-seed
make db-seed
```

## Smoke Test

开发环境启动并迁移后运行：

```bash
make smoke
```

Smoke 检查包括：

- `GET /health`
- `GET /api/health`
- `GET /api/db/health`
- PostgreSQL 基本 schema 查询
- 前端根页面包含 React root

成功输出：

```text
All smoke checks passed
```

## WSL 注意事项

- 默认 PostgreSQL 映射到宿主机 `15432`，避免和其他项目常用的 `5432` 冲突。
- 如果端口冲突，可通过环境变量覆盖。
- 不要把 `.env` 提交到 Git。
- 如果 Docker Desktop 与 WSL 通信异常，先确认 Docker Desktop 已启用对应 WSL distro integration。

## 清理

停止开发环境：

```bash
make down
```

该命令不删除 volume。需要删除开发数据库 volume 时，应先确认数据可丢弃，再执行 Docker volume 清理命令。
