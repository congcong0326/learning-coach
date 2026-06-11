from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files

from backend.app.prompts.types import PromptSpec


_RESOURCE_PACKAGE = "backend.app.prompts.resources"
_GOAL_PLAN_VERSION = "goal-plan-v3-streaming"


@dataclass(frozen=True)
class _PromptDefinition:
    version: str
    resource_name: str
    output_fields: tuple[str, ...] = ()


_PROMPT_DEFINITIONS: dict[str, _PromptDefinition] = {
    "default_language_context": _PromptDefinition(
        version=_GOAL_PLAN_VERSION,
        resource_name="default_language_context.v1.md",
    ),
    "goal_followup": _PromptDefinition(
        version=_GOAL_PLAN_VERSION,
        resource_name="goal_followup.v3.md",
        output_fields=("question_id", "question"),
    ),
    "goal_plan_draft": _PromptDefinition(
        version=_GOAL_PLAN_VERSION,
        resource_name="goal_plan_draft.v3.md",
    ),
    "goal_plan_repair": _PromptDefinition(
        version=_GOAL_PLAN_VERSION,
        resource_name="goal_plan_repair.v3.md",
    ),
    "legacy_learning_followup": _PromptDefinition(
        version=_GOAL_PLAN_VERSION,
        resource_name="legacy_learning_followup.v3.md",
        output_fields=("question_id", "question"),
    ),
    "legacy_learning_plan_draft": _PromptDefinition(
        version=_GOAL_PLAN_VERSION,
        resource_name="legacy_learning_plan_draft.v3.md",
    ),
    "legacy_learning_plan_repair": _PromptDefinition(
        version=_GOAL_PLAN_VERSION,
        resource_name="legacy_learning_plan_repair.v3.md",
    ),
    "coach_turn": _PromptDefinition(
        version="coach-turn-v2-structured",
        resource_name="coach_turn.v2.md",
        output_fields=(
            "phase_after",
            "diagnosed_stuck_point",
            "next_action",
            "reply_md",
            "should_reveal_solution",
        ),
    ),
    "coach_summary": _PromptDefinition(
        version="coach-summary-v1-coaching-review",
        resource_name="coach_summary.v1.md",
        output_fields=("markdown",),
    ),
}


def prompt_keys() -> tuple[str, ...]:
    return tuple(sorted(_PROMPT_DEFINITIONS))


@lru_cache(maxsize=None)
def get_prompt(key: str) -> PromptSpec:
    definition = _PROMPT_DEFINITIONS.get(key)
    if definition is None:
        raise KeyError(f"unknown prompt key: {key}")
    # Prompt 正文作为 package resource 加载，避免 pytest、Docker 或将来打包后
    # 因工作目录不同导致相对路径失效。
    instructions = (
        files(_RESOURCE_PACKAGE)
        .joinpath(definition.resource_name)
        .read_text(encoding="utf-8")
        .strip()
    )
    return PromptSpec(
        key=key,
        version=definition.version,
        instructions=instructions,
        output_fields=definition.output_fields,
    )
