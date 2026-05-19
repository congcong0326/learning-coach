# Project Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable WSL-ready project foundation for the Agentic Coding Learning Coach web application.

**Architecture:** Use a FastAPI backend managed by uv, a Vite React TypeScript SPA managed by pnpm, PostgreSQL with pgvector for business and vector data, and Docker Compose for local development, test, and packaged runtime. All common workflows are exposed through a root Makefile and verified with smoke tests.

**Tech Stack:** Python 3.12, uv, FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL 16, pgvector, Vite, React, TypeScript, Ant Design, React Router, TanStack Query, Monaco Editor, pnpm, Docker Compose, Nginx, pytest, ruff, mypy.

---

## Execution Rules

- Do not change product behavior beyond foundation health and skeleton screens.
- Do not modify existing demo code unless a verification command proves it blocks the foundation.
- Do not commit user changes already present in `docs/prd/prd.md`, `docs/prd/rag-materials.md`, or `archive/`.
- Use `uv` for Python dependencies and commands.
- Use `pnpm` for frontend dependencies and commands.
- Keep Docker, Makefile, and script commands runnable from WSL Ubuntu at `/root/code/py/learning-coach`.

## Task 1: Repository Foundation Layout

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/db/__init__.py`
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/agents/__init__.py`
- Create: `backend/app/rag/__init__.py`
- Create: `backend/app/tools/__init__.py`
- Create: `backend/tests/__init__.py`
- Create: `infra/docker/.gitkeep`
- Create: `infra/compose/.gitkeep`
- Create: `scripts/.gitkeep`

- [ ] **Step 1: Create empty package and infrastructure directories**

Create the directories and marker files listed above.

- [ ] **Step 2: Verify repository shape**

Run: `find backend infra scripts -maxdepth 3 -type d | sort`

Expected: output includes `backend/app/api`, `backend/app/core`, `backend/app/db`, `infra/docker`, `infra/compose`, and `scripts`.

- [ ] **Step 3: Commit**

```bash
git add backend infra scripts
git commit -m "chore: add project foundation layout"
```

## Task 2: Backend Dependencies And Health API

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `backend/app/core/config.py`
- Create: `backend/app/api/health.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Add backend runtime dependencies**

Run:

```bash
uv add fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" asyncpg alembic pydantic-settings
```

Expected: `pyproject.toml` and `uv.lock` include the new runtime dependencies.

- [ ] **Step 2: Add backend test dependency**

Run:

```bash
uv add --dev httpx pytest-asyncio
```

Expected: `pyproject.toml` and `uv.lock` include `httpx` and `pytest-asyncio` in the dev dependency group.

- [ ] **Step 3: Write failing health tests**

Create `backend/tests/test_health.py` with tests for `GET /health` and `GET /api/health`. The expected response body is:

```json
{"status":"ok","service":"learning-coach-backend"}
```

Run: `uv run pytest backend/tests/test_health.py -q`

Expected: FAIL because the routes are not implemented yet.

- [ ] **Step 4: Implement settings**

Create `backend/app/core/config.py` with a Pydantic settings class containing:

- `app_name`: default `learning-coach-backend`
- `environment`: default `local`
- `api_prefix`: default `/api`
- `database_url`: default `postgresql+asyncpg://learning_coach:learning_coach@localhost:5432/learning_coach`

- [ ] **Step 5: Implement health routes**

Create `backend/app/api/health.py` with:

- `router = APIRouter()`
- `GET /health` returning the status JSON above.

Update `backend/app/main.py` to create the FastAPI app, mount `/health`, and include the same health router under `/api`.

- [ ] **Step 6: Verify backend health tests**

Run: `uv run pytest backend/tests/test_health.py -q`

