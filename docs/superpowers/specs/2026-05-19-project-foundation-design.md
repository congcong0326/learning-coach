# Project Foundation Design

## Goal

Build the project foundation for Agentic Coding Learning Coach before feature development starts. The foundation must make frontend, backend, database, RAG storage, code execution, Docker packaging, Makefile orchestration, and WSL local verification explicit and repeatable.

## Confirmed Decisions

- Frontend: Vite + React + TypeScript.
- Frontend UI: Ant Design.
- Frontend routing: React Router.
- Frontend server-state management: TanStack Query.
- Frontend code editor: Monaco Editor.
- Frontend streaming: Server-Sent Events for AI response streaming.
- Frontend package manager: pnpm.
- Backend: Python 3.12 + FastAPI.
- Python project manager: uv, using the repository root `pyproject.toml`.
- Agent stack: LangChain + LangGraph + OpenAI SDK.
- Business database: PostgreSQL.
- RAG vector storage: PostgreSQL + pgvector.
- ORM and migration: SQLAlchemy 2.x + Alembic.
- Local orchestration: Docker Compose.
- Build and developer entry point: root Makefile.
- User code execution: isolated code-runner container, Python-only for MVP.

## Non-Goals

- Do not introduce Next.js for the first foundation version.
- Do not continue with Create React App for a new frontend.
- Do not introduce Kubernetes, service mesh, or cloud deployment manifests.
- Do not introduce Redis until the project has a concrete queue, cache, or distributed session requirement.
- Do not support Java, C++, or multiple code execution runtimes in the foundation milestone.
- Do not build the full LeetCode product workflow in this foundation milestone.

## Rationale

The previous frontend project at `/root/code/homePorxy/home-proxy/frontend` uses Create React App, React Router, Ant Design, Redux Toolkit, and npm. The useful parts for this project are the SPA mental model, React Router, and Ant Design. The part not worth carrying forward is Create React App, because new React projects should use a more current toolchain.

This product is a logged-in training workspace rather than a public SEO site. The main screens are a problem list, a coding workspace, AI coach chat, code editor, local run results, submission feedback, review summary, and trace/debug panels. These screens are naturally SPA-style and interact heavily with a FastAPI backend. Vite gives a smaller and more direct frontend foundation than Next.js while still keeping a modern build pipeline.

PostgreSQL + pgvector is selected for both business data and vector retrieval to keep the first deployable system simple. The PRD requires problem data, sessions, practice events, code snapshots, retrieval traces, agent traces, user profiles, and RAG chunks. Keeping these in one database reduces local Docker complexity and makes WSL verification easier.

## Target Repository Shape

```text
learning-coach/
  backend/
    __init__.py
    app/
      __init__.py
      main.py
      api/
      agents/
      core/
      db/
      models/
      rag/
      schemas/
      services/
      tools/
    tests/

  frontend/
    index.html
    package.json
    pnpm-lock.yaml
    tsconfig.json
    vite.config.ts
    src/
      App.tsx
      main.tsx
      api/
      components/
      features/
      pages/
      routes/
      styles/

  infra/
    docker/
      backend.Dockerfile
      frontend.Dockerfile
      code-runner.Dockerfile
    compose/
      docker-compose.dev.yml
      docker-compose.test.yml
      docker-compose.prod.yml

  scripts/
    wait_for_db.sh
    smoke_backend.sh
    smoke_frontend.sh
    smoke_code_runner.sh
    smoke_all.sh

  alembic.ini
  Makefile
  .env.example
```

The backend remains part of the root uv project. Backend commands should run as `uv run ...` from the repository root, for example `uv run uvicorn backend.app.main:app --reload`.

## Runtime Architecture

```text
Browser
  -> Vite dev server in development
  -> Nginx frontend container in packaged mode
  -> FastAPI backend through /api
  -> PostgreSQL + pgvector
  -> code-runner container for sandboxed Python execution
```

In development, Vite proxies API requests to FastAPI. In packaged mode, the frontend static files are served by an Nginx container that proxies `/api` to the backend service. The backend owns all direct database access, LLM calls, RAG retrieval, trace recording, and code-runner orchestration.

## Backend Foundation

The backend foundation should expose only minimal infrastructure endpoints at first:

- `GET /health`: process-level health check.
- `GET /api/health`: API health check used by frontend and smoke tests.
- `GET /api/db/health`: database connectivity check.

The backend package should be organized by responsibility:

