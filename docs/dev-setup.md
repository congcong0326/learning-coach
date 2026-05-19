# 开发环境设置

本文档说明 Agentic Coding Learning Coach 在 WSL Ubuntu 下的本地开发方式。

## 前置条件

- WSL Ubuntu。
- Docker Desktop 或 Docker Engine，使用 Linux containers。
- `uv`，用于 Python 版本、虚拟环境、依赖和命令管理。
- Node.js LTS 或当前可用的 Node.js 运行时。
- Corepack。前端通过 `corepack pnpm` 使用项目声明的 pnpm 版本，不依赖全局 `pnpm`。

## 首次检查

在仓库根目录运行：

```bash
make bootstrap
```

该命令会检查：

- `uv`
- `node`
- `corepack`
- `corepack pnpm`
- `docker`
- `docker compose`

## 安装依赖

```bash
make install
```

该命令会执行：

- `uv sync`
- `cd frontend && corepack pnpm install`

Python 依赖写入根目录 `pyproject.toml` 和 `uv.lock`。前端依赖写入 `frontend/package.json` 和 `frontend/pnpm-lock.yaml`。

## 日常开发命令

```bash
make up
make db-migrate
make smoke
make down
```

命令含义：

- `make up`：构建并启动开发 Docker 栈。
- `make db-migrate`：在后端容器内执行 Alembic migration。
- `make smoke`：检查后端、数据库、前端和 code-runner。
- `make down`：停止并移除开发容器和网络，保留开发数据库 volume。

## 题库 seed 数据准备

题库原始参考仓库和生成后的题面 seed 文件默认只用于本地或私有环境，不应提交到公开 Git 仓库。

首次准备题库数据：

```bash
mkdir -p data/sources
git clone https://github.com/fishjar/leetcode-problemset.git data/sources/leetcode-problemset
make prepare-problem-seed
make db-migrate
make db-seed
```

执行后，前端题库页会从后端 `GET /api/problems` 读取数据库中的题目静态数据。

## 本地校验

```bash
make lint
make test
make build
```

`make build` 会串行执行后端 lint、mypy、pytest、前端 lint、前端测试和前端生产构建。

## 端口

默认端口：

- 后端：`8000`
- 前端开发服务：`5173`
- 本机访问 PostgreSQL：`15432`
- 生产 compose 前端入口：`8080`

这些端口可通过 `.env` 或 shell 环境变量覆盖：

```bash
BACKEND_PORT=18000 FRONTEND_PORT=15173 POSTGRES_HOST_PORT=15433 make up
```

## 环境变量

从 `.env.example` 复制本地环境：

```bash
cp .env.example .env
```

当前 `.env` 不应提交到 Git。敏感变量包括：

- `OPENAI_API_KEY`
- `LLM_API_KEY`
- `SERPAPI_API_KEY`

## WSL 注意事项

- 建议把仓库放在 WSL Linux 文件系统内，例如 `/root/code/...`，不要放在 `/mnt/c/...` 下。
- 不要在 WSL 系统级安装 PostgreSQL；项目数据库通过 Docker Compose 提供。
- 前端使用 `corepack pnpm`，避免和其他项目的全局 pnpm/npm 状态互相影响。
- `frontend/node_modules` 和 `frontend/dist` 由前端自己的 `.gitignore` 忽略。

## 常见问题

### `python: command not found`

项目脚本默认使用 `uv run python`。如果需要覆盖，可设置：

```bash
PYTHON_CMD=python3 make smoke
```

### 端口冲突

修改端口环境变量后重新启动：

```bash
POSTGRES_HOST_PORT=15433 BACKEND_PORT=18000 FRONTEND_PORT=15173 make up
```

### 重新构建容器

```bash
make docker-build
make up
```

### 停止服务

```bash
make down
```

该命令不会删除数据库 volume。如果需要清理 volume，应手动确认后使用 Docker 命令处理。

## 2026-05-19 验证记录

本轮在 WSL Ubuntu 环境中完成以下基础流程验证：

- `make bootstrap`：通过，基础命令检查完成。
- `make install`：通过，后端 `uv sync` 和前端 `corepack pnpm install` 完成。
- `make lint`：通过，后端 ruff/mypy 和前端 ESLint 通过。
- `make test`：通过，后端 pytest 和前端 Vitest 通过。
- `make build`：通过，后端 lint/test 和前端生产构建通过；Vite 仅输出 chunk size warning。
- `make docker-build`：通过，开发镜像构建完成。
- `make up`：通过，开发 Docker 栈启动完成。
- `make db-migrate`：通过，Alembic migration 可在后端容器内执行。
- `make smoke`：通过，后端、数据库、前端、code-runner smoke check 通过。
- `make package`：通过，生产 compose 镜像构建完成。
- `make down`：通过，开发容器和网络已停止并移除。

收尾检查：

- `docker ps --format '{{.Names}}' | rg '^learning-coach' || true`：无运行中的 `learning-coach` 容器。
- `docker compose -f infra/compose/docker-compose.dev.yml ps`：无运行中的 dev compose 服务。
