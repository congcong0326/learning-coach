from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.models.auth import AppUser, LlmCredential
from backend.app.services.credential_crypto import decrypt_api_key
from backend.app.services.learning_plan_validator import validate_and_repair_plan_draft
from backend.app.services.llm_credential_service import select_llm_credential_for_user


PROMPT_VERSION = "goal-plan-v2"
logger = logging.getLogger(__name__)

# The model receives this schema to stay close to the API contract, but the
# backend validator remains the source of truth for problem slugs and paid status.
PLAN_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "target_snapshot", "generation_summary_md", "stages"],
    "properties": {
        "title": {"type": "string"},
        "target_snapshot": {"type": "object"},
        "generation_summary_md": {"type": "string"},
        "stages": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "title",
                    "objective_md",
                    "focus_tags",
                    "assessment_criteria",
                    "items",
                ],
                "properties": {
                    "title": {"type": "string"},
                    "objective_md": {"type": "string"},
                    "focus_tags": {"type": "array", "items": {"type": "string"}},
                    "assessment_criteria": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "problem_slug",
                                "difficulty",
                                "skill_tags",
                                "suggested_mode",
                                "recommendation_reason",
                            ],
                            "properties": {
                                "problem_slug": {"type": "string"},
                                "difficulty": {
                                    "type": "string",
                                    "enum": ["Easy", "Medium", "Hard"],
                                },
                                "skill_tags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "suggested_mode": {
                                    "type": "string",
                                    "enum": [
                                        "guided",
                                        "independent",
                                        "mock_interview",
                                    ],
                                },
                                "recommendation_reason": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    },
}

# Keep display text in Chinese while preserving machine-readable enum and slug
# values. This prevents downstream code from depending on translated identifiers.
DEFAULT_LANGUAGE_CONTEXT_INSTRUCTIONS = (
    "默认语言语境：简体中文。除 machine-readable 字段（problem_slug、difficulty、"
    "suggested_mode、skill_tags、枚举值、URL、代码语言名称和 target_snapshot 原始值）外，"
    "所有面向用户展示的文本字段必须使用简体中文；不要输出英文标题、英文阶段名或英文推荐理由。"
)


def _with_default_language_context(task_instructions: str) -> str:
    return f"{DEFAULT_LANGUAGE_CONTEXT_INSTRUCTIONS}\n\n{task_instructions}"


FOLLOWUP_INSTRUCTIONS = _with_default_language_context(
    "你是目标校准教练。只在必要时返回一个 JSON 问题；"
    "信息足够时返回 null。返回问题时，question 字段必须使用简体中文。"
)

PLAN_DRAFT_INSTRUCTIONS = _with_default_language_context(
    "根据用户目标生成阶段化学习计划。必须返回 JSON，且 stages 至少包含 1 个阶段；"
    "每个阶段的 items 至少包含 1 道 LeetCode 题目，problem_slug 必须使用英文 slug，"
    "例如 two-sum、valid-parentheses、merge-intervals。不要返回空 stages 或空 items。"
)

REPAIR_PLAN_INSTRUCTIONS = _with_default_language_context(
    "根据 validation_report 修复学习计划。若 item_count 为 0 或 issues 包含 "
    "empty_plan_stages、empty_stage_items、empty_plan_items，必须补充至少 1 道 "
    "LeetCode 题目的 problem_slug。只输出符合 schema 的 JSON。"
)