- `backend.app.main`: FastAPI application factory and router registration.
- `backend.app.core.config`: environment settings loaded from `.env`.
- `backend.app.db.session`: SQLAlchemy engine and session factory.
- `backend.app.db.health`: database health helper.
- `backend.app.api.routes`: route modules.
- `backend.app.models`: SQLAlchemy models.
- `backend.app.schemas`: Pydantic request and response models.
- `backend.app.agents`: LangGraph orchestration code in later milestones.
- `backend.app.rag`: knowledge import, chunking, embedding, and retrieval code in later milestones.
- `backend.app.tools`: code runner and analysis tool clients in later milestones.

## Frontend Foundation

The frontend foundation should create a real application shell rather than a landing page. The first screen should feel like the future product workspace, even before full feature implementation:

- Top navigation with product name and environment indicator.
- Left navigation for Problem Library, Workspace, Review, Trace.
- Main content area with a health/status panel and placeholder routes.
- API health check rendered through TanStack Query.

The frontend should use:

- Vite for dev/build.
- React Router for SPA routing.
- Ant Design for layout and controls.
- TanStack Query for API request state.
- Monaco Editor installed in the foundation, but first used in a later workspace milestone.
- SSE utility prepared for AI streaming in a later coach milestone.

Redux Toolkit should not be introduced in the foundation. It can be added later only if client-only global state becomes complex enough to justify it.

## Database Foundation

The foundation database must enable pgvector and prove that migrations work. The first migration should create:

- `app_metadata`: records schema/application bootstrap values.
- `agent_trace`: minimal trace table for later agent observability.
- `retrieval_trace`: minimal retrieval trace table for later RAG observability.

Full PRD tables such as `problem`, `practice_session`, `practice_event`, `knowledge_doc`, and `knowledge_chunk` belong to product milestones after the foundation is stable.

## Docker Foundation

The foundation should define three Docker images:

- `learning-coach-backend`: FastAPI backend using uv.
- `learning-coach-frontend`: Vite build output served by Nginx.
- `learning-coach-code-runner`: restricted Python execution runtime.

Compose files should be split by purpose:

- `docker-compose.dev.yml`: hot reload for backend and frontend, persistent local database volume.
- `docker-compose.test.yml`: isolated database and test services for CI-like local verification.
- `docker-compose.prod.yml`: packaged frontend, backend, database, and code-runner services.

All services must run in WSL Ubuntu through Docker Desktop or Docker Engine with Linux containers.

## Makefile Contract

The Makefile is the stable entry point for humans and future agents:

```text
make help
make bootstrap
make install
make lint
make test
make build
make docker-build
make up
make down
make logs
make db-migrate
make db-seed
make smoke
make package
make clean
```

`make build` means local build verification: backend checks and frontend production build. `make package` means Docker image build plus packaged compose verification.

## WSL Acceptance Criteria

The foundation is complete only when these commands run successfully from `/root/code/py/learning-coach` in WSL Ubuntu:

```bash
make bootstrap
make install
make lint
make test
make build
make docker-build
make up
make db-migrate
make smoke
make package
make down
```

The smoke test must verify:

- Backend health endpoint returns success.
- Frontend is reachable.
- Backend can connect to PostgreSQL.
- pgvector extension is enabled.
- Code-runner can execute a small Python function.
- Docker Compose service DNS works between containers.
- Restarting services preserves the development database volume.

## Documentation Deliverables

The foundation implementation should update or create:

- `docs/dev-setup.md`: WSL setup, prerequisites, daily commands, troubleshooting.
- `docs/architecture/foundation.md`: architecture and service boundaries.
- `docs/architecture/docker.md`: compose files, images, volumes, ports.
- `docs/architecture/makefile.md`: command contract and expected behavior.

## Risks And Controls

- CRA carry-over risk: avoid `react-scripts`; use Vite from the start.
- Docker-on-WSL path/performance risk: keep source under Linux filesystem, not Windows-mounted paths.
- Database complexity risk: use PostgreSQL + pgvector only, no second vector database in the foundation.
- Sandbox security risk: put user code execution in a separate container from the backend.
- Scope risk: foundation endpoints and screens should prove infrastructure only; product workflows come later.

## Review Gate

After this design is accepted, implementation should proceed through the separate implementation plan at `docs/superpowers/plans/2026-05-19-project-foundation.md`. No code, configuration, Docker, Makefile, or dependency changes should be made before that implementation phase starts.
