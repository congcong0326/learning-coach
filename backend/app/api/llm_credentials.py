from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.auth import current_user_dependency
from backend.app.core.config import settings
from backend.app.db.session import get_session
from backend.app.models.auth import AppUser
from backend.app.schemas.llm_credential import (
    LlmCredentialCreateRequest,
    LlmCredentialListResponse,
    LlmCredentialResponse,
    LlmCredentialTestResponse,
    LlmCredentialUpdateRequest,
)
from backend.app.services.credential_crypto import (
    CredentialEncryptionError,
    decrypt_api_key,
)
from backend.app.services.llm_credential_service import (
    LlmCredentialError,
    create_credential,
    credential_payload,
    delete_credential,
    get_credential,
    list_credentials,
    set_default_credential,
    set_preferred_credential,
    update_credential,
    update_test_status,
)
from backend.app.services.openai_connection_service import test_openai_credential


router = APIRouter(prefix="/me/llm-credentials", tags=["llm-credentials"])


def _credential_not_found(exc: LlmCredentialError) -> HTTPException:
    return HTTPException(status_code=404, detail=exc.detail)


@router.get("", response_model=LlmCredentialListResponse)
async def index(
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    credentials = await list_credentials(session, user)
    return {"items": [credential_payload(item) for item in credentials]}


@router.post("", response_model=LlmCredentialResponse)
async def create(
    payload: LlmCredentialCreateRequest,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        credential = await create_credential(session, user, payload)
    except CredentialEncryptionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return credential_payload(credential)


@router.patch("/{credential_id}", response_model=LlmCredentialResponse)
async def update(
    credential_id: int,
    payload: LlmCredentialUpdateRequest,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        credential = await update_credential(session, user, credential_id, payload)
    except LlmCredentialError as exc:
        raise _credential_not_found(exc) from exc
    except CredentialEncryptionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return credential_payload(credential)


@router.post("/{credential_id}/default", response_model=LlmCredentialResponse)
async def make_default(
    credential_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        credential = await set_default_credential(session, user, credential_id)
    except LlmCredentialError as exc:
        raise _credential_not_found(exc) from exc
    return credential_payload(credential)


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


@router.post("/{credential_id}/test", response_model=LlmCredentialTestResponse)
async def test_connection(
    credential_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        credential = await get_credential(session, user, credential_id)
        api_key = decrypt_api_key(
            credential.api_key_ciphertext,
            settings.credential_encryption_key,
        )
    except LlmCredentialError as exc:
        raise _credential_not_found(exc) from exc
    except CredentialEncryptionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    result = await test_openai_credential(credential, api_key)
    await update_test_status(
        session,
        credential,
        status=result["status"],
        message=result["message"],
    )
    return result


@router.delete("/{credential_id}")
async def delete(
    credential_id: int,
    user: AppUser = Depends(current_user_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        await delete_credential(session, user, credential_id)
    except LlmCredentialError as exc:
        raise _credential_not_found(exc) from exc
    return {"status": "ok"}
