from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.practice import CodeSnapshot, PracticeEvent, PracticeSession


QUALITY_STATUSES = {"pending", "needs_fix", "ready_to_submit"}
_FENCED_CODE_RE = re.compile(
    r"```(?P<language>[A-Za-z0-9_+#.-]*)\s*\n(?P<code>.*?)```",
    re.DOTALL,
)
_LANGUAGE_ALIASES = {
    "py": "python3",
    "python": "python3",
    "python3": "python3",
    "js": "javascript",
    "javascript": "javascript",
    "java": "java",
    "go": "go",
    "golang": "go",
    "c": "c",
}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractedCode:
    language: str
    code_text: str


def extract_code_from_message(content_md: str) -> ExtractedCode | None:
    has_fenced_block = False
    for match in _FENCED_CODE_RE.finditer(content_md):
        has_fenced_block = True
        code_text = match.group("code").strip()
        if _looks_like_code(code_text):
            return ExtractedCode(
                language=_normalize_language(match.group("language")),
                code_text=code_text,
            )
    if has_fenced_block:
        return None
    stripped = content_md.strip()
    if _looks_like_code(stripped):
        return ExtractedCode(language="python3", code_text=stripped)
    return None


def quality_from_decision(coach_decision: dict[str, Any]) -> tuple[str, str]:
    raw_status = coach_decision.get("code_quality_status")
    status = raw_status if raw_status in QUALITY_STATUSES else "pending"
    raw_comment = coach_decision.get("code_quality_comment")
    comment = raw_comment.strip() if isinstance(raw_comment, str) else ""
    return status, comment[:240]


async def persist_review_code_attempt(
    db: AsyncSession,
    *,
    user_id: int,
    practice_session: PracticeSession,
    user_event: PracticeEvent,
    extracted_code: ExtractedCode,
    quality_status: str,
    quality_comment: str,
    client_revision: int,
    now: datetime,
) -> CodeSnapshot:
    code_hash = hashlib.sha256(extracted_code.code_text.encode("utf-8")).hexdigest()
    event = PracticeEvent(
        session_id=practice_session.id,
        user_id=user_id,
        event_type="code_saved",
        role="user",
        phase="review_code",
        intent="code_review",
        content_md="",
        payload_json={
            "language": extracted_code.language,
            "source": "chat_review",
            "client_revision": client_revision,
            "code_hash": code_hash,
            "user_event_id": user_event.id,
            "quality_status": quality_status,
            "quality_comment": quality_comment,
        },
        hint_level=practice_session.current_hint_level,
        visible_hint_gear=practice_session.visible_hint_gear,
        created_at=now,
    )
    db.add(event)
    await db.flush()
    snapshot = CodeSnapshot(
        session_id=practice_session.id,
        user_id=user_id,
        event_id=event.id,
        language=extracted_code.language,
        code_text=extracted_code.code_text,
        code_hash=code_hash,
        source="chat_review",
        client_revision=client_revision,
        created_at=now,
    )
    db.add(snapshot)
    await db.flush()
    event.payload_json = {
        **event.payload_json,
        "snapshot_id": snapshot.id,
    }
    practice_session.latest_code_snapshot_id = snapshot.id
    logger.info(
        "practice_review_code_snapshot_saved user_id=%s session_id=%s snapshot_id=%s "
        "event_id=%s source=%s client_revision=%s quality_status=%s",
        user_id,
        practice_session.id,
        snapshot.id,
        event.id,
        snapshot.source,
        snapshot.client_revision,
        quality_status,
    )
    return snapshot


def _normalize_language(language: str) -> str:
    key = language.strip().lower()
    return _LANGUAGE_ALIASES.get(key, "python3")


def _looks_like_code(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    markers = ("class ", "def ", "return ", "for ", "while ", "{", "}", ";")
    marker_hits = sum(1 for line in lines if any(marker in line for marker in markers))
    return marker_hits >= 2
