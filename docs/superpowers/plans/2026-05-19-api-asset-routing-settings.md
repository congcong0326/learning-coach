# API Asset Routing Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn API settings into a table-driven asset manager and add sticky LLM credential routing with preferred asset fallback after 3 consecutive failures.

**Architecture:** Extend `llm_credential` with enable/preferred/active/failure tracking fields, then route all future LLM credential selection through a focused service API. Preserve the existing `/default` behavior as compatibility while adding `/preferred`. Replace the current always-visible frontend form with an Ant Design table and create/edit modal.

**Tech Stack:** Python 3.12, uv, FastAPI, SQLAlchemy async, Alembic, pytest, Vite, React, TypeScript, Ant Design, TanStack Query, Vitest.

---

## Source Documents

- Spec: `docs/superpowers/specs/2026-05-19-api-asset-routing-settings-design.md`
- Base T0 spec: `docs/superpowers/specs/2026-05-19-local-auth-api-asset-design.md`
- Project progress: `docs/project-todolist.md`
- Architecture: `docs/architecture/foundation.md`
- Makefile contract: `docs/architecture/makefile.md`

## Execution Notes

- The repository may already contain uncommitted T0 implementation files. Do not revert user changes or unrelated files such as `AGENTS.md`.
- When committing, stage only the files listed in the task being completed.
- Use TDD: each behavior change starts with a failing test, then minimal implementation.
- Keep the old `is_default` response field for compatibility. New code treats `is_default` as an alias of `is_preferred`.

## File Structure

Create:

- `backend/app/db/migrations/versions/20260519_0004_llm_credential_routing.py` - add routing fields to `llm_credential`.
- `backend/tests/test_llm_credential_routing.py` - unit-style service tests for sticky selection and failure accounting.

Modify:

- `backend/app/models/auth.py` - add `is_enabled`, `is_preferred`, `is_active`, `failure_count`, `last_used_at`.
- `backend/app/schemas/llm_credential.py` - add request/response fields and preferred endpoint response compatibility.
- `backend/app/services/auth_service.py` - read preferred/default credential for `/api/auth/me`.
- `backend/app/services/llm_credential_service.py` - implement preferred/default compatibility, enable/disable, sticky routing, success/failure recording.
- `backend/app/api/llm_credentials.py` - add `/preferred`, use renamed service methods.
- `backend/tests/test_auth_api.py` - model shape includes new columns.
- `backend/tests/test_llm_credentials_api.py` - API tests for enabled/preferred/default compatibility.
- `frontend/src/api/llmCredentials.ts` - add new fields and `setPreferredLlmCredential`.
- `frontend/src/pages/ApiKeySettingsPage.tsx` - replace permanent form with table and modal.
- `frontend/src/pages/ApiKeySettingsPage.test.tsx` - table/modal/preferred/enabled tests.
- `frontend/src/styles/app.css` - table page and modal layout adjustments.
- `docs/architecture/foundation.md` - describe sticky API asset routing.
- `docs/project-todolist.md` - note T0 enhancement status and validation commands.

---

### Task 1: Database Model And Migration

**Files:**
- Modify: `backend/app/models/auth.py`
- Modify: `backend/tests/test_auth_api.py`
- Create: `backend/app/db/migrations/versions/20260519_0004_llm_credential_routing.py`

- [ ] **Step 1: Write failing model shape test**

Add the new column expectations to `backend/tests/test_auth_api.py::test_auth_models_expose_required_columns`:

```python
    assert {
        "is_enabled",
        "is_preferred",
        "is_active",
        "failure_count",
        "last_used_at",
    } <= set(LlmCredential.__table__.columns.keys())
```

- [ ] **Step 2: Run model shape test to verify failure**

Run:

```bash
uv run pytest backend/tests/test_auth_api.py::test_auth_models_expose_required_columns -q
```

Expected: FAIL because `is_enabled`, `is_preferred`, `is_active`, `failure_count`, and `last_used_at` do not exist on `LlmCredential`.

- [ ] **Step 3: Add model fields**

Update `backend/app/models/auth.py` inside `class LlmCredential` after `is_default`:

```python
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    is_preferred: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    failure_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
```

Add `Integer` to the `sqlalchemy` import list in `backend/app/models/auth.py`.

Add indexes to `__table_args__`:

```python
        Index("ix_llm_credential_user_preferred", "user_id", "is_preferred"),
        Index("ix_llm_credential_user_active", "user_id", "is_active"),
        Index("ix_llm_credential_user_enabled", "user_id", "is_enabled"),
```

- [ ] **Step 4: Add Alembic migration**

Create `backend/app/db/migrations/versions/20260519_0004_llm_credential_routing.py`:

