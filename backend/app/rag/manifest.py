from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


SourceType = Literal[
    "manual_cards",
    "book",
    "tutorial",
    "blog",
    "course",
    "problem_list",
    "repository",
]
Language = Literal["zh", "en"]
Priority = Literal["P0", "P1", "P2"]


class SourceManifest(BaseModel):
    source_name: str = Field(min_length=1, max_length=180)
    source_type: SourceType
    language: Language
    priority: Priority
    main_usage: list[str] = Field(min_length=1)
    local_path: str = Field(min_length=1, max_length=500)
    license_note: str = Field(min_length=1)
    source_url: str | None = None
    source_locator: str | None = None
    notes: str | None = None

    @field_validator("local_path")
    @classmethod
    def validate_local_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("local_path_must_be_relative")
        return path.as_posix()

    @field_validator("main_usage")
    @classmethod
    def validate_main_usage(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized:
            raise ValueError("main_usage_required")
        return normalized


def load_source_manifest(path: str | Path) -> SourceManifest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return SourceManifest.model_validate(payload)
