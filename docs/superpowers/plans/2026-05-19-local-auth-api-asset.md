# Local Auth And API Asset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build local registration/login plus per-user OpenAI API asset management as the T0 foundation for later LLM goal generation.

**Architecture:** Add local user, session, and LLM credential tables behind FastAPI APIs. Store session tokens as HttpOnly cookies, password hashes via PBKDF2, and API keys encrypted with Fernet. The React app protects product routes, adds login/register/settings screens, and uses the current user plus default API asset to decide the next screen.

**Tech Stack:** Python 3.12, uv, FastAPI, SQLAlchemy async, Alembic, cryptography/Fernet, OpenAI SDK, pytest, Vite, React, TypeScript, Ant Design, TanStack Query, Vitest.

**Execution Status:** Completed on 2026-05-19. Implementation also switched password hashing from the early PBKDF2 draft to Argon2id to match the approved spec.

---

## Source Documents

- Spec: `docs/superpowers/specs/2026-05-19-local-auth-api-asset-design.md`
- Project progress: `docs/project-todolist.md`
- Architecture: `docs/architecture/foundation.md`
- Makefile contract: `docs/architecture/makefile.md`
- Dev setup: `docs/dev-setup.md`

## File Structure

Create:

- `backend/app/models/auth.py` - `AppUser`, `AuthSession`, and `LlmCredential` SQLAlchemy models.
- `backend/app/schemas/auth.py` - auth request/response Pydantic schemas.
- `backend/app/schemas/llm_credential.py` - LLM credential request/response schemas.
- `backend/app/services/auth_service.py` - password hash, session token, registration, login, logout, current-user lookup.
- `backend/app/services/credential_crypto.py` - Fernet key loading, API key encrypt/decrypt/mask helpers.
- `backend/app/services/llm_credential_service.py` - credential CRUD, ownership checks, default handling.
- `backend/app/services/openai_connection_service.py` - OpenAI model-list based connection test.
- `backend/app/api/auth.py` - auth routes.
- `backend/app/api/llm_credentials.py` - credential routes.
- `backend/app/db/migrations/versions/20260519_0003_auth_llm_credentials.py` - auth and credential tables.
- `backend/tests/test_auth_api.py` - auth API tests.
- `backend/tests/test_llm_credentials_api.py` - LLM credential API tests.
- `backend/tests/test_credential_crypto.py` - encryption and mask tests.
- `frontend/src/api/auth.ts` - frontend auth API client.
- `frontend/src/api/llmCredentials.ts` - frontend credential API client.
- `frontend/src/pages/LoginPage.tsx` - login page.
- `frontend/src/pages/RegisterPage.tsx` - register page.
- `frontend/src/pages/ApiKeySettingsPage.tsx` - API asset settings page.
- `frontend/src/routes/ProtectedRoute.tsx` - auth guard.
- `frontend/src/routes/AuthRedirect.tsx` - root redirect based on auth/default credential state.
- `frontend/src/pages/LoginPage.test.tsx` - login page tests.
- `frontend/src/pages/RegisterPage.test.tsx` - register page tests.
- `frontend/src/pages/ApiKeySettingsPage.test.tsx` - settings page tests.

Modify:

- `pyproject.toml` / `uv.lock` - add `cryptography`.
- `backend/app/core/config.py` - add credential encryption and cookie settings.
- `backend/app/main.py` - register auth and credential routers.
- `backend/app/models/__init__.py` - import auth models for migration metadata.
- `frontend/src/api/client.ts` - support methods, JSON body, and credentials.
- `frontend/src/App.tsx` - protect app shell routes and add API settings navigation.
- `frontend/src/routes/AppRoutes.tsx` - add auth/settings/root redirect routes.
- `frontend/src/styles/app.css` - ChatGPT-like quiet login/settings/workspace styling.
- `docs/project-todolist.md` - mark T0 complete after implementation.
- `docs/architecture/foundation.md` - document local auth and API asset boundary.
- `docs/dev-setup.md` - document `CREDENTIAL_ENCRYPTION_KEY`.