```python
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260519_0004"
down_revision = "20260519_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_credential",
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "llm_credential",
        sa.Column("is_preferred", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "llm_credential",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "llm_credential",
        sa.Column("failure_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "llm_credential",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE llm_credential SET is_preferred = is_default")
    op.create_index(
        "ix_llm_credential_user_preferred",
        "llm_credential",
        ["user_id", "is_preferred"],
    )
    op.create_index(
        "ix_llm_credential_user_active",
        "llm_credential",
        ["user_id", "is_active"],
    )
    op.create_index(
        "ix_llm_credential_user_enabled",
        "llm_credential",
        ["user_id", "is_enabled"],
    )


def downgrade() -> None:
    op.drop_index("ix_llm_credential_user_enabled", table_name="llm_credential")
    op.drop_index("ix_llm_credential_user_active", table_name="llm_credential")
    op.drop_index("ix_llm_credential_user_preferred", table_name="llm_credential")
    op.drop_column("llm_credential", "last_used_at")
    op.drop_column("llm_credential", "failure_count")
    op.drop_column("llm_credential", "is_active")
    op.drop_column("llm_credential", "is_preferred")
    op.drop_column("llm_credential", "is_enabled")
```

- [ ] **Step 5: Run model shape test**

Run:

```bash
uv run pytest backend/tests/test_auth_api.py::test_auth_models_expose_required_columns -q
```

Expected: PASS.

- [ ] **Step 6: Commit database model and migration**

Run:

```bash
git add backend/app/models/auth.py backend/tests/test_auth_api.py backend/app/db/migrations/versions/20260519_0004_llm_credential_routing.py
git commit -m "feat: add llm credential routing fields"
```

---

### Task 2: Backend Routing Service

**Files:**
- Create: `backend/tests/test_llm_credential_routing.py`
- Modify: `backend/app/services/llm_credential_service.py`

- [ ] **Step 1: Write failing sticky selection tests**

Create `backend/tests/test_llm_credential_routing.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.core.config import settings
from backend.app.models.auth import AppUser, LlmCredential
from backend.app.services.llm_credential_service import (
    LLM_CREDENTIAL_FAILURE_THRESHOLD,
    LlmCredentialError,
    record_llm_credential_failure,
    record_llm_credential_success,
    select_llm_credential_for_user,
)


@pytest_asyncio.fixture
async def routing_session_factory(monkeypatch):
    monkeypatch.setattr(settings, "credential_encryption_key", Fernet.generate_key().decode())
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(AppUser.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def create_user_and_credentials(session):
    user = AppUser(
        username="alice",
        email="alice@example.com",
        password_hash="hash",
        display_name="alice",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    first = LlmCredential(
        user_id=user.id,
        provider="openai",
        display_name="primary",
        base_url="https://api.openai.com/v1",
        api_mode="responses",
        model_name="gpt-4.1-mini",
        api_key_ciphertext="cipher-1",
        api_key_mask="sk-...1111",
        is_default=True,
        is_enabled=True,
        is_preferred=True,
        is_active=True,
        failure_count=0,
        status="valid",
        last_error="",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_used_at=datetime.now(UTC),
    )
    second = LlmCredential(
        user_id=user.id,
        provider="openai",
        display_name="backup",
        base_url="https://api.openai.com/v1",
        api_mode="responses",
        model_name="gpt-4.1",
        api_key_ciphertext="cipher-2",
        api_key_mask="sk-...2222",
        is_default=False,
        is_enabled=True,
        is_preferred=False,
        is_active=False,
        failure_count=0,
        status="valid",
        last_error="",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_used_at=datetime.now(UTC) - timedelta(hours=1),
    )
    session.add_all([first, second])
    await session.commit()
    await session.refresh(user)
    await session.refresh(first)
    await session.refresh(second)
    return user, first, second


@pytest.mark.asyncio
async def test_select_keeps_active_credential_until_failure_threshold(routing_session_factory):
    async with routing_session_factory() as session:
        user, first, _second = await create_user_and_credentials(session)

        selected = await select_llm_credential_for_user(session, user)

        assert selected.id == first.id


@pytest.mark.asyncio
async def test_select_switches_after_active_reaches_failure_threshold(routing_session_factory):
    async with routing_session_factory() as session:
        user, first, second = await create_user_and_credentials(session)
        first.failure_count = LLM_CREDENTIAL_FAILURE_THRESHOLD
        first.is_active = False
        await session.commit()

        selected = await select_llm_credential_for_user(session, user)

        assert selected.id == second.id
        assert selected.is_active is True


@pytest.mark.asyncio
async def test_disabled_credentials_are_not_selected(routing_session_factory):
    async with routing_session_factory() as session:
        user, first, second = await create_user_and_credentials(session)
        first.is_enabled = False
        first.is_active = False
        second.is_enabled = False
        await session.commit()

        with pytest.raises(LlmCredentialError, match="llm_credential_unavailable"):
            await select_llm_credential_for_user(session, user)


@pytest.mark.asyncio
async def test_success_clears_failure_count(routing_session_factory):
    async with routing_session_factory() as session:
        _user, first, _second = await create_user_and_credentials(session)
        first.failure_count = 2
        first.status = "invalid"
        first.last_error = "timeout"
        await session.commit()

        updated = await record_llm_credential_success(session, first)

        assert updated.failure_count == 0
        assert updated.status == "valid"
        assert updated.last_error == ""
        assert updated.last_used_at is not None


@pytest.mark.asyncio
async def test_failure_increments_count_and_clears_active_at_threshold(routing_session_factory):
    async with routing_session_factory() as session:
        _user, first, _second = await create_user_and_credentials(session)
        first.failure_count = LLM_CREDENTIAL_FAILURE_THRESHOLD - 1
        first.is_active = True
        await session.commit()

        updated = await record_llm_credential_failure(session, first, "rate_limit")

        assert updated.failure_count == LLM_CREDENTIAL_FAILURE_THRESHOLD
        assert updated.status == "invalid"
        assert updated.last_error == "rate_limit"
        assert updated.is_active is False
```

