from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSpec:
    key: str
    version: str
    instructions: str
    output_fields: tuple[str, ...] = ()
