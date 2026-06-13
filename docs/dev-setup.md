# 开发环境设置

本文档说明题库与本地登录极简版在 WSL Ubuntu 下的本地开发方式。

## 前置条件

- WSL Ubuntu。
- Docker Desktop 或 Docker Engine，使用 Linux containers。
- `uv`，用于 Python 版本、虚拟环境、依赖和命令管理。
- Node.js LTS 或当前可用的 Node.js 运行时。
- Corepack。前端通过 `corepack pnpm` 使用项目声明的 pnpm 版本。

## 首次检查

在仓库根目录运行：

```bash
make bootstrap
```

该命令检查：

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

该命令执行：

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
- `make smoke`：检查后端、数据库和前端。
- `make down`：停止并移除开发容器和网络，保留开发数据库 volume。

如果本地数据库曾运行旧版 AI 教练迁移，`make db-migrate` 可能因旧 Alembic 版本号找不到而失败。当前极简版只需要题库和登录表；确认开发数据可丢弃后，重建开发数据库 volume 可得到干净 schema。

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

执行后，前端题库页会从后端 `GET /api/problems` 读取数据库题目静态数据。

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

当前 `.env` 不应提交到 Git。常用变量：

- `APP_ENV`
- `BACKEND_PORT`
- `FRONTEND_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST_PORT`
- `DATABASE_URL`
- `DOCKER_DATABASE_URL`

本机直接运行后端时，数据库地址应指向 `localhost:15432`。容器内后端运行时，数据库地址应指向 `postgres:5432`。

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

### Vite 代理域名被拒绝

开发环境的 Vite dev server 保留 host 校验。当前已允许通过本地代理域名 `my-leetcode.com` 访问前端容器；如果代理软件使用新的自定义域名，需要同步更新 `frontend/vite.config.ts` 的 `server.allowedHosts`。

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

## 当前建议验证

本轮精简后的文档和基座建议至少验证：

```bash
uv run pytest -q
cd frontend && corepack pnpm test
uv run ruff check .
uv run mypy backend
cd frontend && corepack pnpm lint
cd frontend && corepack pnpm build
docker compose -f infra/compose/docker-compose.dev.yml config
```