---

### Task 1: Dependencies And Configuration

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `backend/app/core/config.py`

- [x] **Step 1: Add encryption dependency**

Run:

```bash
uv add cryptography
```

Expected: `pyproject.toml` and `uv.lock` include `cryptography`.

- [x] **Step 2: Add config tests through service tests**

The first concrete failing config behavior is covered in Task 3 by `test_missing_encryption_key_raises_clear_error`, which imports settings-driven crypto helpers before implementation exists.

- [x] **Step 3: Add settings fields**

Update `backend/app/core/config.py` with fields:

```python
credential_encryption_key: str = ""
session_cookie_name: str = "learning_coach_session"
session_ttl_hours: int = 24 * 14
session_cookie_secure: bool = False
```

Expected: importing `settings` still works with no `.env`; crypto write operations fail clearly when the key is empty.

---

### Task 2: Auth Models And Migration

**Files:**
- Create: `backend/app/models/auth.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/db/migrations/versions/20260519_0003_auth_llm_credentials.py`
- Test: `backend/tests/test_auth_api.py`

- [x] **Step 1: Write failing model shape test**

Add to `backend/tests/test_auth_api.py`:

```python
from backend.app.models.auth import AppUser, AuthSession, LlmCredential


def test_auth_models_expose_required_columns() -> None:
    assert {
        "id",
        "username",
        "email",
        "password_hash",
        "display_name",
        "status",
        "created_at",
        "updated_at",
        "last_login_at",
    } <= set(AppUser.__table__.columns.keys())
    assert {
        "id",
        "user_id",
        "session_token_hash",
        "expires_at",
        "revoked_at",
        "created_at",
        "last_seen_at",
    } <= set(AuthSession.__table__.columns.keys())
    assert {
        "id",
        "user_id",
        "provider",
        "display_name",
        "base_url",
        "api_mode",
        "model_name",
        "api_key_ciphertext",
        "api_key_mask",
        "is_default",
        "status",
        "last_tested_at",
        "last_error",
        "created_at",
        "updated_at",
    } <= set(LlmCredential.__table__.columns.keys())
```

- [x] **Step 2: Run model test to verify failure**

Run:

```bash
uv run pytest backend/tests/test_auth_api.py::test_auth_models_expose_required_columns -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.models.auth'`.

- [x] **Step 3: Implement models**

Create `backend/app/models/auth.py` with `AppUser`, `AuthSession`, and `LlmCredential`. Reuse `ID_TYPE` from `backend.app.models.problem`. Use `String`, `Text`, `Boolean`, `DateTime(timezone=True)`, `ForeignKey`, indexes, and unique constraints. Use relationship names:

```python
AppUser.sessions
AppUser.llm_credentials
AuthSession.user
LlmCredential.user
```

Modify `backend/app/models/__init__.py` to import these models.

- [x] **Step 4: Add migration**

Create Alembic migration `20260519_0003_auth_llm_credentials.py` that creates:

```text
app_user
auth_session
llm_credential
```

Use `20260519_0002` as `down_revision`. Add indexes for username/email uniqueness, session token hash uniqueness, user credential lookup, and default credential lookup.

- [x] **Step 5: Run model test**

Run:

```bash
uv run pytest backend/tests/test_auth_api.py::test_auth_models_expose_required_columns -q
```

Expected: PASS.

---

### Task 3: Credential Crypto Service

**Files:**
- Create: `backend/app/services/credential_crypto.py`
- Test: `backend/tests/test_credential_crypto.py`

- [x] **Step 1: Write failing crypto tests**

Create `backend/tests/test_credential_crypto.py`:

