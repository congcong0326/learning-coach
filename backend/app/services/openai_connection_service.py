from __future__ import annotations

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, AuthenticationError

from backend.app.models.auth import LlmCredential


async def test_openai_credential(
    credential: LlmCredential,
    api_key: str,
) -> dict:
    client = AsyncOpenAI(api_key=api_key, base_url=credential.base_url)
    try:
        models = await client.models.list()
    except AuthenticationError:
        return {
            "status": "invalid",
            "message": "authentication_failed",
            "model_name": credential.model_name,
        }
    except APIConnectionError:
        return {
            "status": "invalid",
            "message": "connection_failed",
            "model_name": credential.model_name,
        }
    except APIStatusError:
        return {
            "status": "invalid",
            "message": "connection_failed",
            "model_name": credential.model_name,
        }

    model_ids = {item.id for item in models.data}
    if credential.model_name not in model_ids:
        return {
            "status": "invalid",
            "message": "model_not_found",
            "model_name": credential.model_name,
        }
    return {
        "status": "valid",
        "message": "connection_ok",
        "model_name": credential.model_name,
    }
