from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import case, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.models.auth import AppUser, LlmCredential
from backend.app.schemas.llm_credential import (
    LlmCredentialCreateRequest,
    LlmCredentialUpdateRequest,
)
from backend.app.services.credential_crypto import encrypt_api_key, mask_api_key


# After this many consecutive failures the sticky router stops using an active
# credential and lets the next selection pick another enabled asset.
LLM_CREDENTIAL_FAILURE_THRESHOLD = 3
logger = logging.getLogger(__name__)


class LlmCredentialError(RuntimeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def credential_payload(credential: LlmCredential) -> dict:
    return {
        "id": credential.id,
        "provider": credential.provider,
        "display_name": credential.display_name,
        "base_url": credential.base_url,
        "api_mode": credential.api_mode,
        "model_name": credential.model_name,
        "api_key_mask": credential.api_key_mask,
        "is_enabled": credential.is_enabled,
        "is_preferred": credential.is_preferred,
        "is_default": credential.is_preferred,
        "is_active": credential.is_active,
        "failure_count": credential.failure_count,
        "status": credential.status,
        "last_tested_at": credential.last_tested_at,
        "last_used_at": credential.last_used_at,
        "last_error": credential.last_error,
    }


async def list_credentials(db: AsyncSession, user: AppUser) -> list[LlmCredential]:
    result = await db.execute(
        select(LlmCredential)
        .where(LlmCredential.user_id == user.id)
        .order_by(LlmCredential.is_preferred.desc(), LlmCredential.created_at)
    )
    return list(result.scalars().all())


async def get_credential(
    db: AsyncSession,
    user: AppUser,
    credential_id: int,
) -> LlmCredential:
    result = await db.execute(
        select(LlmCredential).where(
            LlmCredential.id == credential_id,
            LlmCredential.user_id == user.id,
        )
    )
    credential = result.scalar_one_or_none()
    if credential is None:
        raise LlmCredentialError("llm_credential_not_found")
    return credential


async def _clear_default(db: AsyncSession, user: AppUser) -> None:
    await db.execute(
        update(LlmCredential)
        .where(LlmCredential.user_id == user.id)
        .values(is_default=False, is_preferred=False)
    )


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
    selection_source = "active"
    active_result = await db.execute(
        select(LlmCredential)
        .where(
            LlmCredential.user_id == user.id,
            LlmCredential.is_active.is_(True),
            LlmCredential.is_enabled.is_(True),
            LlmCredential.failure_count < LLM_CREDENTIAL_FAILURE_THRESHOLD,
        )
        .order_by(LlmCredential.id.asc())
    )
    selected = active_result.scalars().first()

    if selected is None:
        selection_source = "preferred"
        preferred_result = await db.execute(
            select(LlmCredential)
            .where(
                LlmCredential.user_id == user.id,
                LlmCredential.is_preferred.is_(True),
                LlmCredential.is_enabled.is_(True),
                LlmCredential.failure_count < LLM_CREDENTIAL_FAILURE_THRESHOLD,
            )
            .order_by(LlmCredential.id.asc())
        )
        selected = preferred_result.scalars().first()

    if selected is None:
        selection_source = "fallback"
        fallback_result = await db.execute(
            select(LlmCredential)
            .where(
                LlmCredential.user_id == user.id,
                LlmCredential.is_enabled.is_(True),
                LlmCredential.failure_count < LLM_CREDENTIAL_FAILURE_THRESHOLD,
            )
            .order_by(
                (LlmCredential.status == "valid").desc(),
                LlmCredential.last_used_at.is_not(None),
                LlmCredential.last_used_at.asc(),
                LlmCredential.id.asc(),
            )
        )
        selected = fallback_result.scalars().first()

    if selected is None:
        logger.warning(
            "llm credential selection failed user_id=%s reason=unavailable", user.id
        )
        raise LlmCredentialError("llm_credential_unavailable")

    await _clear_active(db, user)
    selected.is_active = True
    selected.last_used_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(selected)
    logger.info(
        "llm credential selected user_id=%s credential_id=%s source=%s "
        "provider=%s model=%s failure_count=%s",
        user.id,
        selected.id,
        selection_source,
        selected.provider,
        selected.model_name,
        selected.failure_count,
    )
    return selected


async def record_llm_credential_success(
    db: AsyncSession,
    credential: LlmCredential,
) -> LlmCredential:
    now = datetime.now(UTC)
    credential.failure_count = 0
    credential.status = "valid"
    credential.last_error = ""
    credential.last_used_at = now
    credential.updated_at = now
    await db.commit()
    await db.refresh(credential)
    logger.info(
        "llm credential success recorded credential_id=%s user_id=%s",
        credential.id,
        credential.user_id,
    )
    return credential


async def record_llm_credential_failure(
    db: AsyncSession,
    credential: LlmCredential,
    error_summary: str,
) -> LlmCredential:
    now = datetime.now(UTC)
    next_failure_count = LlmCredential.failure_count + 1
    await db.execute(
        update(LlmCredential)
        .where(LlmCredential.id == credential.id)
        .values(
            failure_count=next_failure_count,
            status="invalid",
            last_error=error_summary[:500],
            last_used_at=now,
            updated_at=now,
            is_active=case(
                (
                    next_failure_count >= LLM_CREDENTIAL_FAILURE_THRESHOLD,
                    False,
                ),
                else_=LlmCredential.is_active,
            ),
        )
    )
    await db.commit()
    await db.refresh(credential)
    logger.warning(
        "llm credential failure recorded credential_id=%s user_id=%s "
        "failure_count=%s threshold=%s is_active=%s",
        credential.id,
        credential.user_id,
        credential.failure_count,
        LLM_CREDENTIAL_FAILURE_THRESHOLD,
        credential.is_active,
    )
    return credential


async def create_credential(
    db: AsyncSession,
    user: AppUser,
    payload: LlmCredentialCreateRequest,
) -> LlmCredential:
    existing = await db.execute(
        select(LlmCredential.id).where(LlmCredential.user_id == user.id).limit(1)
    )
    should_prefer = (
        payload.is_preferred
        or payload.is_default
        or existing.scalar_one_or_none() is None
    )

    if should_prefer:
        await _clear_default(db, user)
        await _clear_active(db, user)

    now = datetime.now(UTC)
    credential = LlmCredential(
        user_id=user.id,
        provider=payload.provider,
        display_name=payload.display_name,
        base_url=payload.base_url,
        api_mode=payload.api_mode,
        model_name=payload.model_name,
        api_key_ciphertext=encrypt_api_key(
            payload.api_key,
            settings.credential_encryption_key,
        ),
        api_key_mask=mask_api_key(payload.api_key),
        is_default=should_prefer,
        is_enabled=payload.is_enabled,
        is_preferred=should_prefer,
        is_active=should_prefer and payload.is_enabled,
        failure_count=0,
        status="untested",
        last_error="",
        created_at=now,
        updated_at=now,
    )
    db.add(credential)
    await db.commit()
    await db.refresh(credential)
    logger.info(
        "llm credential created user_id=%s credential_id=%s provider=%s model=%s "
        "is_preferred=%s is_enabled=%s",
        user.id,
        credential.id,
        credential.provider,
        credential.model_name,
        credential.is_preferred,
        credential.is_enabled,
    )
    return credential


async def update_credential(
    db: AsyncSession,
    user: AppUser,
    credential_id: int,
    payload: LlmCredentialUpdateRequest,
) -> LlmCredential:
    credential = await get_credential(db, user, credential_id)
    if payload.display_name is not None:
        credential.display_name = payload.display_name
    if payload.base_url is not None:
        credential.base_url = payload.base_url
    if payload.api_mode is not None:
        credential.api_mode = payload.api_mode
    if payload.model_name is not None:
        credential.model_name = payload.model_name
    if payload.api_key is not None:
        credential.api_key_ciphertext = encrypt_api_key(
            payload.api_key,
            settings.credential_encryption_key,
        )
        credential.api_key_mask = mask_api_key(payload.api_key)
        credential.status = "untested"
        credential.failure_count = 0
        credential.last_error = ""
    if payload.is_enabled is not None:
        credential.is_enabled = payload.is_enabled
        if not payload.is_enabled:
            credential.is_active = False
        elif (
            credential.is_preferred
            and credential.failure_count < LLM_CREDENTIAL_FAILURE_THRESHOLD
        ):
            await _clear_active(db, user)
            credential.is_active = True
    credential.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(credential)
    logger.info(
        "llm credential updated user_id=%s credential_id=%s is_enabled=%s "
        "is_preferred=%s status=%s",
        user.id,
        credential.id,
        credential.is_enabled,
        credential.is_preferred,
        credential.status,
    )
    return credential


async def set_default_credential(
    db: AsyncSession,
    user: AppUser,
    credential_id: int,
) -> LlmCredential:
    return await set_preferred_credential(db, user, credential_id)


async def set_preferred_credential(
    db: AsyncSession,
    user: AppUser,
    credential_id: int,
) -> LlmCredential:
    credential = await get_credential(db, user, credential_id)
    await _clear_default(db, user)
    credential.is_default = True
    credential.is_preferred = True
    if (
        credential.is_enabled
        and credential.failure_count < LLM_CREDENTIAL_FAILURE_THRESHOLD
    ):
        await _clear_active(db, user)
        credential.is_active = True
    credential.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(credential)
    logger.info(
        "llm credential preferred user_id=%s credential_id=%s is_active=%s",
        user.id,
        credential.id,
        credential.is_active,
    )
    return credential


async def delete_credential(
    db: AsyncSession,
    user: AppUser,
    credential_id: int,
) -> None:
    credential = await get_credential(db, user, credential_id)
    await db.delete(credential)
    await db.commit()
    logger.info(
        "llm credential deleted user_id=%s credential_id=%s", user.id, credential_id
    )


async def update_test_status(
    db: AsyncSession,
    credential: LlmCredential,
    *,
    status: str,
    message: str,
) -> LlmCredential:
    credential.status = status
    credential.last_error = "" if status == "valid" else message[:500]
    credential.last_tested_at = datetime.now(UTC)
    credential.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(credential)
    logger.info(
        "llm credential test status updated credential_id=%s user_id=%s status=%s",
        credential.id,
        credential.user_id,
        credential.status,
    )
    return credential