- [ ] **Step 2: Run routing tests to verify failure**

Run:

```bash
uv run pytest backend/tests/test_llm_credential_routing.py -q
```

Expected: FAIL with import errors for `LLM_CREDENTIAL_FAILURE_THRESHOLD`, `select_llm_credential_for_user`, `record_llm_credential_success`, or `record_llm_credential_failure`.

- [ ] **Step 3: Implement routing helpers**

Add to `backend/app/services/llm_credential_service.py`:

```python
LLM_CREDENTIAL_FAILURE_THRESHOLD = 3


async def _clear_active(db: AsyncSession, user: AppUser) -> None:
    await db.execute(
        update(LlmCredential)
        .where(LlmCredential.user_id == user.id)
        .values(is_active=False)
    )


async def select_llm_credential_for_user(
    db: AsyncSession,
    user: AppUser,
) -> LlmCredential:
    active_result = await db.execute(
        select(LlmCredential).where(
            LlmCredential.user_id == user.id,
            LlmCredential.is_active.is_(True),
            LlmCredential.is_enabled.is_(True),
            LlmCredential.failure_count < LLM_CREDENTIAL_FAILURE_THRESHOLD,
        )
    )
    active = active_result.scalar_one_or_none()
    if active is not None:
        return active

    preferred_result = await db.execute(
        select(LlmCredential).where(
            LlmCredential.user_id == user.id,
            LlmCredential.is_preferred.is_(True),
            LlmCredential.is_enabled.is_(True),
            LlmCredential.failure_count < LLM_CREDENTIAL_FAILURE_THRESHOLD,
        )
    )
    selected = preferred_result.scalar_one_or_none()
    if selected is None:
        fallback_result = await db.execute(
            select(LlmCredential)
            .where(
                LlmCredential.user_id == user.id,
                LlmCredential.is_enabled.is_(True),
                LlmCredential.failure_count < LLM_CREDENTIAL_FAILURE_THRESHOLD,
            )
            .order_by(
                LlmCredential.status.desc(),
                LlmCredential.last_used_at.asc().nullsfirst(),
                LlmCredential.id.asc(),
            )
        )
        selected = fallback_result.scalars().first()
    if selected is None:
        raise LlmCredentialError("llm_credential_unavailable")

    await _clear_active(db, user)
    selected.is_active = True
    selected.last_used_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(selected)
    return selected


async def record_llm_credential_success(
    db: AsyncSession,
    credential: LlmCredential,
) -> LlmCredential:
    credential.failure_count = 0
    credential.status = "valid"
    credential.last_error = ""
    credential.last_used_at = datetime.now(UTC)
    credential.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(credential)
    return credential


async def record_llm_credential_failure(
    db: AsyncSession,
    credential: LlmCredential,
    error_summary: str,
) -> LlmCredential:
    credential.failure_count += 1
    credential.status = "invalid"
    credential.last_error = error_summary[:500]
    credential.last_used_at = datetime.now(UTC)
    credential.updated_at = datetime.now(UTC)
    if credential.failure_count >= LLM_CREDENTIAL_FAILURE_THRESHOLD:
        credential.is_active = False
    await db.commit()
    await db.refresh(credential)
    return credential
```

- [ ] **Step 4: Run routing tests**

Run:

```bash
uv run pytest backend/tests/test_llm_credential_routing.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit routing service**

Run:

```bash
git add backend/tests/test_llm_credential_routing.py backend/app/services/llm_credential_service.py
git commit -m "feat: add sticky llm credential routing"
```

---

### Task 3: Backend API And Compatibility

**Files:**
- Modify: `backend/app/schemas/llm_credential.py`
- Modify: `backend/app/services/llm_credential_service.py`
- Modify: `backend/app/services/auth_service.py`
- Modify: `backend/app/api/llm_credentials.py`
- Modify: `backend/tests/test_llm_credentials_api.py`

- [ ] **Step 1: Add failing API tests**

Append to `backend/tests/test_llm_credentials_api.py`:

```python
def test_create_list_and_update_enabled_preferred_fields(
    credential_client: TestClient,
) -> None:
    created = credential_client.post(
        "/api/me/llm-credentials",
        json={
            "display_name": "个人 OpenAI key",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_mode": "responses",
            "model_name": "gpt-4.1-mini",
            "api_key": "sk-test-secret-abcd",
            "is_enabled": True,
            "is_preferred": True,
        },
    )
    assert created.status_code == 200
    assert created.json()["is_enabled"] is True
    assert created.json()["is_preferred"] is True
    assert created.json()["is_default"] is True
    assert created.json()["failure_count"] == 0

    updated = credential_client.patch(
        f"/api/me/llm-credentials/{created.json()['id']}",
        json={"is_enabled": False},
    )
    assert updated.status_code == 200
    assert updated.json()["is_enabled"] is False