Expected: tests pass.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock backend
git commit -m "feat: add FastAPI health foundation"
```

## Task 3: Database And Alembic Foundation

**Files:**
- Create: `alembic.ini`
- Create: `backend/app/db/session.py`
- Create: `backend/app/db/health.py`
- Create: `backend/app/db/migrations/env.py`
- Create: `backend/app/db/migrations/script.py.mako`
- Create: `backend/app/db/migrations/versions/20260519_0001_foundation.py`
- Create: `backend/app/api/db_health.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_db_health.py`

- [ ] **Step 1: Create SQLAlchemy async session module**

Create `backend/app/db/session.py` with an async engine built from `settings.database_url` and an async session factory.

- [ ] **Step 2: Create database health helper**

Create `backend/app/db/health.py` with `check_database()` that executes `select 1` and returns `True` on success.

- [ ] **Step 3: Add Alembic configuration**

Create Alembic files under `backend/app/db/migrations`. Set `script_location = backend/app/db/migrations` in `alembic.ini`.

- [ ] **Step 4: Add first migration**

Create migration `20260519_0001_foundation.py` that:

- enables extension `vector`
- creates table `app_metadata`
- creates table `agent_trace`
- creates table `retrieval_trace`

- [ ] **Step 5: Add DB health API**

Create `GET /api/db/health` returning:

```json
{"status":"ok","database":"reachable"}
```

When the database check fails, return HTTP 503 with:

```json
{"detail":"database_unreachable"}
```

- [ ] **Step 6: Write tests**

Create `backend/tests/test_db_health.py` with one test that monkeypatches the database checker to return success and one test that monkeypatches it to return failure.

- [ ] **Step 7: Verify tests**

Run: `uv run pytest backend/tests/test_db_health.py -q`

Expected: tests pass.

- [ ] **Step 8: Commit**

```bash
git add alembic.ini backend/app backend/tests
git commit -m "feat: add database migration foundation"
```

## Task 4: Frontend Vite Foundation

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/pnpm-lock.yaml`
- Create: `frontend/index.html`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/routes/AppRoutes.tsx`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/health.ts`
- Create: `frontend/src/pages/ProblemLibraryPage.tsx`
- Create: `frontend/src/pages/WorkspacePage.tsx`
- Create: `frontend/src/pages/ReviewPage.tsx`
- Create: `frontend/src/pages/TracePage.tsx`
- Create: `frontend/src/styles/app.css`

- [ ] **Step 1: Initialize Vite React TypeScript app**

Run:

```bash
pnpm create vite frontend --template react-ts
```

Expected: Vite creates the frontend project files.

- [ ] **Step 2: Add frontend dependencies**

Run:

```bash
cd frontend
pnpm add antd @ant-design/icons react-router-dom @tanstack/react-query @monaco-editor/react
pnpm add -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

Expected: `frontend/package.json` and `frontend/pnpm-lock.yaml` include the dependencies.

- [ ] **Step 3: Configure Vite API proxy**

Update `frontend/vite.config.ts` so `/api` proxies to `http://localhost:8000`.

- [ ] **Step 4: Build application shell**

Create an Ant Design layout with routes:

- `/problems`
- `/workspace`
- `/review`
- `/trace`
- `/`

The root route redirects to `/problems`.

- [ ] **Step 5: Add API health query**

Create a typed API client that fetches `/api/health`. Render health status in the shell using TanStack Query.

- [ ] **Step 6: Verify frontend build**

Run:

```bash
cd frontend
pnpm lint
pnpm build
```

Expected: lint and build pass, and production output is written to `frontend/dist`.

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "feat: add Vite React frontend foundation"
```

## Task 5: Docker Development Environment

**Files:**
- Create: `.env.example`
- Create: `.dockerignore`
- Create: `infra/docker/backend.Dockerfile`
- Create: `infra/docker/frontend.Dockerfile`
- Create: `infra/docker/code-runner.Dockerfile`
- Create: `infra/compose/docker-compose.dev.yml`
- Create: `scripts/wait_for_db.sh`

- [ ] **Step 1: Add environment example**

Create `.env.example` with:

```dotenv
APP_ENV=local
BACKEND_PORT=8000
FRONTEND_PORT=5173
POSTGRES_DB=learning_coach
POSTGRES_USER=learning_coach
POSTGRES_PASSWORD=learning_coach
DATABASE_URL=postgresql+asyncpg://learning_coach:learning_coach@postgres:5432/learning_coach
OPENAI_API_KEY=
```

- [ ] **Step 2: Add backend Dockerfile**

Create a backend image based on Python 3.12 slim, install uv, copy `pyproject.toml` and `uv.lock`, install dependencies through uv, and run:

```bash
uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 3: Add frontend Dockerfile**