```python
import pytest
from cryptography.fernet import Fernet

from backend.app.services.credential_crypto import (
    CredentialEncryptionError,
    decrypt_api_key,
    encrypt_api_key,
    mask_api_key,
)


def test_api_key_round_trip_with_fernet_key() -> None:
    key = Fernet.generate_key().decode()

    ciphertext = encrypt_api_key("sk-test-secret", key)

    assert ciphertext != "sk-test-secret"
    assert decrypt_api_key(ciphertext, key) == "sk-test-secret"


def test_mask_api_key_keeps_prefix_and_suffix_only() -> None:
    assert mask_api_key("sk-abcdefghijklmnopqrstuvwxyz") == "sk-...wxyz"


def test_missing_encryption_key_raises_clear_error() -> None:
    with pytest.raises(CredentialEncryptionError, match="credential_encryption_key_missing"):
        encrypt_api_key("sk-test-secret", "")
```

- [x] **Step 2: Run crypto tests to verify failure**

Run:

```bash
uv run pytest backend/tests/test_credential_crypto.py -q
```

Expected: FAIL with `ModuleNotFoundError`.

- [x] **Step 3: Implement crypto helpers**

Implement `CredentialEncryptionError`, `encrypt_api_key`, `decrypt_api_key`, and `mask_api_key`. Use `Fernet(key.encode())`; convert Fernet errors into `CredentialEncryptionError("credential_decryption_failed")`.

- [x] **Step 4: Run crypto tests**

Run:

```bash
uv run pytest backend/tests/test_credential_crypto.py -q
```

Expected: PASS.

---

### Task 4: Auth Service And API

**Files:**
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/services/auth_service.py`
- Create: `backend/app/api/auth.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auth_api.py`

- [x] **Step 1: Add failing auth API tests**

Extend `backend/tests/test_auth_api.py` with tests using in-memory SQLite and dependency override for `get_session`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.db.session import get_session
from backend.app.main import create_app
from backend.app.models.auth import AppUser, AuthSession, LlmCredential


@pytest.fixture
async def auth_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(AppUser.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def auth_client(auth_session_factory):
    app = create_app()

    async def override_session():
        async with auth_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def test_register_creates_user_and_sets_session_cookie(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/auth/register",
        json={"username": "alice", "email": "alice@example.com", "password": "secret123"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "alice"
    assert "learning_coach_session" in response.cookies
    assert "password_hash" not in response.text


def test_me_requires_login(auth_client: TestClient) -> None:
    response = auth_client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


def test_login_and_logout_session(auth_client: TestClient) -> None:
    auth_client.post(
        "/api/auth/register",
        json={"username": "alice", "email": "alice@example.com", "password": "secret123"},
    )
    logout = auth_client.post("/api/auth/logout")
    login = auth_client.post(
        "/api/auth/login",
        json={"login": "alice", "password": "secret123"},
    )
    me = auth_client.get("/api/auth/me")

    assert logout.status_code == 200
    assert login.status_code == 200
    assert me.status_code == 200
    assert me.json()["username"] == "alice"
```

- [x] **Step 2: Run auth API tests to verify failure**

Run:

```bash
uv run pytest backend/tests/test_auth_api.py -q
```

Expected: FAIL because auth routes and services are missing.

- [x] **Step 3: Implement auth schemas**

Create schemas:

```python
RegisterRequest
LoginRequest
UserResponse
AuthUserEnvelope
CurrentUserResponse
```

Use `EmailStr` only if adding email validation dependency is acceptable; otherwise validate email as a bounded string with `@` in service.

- [x] **Step 4: Implement auth service**

Implement:

```python
hash_password(password: str) -> str
verify_password(password: str, password_hash: str) -> bool
create_session(session: AsyncSession, user: AppUser) -> tuple[AuthSession, str]
get_current_user_from_token(session: AsyncSession, token: str | None) -> AppUser | None
register_user(...)
login_user(...)
logout_token(...)
```

Use `secrets.token_urlsafe(32)` for session token and `hashlib.sha256(token.encode()).hexdigest()` for session token hash. Use `hashlib.pbkdf2_hmac` with per-password salt for password hashes.

- [x] **Step 5: Implement auth routes**

Create routes under `/api/auth`. Set and clear cookie using settings fields. Register router in `backend/app/main.py`.

