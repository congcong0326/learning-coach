# Makefile 命令契约

本文档说明根目录 [Makefile](../../Makefile) 中每个目标的职责、执行内容和成功标准。

## 总体原则

- 所有命令都从仓库根目录执行。
- Python 命令通过 `uv run` 执行。
- 前端命令通过 `corepack pnpm` 执行，避免依赖全局 pnpm。
- Docker 命令默认使用 `infra/compose/docker-compose.dev.yml`。

## 命令列表

### `make help`

显示可用命令和说明。

成功标准：

- 输出包含 `bootstrap install lint test build docker-build up down logs db-migrate prepare-problem-seed db-seed smoke package clean`。

### `make bootstrap`

检查本地工具。

检查项：

- `uv`
- `node`
- `corepack`
- `corepack pnpm`
- `docker`
- `docker compose`

成功标准：

- 输出 `Bootstrap checks passed`。

### `make install`

安装后端和前端依赖。

执行内容：

```bash
uv sync
cd frontend && corepack pnpm install
```

成功标准：

- Python 虚拟环境可用。
- 前端 `node_modules` 可用。
- 依赖锁文件与配置一致。

### `make lint`

执行静态检查。

执行内容：

```bash
uv run ruff check .
uv run mypy backend
cd frontend && corepack pnpm lint
```

成功标准：

- Ruff 无错误。
- Mypy 无错误。
- ESLint 无错误。

### `make test`

执行后端和前端测试。

执行内容：

```bash
uv run pytest -q
cd frontend && corepack pnpm test
```

成功标准：

- 后端 pytest 通过。
- 前端 Vitest 通过。

### `make build`

执行完整本地构建校验。

执行内容：

```bash
uv run ruff check .
uv run mypy backend
uv run pytest -q
cd frontend && corepack pnpm lint
cd frontend && corepack pnpm test
cd frontend && corepack pnpm build
```

成功标准：

- 后端 lint、类型检查、测试通过。
- 前端 lint、测试、生产构建通过。
- 前端生成 `frontend/dist`。

说明：

- 当前 Vite 构建可能出现 chunk size warning。这是警告，不代表构建失败。

### `make docker-build`

构建开发环境 Docker 镜像。

执行内容：

```bash
docker compose -f infra/compose/docker-compose.dev.yml build
```

成功标准：

- backend、frontend、code-runner 镜像构建成功。

### `make up`

启动开发环境。

执行内容：

```bash
docker compose -f infra/compose/docker-compose.dev.yml up --build -d
```

成功标准：

- `postgres` healthy。
- `backend` started。
- `frontend` started。
- `code-runner` started。

### `make down`

停止开发环境。

执行内容：

```bash
docker compose -f infra/compose/docker-compose.dev.yml down
```

成功标准：

- 开发容器和网络被移除。
- 数据库 volume 保留。

### `make logs`

跟随开发环境日志。

执行内容：

```bash
docker compose -f infra/compose/docker-compose.dev.yml logs -f
```

### `make db-migrate`

在后端容器内执行 Alembic migration。

执行内容：

```bash
docker compose -f infra/compose/docker-compose.dev.yml exec backend uv run --no-sync alembic upgrade head
```

成功标准：

- Alembic 升级到 head。
- 当前 head 为 `20260519_0002`。

### `make prepare-problem-seed`

从本地忽略目录 `data/sources/leetcode-problemset` 读取参考仓库，生成结构化 seed 文件。

执行内容：

```bash
uv run python scripts/prepare_problem_seed.py --source data/sources/leetcode-problemset --output data/seed
```

成功标准：

- 原始参考仓库存在。
- `data/seed/problems.jsonl` 生成成功。
- `data/seed/problem_categories.jsonl` 和 `data/seed/problem_category_items.jsonl` 生成成功。
- 生成的题目 seed 不包含题解内容。

### `make db-seed`

从 `data/seed/` 导入题库基础数据。

执行内容：

```bash
uv run python -m backend.app.cli.problem_seed
```

成功标准：

- 数据库已完成 migration。
- seed 文件存在。
- `problem` 表写入题目基础数据。
- 重复执行不会产生重复题目。

### `make smoke`

对运行中的开发环境执行 smoke test。

执行内容：

```bash
COMPOSE_FILE=infra/compose/docker-compose.dev.yml ./scripts/smoke_all.sh
```

检查项：

- 后端 `/health`。
- 后端 `/api/health`。
- 后端 `/api/db/health`。
- PostgreSQL `vector` extension。
- 前端根页面。
- code-runner 最小 Python 执行。

成功标准：

- 输出 `All smoke checks passed`。

### `make package`

构建生产/打包 compose 中定义的镜像。

执行内容：

```bash
docker compose -f infra/compose/docker-compose.prod.yml build
```

成功标准：

- `backend` 镜像构建成功。
- `frontend` runtime 镜像构建成功，并包含 Nginx 静态文件服务配置。
- `code-runner` 镜像构建成功。

### `make clean`

清理本地构建和缓存产物。

执行内容：

```bash
rm -rf frontend/dist
rm -rf .pytest_cache .ruff_cache .mypy_cache
find backend tests demo -type d -name __pycache__ -prune -exec rm -rf {} +
```

成功标准：

- 常见本地缓存和前端构建产物被清理。

## 推荐工作流

首次启动：

```bash
make bootstrap
make install
make up
make db-migrate
make smoke
```

日常开发前：

```bash
make up
```

提交前：

```bash
make build
```

结束开发：

```bash
make down
```
