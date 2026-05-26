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
    has_fence_token = "```" in content_md
    for language, code_text in _iter_fenced_blocks(content_md):
        if _looks_like_code(code_text):
            return ExtractedCode(
                language=_normalize_language(language, code_text=code_text),
                code_text=code_text,
            )
    if has_fence_token:
        return None
    return _extract_unfenced_code_block(content_md)


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


def _normalize_language(language: str, *, code_text: str = "") -> str:
    key = language.strip().lower()
    if key in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[key]
    return _infer_language_from_code(code_text)


def _infer_language_from_code(code_text: str) -> str:
    stripped = code_text.strip()
    if not stripped:
        return "python3"
    lower = stripped.lower()
    if re.search(r"\b(public|private|protected)\s+", stripped) and re.search(
        r"\b(class|boolean|int|long|string|void)\b",
        stripped,
    ):
        return "java"
    if re.search(r"\bclass\s+\w+\s*\{", stripped) and re.search(
        r"\b(public|boolean|int|long|string|void)\b",
        stripped,
    ):
        return "java"
    if re.search(r"^\s*(def|class)\s+\w+.*:", stripped, re.MULTILINE):
        return "python3"
    if "from " in lower and " import " in lower:
        return "python3"
    if re.search(r"\b(function|const|let|var)\s+", stripped) or "=>" in stripped:
        return "javascript"
    if re.search(r"^\s*package\s+\w+", stripped, re.MULTILINE) or re.search(
        r"\bfunc\s+\w+\s*\(",
        stripped,
    ):
        return "go"
    if "#include" in stripped or re.search(r"\bint\s+main\s*\(", stripped):
        return "c"
    return "python3"


def _iter_fenced_blocks(content_md: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    current_language = ""
    current_lines: list[str] = []
    in_block = False
    block_malformed = False

    # 只接受独占一行的 closing fence；块内再次出现 fence token 视为 malformed，
    # 避免把说明文字和后续 fence 拼进代码快照。
    for line in content_md.splitlines():
        stripped = line.strip()
        if not in_block:
            if stripped.startswith("```"):
                in_block = True
                current_language = stripped[3:].strip()
                current_lines = []
                block_malformed = False
            continue
        if stripped == "```":
            if not block_malformed:
                blocks.append((current_language, "\n".join(current_lines).strip()))
            in_block = False
            current_language = ""
            current_lines = []
            block_malformed = False
            continue
        if stripped.startswith("```"):
            block_malformed = True
        current_lines.append(line)
    return blocks


def _looks_like_code(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    markers = ("class ", "def ", "return ", "for ", "while ", "{", "}", ";")
    marker_hits = sum(1 for line in lines if any(marker in line for marker in markers))
    return marker_hits >= 2


def _extract_unfenced_code_block(content_md: str) -> ExtractedCode | None:
    lines = content_md.strip().splitlines()
    for start_index, line in enumerate(lines):
        if not _line_starts_code_block(line):
            continue
        candidate_lines: list[str] = []
        for candidate_line in lines[start_index:]:
            if not candidate_line.strip():
                candidate_lines.append(candidate_line)
                continue
            if not candidate_lines or _line_can_belong_to_code(candidate_line):
                candidate_lines.append(candidate_line)
                continue
            break
        code_text = "\n".join(candidate_lines).strip()
        if _looks_like_code(code_text):
            return ExtractedCode(
                language=_infer_language_from_code(code_text),
                code_text=code_text,
            )
    return None


def _line_starts_code_block(line: str) -> bool:
    stripped = line.strip()
    start_markers = (
        "class ",
        "def ",
        "import ",
        "from ",
        "public ",
        "private ",
        "protected ",
        "function ",
        "const ",
        "let ",
        "var ",
    )
    return any(stripped.startswith(marker) for marker in start_markers)


def _line_can_belong_to_code(line: str) -> bool:
    stripped = line.strip()
    if _line_starts_code_block(line):
        return True
    if line[:1].isspace():
        return True
    code_markers = (
        "return ",
        "for ",
        "while ",
        "if ",
        "elif ",
        "else:",
        "try:",
        "except ",
        "with ",
        "{",
        "}",
    )
    if any(stripped.startswith(marker) for marker in code_markers):
        return True
    # 无围栏输入常混有前后说明，这里只保留连续代码块，
    # 避免把“这是我的思路”“请帮我看看”等聊天文本写入代码快照。
    return stripped.endswith(";") or stripped.endswith("{") or stripped.endswith("}")
