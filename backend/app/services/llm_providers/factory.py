from __future__ import annotations

import logging

from backend.app.models.auth import LlmCredential
from backend.app.services.llm_credential_service import LlmCredentialError
from backend.app.services.llm_providers.base import LlmProvider
from backend.app.services.llm_providers.openai_responses import OpenAIResponsesProvider


logger = logging.getLogger(__name__)


def create_llm_provider(credential: LlmCredential, *, api_key: str) -> LlmProvider:
    provider = credential.provider
    api_mode = credential.api_mode
    if provider == "openai" and api_mode == "responses":
        logger.info(
            "llm provider created credential_id=%s provider=%s api_mode=%s model=%s",
            credential.id,
            provider,
            api_mode,
            credential.model_name,
        )
        return OpenAIResponsesProvider(api_key=api_key, base_url=credential.base_url)
    logger.warning(
        "llm provider unsupported credential_id=%s provider=%s api_mode=%s",
        credential.id,
        provider,
        api_mode,
    )
    raise LlmCredentialError("llm_credential_unavailable")