Create a multi-stage Dockerfile that builds `frontend/dist` with pnpm and serves it with Nginx.

- [ ] **Step 4: Add code-runner Dockerfile**

Create a Python 3.12 slim image with a non-root user and no project source mounted by default.

- [ ] **Step 5: Add development compose**

Create `docker-compose.dev.yml` with services:

- `postgres`, using a pgvector-enabled PostgreSQL image
- `backend`, exposing port 8000
- `frontend`, exposing port 5173
- `code-runner`, internal only

- [ ] **Step 6: Verify compose config**

Run:

```bash
docker compose -f infra/compose/docker-compose.dev.yml config
```

Expected: compose renders a valid configuration.

- [ ] **Step 7: Commit**

```bash
git add .env.example .dockerignore infra scripts/wait_for_db.sh
git commit -m "feat: add Docker development foundation"
```

## Task 6: Makefile Command Contract

**Files:**
- Create: `Makefile`
- Create: `scripts/smoke_backend.sh`
- Create: `scripts/smoke_frontend.sh`
- Create: `scripts/smoke_code_runner.sh`
- Create: `scripts/smoke_all.sh`

- [ ] **Step 1: Add Makefile help target**

Create `make help` that lists:

```text
bootstrap install lint test build docker-build up down logs db-migrate db-seed smoke package clean
```

- [ ] **Step 2: Add local commands**

Implement:

- `make bootstrap`: check `uv`, `node`, `pnpm`, `docker`, and `docker compose`
- `make install`: run `uv sync` and `cd frontend && pnpm install`
- `make lint`: run `uv run ruff check .`, `uv run mypy backend`, and `cd frontend && pnpm lint`
- `make test`: run `uv run pytest -q` and `cd frontend && pnpm test -- --run`
- `make build`: run backend checks and `cd frontend && pnpm build`

- [ ] **Step 3: Add Docker commands**

Implement:

- `make docker-build`
- `make up`
- `make down`
- `make logs`
- `make db-migrate`
- `make smoke`
- `make package`
- `make clean`

- [ ] **Step 4: Add smoke scripts**

Create scripts that verify:

- backend health through `curl`
- frontend reachability through `curl`
- code-runner Python execution through Docker Compose

- [ ] **Step 5: Verify Makefile command discovery**

Run: `make help`

Expected: all command names are listed with short descriptions.

- [ ] **Step 6: Commit**

```bash
git add Makefile scripts
git commit -m "feat: add Makefile orchestration"
```

## Task 7: Test Compose And Packaged Compose

**Files:**
- Create: `infra/compose/docker-compose.test.yml`
- Create: `infra/compose/docker-compose.prod.yml`
- Modify: `infra/docker/frontend.Dockerfile`
- Create: `infra/docker/nginx.conf`

- [ ] **Step 1: Add test compose**

Create `docker-compose.test.yml` with an isolated PostgreSQL volume and backend test command:

```bash
uv run pytest -q
```

- [ ] **Step 2: Add production compose**

Create `docker-compose.prod.yml` with packaged `frontend`, `backend`, `postgres`, and `code-runner` services.

- [ ] **Step 3: Add Nginx config**

Create `infra/docker/nginx.conf` to serve frontend static files and proxy `/api` to `backend:8000`.

- [ ] **Step 4: Verify packaged compose config**

Run:

```bash
docker compose -f infra/compose/docker-compose.prod.yml config
```

Expected: compose renders a valid configuration.

- [ ] **Step 5: Commit**

