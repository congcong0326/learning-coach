# Makefile 命令契约

本文档说明根目录 `Makefile` 中每个目标的职责、执行内容和成功标准。实际命令以 `Makefile` 为准。

## 总体原则

- 所有命令从仓库根目录执行。
- Python 命令通过 `uv run` 执行。
- 前端命令通过 `corepack pnpm` 执行。
- Docker 命令默认使用 `infra/compose/docker-compose.dev.yml`。
- 如果仓库根目录存在 `.env`，Docker Compose 命令会追加 `--env-file .env`。

## 命令列表

| 目标 | 职责 | 成功标准 |
| --- | --- | --- |
| `make help` | 显示可用命令 | 输出包含当前 Makefile 目标 |
| `make bootstrap` | 检查本地工具 | `uv`、`node`、`corepack pnpm`、`docker`、`docker compose` 可用，并输出 `Bootstrap checks passed` |
| `make install` | 安装后端和前端依赖 | `uv sync` 和 `corepack pnpm install` 成功 |
| `make lint` | 静态检查 | Ruff、mypy、ESLint 通过 |
| `make test` | 后端和前端测试 | pytest、Vitest 通过 |
| `make eval` | 本地 AI Coach 固定样例评估 | Hint Leakage、Diagnosis、Code Review 样例通过 |
| `make build` | 完整本地校验和前端生产构建 | 后端 lint/type/test、前端 lint/test/build 全部通过 |
| `make docker-build` | 构建开发环境 Docker 镜像 | backend、frontend 镜像构建成功 |
| `make up` | 启动开发 Docker 栈 | postgres healthy，backend 和 frontend 启动 |
| `make down` | 停止开发 Docker 栈 | 容器和网络移除，数据库 volume 保留 |
| `make logs` | 跟随开发环境日志 | Docker logs 正常输出 |
| `make db-migrate` | 在后端容器内执行 Alembic migration | 数据库升级到 Alembic head |
| `make prepare-problem-seed` | 从本地忽略题库源生成 seed | `data/seed/*.jsonl` 生成成功 |
| `make db-seed` | 导入题库 seed | `problem` 相关表写入或更新，重复执行不产生重复题 |
| `make smoke` | 对运行中的开发栈执行 smoke test | 输出 `All smoke checks passed` |
| `make package` | 构建生产/打包 compose 镜像 | backend 和 frontend runtime 镜像构建成功 |
| `make clean` | 清理常见本地构建和缓存 | `frontend/dist`、Python 缓存、工具缓存被删除 |

## 关键命令内容

### 安装依赖

```bash
uv sync
cd frontend && corepack pnpm install
```

### 静态检查

```bash
uv run ruff check .
uv run mypy backend
cd frontend && corepack pnpm lint
```

### 测试

```bash
uv run pytest -q
cd frontend && corepack pnpm test
```

### 完整构建校验

```bash
uv run ruff check .
uv run mypy backend
uv run pytest -q
cd frontend && corepack pnpm lint
cd frontend && corepack pnpm test
cd frontend && corepack pnpm build
```

当前 Vite 构建可能出现 chunk size warning。这是警告，不代表构建失败。

### 迁移

```bash
docker compose --env-file .env -f infra/compose/docker-compose.dev.yml exec backend uv run --no-sync alembic upgrade head
```

如果没有 `.env`，Makefile 会省略 `--env-file .env`。

当前 Alembic head 是 `20260522_0007`。

### 题库 seed

```bash
uv run python scripts/prepare_problem_seed.py --source data/sources/leetcode-problemset --output data/seed
uv run python -m backend.app.cli.problem_seed
```

生成的题目 seed 不应包含题解内容，也不应默认提交公开仓库。

## 推荐工作流

首次启动：

```bash
make bootstrap
make install
make up
make db-migrate
make smoke
```

日常开发：

```bash
make up
```

提交前：

```bash
make build
docker compose -f infra/compose/docker-compose.dev.yml config
```

结束开发：

```bash
make down
```