- [x] **Step 6: Run auth API tests**

Run:

```bash
uv run pytest backend/tests/test_auth_api.py -q
```

Expected: PASS.

---

### Task 5: LLM Credential API

**Files:**
- Create: `backend/app/schemas/llm_credential.py`
- Create: `backend/app/services/llm_credential_service.py`
- Create: `backend/app/services/openai_connection_service.py`
- Create: `backend/app/api/llm_credentials.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_llm_credentials_api.py`

- [x] **Step 1: Write failing credential API tests**

Create tests covering create/list/default/update/test/delete. Use the same in-memory session override pattern as auth tests, register/login first, and monkeypatch OpenAI connection test.

Core assertions:

```python
assert create_response.json()["api_key_mask"] == "sk-...abcd"
assert "sk-test-secret" not in create_response.text
assert list_response.json()["items"][0]["is_default"] is True
assert test_response.json()["status"] == "valid"
```

- [x] **Step 2: Run credential API tests to verify failure**

Run:

```bash
uv run pytest backend/tests/test_llm_credentials_api.py -q
```

Expected: FAIL because credential routes and services are missing.

- [x] **Step 3: Implement credential schemas**

Create:

```python
LlmCredentialCreateRequest
LlmCredentialUpdateRequest
LlmCredentialResponse
LlmCredentialListResponse
LlmCredentialTestResponse
```

Validate provider as `openai`, api mode as `responses`, and base URL beginning with `http://` or `https://`.

- [x] **Step 4: Implement credential service**

Implement owner-scoped operations:

```python
list_credentials(session, user)
create_credential(session, user, request)
update_credential(session, user, credential_id, request)
set_default_credential(session, user, credential_id)
delete_credential(session, user, credential_id)
get_default_credential(session, user)
```

Ensure all queries filter by `user_id`. Ensure setting default clears other defaults for the same user.

- [x] **Step 5: Implement connection service**

Implement `test_openai_credential(credential, decrypted_api_key)` by calling OpenAI model list through the OpenAI SDK or a small HTTP client abstraction. Return normalized statuses:

```text
valid / model_not_found / authentication_failed / connection_failed
```

Tests should monkeypatch this service to avoid network calls.

- [x] **Step 6: Implement credential routes**

Create routes under `/api/me/llm-credentials`. Require current user via auth dependency. Register router in `backend/app/main.py`.

- [x] **Step 7: Run credential API tests**

Run:

```bash
uv run pytest backend/tests/test_llm_credentials_api.py -q
```

Expected: PASS.

---

### Task 6: Frontend Auth Client And Routing

**Files:**
- Create: `frontend/src/api/auth.ts`
- Create: `frontend/src/routes/ProtectedRoute.tsx`
- Create: `frontend/src/routes/AuthRedirect.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/routes/AppRoutes.tsx`
- Test: `frontend/src/App.test.tsx`

- [x] **Step 1: Write failing frontend route tests**

Update `frontend/src/App.test.tsx` so root route redirects unauthenticated users to login and authenticated users without default API asset to settings.

Expected assertions:

```typescript
expect(await screen.findByRole('heading', { name: '登录' })).toBeInTheDocument()
expect(await screen.findByRole('heading', { name: 'API 设置' })).toBeInTheDocument()
```

- [x] **Step 2: Run frontend tests to verify failure**

Run:

```bash
cd frontend && corepack pnpm test -- App.test.tsx
```

Expected: FAIL because auth routes do not exist.

- [x] **Step 3: Update API client**

Modify `requestJson` to accept:

```typescript
method?: string
body?: unknown
```

Always set `credentials: 'include'`. Add `Content-Type: application/json` when a body is present.

- [x] **Step 4: Implement auth API client**

Create functions:

```typescript
getCurrentUser()
registerUser()
loginUser()
logoutUser()
```

- [x] **Step 5: Implement routing guards**