def test_preferred_endpoint_replaces_default_semantics(
    credential_client: TestClient,
) -> None:
    first = credential_client.post(
        "/api/me/llm-credentials",
        json={
            "display_name": "first",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_mode": "responses",
            "model_name": "gpt-4.1-mini",
            "api_key": "sk-first-secret-abcd",
            "is_enabled": True,
            "is_preferred": True,
        },
    ).json()
    second = credential_client.post(
        "/api/me/llm-credentials",
        json={
            "display_name": "second",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_mode": "responses",
            "model_name": "gpt-4.1",
            "api_key": "sk-second-secret-wxyz",
            "is_enabled": True,
            "is_preferred": False,
        },
    ).json()

    response = credential_client.post(
        f"/api/me/llm-credentials/{second['id']}/preferred"
    )
    listed = credential_client.get("/api/me/llm-credentials").json()["items"]

    assert response.status_code == 200
    preferred = {item["id"]: item["is_preferred"] for item in listed}
    defaults = {item["id"]: item["is_default"] for item in listed}
    assert preferred[first["id"]] is False
    assert preferred[second["id"]] is True
    assert defaults[first["id"]] is False
    assert defaults[second["id"]] is True
```

- [ ] **Step 2: Run API tests to verify failure**

Run:

```bash
uv run pytest backend/tests/test_llm_credentials_api.py::test_create_list_and_update_enabled_preferred_fields backend/tests/test_llm_credentials_api.py::test_preferred_endpoint_replaces_default_semantics -q
```

Expected: FAIL because request/response schemas and `/preferred` route do not exist.

- [ ] **Step 3: Update schemas**

Modify `backend/app/schemas/llm_credential.py`:

```python
class LlmCredentialCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    provider: Provider = "openai"
    base_url: str = Field(min_length=8, max_length=500)
    api_mode: ApiMode = "responses"
    model_name: str = Field(min_length=1, max_length=120)
    api_key: str = Field(min_length=1, max_length=500)
    is_default: bool = False
    is_enabled: bool = True
    is_preferred: bool = False
```

```python
class LlmCredentialUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: str | None = Field(default=None, min_length=8, max_length=500)
    api_mode: ApiMode | None = None
    model_name: str | None = Field(default=None, min_length=1, max_length=120)
    api_key: str | None = Field(default=None, min_length=1, max_length=500)
    is_enabled: bool | None = None
```

```python
class LlmCredentialResponse(BaseModel):
    id: int
    provider: str
    display_name: str
    base_url: str
    api_mode: str
    model_name: str
    api_key_mask: str
    is_default: bool
    is_enabled: bool
    is_preferred: bool
    is_active: bool
    failure_count: int
    status: str
    last_used_at: datetime | None
    last_tested_at: datetime | None
    last_error: str
```

- [ ] **Step 4: Update service payload and preferred/default logic**

In `backend/app/services/llm_credential_service.py`, update `credential_payload`:

```python
def credential_payload(credential: LlmCredential) -> dict:
    return {
        "id": credential.id,
        "provider": credential.provider,
        "display_name": credential.display_name,
        "base_url": credential.base_url,
        "api_mode": credential.api_mode,
        "model_name": credential.model_name,
        "api_key_mask": credential.api_key_mask,
        "is_default": credential.is_preferred,
        "is_enabled": credential.is_enabled,
        "is_preferred": credential.is_preferred,
        "is_active": credential.is_active,
        "failure_count": credential.failure_count,
        "status": credential.status,
        "last_used_at": credential.last_used_at,
        "last_tested_at": credential.last_tested_at,
        "last_error": credential.last_error,
    }
```

Add helper:

```python
async def _clear_preferred(db: AsyncSession, user: AppUser) -> None:
    await db.execute(
        update(LlmCredential)
        .where(LlmCredential.user_id == user.id)
        .values(is_preferred=False, is_default=False)
    )
```

Update `create_credential` preferred handling:

```python
    existing_credentials = await list_credentials(db, user)
    should_prefer = payload.is_preferred or payload.is_default or not existing_credentials
    if should_prefer:
        await _clear_preferred(db, user)
        await _clear_active(db, user)
```

Set new fields when constructing `LlmCredential`:

```python
        is_default=should_prefer,
        is_enabled=payload.is_enabled,
        is_preferred=should_prefer,
        is_active=should_prefer and payload.is_enabled,
        failure_count=0,
