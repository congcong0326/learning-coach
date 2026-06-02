# Database Backup Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a UI-driven full PostgreSQL database backup and restore feature.

**Architecture:** The frontend only triggers HTTP download/upload operations. The backend owns all database access and shells out to PostgreSQL client tools with a single-operation lock and explicit error mapping.

**Tech Stack:** FastAPI, SQLAlchemy async session/auth boundary, PostgreSQL `pg_dump`/`pg_restore`, Vite React, Ant Design, TanStack Query, Vitest, pytest.

---

### Task 1: Backend API And Service

**Files:**
- Create: `backend/app/api/database_backups.py`
- Create: `backend/app/services/database_backup_service.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_database_backup_api.py`
- Test: `backend/tests/test_database_backup_service.py`

- [x] Add tests for auth, export download, restore upload, upload size limit, invalid file mapping, busy operation mapping, command shape and URL conversion.
- [x] Register `/api/database-backups/export` and `/api/database-backups/restore`.
- [x] Implement `pg_dump -Fc` export and `pg_restore` validation/restore.
- [x] Add `DATABASE_BACKUP_MAX_BYTES` config with 256MB default.
- [x] Verify with `uv run pytest -q backend/tests/test_database_backup_api.py backend/tests/test_database_backup_service.py`.

### Task 2: Docker Support

**Files:**
- Modify: `infra/docker/backend.Dockerfile`
- Test: `backend/tests/test_docker_compose_config.py`

- [x] Add a test asserting the backend image installs `postgresql-client`.
- [x] Install `postgresql-client` in the backend runtime image.
- [x] Verify with `uv run pytest -q backend/tests/test_docker_compose_config.py`.

### Task 3: Frontend Page

**Files:**
- Create: `frontend/src/api/databaseBackups.ts`
- Create: `frontend/src/pages/BackupRestorePage.tsx`
- Create: `frontend/src/pages/BackupRestorePage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/routes/AppRoutes.tsx`
- Modify: `frontend/src/routes/ProtectedRoute.tsx`
- Modify: `frontend/src/styles/app.css`
- Test: `frontend/src/App.test.tsx`

- [x] Add page tests for rendering, export action and restore confirmation.
- [x] Add app shell tests for nav link and route access without default API asset.
- [x] Implement download/upload API client, page UI, route, navigation and access exception.
- [x] Verify with `corepack pnpm exec vitest run src/pages/BackupRestorePage.test.tsx src/App.test.tsx`.

### Task 4: Documentation And Verification

**Files:**
- Modify: `docs/index.md`
- Modify: `docs/architecture/foundation.md`
- Modify: `docs/architecture/docker.md`
- Modify: `docs/dev-setup.md`
- Create: `docs/superpowers/specs/2026-06-02-database-backup-restore-design.md`
- Create: `docs/superpowers/plans/2026-06-02-database-backup-restore.md`

- [x] Document API/service/page ownership, Docker dependency, local usage and restore risks.
- [x] Run final backend and frontend verification commands.