`ProtectedRoute` calls `getCurrentUser` and renders login redirect on 401. `AuthRedirect` sends users to `/login`, `/settings/api-keys`, or `/study-plan` based on auth and `has_default_llm_credential`.

- [x] **Step 6: Update routes and shell**

Add routes `/login`, `/register`, `/settings/api-keys`. Add API 设置 nav item. Keep product pages protected.

- [x] **Step 7: Run frontend route tests**

Run:

```bash
cd frontend && corepack pnpm test -- App.test.tsx
```

Expected: PASS.

---

### Task 7: Frontend Login, Register, And API Settings Pages

**Files:**
- Create: `frontend/src/api/llmCredentials.ts`
- Create: `frontend/src/pages/LoginPage.tsx`
- Create: `frontend/src/pages/RegisterPage.tsx`
- Create: `frontend/src/pages/ApiKeySettingsPage.tsx`
- Create: `frontend/src/pages/LoginPage.test.tsx`
- Create: `frontend/src/pages/RegisterPage.test.tsx`
- Create: `frontend/src/pages/ApiKeySettingsPage.test.tsx`
- Modify: `frontend/src/styles/app.css`

- [x] **Step 1: Write failing page tests**

Tests should verify:

```text
Login page posts login credentials and redirects.
Register page posts registration and redirects to API settings.
API settings page saves a credential, displays only mask, tests connection, and marks default.
```

- [x] **Step 2: Run page tests to verify failure**

Run:

```bash
cd frontend && corepack pnpm test -- LoginPage.test.tsx RegisterPage.test.tsx ApiKeySettingsPage.test.tsx
```

Expected: FAIL because pages do not exist.

- [x] **Step 3: Implement pages**

Use Ant Design `Form`, `Input`, `Button`, `Alert`, `Table`, `Tag`, and `Space`. Keep styling quiet and focused:

```text
auth-page
auth-panel
settings-layout
settings-list
settings-form
```

- [x] **Step 4: Implement credential client**

Create functions:

```typescript
listLlmCredentials()
createLlmCredential()
updateLlmCredential()
setDefaultLlmCredential()
testLlmCredential()
deleteLlmCredential()
```

- [x] **Step 5: Run page tests**

Run:

```bash
cd frontend && corepack pnpm test -- LoginPage.test.tsx RegisterPage.test.tsx ApiKeySettingsPage.test.tsx
```

Expected: PASS.

---

### Task 8: Documentation And Verification

**Files:**
- Modify: `docs/project-todolist.md`
- Modify: `docs/architecture/foundation.md`
- Modify: `docs/dev-setup.md`

- [x] **Step 1: Update documentation**

Update:

```text
docs/project-todolist.md
docs/architecture/foundation.md
docs/dev-setup.md
```

Document auth/API asset modules and `CREDENTIAL_ENCRYPTION_KEY`.

- [x] **Step 2: Run focused backend tests**

Run:

```bash
uv run pytest backend/tests/test_auth_api.py backend/tests/test_llm_credentials_api.py backend/tests/test_credential_crypto.py -q
```

Expected: PASS.

- [x] **Step 3: Run focused frontend tests**

Run:

```bash
cd frontend && corepack pnpm test -- App.test.tsx LoginPage.test.tsx RegisterPage.test.tsx ApiKeySettingsPage.test.tsx
```

Expected: PASS.

- [x] **Step 4: Run full build**

Run:

```bash
make build
```

Expected: PASS.

- [x] **Step 5: Commit**

Commit message:

```bash
git add pyproject.toml uv.lock backend frontend docs
git commit -m "feat: add local auth and API asset management"
```

## Self-Review

- Spec coverage: covers local registration, login, logout, current user, encrypted OpenAI API assets, test connection, default asset, protected routes, ChatGPT-like frontend styling, and docs.
- Placeholder scan: this plan has no placeholder markers.
- Type consistency: backend uses `LlmCredential` model and frontend uses `llmCredentials` client; API paths are consistently `/api/auth/*` and `/api/me/llm-credentials*`.