```

Update `update_credential`:

```python
    if payload.is_enabled is not None:
        credential.is_enabled = payload.is_enabled
        if not payload.is_enabled:
            credential.is_active = False
    if payload.api_key is not None:
        credential.api_key_ciphertext = encrypt_api_key(
            payload.api_key,
            settings.credential_encryption_key,
        )
        credential.api_key_mask = mask_api_key(payload.api_key)
        credential.status = "untested"
        credential.failure_count = 0
        credential.last_error = ""
```

Replace `set_default_credential` body with alias behavior:

```python
async def set_preferred_credential(
    db: AsyncSession,
    user: AppUser,
    credential_id: int,
) -> LlmCredential:
    credential = await get_credential(db, user, credential_id)
    await _clear_preferred(db, user)
    if credential.is_enabled and credential.failure_count < LLM_CREDENTIAL_FAILURE_THRESHOLD:
        await _clear_active(db, user)
        credential.is_active = True
    credential.is_default = True
    credential.is_preferred = True
    credential.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(credential)
    return credential


async def set_default_credential(
    db: AsyncSession,
    user: AppUser,
    credential_id: int,
) -> LlmCredential:
    return await set_preferred_credential(db, user, credential_id)
```

- [ ] **Step 5: Update auth default check**

In `backend/app/services/auth_service.py::has_default_llm_credential`, update the query:

```python
        select(LlmCredential.id).where(
            LlmCredential.user_id == user.id,
            LlmCredential.is_preferred.is_(True),
            LlmCredential.is_enabled.is_(True),
        )