```bash
git add infra/compose/docker-compose.test.yml infra/compose/docker-compose.prod.yml infra/docker/nginx.conf infra/docker/frontend.Dockerfile
git commit -m "feat: add test and packaged compose files"
```

## Task 8: WSL Smoke Verification

**Files:**
- Modify: `scripts/smoke_all.sh`
- Modify: `Makefile`

- [ ] **Step 1: Start development environment**

Run:

```bash
make up
```

Expected: frontend, backend, postgres, and code-runner services start.

- [ ] **Step 2: Run migrations**

Run:

```bash
make db-migrate
```

Expected: Alembic applies `20260519_0001_foundation.py`.

- [ ] **Step 3: Run smoke tests**

Run:

```bash
make smoke
```

Expected:

- backend health returns success
- frontend returns HTTP 200
- `/api/db/health` returns success
- pgvector extension exists
- code-runner executes a tiny Python snippet

- [ ] **Step 4: Stop services**

Run:

```bash
make down
```

Expected: services stop without removing the development database volume.

- [ ] **Step 5: Commit fixes if needed**

If smoke verification requires changes, commit them:

```bash
git add Makefile scripts infra backend frontend
git commit -m "fix: pass WSL smoke verification"
```

## Task 9: Developer Documentation

**Files:**
- Create: `docs/dev-setup.md`
- Create: `docs/architecture/foundation.md`
- Create: `docs/architecture/docker.md`
- Create: `docs/architecture/makefile.md`

- [ ] **Step 1: Document WSL setup**

Create `docs/dev-setup.md` with prerequisites:

- WSL Ubuntu
- Docker Desktop or Docker Engine with Linux containers
- uv
- Node.js LTS
- pnpm through Corepack

Include daily commands:

```bash
make install
make up
make db-migrate
make smoke
make down
```

- [ ] **Step 2: Document foundation architecture**

Create `docs/architecture/foundation.md` summarizing service boundaries and why Vite SPA, FastAPI, PostgreSQL, pgvector, and Docker Compose were selected.

- [ ] **Step 3: Document Docker design**

Create `docs/architecture/docker.md` describing images, compose files, volumes, ports, and WSL notes.

- [ ] **Step 4: Document Makefile contract**

Create `docs/architecture/makefile.md` listing every target, what it runs, and expected success criteria.

- [ ] **Step 5: Commit**

```bash
git add docs/dev-setup.md docs/architecture
git commit -m "docs: document foundation workflow"
```

## Task 10: Final Verification

**Files:**
- All foundation files from earlier tasks.

- [ ] **Step 1: Run local verification**

Run:

```bash
make bootstrap
make install
make lint
make test
make build
```

Expected: all commands pass.

- [ ] **Step 2: Run Docker verification**

Run:

```bash
make docker-build
make up
make db-migrate
make smoke
make package
make down
```

Expected: all commands pass in WSL Ubuntu.

- [ ] **Step 3: Check git status**

Run:

```bash
git status --short
```

Expected: only intentional foundation files are modified or added. Pre-existing user changes remain untouched.

- [ ] **Step 4: Record verification result**

Append a short verification section to `docs/dev-setup.md` with the exact commands run and the date `2026-05-19`.

- [ ] **Step 5: Commit final verification notes**

```bash
git add docs/dev-setup.md
git commit -m "docs: record foundation verification"
```

## Completion Criteria

The foundation is complete when all of these are true:

- `make help` documents the command contract.
- `make install` installs backend and frontend dependencies.
- `make lint`, `make test`, and `make build` pass.
- `make docker-build` builds backend, frontend, and code-runner images.
- `make up` starts the development stack.
- `make db-migrate` enables pgvector and applies the foundation migration.
- `make smoke` verifies backend, frontend, database, pgvector, and code-runner.
- `make package` verifies packaged Docker runtime.
- The frontend uses Vite, React, TypeScript, Ant Design, React Router, TanStack Query, and Monaco Editor.
- The backend uses FastAPI, uv, SQLAlchemy, Alembic, PostgreSQL, and pgvector.
- No product feature beyond foundation health and skeleton routes is introduced.
