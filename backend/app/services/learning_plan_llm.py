from __future__ import annotations

import json
from typing import Any, Protocol

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.models.auth import AppUser, LlmCredential
from backend.app.services.credential_crypto import decrypt_api_key
from backend.app.services.learning_plan_validator import validate_and_repair_plan_draft
from backend.app.services.llm_credential_service import select_llm_credential_for_user


PROMPT_VERSION = "goal-plan-v1"

PLAN_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "target_snapshot", "generation_summary_md", "stages"],
    "properties": {
        "title": {"type": "string"},
        "target_snapshot": {"type": "object"},
        "generation_summary_md": {"type": "string"},
        "stages": {"type": "array"},
    },
}


class LearningPlanLlmClient(Protocol):
    async def followup_question(
        self,
        payload: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        ...

    async def plan_draft(
        self,
        payload: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ...

    async def repair_plan_draft(
        self,
        payload: dict[str, Any],
        report: dict[str, Any],
        repair_log: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ...


class OpenAILearningPlanClient:
    def __init__(self, credential: LlmCredential, api_key: str) -> None:
        self.credential = credential
        self.client = AsyncOpenAI(api_key=api_key, base_url=credential.base_url)

    async def _json_response(
        self,
        instructions: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
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
            return None
        response = await self.client.responses.create(
            model=self.credential.model_name,
            instructions=(
                "你是目标校准教练。只在必要时返回一个 JSON 问题；"
                "信息足够时返回 null。"
            ),
            input=json.dumps({"payload": payload, "history": history}, ensure_ascii=False),
        )
        output_text = response.output_text.strip()
        if output_text == "null":
            return None
        parsed = json.loads(output_text)
        return parsed if isinstance(parsed, dict) else None

    async def plan_draft(
        self,
        payload: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return await self._json_response(
            "根据用户目标生成阶段化学习计划。当前阶段必须包含 LeetCode 题目 slug。",
            {"payload": payload, "history": history},
        )

    async def repair_plan_draft(
        self,
        payload: dict[str, Any],
        report: dict[str, Any],
        repair_log: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return await self._json_response(
            "根据校验失败原因修复学习计划，只替换无效题目。",
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
    return OpenAILearningPlanClient(credential, api_key), credential


async def generate_plan_with_repair(
    session: AsyncSession,
    client: LearningPlanLlmClient,
    payload: dict[str, Any],
    history: list[dict[str, Any]],
    *,
    max_repairs: int = 2,
    locked_problem_slugs: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    draft = await client.plan_draft(payload, history)
    combined_repair_log: list[dict[str, Any]] = []
    for attempt in range(max_repairs + 1):
        repaired, report, repair_log = await validate_and_repair_plan_draft(
            session,
            draft,
            locked_problem_slugs=locked_problem_slugs,
        )
        combined_repair_log.extend(repair_log)
        if report.get("valid"):
            return repaired, report, combined_repair_log
        if attempt == max_repairs:
            return repaired, report, combined_repair_log
        draft = await client.repair_plan_draft(payload, report, combined_repair_log)
    return draft, {"valid": False, "issues": ["repair_loop_exhausted"]}, combined_repair_log
