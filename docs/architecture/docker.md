# Docker 设计

本文档说明当前 Docker 镜像、Compose 文件、端口、数据卷和 WSL 注意事项。

## 文件结构

```text
infra/
  docker/
    backend.Dockerfile
    frontend.Dockerfile
    code-runner.Dockerfile
    nginx.conf
  compose/
    docker-compose.dev.yml
    docker-compose.test.yml
    docker-compose.prod.yml
```

## 镜像

### backend

文件：[infra/docker/backend.Dockerfile](../../infra/docker/backend.Dockerfile)

职责：

- 使用 Python 3.12 slim。
- 使用 uv 安装 Python 依赖。
- 安装 PostgreSQL 官方 APT 源中的 `postgresql-client-16`，提供全库备份恢复需要的 `pg_dump` 和 `pg_restore`；客户端版本需要和当前 `pgvector/pgvector:pg16` 数据库主版本匹配，避免新版 client 生成或执行 PG16 不支持的恢复语句。
- 运行 FastAPI 应用。
- 打包 `scripts/` 和 `data/seed/`，用于私有或本地镜像中的题库 seed 导入。

默认启动命令：

```bash
uv run --no-sync uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

开发 compose 会加 `--reload`，并把本地 `backend/` 挂载进容器。

题库原始参考仓库不进入镜像。题库 seed 文件由本地命令生成到 `data/seed/`；生产/打包镜像可以包含该目录，用于启动前执行一次性 seed 导入。由于 seed 文件包含完整题面，打包后的镜像默认面向本地或私有环境，不应直接公开分发。

### frontend

文件：[infra/docker/frontend.Dockerfile](../../infra/docker/frontend.Dockerfile)

职责：

- dev 阶段运行 Vite dev server。
- build 阶段构建 `frontend/dist`。
- runtime 阶段用 Nginx 托管静态文件。

生产 runtime 使用：[infra/docker/nginx.conf](../../infra/docker/nginx.conf)

Nginx 行为：

- `/api/` 代理到 `backend:8000/api/`。
- `/health` 代理到后端 `/health`。
- 其他路径使用 SPA fallback 到 `index.html`。

### code-runner

文件：[infra/docker/code-runner.Dockerfile](../../infra/docker/code-runner.Dockerfile)

职责：

- 提供后续用户 Python 代码执行环境。
- 当前基座只验证最小执行能力。

安全限制在 Compose 中声明：

- `network_mode: none`
- `read_only: true`
- `no-new-privileges`
- `cap_drop: ALL`
- `mem_limit: 256m`
- `cpus: 0.5`
- `/tmp` 使用 tmpfs

## Compose 文件

### 开发环境

文件：[infra/compose/docker-compose.dev.yml](../../infra/compose/docker-compose.dev.yml)

服务：

- `postgres`
- `backend`
- `frontend`
- `code-runner`

默认端口：

- 后端：`8000`
- 前端：`5173`
- PostgreSQL 宿主机端口：`15432`

启动：

```bash
make up
```

停止：

```bash
make down
```

开发数据库 volume：

- `learning-coach-dev_postgres_data`

前端依赖 volume：

- `learning-coach-dev_frontend_node_modules`

前端容器使用独立 volume 保存 `node_modules`，避免与宿主机或其他 WSL 前端项目互相影响。开发环境启动 frontend 服务时会先执行 `CI=true pnpm install --frozen-lockfile`，再启动 Vite dev server；这样当 `package.json` 或 `pnpm-lock.yaml` 变化时，容器内的依赖 volume 会以非交互方式同步，避免 pnpm 在无 TTY 容器中等待清理确认。

### 测试环境

文件：[infra/compose/docker-compose.test.yml](../../infra/compose/docker-compose.test.yml)

服务：

- `postgres`
- `backend-test`

数据库使用 tmpfs，不保留测试数据。

测试命令：

```bash
docker compose -f infra/compose/docker-compose.test.yml run --rm backend-test
```

### 生产/打包环境

文件：[infra/compose/docker-compose.prod.yml](../../infra/compose/docker-compose.prod.yml)

服务：

- `postgres`
- `backend`
- `frontend`
- `code-runner`

前端默认暴露端口：

- `8080`

启动示例：

```bash
docker compose -f infra/compose/docker-compose.prod.yml up -d --build
```

## 环境变量

参考 [.env.example](../../.env.example)。

常用变量：

- `BACKEND_PORT`
- `FRONTEND_PORT`
- `FRONTEND_HTTP_PORT`
- `POSTGRES_HOST_PORT`
- `DATABASE_URL`
- `DOCKER_DATABASE_URL`
- `CREDENTIAL_ENCRYPTION_KEY`
- `RAG_EMBEDDING_API_KEY`
- `RAG_EMBEDDING_BASE_URL`
- `RAG_EMBEDDING_MODEL`
- `RAG_EMBEDDING_DIMENSIONS`
- `DATABASE_BACKUP_MAX_BYTES`
- `PROBLEM_SEED_PATH`
- `SEED_PROBLEMS_ON_STARTUP`

本机直接运行后端时，数据库地址应指向 `localhost:15432`。容器内后端运行时，数据库地址应指向 `postgres:5432`。

`CREDENTIAL_ENCRYPTION_KEY` 是后端加密用户 OpenAI API key 的 Fernet key。开发和生产 compose 会从宿主机环境或 `.env` 传入该变量；为空时，登录注册可用，但 API 资产创建、覆盖更新和测试连接会失败。测试 compose 使用固定测试 key，避免在临时测试环境中依赖开发者本机密钥。

`RAG_EMBEDDING_*` 变量用于本地 RAG 语料导入时调用 OpenAI-compatible embedding provider。开发、测试和生产 compose 都会透传这些变量；未配置 `RAG_EMBEDDING_API_KEY` 时，RAG CLI 会跳过 embedding 生成，仅导入 manifest、doc 和 chunk metadata。

`DATABASE_BACKUP_MAX_BYTES` 控制 `/api/database-backups/restore` 接受的上传文件大小上限，默认 256MB。备份恢复文件不加密，恢复会覆盖当前全库数据；生产或共享环境应谨慎暴露该页面。

默认推荐使用显式 seed 命令，而不是后端启动时隐式导入：

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
- PostgreSQL 中存在 `vector` extension
- 前端根页面包含 React root
- code-runner 能输出 `42`

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