class LearningPlanLlmClient(Protocol):
    """Small interface used by tests and services to swap the OpenAI client."""

    async def followup_question(
        self,
        payload: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> dict[str, Any] | None: ...

    async def plan_draft(
        self,
        payload: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> dict[str, Any]: ...

    async def repair_plan_draft(
        self,
        payload: dict[str, Any],
        report: dict[str, Any],
        repair_log: list[dict[str, Any]],
    ) -> dict[str, Any]: ...


class OpenAILearningPlanClient:
    """OpenAI Responses client for goal followups and structured plan drafts."""

    def __init__(self, credential: LlmCredential, api_key: str) -> None:
        self.credential = credential
        self.client = AsyncOpenAI(api_key=api_key, base_url=credential.base_url)

    async def _json_response(
        self,
        instructions: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # Payloads can contain user free text, so logs around this call only use
        # counts and credential metadata from the caller instead of raw content.
        response = await self.client.responses.create(
            model=self.credential.model_name,
            instructions=instructions,
            input=json.dumps(payload, ensure_ascii=False),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "learning_plan_payload",
                    "schema": PLAN_JSON_SCHEMA,
                    "strict": False,
                }
            },
        )
        parsed = json.loads(response.output_text)
        return parsed if isinstance(parsed, dict) else {}

    async def followup_question(
        self,
        payload: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if len(history) >= 3:
            logger.info(
                "learning plan followup skipped credential_id=%s model=%s "
                "history_messages=%s reason=max_history_reached",
                self.credential.id,
                self.credential.model_name,
                len(history),
            )
            return None
        logger.info(
            "learning plan followup requested credential_id=%s model=%s "
            "history_messages=%s",
            self.credential.id,
            self.credential.model_name,
            len(history),
        )
        response = await self.client.responses.create(
            model=self.credential.model_name,
            instructions=FOLLOWUP_INSTRUCTIONS,
            input=json.dumps(
                {"payload": payload, "history": history}, ensure_ascii=False
            ),
        )
        output_text = response.output_text.strip()
        if output_text == "null":
            logger.info(
                "learning plan followup completed credential_id=%s model=%s "
                "has_question=false",
                self.credential.id,
                self.credential.model_name,
            )
            return None
        parsed = json.loads(output_text)
        logger.info(
            "learning plan followup completed credential_id=%s model=%s "
            "has_question=%s",
            self.credential.id,
            self.credential.model_name,
            isinstance(parsed, dict),
        )
        return parsed if isinstance(parsed, dict) else None

    async def plan_draft(
        self,
        payload: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return await self._json_response(
            PLAN_DRAFT_INSTRUCTIONS,
            {"payload": payload, "history": history},
        )

    async def repair_plan_draft(
        self,
        payload: dict[str, Any],
        report: dict[str, Any],
        repair_log: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return await self._json_response(
            REPAIR_PLAN_INSTRUCTIONS,
            {
                "payload": payload,
                "validation_report": report,
                "repair_log": repair_log,
            },
        )


async def client_for_user(
    db: AsyncSession,
    user: AppUser,
) -> tuple[LearningPlanLlmClient, LlmCredential]:
    credential = await select_llm_credential_for_user(db, user)
    api_key = decrypt_api_key(
        credential.api_key_ciphertext,
        settings.credential_encryption_key,
    )
    logger.info(
        "learning plan llm credential selected user_id=%s credential_id=%s "
        "provider=%s model=%s",
        user.id,
        credential.id,
        credential.provider,
        credential.model_name,
    )
    return OpenAILearningPlanClient(credential, api_key), credential


def _format_issues(report: dict[str, Any]) -> str:
    issues = report.get("issues", [])
    if isinstance(issues, list):
        return ",".join(str(issue) for issue in issues) or "none"
    return str(issues) if issues else "none"


def _draft_stage_count(draft: dict[str, Any]) -> int:
    stages = draft.get("stages", [])
    return len(stages) if isinstance(stages, list) else 0


def _draft_item_count(draft: dict[str, Any]) -> int:
    stages = draft.get("stages", [])
    if not isinstance(stages, list):
        return 0
    item_count = 0
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        items = stage.get("items", [])
        if isinstance(items, list):
            item_count += len(items)
    return item_count


async def generate_plan_with_repair(
    session: AsyncSession,
    client: LearningPlanLlmClient,
    payload: dict[str, Any],
    history: list[dict[str, Any]],
    *,
    max_repairs: int = 2,
    locked_problem_slugs: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    locked_problem_count = len(locked_problem_slugs or set())
    logger.info(
        "learning plan draft generation started "
        "history_messages=%s max_repairs=%s locked_problem_count=%s",
        len(history),
        max_repairs,
        locked_problem_count,
    )
    # The first draft is treated as untrusted: the LLM proposes structure and
    # slugs, then the local validator repairs or rejects before anything is saved.
    draft = await client.plan_draft(payload, history)
    logger.info(
        "learning plan draft generated stage_count=%s item_count=%s",
        _draft_stage_count(draft),
        _draft_item_count(draft),
    )
    combined_repair_log: list[dict[str, Any]] = []
    # Each pass first applies deterministic backend repair, then optionally asks
    # the model to produce a cleaner draft using only the validation report.
    for attempt in range(max_repairs + 1):
        repaired, report, repair_log = await validate_and_repair_plan_draft(
            session,
            draft,
            locked_problem_slugs=locked_problem_slugs,
        )
        combined_repair_log.extend(repair_log)
        log_validation = logger.info if report.get("valid") else logger.warning
        log_validation(
            "learning plan draft validation result "
            "attempt=%s valid=%s issues=%s item_count=%s repair_log_count=%s",
            attempt,
            bool(report.get("valid")),
            _format_issues(report),
            report.get("item_count", 0),
            len(combined_repair_log),
        )
        if report.get("valid"):
            return repaired, report, combined_repair_log
        if attempt == max_repairs:
            logger.warning(
                "learning plan draft validation exhausted "
                "attempt=%s issues=%s item_count=%s repair_log_count=%s",
                attempt,
                _format_issues(report),
                report.get("item_count", 0),
                len(combined_repair_log),
            )
            return repaired, report, combined_repair_log
        logger.info(
            "learning plan draft repair requested attempt=%s next_attempt=%s issues=%s",
            attempt,
            attempt + 1,
            _format_issues(report),
        )
        draft = await client.repair_plan_draft(payload, report, combined_repair_log)
        logger.info(
            "learning plan draft repair received attempt=%s stage_count=%s item_count=%s",
            attempt + 1,
            _draft_stage_count(draft),
            _draft_item_count(draft),
        )
    return (
        draft,
        {"valid": False, "issues": ["repair_loop_exhausted"]},
        combined_repair_log,
    )