```

- [ ] **Step 6: Add preferred API route**

In `backend/app/api/llm_credentials.py`, import `set_preferred_credential` and add route before `/test`:

```python
@router.post("/{credential_id}/preferred", response_model=LlmCredentialResponse)
async def make_preferred(
    credential_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        credential = await set_preferred_credential(session, user, credential_id)
    except LlmCredentialError as exc:
        raise _credential_not_found(exc) from exc
    return credential_payload(credential)
```

- [ ] **Step 7: Run API tests**

Run:

```bash
uv run pytest backend/tests/test_llm_credentials_api.py backend/tests/test_auth_api.py backend/tests/test_llm_credential_routing.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit backend API changes**

Run:

```bash
git add backend/app/schemas/llm_credential.py backend/app/services/llm_credential_service.py backend/app/services/auth_service.py backend/app/api/llm_credentials.py backend/tests/test_llm_credentials_api.py
git commit -m "feat: expose preferred api asset controls"
```

---

### Task 4: Frontend API Client

**Files:**
- Modify: `frontend/src/api/llmCredentials.ts`
- Modify: `frontend/src/pages/ApiKeySettingsPage.test.tsx`

- [ ] **Step 1: Update failing test expectations for preferred endpoint**

In `frontend/src/pages/ApiKeySettingsPage.test.tsx`, replace the previous default URL expectation:

```typescript
await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
  '/api/me/llm-credentials/7/preferred',
  expect.objectContaining({ method: 'POST', credentials: 'include' }),
))
```

Expected: this will fail before `setPreferredLlmCredential` exists and the page uses it.

- [ ] **Step 2: Run focused frontend test to verify failure**

Run:

```bash
cd frontend && corepack pnpm test -- ApiKeySettingsPage.test.tsx
```

Expected: FAIL because frontend still calls `/default`.

- [ ] **Step 3: Update frontend credential types and client**

Modify `frontend/src/api/llmCredentials.ts`:

```typescript
export type LlmCredential = {
  id: number
  provider: 'openai'
  display_name: string
  base_url: string
  api_mode: 'responses'
  model_name: string
  api_key_mask: string
  is_default: boolean
  is_enabled: boolean
  is_preferred: boolean
  is_active: boolean
  failure_count: number
  status: LlmCredentialStatus
  last_used_at: string | null
  last_tested_at: string | null
  last_error: string
}
```

```typescript
export type LlmCredentialPayload = {
  display_name: string
  provider: 'openai'
  base_url: string
  api_mode: 'responses'
  model_name: string
  api_key: string
  is_enabled: boolean
  is_preferred: boolean
}
```

```typescript
export type LlmCredentialUpdatePayload = {
  display_name?: string
  base_url?: string
  api_mode?: 'responses'
  model_name?: string
  api_key?: string
  is_enabled?: boolean
}
```

Add:

```typescript
export function setPreferredLlmCredential(id: number): Promise<LlmCredential> {
  return requestJson<LlmCredential>(`/api/me/llm-credentials/${id}/preferred`, {
    method: 'POST',
  })
}
```

Keep `setDefaultLlmCredential` for compatibility:

```typescript
export function setDefaultLlmCredential(id: number): Promise<LlmCredential> {
  return requestJson<LlmCredential>(`/api/me/llm-credentials/${id}/default`, {
    method: 'POST',
  })
}
```

- [ ] **Step 4: Run focused test**

Run:

```bash
cd frontend && corepack pnpm test -- ApiKeySettingsPage.test.tsx
```

Expected: FAIL still, because the page has not been refactored to use the new client and table/modal UI.

---

### Task 5: Frontend Table And Modal Settings Page

**Files:**
- Modify: `frontend/src/pages/ApiKeySettingsPage.tsx`
- Modify: `frontend/src/pages/ApiKeySettingsPage.test.tsx`
- Modify: `frontend/src/styles/app.css`

- [ ] **Step 1: Replace page tests with table/modal behavior**

Replace `frontend/src/pages/ApiKeySettingsPage.test.tsx` with:

```typescript
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiKeySettingsPage } from './ApiKeySettingsPage'

const savedCredential = {
  id: 7,
  provider: 'openai',
  display_name: '个人 OpenAI key',
  base_url: 'https://api.openai.com/v1',
  api_mode: 'responses',
  model_name: 'gpt-4.1-mini',
  api_key_mask: 'sk-...abcd',
  is_default: true,
  is_enabled: true,
  is_preferred: true,
  is_active: true,
  failure_count: 0,
  status: 'valid',
  last_used_at: null,
  last_tested_at: null,
  last_error: '',
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ApiKeySettingsPage />
    </QueryClientProvider>,
  )
}

function okJson(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('ApiKeySettingsPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders api assets as a table with routing state', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => okJson({ items: [savedCredential] })),
    )

    renderPage()

    expect(await screen.findByText('个人 OpenAI key')).toBeInTheDocument()
    expect(screen.getByText('模型')).toBeInTheDocument()
    expect(screen.getByText('Base URL')).toBeInTheDocument()
    expect(screen.getByText('API key')).toBeInTheDocument()
    expect(screen.getByText('连续失败')).toBeInTheDocument()
    expect(screen.getByText('gpt-4.1-mini')).toBeInTheDocument()
    expect(screen.getByText('sk-...abcd')).toBeInTheDocument()
    expect(screen.getByText('首选')).toBeInTheDocument()
    expect(screen.getByText('当前通讯中')).toBeInTheDocument()
    expect(screen.getByText('0')).toBeInTheDocument()
  })

  it('opens create modal and submits a new enabled preferred asset', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/me/llm-credentials' && init?.method === 'POST') {
        return okJson({ ...savedCredential, id: 8, display_name: '备用 key' })
      }
      return okJson({ items: [savedCredential] })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: '新增 API 资产' }))
    fireEvent.change(screen.getByLabelText('名称'), {
      target: { value: '备用 key' },
    })
    fireEvent.change(screen.getByLabelText('模型名称'), {
      target: { value: 'gpt-4.1-mini' },
    })
    fireEvent.change(screen.getByLabelText('API key'), {
      target: { value: 'sk-live-secret' },
    })
    fireEvent.click(screen.getByLabelText('设为首选资产'))
    fireEvent.click(screen.getByRole('button', { name: '创建' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/me/llm-credentials',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify({
          display_name: '备用 key',
          provider: 'openai',
          base_url: 'https://api.openai.com/v1',
          api_mode: 'responses',
          model_name: 'gpt-4.1-mini',
          api_key: 'sk-live-secret',
          is_enabled: true,
          is_preferred: true,
        }),
      }),
    ))
  })

  it('opens edit modal and omits empty api key overwrite', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/me/llm-credentials/7' && init?.method === 'PATCH') {
        return okJson({ ...savedCredential, model_name: 'gpt-4.1' })
      }
      return okJson({ items: [savedCredential] })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    expect(await screen.findByText('个人 OpenAI key')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '编辑' }))
    fireEvent.change(screen.getByLabelText('模型名称'), {
      target: { value: 'gpt-4.1' },
    })
    fireEvent.click(screen.getByRole('button', { name: '更新' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/me/llm-credentials/7',
      expect.objectContaining({
        method: 'PATCH',
        credentials: 'include',
        body: JSON.stringify({
          display_name: '个人 OpenAI key',
          base_url: 'https://api.openai.com/v1',
          api_mode: 'responses',
          model_name: 'gpt-4.1',
          is_enabled: true,
        }),
      }),
    ))
  })

  it('toggles enabled and sets preferred asset', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/me/llm-credentials/7' && init?.method === 'PATCH') {
        return okJson({ ...savedCredential, is_enabled: false })
      }
      if (url === '/api/me/llm-credentials/7/preferred') {
        return okJson({ ...savedCredential, is_preferred: true })
      }
      return okJson({ items: [{ ...savedCredential, is_preferred: false }] })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    expect(await screen.findByText('个人 OpenAI key')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('个人 OpenAI key 启用'))
    fireEvent.click(screen.getByRole('button', { name: '设为首选' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/me/llm-credentials/7',
      expect.objectContaining({
        method: 'PATCH',
        credentials: 'include',
        body: JSON.stringify({ is_enabled: false }),
      }),
    ))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/me/llm-credentials/7/preferred',
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    ))
  })
})
```

- [ ] **Step 2: Run frontend tests to verify failure**

Run:

```bash
cd frontend && corepack pnpm test -- ApiKeySettingsPage.test.tsx
```

Expected: FAIL because current page renders a permanent form, not a table/modal.

- [ ] **Step 3: Refactor `ApiKeySettingsPage.tsx` to table/modal**

Use these key imports:

```typescript
import {
  Alert,
  Button,
  Checkbox,
  Form,
  Input,
  Modal,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
```

Use state:

```typescript
const [form] = Form.useForm<LlmCredentialPayload>()
const [modalOpen, setModalOpen] = useState(false)
const [editingCredential, setEditingCredential] = useState<LlmCredential | null>(null)
```

Use initial values:

```typescript
const initialValues: LlmCredentialPayload = {
  display_name: '',
  provider: 'openai',
  base_url: 'https://api.openai.com/v1',
  api_mode: 'responses',
  model_name: '',
  api_key: '',
  is_enabled: true,
  is_preferred: false,
}
```

Use modal open helpers:

```typescript
function openCreateModal() {
  setEditingCredential(null)
  form.setFieldsValue(initialValues)
  setModalOpen(true)
}

function openEditModal(credential: LlmCredential) {
  setEditingCredential(credential)
  form.setFieldsValue({
    display_name: credential.display_name,
    provider: 'openai',
    base_url: credential.base_url,
    api_mode: 'responses',
    model_name: credential.model_name,
    api_key: '',
    is_enabled: credential.is_enabled,
    is_preferred: credential.is_preferred,
  })
  setModalOpen(true)
}

function closeModal() {
  setModalOpen(false)
  setEditingCredential(null)
  form.resetFields()
}
```

Use submit logic:

```typescript
function submitCredential(values: LlmCredentialPayload) {
  if (!editingCredential) {
    createMutation.mutate(values)
    return
  }

  const updatePayload: LlmCredentialUpdatePayload = {
    display_name: values.display_name,
    base_url: values.base_url,
    api_mode: values.api_mode,
    model_name: values.model_name,
    is_enabled: values.is_enabled,
  }
  if (values.api_key) {
    updatePayload.api_key = values.api_key
  }
  updateMutation.mutate({
    id: editingCredential.id,
    payload: updatePayload,
  })
}
```

Use enabled mutation:

```typescript
const toggleEnabledMutation = useMutation({
  mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
    updateLlmCredential(id, { is_enabled: enabled }),
  onSuccess: refreshCredentials,
})
```

Use preferred mutation:

```typescript
const preferredMutation = useMutation({
  mutationFn: setPreferredLlmCredential,
  onSuccess: refreshCredentials,
})
```

Use table columns:

```typescript
const columns: ColumnsType<LlmCredential> = [
  { title: '名称', dataIndex: 'display_name' },
  { title: '模型', dataIndex: 'model_name' },
  { title: 'Base URL', dataIndex: 'base_url' },
  { title: 'API key', dataIndex: 'api_key_mask' },
  {
    title: '启用',
    key: 'enabled',
    render: (_, row) => (
      <Switch
        checked={row.is_enabled}
        aria-label={`${row.display_name} 启用`}
        onChange={(checked) =>
          toggleEnabledMutation.mutate({ id: row.id, enabled: checked })
        }
      />
    ),
  },
  {
    title: '状态',
    dataIndex: 'status',
    render: (status: LlmCredential['status']) => (
      <Tag color={statusColor(status)}>{statusLabel(status)}</Tag>
    ),
  },
  { title: '连续失败', dataIndex: 'failure_count' },
  {
    title: '标记',
    key: 'marks',
    render: (_, row) => (
      <Space wrap>
        {row.is_preferred ? <Tag color="blue">首选</Tag> : null}
        {row.is_active ? <Tag color="green">当前通讯中</Tag> : null}
      </Space>
    ),
  },
  {
    title: '操作',
    key: 'actions',
    render: (_, row) => (
      <Space wrap>
        <Button onClick={() => testMutation.mutate(row.id)}>测试连接</Button>
        <Button
          disabled={row.is_preferred}
          onClick={() => preferredMutation.mutate(row.id)}
        >
          设为首选
        </Button>
        <Button aria-label="编辑" onClick={() => openEditModal(row)}>
          编辑
        </Button>
        <Button danger aria-label="删除" onClick={() => deleteMutation.mutate(row.id)}>
          删除
        </Button>
      </Space>
    ),
  },
]
```

Render page with top action and modal:

```tsx
<section className="page-section settings-page">
  <div className="page-heading">
    <Typography.Title level={2}>API 设置</Typography.Title>
    <Button type="primary" onClick={openCreateModal}>
      新增 API 资产
    </Button>
  </div>
  <Table
    rowKey="id"
    columns={columns}
    dataSource={credentials}
    loading={credentialsQuery.isLoading}
    pagination={false}
  />
  <Modal
    title={editingCredential ? '编辑 API 资产' : '新增 API 资产'}
    open={modalOpen}
    okText={editingCredential ? '更新' : '创建'}
    cancelText="取消"
    onCancel={closeModal}
    onOk={() => form.submit()}
    confirmLoading={submitMutation.isPending}
  >
    <Form<LlmCredentialPayload>
      form={form}
      layout="vertical"
      requiredMark={false}
      onFinish={submitCredential}
    >
      <Form.Item
        label="名称"
        name="display_name"
        rules={[{ required: true, message: '请输入名称' }]}
      >
        <Input />
      </Form.Item>
      <Form.Item label="Provider" name="provider">
        <Input disabled />
      </Form.Item>
      <Form.Item
        label="Base URL"
        name="base_url"
        rules={[{ required: true, message: '请输入 Base URL' }]}
      >
        <Input />
      </Form.Item>
      <Form.Item label="API Mode" name="api_mode">
        <Input disabled />
      </Form.Item>
      <Form.Item
        label="模型名称"
        name="model_name"
        rules={[{ required: true, message: '请输入模型名称' }]}
      >
        <Input />
      </Form.Item>
      <Form.Item
        label="API key"
        name="api_key"
        rules={
          editingCredential
            ? []
            : [{ required: true, message: '请输入 API key' }]
        }
      >
        <Input.Password autoComplete="off" />
      </Form.Item>
      <Form.Item name="is_enabled" valuePropName="checked">
        <Checkbox>启用资产</Checkbox>
      </Form.Item>
      {!editingCredential ? (
        <Form.Item name="is_preferred" valuePropName="checked">
          <Checkbox>设为首选资产</Checkbox>
        </Form.Item>
      ) : null}
    </Form>
  </Modal>
</section>
```

- [ ] **Step 4: Update CSS for table page**

Add to `frontend/src/styles/app.css`:

```css
.settings-page .ant-table {
  border: 1px solid #deded8;
  border-radius: 8px;
  background: #ffffff;
}

.settings-page .ant-table-cell {
  vertical-align: middle;
}

.settings-page .ant-modal .ant-form-item:last-child {
  margin-bottom: 0;
}
```

- [ ] **Step 5: Run focused frontend tests**

Run:

```bash
cd frontend && corepack pnpm test -- ApiKeySettingsPage.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Run all frontend tests**

Run:

```bash
cd frontend && corepack pnpm test
```

Expected: PASS.

- [ ] **Step 7: Commit frontend settings page**

Run:

```bash
git add frontend/src/api/llmCredentials.ts frontend/src/pages/ApiKeySettingsPage.tsx frontend/src/pages/ApiKeySettingsPage.test.tsx frontend/src/styles/app.css
git commit -m "feat: improve api asset settings table"
```

---

### Task 6: Documentation And Verification

**Files:**
- Modify: `docs/architecture/foundation.md`
- Modify: `docs/project-todolist.md`
- Inspect and modify only if stale: `docs/index.md`

- [ ] **Step 1: Update architecture documentation**

In `docs/architecture/foundation.md`, update the local auth/API asset section with:

```markdown
用户级 OpenAI API 资产支持启用/禁用、首选资产和当前通讯资产。后端 LLM 调用不直接读取单个默认资产，而是通过统一选择服务使用粘性策略：优先保持当前通讯资产；当连续失败达到 3 次后，切换到其他启用且可用的资产。API key 仍然只保存 Fernet 密文，前端只展示 mask。
```

- [ ] **Step 2: Update progress documentation**

In `docs/project-todolist.md`, add T0 enhancement completion note:

```markdown
- [x] API 设置页列表化，新增/编辑使用弹窗。
- [x] API 资产支持启用/禁用、首选资产和连续失败切换策略。
```

- [ ] **Step 3: Check index impact**

Read `docs/index.md`. If it already says API assets live in `backend/app/services/` and frontend pages include API settings, no update is required. If it still says only “默认资产”，replace it with “用户级 API 资产和粘性路由策略”。

- [ ] **Step 4: Run backend focused tests**

Run:

```bash
uv run pytest backend/tests/test_auth_api.py backend/tests/test_llm_credentials_api.py backend/tests/test_llm_credential_routing.py backend/tests/test_credential_crypto.py -q
```

Expected: PASS.

- [ ] **Step 5: Run frontend focused tests**

Run:

```bash
cd frontend && corepack pnpm test -- ApiKeySettingsPage.test.tsx App.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Run full build**

Run:

```bash
make build
```

Expected: PASS. Vite may print a chunk size warning; this warning is acceptable if the command exits 0.

- [ ] **Step 7: Commit documentation and verification notes**

Run:

```bash
git add docs/architecture/foundation.md docs/project-todolist.md docs/index.md
git commit -m "docs: document api asset routing behavior"
```

If `docs/index.md` had no changes, omit it from `git add`.

---

## Final Verification Checklist

- [ ] `uv run pytest backend/tests/test_auth_api.py backend/tests/test_llm_credentials_api.py backend/tests/test_llm_credential_routing.py backend/tests/test_credential_crypto.py -q`
- [ ] `cd frontend && corepack pnpm test -- ApiKeySettingsPage.test.tsx App.test.tsx`
- [ ] `make build`
- [ ] `git status --short` reviewed so unrelated user changes are not included in commits.
