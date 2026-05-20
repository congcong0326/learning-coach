from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


Provider = Literal["openai"]
ApiMode = Literal["responses"]
CredentialStatus = Literal["untested", "valid", "invalid"]


class LlmCredentialCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    provider: Provider = "openai"
    base_url: str = Field(min_length=8, max_length=500)
    api_mode: ApiMode = "responses"
    model_name: str = Field(min_length=1, max_length=120)
    api_key: str = Field(min_length=1, max_length=500)
    is_enabled: bool = True
    is_preferred: bool = False
    is_default: bool = False

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        if not (value.startswith("https://") or value.startswith("http://")):
            raise ValueError("base_url_must_be_http_url")
        return value.rstrip("/")


class LlmCredentialUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: str | None = Field(default=None, min_length=8, max_length=500)
    api_mode: ApiMode | None = None
    model_name: str | None = Field(default=None, min_length=1, max_length=120)
    api_key: str | None = Field(default=None, min_length=1, max_length=500)
    is_enabled: bool | None = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not (value.startswith("https://") or value.startswith("http://")):
            raise ValueError("base_url_must_be_http_url")
        return value.rstrip("/")


class LlmCredentialResponse(BaseModel):
    id: int
    provider: str
    display_name: str
    base_url: str
    api_mode: str
    model_name: str
    api_key_mask: str
    is_enabled: bool
    is_preferred: bool
    is_default: bool
    is_active: bool
    failure_count: int
    status: str
    last_tested_at: datetime | None
    last_used_at: datetime | None
    last_error: str


class LlmCredentialListResponse(BaseModel):
    items: list[LlmCredentialResponse]


class LlmCredentialTestResponse(BaseModel):
    status: CredentialStatus
    message: str
    model_name: str
