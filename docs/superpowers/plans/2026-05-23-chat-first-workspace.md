# Chat-first Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将做题工作台改为左侧题面、右侧 ChatGPT 式教练聊天，并用自动代码尝试记录替代独立代码卡片。

**Architecture:** 后端继续复用 `practice_session`、`practice_event`、`code_snapshot` 和 `submission_feedback`，不新增表。代码尝试记录由 `review_code` 阶段的用户消息提取代码后生成 `code_snapshot`，AI 质量判断写入事件 payload 并通过 session response 暴露给前端。前端改为两栏布局，聊天区顶部提供代码尝试记录抽屉，输入区提供“LeetCode 已 AC”结构化动作。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy async、Pydantic、uv、React、TypeScript、Ant Design、TanStack Query、Vitest。

---

## File Structure

- Modify `backend/app/schemas/practice.py`: 增加代码尝试记录响应类型、`chat_review` code snapshot source、session response 字段。
- Modify `backend/app/services/practice_session_service.py`: 组装 `code_attempts`，放宽 AC 无代码快照，保存代码快照时写入 `snapshot_id` 与质量字段默认值。
- Create `backend/app/services/code_attempts.py`: 从聊天消息提取代码、校验 AI 质量判断、持久化 review 阶段代码尝试。
- Modify `backend/app/services/learning_flows/coach_turn.py`: 将本轮用户消息中的明确代码纳入 guard 判断；进入 `review_code` 后自动持久化代码尝试记录；解析模型输出中的质量判断与简评。
- Modify `backend/tests/test_practice_session_service.py`: 覆盖 session response 的代码尝试记录与 AC 无快照。
- Modify `backend/tests/test_learning_flows.py`: 覆盖聊天代码进入 `review_code` 后自动生成代码尝试记录，非 review 阶段不生成。
- Modify `frontend/src/api/practice.ts`: 增加 `CodeAttempt` 类型和 `PracticeSession.code_attempts` 字段。
- Create `frontend/src/pages/workspace/CodeAttemptDrawer.tsx`: 代码尝试记录抽屉，展示灰色、红灯、绿灯和感叹号简评 tooltip。
- Create `frontend/src/pages/workspace/CodeAttemptDrawer.test.tsx`: 覆盖三种状态与 tooltip。
- Modify `frontend/src/pages/workspace/CoachPanel.tsx`: 改成聊天主界面，顶部状态区和代码尝试记录入口，新增“LeetCode 已 AC”按钮。
- Modify `frontend/src/pages/workspace/CoachPanel.test.tsx`: 更新为 chat-first 行为测试，覆盖 AC 动作。
- Modify `frontend/src/pages/WorkspacePage.tsx`: 从三栏改成两栏，移除主界面 `CodePane`。
- Modify `frontend/src/pages/WorkspacePage.test.tsx`: 删除代码草稿相关测试，新增两栏与代码尝试记录入口测试。
- Modify `frontend/src/styles/app.css`: 增加两栏工作台、聊天气泡、系统事件、代码尝试抽屉样式。
- Modify `docs/prd/ai-coach-workbench-prd.md`: 同步 Chat-first 工作台、代码尝试记录和 AC 按钮语义。
- Modify `docs/architecture/foundation.md`: 更新当前工作台架构描述。
- Modify `docs/project-todolist.md`: 更新后续任务表述和验证记录。

Before editing, run `git status --short` and do not revert existing user changes. This repository already has unrelated modified files; each task must stage only its own files.

---

### Task 1: Backend Session Response And AC Rules

**Files:**
- Modify: `backend/app/schemas/practice.py`
- Modify: `backend/app/services/practice_session_service.py`
- Test: `backend/tests/test_practice_session_service.py`

- [x] **Step 1: Write failing service tests**

Add these tests to `backend/tests/test_practice_session_service.py` near the submission feedback tests:

```python
@pytest.mark.asyncio
async def test_session_payload_includes_code_attempts(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> None:
    from backend.app.services.practice_session_service import get_session_payload

    snapshot_id = await save_python_snapshot(db_session, user, practice_session)
    result = await db_session.execute(
        select(PracticeEvent).where(
            PracticeEvent.session_id == practice_session.id,
            PracticeEvent.event_type == "code_saved",
        )
    )
    event = result.scalar_one()
    event.payload_json = {
        **event.payload_json,
        "snapshot_id": snapshot_id,
        "quality_status": "ready_to_submit",
        "quality_comment": "哈希表维护正确，可以去 LeetCode 尝试提交。",
    }
    await db_session.commit()

    payload = await get_session_payload(db_session, user, practice_session.id)

    assert len(payload.code_attempts) == 1
    attempt = payload.code_attempts[0]
    assert attempt.snapshot_id == snapshot_id
    assert attempt.language == "python3"
    assert attempt.source == "manual_save"
    assert attempt.quality_status == "ready_to_submit"
    assert attempt.quality_comment == "哈希表维护正确，可以去 LeetCode 尝试提交。"
    assert attempt.code_preview == "class Solution:\n    pass"


@pytest.mark.asyncio
async def test_ac_submission_feedback_without_code_snapshot_is_allowed(
    db_session: AsyncSession,
    user: AppUser,
    practice_session: PracticeSession,
) -> None:
    from backend.app.schemas.practice import SubmissionFeedbackCreate
    from backend.app.services.practice_session_service import record_submission_feedback

    result = await record_submission_feedback(
        db_session,
        user,
        practice_session.id,
        SubmissionFeedbackCreate(result="ac"),
    )

    await db_session.refresh(practice_session)
    assert result.result == "ac"
    assert result.code_snapshot_id is None
    assert practice_session.final_result == "ac"
    assert practice_session.phase == "summarize"
    assert practice_session.status == "summarizing"
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest backend/tests/test_practice_session_service.py::test_session_payload_includes_code_attempts backend/tests/test_practice_session_service.py::test_ac_submission_feedback_without_code_snapshot_is_allowed -q
```

Expected: FAIL because `PracticeSessionResponse` has no `code_attempts`, and AC without a snapshot raises `code_snapshot_required_for_submission_feedback`.

- [x] **Step 3: Extend practice schemas**

In `backend/app/schemas/practice.py`, update `CodeSnapshotSource` and add `CodeAttemptResponse`:

```python
CodeSnapshotSource = Literal[
    "paste",
    "manual_save",
    "before_review",
    "chat_review",
    "before_submit",
    "final",
]
CodeAttemptQuality = Literal["pending", "needs_fix", "ready_to_submit"]
```

Add this class after `PracticeEventResponse`:

```python
class CodeAttemptResponse(BaseModel):
    snapshot_id: int
    event_id: int | None
    language: str
    source: str
    client_revision: int
    code_hash: str
    code_preview: str
    quality_status: CodeAttemptQuality
    quality_comment: str
    created_at: datetime
```

Add this field to `PracticeSessionResponse`:

```python
    code_attempts: list[CodeAttemptResponse] = Field(default_factory=list)
```

- [x] **Step 4: Implement code attempts in session service**

In `backend/app/services/practice_session_service.py`, import `CodeAttemptResponse`:

```python
from backend.app.schemas.practice import (
    CodeAttemptResponse,
    CodeSnapshotCreate,
    CodeSnapshotResponse,
    PracticeEventResponse,
    PracticeMessageCreate,
    PracticeMessageResponse,
    PracticeSessionResponse,
    SubmissionFeedbackCreate,
    SubmissionFeedbackResponse,
)
```

Change `get_session_payload`:

```python
async def get_session_payload(
    db: AsyncSession,
    user: AppUser,
    session_id: int,
) -> PracticeSessionResponse:
    practice_session = await _load_session(db, user, session_id)
    events = await list_session_events(db, user, session_id)
    code_attempts = await _list_code_attempts(db, user, session_id)
    return _session_response(
        practice_session,
        events=events,
        code_attempts=code_attempts,
    )
```

In `save_code_snapshot`, after `await db.flush()` for `snapshot`, update the event payload before commit:

```python
    event.payload_json = {
        **event.payload_json,
        "snapshot_id": snapshot.id,
        "quality_status": "pending",
        "quality_comment": "",
    }
```

Change the no-snapshot branch in `record_submission_feedback`:

```python
    if code_snapshot_id is None and payload.result != "ac":
        logger.warning(
            "practice_submission_feedback_rejected user_id=%s session_id=%s "
            "reason=code_snapshot_required_for_submission_feedback",
            user.id,
            session_id,
        )
        raise PracticeSessionError("code_snapshot_required_for_submission_feedback")
    if code_snapshot_id is not None:
        await _load_code_snapshot(db, user, practice_session.id, code_snapshot_id)
```

Add these helpers near `_event_response`:

```python
async def _list_code_attempts(
    db: AsyncSession,
    user: AppUser,
    session_id: int,
) -> list[CodeAttemptResponse]:
    result = await db.execute(
        select(CodeSnapshot, PracticeEvent)
        .join(
            PracticeEvent,
            PracticeEvent.id == CodeSnapshot.event_id,
        )
        .where(
            CodeSnapshot.session_id == session_id,
            CodeSnapshot.user_id == user.id,
        )
        .order_by(CodeSnapshot.created_at, CodeSnapshot.id)
    )
    return [
        _code_attempt_response(snapshot, event)
        for snapshot, event in result.all()
    ]


def _code_attempt_response(
    snapshot: CodeSnapshot,
    event: PracticeEvent,
) -> CodeAttemptResponse:
    payload = event.payload_json if isinstance(event.payload_json, dict) else {}
    quality_status = payload.get("quality_status")
    if quality_status not in {"pending", "needs_fix", "ready_to_submit"}:
        quality_status = "pending"
    quality_comment = payload.get("quality_comment")
    if not isinstance(quality_comment, str):
        quality_comment = ""
    return CodeAttemptResponse.model_validate(
        {
            "snapshot_id": snapshot.id,
            "event_id": event.id,
            "language": snapshot.language,
            "source": snapshot.source,
            "client_revision": snapshot.client_revision,
            "code_hash": snapshot.code_hash,
            "code_preview": _code_preview(snapshot.code_text),
            "quality_status": quality_status,
            "quality_comment": quality_comment,
            "created_at": snapshot.created_at,
        }
    )


def _code_preview(code_text: str) -> str:
    return code_text.strip()[:400]
```

Change `_session_response` signature and payload:

```python
def _session_response(
    practice_session: PracticeSession,
    *,
    events: list[PracticeEventResponse] | None = None,
    code_attempts: list[CodeAttemptResponse] | None = None,
) -> PracticeSessionResponse:
    return PracticeSessionResponse.model_validate(
        {
            "id": practice_session.id,
            "study_plan_id": practice_session.study_plan_id,
            "problem_id": practice_session.problem_id,
            "problem_slug": practice_session.problem_slug,
            "latest_plan_version_id": practice_session.latest_plan_version_id or 0,
            "latest_plan_item_id": practice_session.latest_plan_item_id or 0,
            "training_mode": practice_session.training_mode,
            "phase": practice_session.phase,
            "status": practice_session.status,
            "current_hint_level": practice_session.current_hint_level,
            "visible_hint_gear": _hint_gear_label(practice_session.visible_hint_gear),
            "max_hint_level_used": practice_session.max_hint_level_used or None,
            "attempt_count": practice_session.attempt_count,
            "final_result": practice_session.final_result or None,
            "profile_snapshot": practice_session.profile_snapshot_json,
            "events": events or [],
            "code_attempts": code_attempts or [],
            "created_at": practice_session.created_at,
            "updated_at": practice_session.updated_at,
        }
    )
```

- [x] **Step 5: Run tests to verify Task 1 passes**

Run:

```bash
uv run pytest backend/tests/test_practice_session_service.py::test_session_payload_includes_code_attempts backend/tests/test_practice_session_service.py::test_ac_submission_feedback_without_code_snapshot_is_allowed backend/tests/test_practice_session_service.py::test_submission_feedback_without_any_snapshot_is_rejected -q
```

Expected: PASS. The existing rejection test must still pass for `wa` without a snapshot.

- [x] **Step 6: Commit Task 1**

```bash
git add backend/app/schemas/practice.py backend/app/services/practice_session_service.py backend/tests/test_practice_session_service.py
git commit -m "feat: expose code attempt records"
```

---

### Task 2: Backend Chat Code Extraction During Review

**Files:**
- Create: `backend/app/services/code_attempts.py`
- Modify: `backend/app/services/learning_flows/coach_turn.py`
- Test: `backend/tests/test_learning_flows.py`

- [x] **Step 1: Write failing flow tests**

Add tests to `backend/tests/test_learning_flows.py` near existing `coach_turn` tests:

```python
@pytest.mark.asyncio
async def test_coach_turn_extracts_code_attempt_when_review_code_is_accepted(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from backend.app.models.practice import CodeSnapshot, PracticeEvent

    async with session_factory() as session:
        user = await create_user(session)
        practice_session, user_event, _snapshot = await create_practice_session_with_user_event(
            session,
            user,
            phase="write_code",
            user_intent="code_review",
            content_md=(
                "请 review：\n"
                "```python\n"
                "class Solution:\n"
                "    def twoSum(self, nums, target):\n"
                "        return []\n"
                "```"
            )
        )
        run = await create_coach_run(
            session,
            user,
            practice_session,
            user_event_id=user_event.id,
            trigger="code_review",
        )

        async def publish(_event: LlmRunEvent) -> None:
            return None

        result = await run_coach_turn(
            session,
            user_id=user.id,
            run=run,
            provider=FakeCoachProvider(
                {
                    "phase_after": "review_code",
                    "diagnosed_stuck_point": "implementation_bug",
                    "next_action": "review_code",
                    "reply_md": "这版代码还没有实现哈希表查找。",
                    "should_reveal_solution": False,
                    "code_quality_status": "needs_fix",
                    "code_quality_comment": "当前代码直接返回空列表，不建议提交。",
                }
            ),
            model_name="gpt-test",
            publish=publish,
        )

        assert result["code_attempt_snapshot_id"] is not None
        snapshot = await session.get(CodeSnapshot, result["code_attempt_snapshot_id"])
        assert snapshot is not None
        assert snapshot.source == "chat_review"
        assert snapshot.language == "python3"
        assert "def twoSum" in snapshot.code_text

        event_result = await session.execute(
            select(PracticeEvent).where(
                PracticeEvent.session_id == practice_session.id,
                PracticeEvent.event_type == "code_saved",
            )
        )
        code_event = event_result.scalar_one()
        assert code_event.payload_json["quality_status"] == "needs_fix"
        assert code_event.payload_json["quality_comment"] == "当前代码直接返回空列表，不建议提交。"
    )


@pytest.mark.asyncio
async def test_coach_turn_does_not_extract_code_attempt_outside_review_code(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from backend.app.models.practice import CodeSnapshot

    async with session_factory() as session:
        user = await create_user(session)
        practice_session, user_event, _snapshot = await create_practice_session_with_user_event(
            session,
            user,
            phase="understand_problem",
            user_intent="unknown",
            content_md="我可能会写 for i in range(len(nums))，先讨论思路。",
        )
        run = await create_coach_run(
            session,
            user,
            practice_session,
            user_event_id=user_event.id,
            trigger="unknown",
        )

        async def publish(_event: LlmRunEvent) -> None:
            return None

        await run_coach_turn(
            session,
            user_id=user.id,
            run=run,
            provider=FakeCoachProvider(
                {
                    "phase_after": "understand_problem",
                    "diagnosed_stuck_point": "intent_unclear",
                    "next_action": "ask_clarifying_question",
                    "reply_md": "先说输入输出。",
                    "should_reveal_solution": False,
                }
            ),
            model_name="gpt-test",
            publish=publish,
        )

        result = await session.execute(
            select(CodeSnapshot).where(CodeSnapshot.session_id == practice_session.id)
        )
        assert result.scalars().all() == []
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest backend/tests/test_learning_flows.py::test_coach_turn_extracts_code_attempt_when_review_code_is_accepted backend/tests/test_learning_flows.py::test_coach_turn_does_not_extract_code_attempt_outside_review_code -q
```

Expected: FAIL because no automatic code extraction exists and `review_code` is rejected when no previous code snapshot exists.

- [x] **Step 3: Create code attempt helper module**

Create `backend/app/services/code_attempts.py`:

```python
from __future__ import annotations

import hashlib
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


@dataclass(frozen=True)
class ExtractedCode:
    language: str
    code_text: str


def extract_code_from_message(content_md: str) -> ExtractedCode | None:
    match = _FENCED_CODE_RE.search(content_md)
    if match is not None:
        code_text = match.group("code").strip()
        if _looks_like_code(code_text):
            return ExtractedCode(
                language=_normalize_language(match.group("language")),
                code_text=code_text,
            )
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
```

- [x] **Step 4: Wire helper into coach turn flow**

In `backend/app/services/learning_flows/coach_turn.py`, import helpers:

```python
from backend.app.services.code_attempts import (
    extract_code_from_message,
    persist_review_code_attempt,
    quality_from_decision,
)
```

Extend `COACH_REPLY_INSTRUCTIONS` so model can return quality fields:

```python
    "JSON 字段必须包含：phase_after、diagnosed_stuck_point、next_action、reply_md、"
    "should_reveal_solution。phase_after 只能使用允许状态；reply_md 必须是面向用户的简体中文。"
    "当 phase_after 为 review_code 且用户本轮提供代码时，可以额外返回 code_quality_status "
    "和 code_quality_comment。code_quality_status 只能是 pending、needs_fix 或 ready_to_submit。"
```

After loading `user_event`, compute extracted code:

```python
    extracted_code = (
        extract_code_from_message(user_event.content_md)
        if user_event is not None
        else None
    )
```

Change guard input:

```python
    decision = guard_transition(
        phase_before=practice_session.phase,
        proposed_phase_after=coach_decision["phase_after"],
        has_code=practice_session.latest_code_snapshot_id is not None or extracted_code is not None,
        has_submission_feedback=has_feedback,
        hint_level=practice_session.current_hint_level,
        should_reveal_solution=bool(coach_decision["should_reveal_solution"]),
    )
```

Extend `_coach_input_context` output contract:

```python
            "code_quality_status": "optional pending | needs_fix | ready_to_submit when reviewing code",
            "code_quality_comment": "optional short Chinese review summary",
```

In `_parse_coach_json`, add optional validation before the return:

```python
    code_quality_status = parsed.get("code_quality_status")
    if code_quality_status is not None and code_quality_status not in {"pending", "needs_fix", "ready_to_submit"}:
        raise LearningFlowError("coach_output_invalid")
    code_quality_comment = parsed.get("code_quality_comment")
    if code_quality_comment is not None and not isinstance(code_quality_comment, str):
        raise LearningFlowError("coach_output_invalid")
```

Add these keys to the returned dict:

```python
        "code_quality_status": code_quality_status,
        "code_quality_comment": code_quality_comment.strip() if isinstance(code_quality_comment, str) else "",
```

After `session.add(coach_turn)` and before updating `practice_session.phase`, persist a review attempt:

```python
    code_attempt_snapshot_id: int | None = None
    if (
        decision.accepted
        and decision.phase_after == "review_code"
        and user_event is not None
        and extracted_code is not None
    ):
        quality_status, quality_comment = quality_from_decision(coach_decision)
        snapshot = await persist_review_code_attempt(
            session,
            user_id=user_id,
            practice_session=practice_session,
            user_event=user_event,
            extracted_code=extracted_code,
            quality_status=quality_status,
            quality_comment=quality_comment,
            client_revision=practice_session.attempt_count + 1,
            now=now,
        )
        code_attempt_snapshot_id = snapshot.id
```

Include snapshot id in `coach_turn.response_json`:

```python
            "code_attempt_snapshot_id": code_attempt_snapshot_id,
```

Pass it through `_result_payload` by adding a parameter:

```python
        code_attempt_snapshot_id=code_attempt_snapshot_id,
```

and returning:

```python
        "code_attempt_snapshot_id": code_attempt_snapshot_id,
```

- [x] **Step 5: Run focused backend tests**

Run:

```bash
uv run pytest backend/tests/test_learning_flows.py::test_coach_turn_extracts_code_attempt_when_review_code_is_accepted backend/tests/test_learning_flows.py::test_coach_turn_does_not_extract_code_attempt_outside_review_code backend/tests/test_coach_guard.py -q
```

Expected: PASS.

- [x] **Step 6: Commit Task 2**

```bash
git add backend/app/services/code_attempts.py backend/app/services/learning_flows/coach_turn.py backend/tests/test_learning_flows.py
git commit -m "feat: extract review code attempts"
```

---

### Task 3: Frontend Code Attempt Drawer

**Files:**
- Modify: `frontend/src/api/practice.ts`
- Create: `frontend/src/pages/workspace/CodeAttemptDrawer.tsx`
- Create: `frontend/src/pages/workspace/CodeAttemptDrawer.test.tsx`
- Modify: `frontend/src/styles/app.css`

- [x] **Step 1: Write failing drawer tests**

Create `frontend/src/pages/workspace/CodeAttemptDrawer.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { CodeAttemptDrawer } from './CodeAttemptDrawer'

const attempts = [
  {
    snapshot_id: 1,
    event_id: 11,
    language: 'python3',
    source: 'chat_review',
    client_revision: 1,
    code_hash: 'hash-1',
    code_preview: 'class Solution:\n    pass',
    quality_status: 'pending' as const,
    quality_comment: '',
    created_at: '2026-05-23T00:00:00Z',
  },
  {
    snapshot_id: 2,
    event_id: 12,
    language: 'python3',
    source: 'chat_review',
    client_revision: 2,
    code_hash: 'hash-2',
    code_preview: 'class Solution:\n    def twoSum(self, nums, target):\n        return []',
    quality_status: 'needs_fix' as const,
    quality_comment: '当前代码直接返回空列表，不建议提交。',
    created_at: '2026-05-23T00:01:00Z',
  },
  {
    snapshot_id: 3,
    event_id: 13,
    language: 'python3',
    source: 'chat_review',
    client_revision: 3,
    code_hash: 'hash-3',
    code_preview: 'class Solution:\n    def twoSum(self, nums, target):\n        return [0, 1]',
    quality_status: 'ready_to_submit' as const,
    quality_comment: '可以去 LeetCode 尝试提交。',
    created_at: '2026-05-23T00:02:00Z',
  },
]

describe('CodeAttemptDrawer', () => {
  it('shows attempt statuses and comments', async () => {
    render(<CodeAttemptDrawer open attempts={attempts} onClose={() => undefined} />)

    expect(screen.getByText('第 1 次尝试')).toBeInTheDocument()
    expect(screen.getByText('待评估')).toBeInTheDocument()
    expect(screen.getByText('建议修改')).toBeInTheDocument()
    expect(screen.getByText('可尝试提交')).toBeInTheDocument()

    fireEvent.mouseOver(screen.getAllByLabelText('AI 简评')[0])
    expect(await screen.findByText('当前代码直接返回空列表，不建议提交。')).toBeInTheDocument()
  })

  it('shows an empty state', () => {
    render(<CodeAttemptDrawer open attempts={[]} onClose={() => undefined} />)

    expect(screen.getByText('暂无代码尝试记录')).toBeInTheDocument()
  })
})
```

- [x] **Step 2: Run drawer test to verify it fails**

Run:

```bash
cd frontend && corepack pnpm test -- CodeAttemptDrawer.test.tsx
```

Expected: FAIL because component and types do not exist.

- [x] **Step 3: Extend frontend API types**

In `frontend/src/api/practice.ts`, add:

```ts
export type CodeAttemptQuality = 'pending' | 'needs_fix' | 'ready_to_submit'

export type CodeAttempt = {
  snapshot_id: number
  event_id: number | null
  language: string
  source: string
  client_revision: number
  code_hash: string
  code_preview: string
  quality_status: CodeAttemptQuality
  quality_comment: string
  created_at: string
}
```

Update `CodeSnapshotSource`:

```ts
export type CodeSnapshotSource =
  | 'paste'
  | 'manual_save'
  | 'before_review'
  | 'chat_review'
  | 'before_submit'
  | 'final'
```

Add this field to `PracticeSession`:

```ts
  code_attempts: CodeAttempt[]
```

- [x] **Step 4: Implement CodeAttemptDrawer**

Create `frontend/src/pages/workspace/CodeAttemptDrawer.tsx`:

```tsx
import {
  CheckCircleFilled,
  CloseCircleFilled,
  ExclamationCircleOutlined,
  MinusCircleFilled,
} from '@ant-design/icons'
import { Drawer, Empty, List, Space, Tag, Tooltip, Typography } from 'antd'

import type { CodeAttempt, CodeAttemptQuality } from '../../api/practice'

type CodeAttemptDrawerProps = {
  open: boolean
  attempts: CodeAttempt[]
  onClose: () => void
}

const statusMeta: Record<
  CodeAttemptQuality,
  { label: string; className: string; icon: JSX.Element }
> = {
  pending: {
    label: '待评估',
    className: 'code-attempt-status-pending',
    icon: <MinusCircleFilled aria-hidden="true" />,
  },
  needs_fix: {
    label: '建议修改',
    className: 'code-attempt-status-needs-fix',
    icon: <CloseCircleFilled aria-hidden="true" />,
  },
  ready_to_submit: {
    label: '可尝试提交',
    className: 'code-attempt-status-ready',
    icon: <CheckCircleFilled aria-hidden="true" />,
  },
}

export function CodeAttemptDrawer({
  open,
  attempts,
  onClose,
}: CodeAttemptDrawerProps) {
  return (
    <Drawer title="代码尝试记录" open={open} onClose={onClose} width={520}>
      {attempts.length === 0 ? (
        <Empty description="暂无代码尝试记录" />
      ) : (
        <List
          dataSource={attempts}
          renderItem={(attempt, index) => {
            const meta = statusMeta[attempt.quality_status]
            return (
              <List.Item className="code-attempt-item">
                <div className="code-attempt-row">
                  <Space className="code-attempt-heading" wrap>
                    <Typography.Text strong>{`第 ${index + 1} 次尝试`}</Typography.Text>
                    <Tag className={meta.className} icon={meta.icon}>
                      {meta.label}
                    </Tag>
                    <Typography.Text type="secondary">{attempt.language}</Typography.Text>
                    {attempt.quality_comment ? (
                      <Tooltip title={attempt.quality_comment}>
                        <button
                          aria-label="AI 简评"
                          className="icon-button-plain"
                          type="button"
                        >
                          <ExclamationCircleOutlined aria-hidden="true" />
                        </button>
                      </Tooltip>
                    ) : null}
                  </Space>
                  <pre className="code-attempt-preview">{attempt.code_preview}</pre>
                </div>
              </List.Item>
            )
          }}
        />
      )}
    </Drawer>
  )
}
```

- [x] **Step 5: Add drawer styles**

Append to `frontend/src/styles/app.css`:

```css
.code-attempt-row {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 8px;
}

.code-attempt-heading {
  width: 100%;
}

.code-attempt-preview {
  max-height: 180px;
  margin: 0;
  overflow: auto;
  padding: 10px;
  border: 1px solid #e2e3de;
  border-radius: 6px;
  background: #fafaf7;
  color: #273029;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: 12px;
  white-space: pre-wrap;
}

.code-attempt-status-pending {
  color: #606761;
}

.code-attempt-status-needs-fix {
  color: #9f2a2a;
}

.code-attempt-status-ready {
  color: #167246;
}

.icon-button-plain {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  color: #5e665f;
  background: transparent;
  cursor: pointer;
}

.icon-button-plain:hover {
  color: #0a5f5a;
  background: #eef5f1;
}
```

- [x] **Step 6: Run drawer tests**

Run:

```bash
cd frontend && corepack pnpm test -- CodeAttemptDrawer.test.tsx
```

Expected: PASS.

- [x] **Step 7: Commit Task 3**

```bash
git add frontend/src/api/practice.ts frontend/src/pages/workspace/CodeAttemptDrawer.tsx frontend/src/pages/workspace/CodeAttemptDrawer.test.tsx frontend/src/styles/app.css
git commit -m "feat: add code attempt drawer"
```

---

### Task 4: Chat-first Coach Panel

**Files:**
- Modify: `frontend/src/pages/workspace/CoachPanel.tsx`
- Modify: `frontend/src/pages/workspace/CoachPanel.test.tsx`
- Modify: `frontend/src/styles/app.css`

- [x] **Step 1: Write failing CoachPanel tests**

Update `frontend/src/pages/workspace/CoachPanel.test.tsx` so the expected primary controls are chat-first:

```tsx
it('shows chat-first controls and code attempt entry', () => {
  render(<CoachPanel session={stubSession()} onSessionRefresh={vi.fn()} />)

  expect(screen.getByRole('button', { name: '代码尝试记录' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'LeetCode 已 AC' })).toBeInTheDocument()
  expect(screen.getByLabelText('发送给教练')).toBeInTheDocument()
  expect(screen.queryByText('画像来源')).not.toBeInTheDocument()
  expect(screen.queryByText('事件时间线')).not.toBeInTheDocument()
})

it('marks the session as LeetCode AC and starts summary', async () => {
  practiceApiMock.submitLeetCodeFeedback.mockResolvedValue({
    id: 901,
    result: 'ac',
    event_id: 902,
    code_snapshot_id: null,
    created_at: '2026-05-23T00:00:00Z',
  })
  llmRunMock.startRun.mockResolvedValue({ run_id: 1001 })
  const refresh = vi.fn()

  render(<CoachPanel session={stubSession()} onSessionRefresh={refresh} />)

  fireEvent.click(screen.getByRole('button', { name: 'LeetCode 已 AC' }))

  await waitFor(() =>
    expect(practiceApiMock.submitLeetCodeFeedback).toHaveBeenCalledWith(100, {
      result: 'ac',
      code_snapshot_id: null,
    }),
  )
  expect(llmRunMock.startRun).toHaveBeenCalledWith('coach_summary', {
    session_id: 100,
    trigger: 'request_summary',
  })
  expect(refresh).toHaveBeenCalled()
})
```

Update `stubSession()` to include:

```ts
    code_attempts: [],
```

- [x] **Step 2: Run CoachPanel tests to verify they fail**

Run:

```bash
cd frontend && corepack pnpm test -- CoachPanel.test.tsx
```

Expected: FAIL because current panel still shows profile/timeline sections and has no AC button.

- [x] **Step 3: Implement chat-first CoachPanel**

In `frontend/src/pages/workspace/CoachPanel.tsx`:

1. Import `submitLeetCodeFeedback` and `CodeAttemptDrawer`.
2. Add state:

```tsx
  const [attemptDrawerOpen, setAttemptDrawerOpen] = useState(false)
  const [isMarkingAccepted, setIsMarkingAccepted] = useState(false)
```

3. Add latest attempt id:

```tsx
  const latestAttemptSnapshotId =
    session.code_attempts.length > 0
      ? session.code_attempts[session.code_attempts.length - 1].snapshot_id
      : null
```

4. Add AC handler:

```tsx
  async function handleAccepted() {
    setIsMarkingAccepted(true)
    try {
      await submitLeetCodeFeedback(session.id, {
        result: 'ac',
        code_snapshot_id: latestAttemptSnapshotId,
      })
      onSessionRefresh()
      await llmRun.startRun('coach_summary', {
        session_id: session.id,
        trigger: 'request_summary',
      })
    } catch {
      toast.error('AC 状态记录失败，请稍后重试')
    } finally {
      setIsMarkingAccepted(false)
    }
  }
```

5. Replace profile and technical timeline sections with chat timeline:

```tsx
      <section className="coach-chat-timeline" aria-label="教练聊天记录">
        {session.events.length === 0 ? (
          <Typography.Text type="secondary">暂无训练消息</Typography.Text>
        ) : (
          session.events.map((event) => (
            <div
              className={`coach-chat-message coach-chat-message-${event.role}`}
              key={event.id}
            >
              <Space wrap size={6}>
                <Tag>{event.role === 'assistant' ? '教练' : event.role === 'user' ? '我' : '系统'}</Tag>
                <Tag>{phaseLabel(event.phase)}</Tag>
                {event.visible_hint_gear ? (
                  <Tag>{hintLevelLabel(event.visible_hint_gear)}</Tag>
                ) : null}
              </Space>
              {event.content_md ? (
                <Typography.Paragraph className="coach-chat-content">
                  {event.content_md}
                </Typography.Paragraph>
              ) : (
                <Typography.Text type="secondary">
                  {event.event_type === 'code_saved'
                    ? '已记录一次代码尝试'
                    : event.event_type === 'submission_feedback'
                      ? '已记录 LeetCode 结果'
                      : event.event_type}
                </Typography.Text>
              )}
            </div>
          ))
        )}
      </section>
```

6. Update header actions:

```tsx
          <Button onClick={() => setAttemptDrawerOpen(true)}>代码尝试记录</Button>
          <Button
            type="primary"
            onClick={handleAccepted}
            loading={isMarkingAccepted || llmRun.isRunning}
          >
            LeetCode 已 AC
          </Button>
```

7. Render drawer:

```tsx
      <CodeAttemptDrawer
        open={attemptDrawerOpen}
        attempts={session.code_attempts}
        onClose={() => setAttemptDrawerOpen(false)}
      />
```

- [x] **Step 4: Add chat styles**

Append to `frontend/src/styles/app.css`:

```css
.coach-chat-timeline {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 12px;
  min-height: 420px;
  padding: 4px 0;
}

.coach-chat-message {
  max-width: 92%;
  padding: 12px;
  border: 1px solid #e5e6df;
  border-radius: 8px;
  background: #ffffff;
}

.coach-chat-message-user {
  align-self: flex-end;
  background: #eef5f1;
}

.coach-chat-message-assistant,
.coach-chat-message-system,
.coach-chat-message-tool {
  align-self: flex-start;
}

.coach-chat-content {
  margin: 8px 0 0;
  white-space: pre-wrap;
}
```

- [x] **Step 5: Run CoachPanel tests**

Run:

```bash
cd frontend && corepack pnpm test -- CoachPanel.test.tsx
```

Expected: PASS.

- [x] **Step 6: Commit Task 4**

```bash
git add frontend/src/pages/workspace/CoachPanel.tsx frontend/src/pages/workspace/CoachPanel.test.tsx frontend/src/styles/app.css
git commit -m "feat: make coach panel chat first"
```

---

### Task 5: Workspace Two-column Layout

**Files:**
- Modify: `frontend/src/pages/WorkspacePage.tsx`
- Modify: `frontend/src/pages/WorkspacePage.test.tsx`
- Modify: `frontend/src/styles/app.css`

- [x] **Step 1: Write failing workspace tests**

In `frontend/src/pages/WorkspacePage.test.tsx`, replace code draft tests with:

```tsx
it('renders planned workspace as problem and chat coach only', async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = input.toString()
    if (url === '/api/study-plan/items/40/practice-session') {
      expect(init?.method).toBe('POST')
      return okJson(stubPracticeSession())
    }
    if (url === '/api/problems/two-sum') {
      return okJson(stubProblemDetail('# Two Sum\n\n## 翻译\n\n计划题题面'))
    }
    return new Response('not found', { status: 404 })
  })
  vi.stubGlobal('fetch', fetchMock)

  renderWorkspaceAt('/workspace/items/40', '/workspace/items/:itemId')

  expect(await screen.findByText('计划题题面')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '代码尝试记录' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'LeetCode 已 AC' })).toBeInTheDocument()
  expect(screen.queryByLabelText('代码草稿')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '保存快照' })).not.toBeInTheDocument()
})
```

Update `stubPracticeSession()` with:

```ts
    code_attempts: [],
```

Remove tests that depend on `CodePane` preserving a draft and saving snapshots from the main workspace.

- [x] **Step 2: Run workspace tests to verify they fail**

Run:

```bash
cd frontend && corepack pnpm test -- WorkspacePage.test.tsx
```

Expected: FAIL because `WorkspacePage` still renders `CodePane`.

- [x] **Step 3: Remove main CodePane from workspace**

In `frontend/src/pages/WorkspacePage.tsx`:

1. Remove imports:

```tsx
import { useState } from 'react'
import { CodePane } from './workspace/CodePane'
```

2. Remove `latestCodeSnapshot` state and `latestCodeSnapshotId`.
3. Replace the three `Col lg={8}` layout with:

```tsx
      <Row gutter={[16, 16]} className="workspace-two-column">
        <Col xs={24} lg={10}>
          <ProblemPane markdown={problem?.statement_md} isLoading={isLoading} />
        </Col>
        <Col xs={24} lg={14}>
          {sessionQuery.data ? (
            <CoachPanel
              session={sessionQuery.data}
              onSessionRefresh={() => {
                void sessionQuery.refetch()
              }}
            />
          ) : (
            <div className="workspace-pane">
              <h3>教练</h3>
              <Typography.Text type="secondary">从学习计划进入后启用 AI 教练。</Typography.Text>
            </div>
          )}
        </Col>
      </Row>
```

4. Remove `codeSnapshotId` prop from `CoachPanel` calls.

- [x] **Step 4: Run workspace tests**

Run:

```bash
cd frontend && corepack pnpm test -- WorkspacePage.test.tsx
```

Expected: PASS.

- [x] **Step 5: Commit Task 5**

```bash
git add frontend/src/pages/WorkspacePage.tsx frontend/src/pages/WorkspacePage.test.tsx frontend/src/styles/app.css
git commit -m "feat: simplify workspace to two columns"
```

---

### Task 6: Documentation Sync

**Files:**
- Modify: `docs/prd/ai-coach-workbench-prd.md`
- Modify: `docs/architecture/foundation.md`
- Modify: `docs/project-todolist.md`

- [x] **Step 1: Update workbench PRD**

In `docs/prd/ai-coach-workbench-prd.md`, update section `13.1 工作台布局` to state:

```markdown
做题工作台第一屏采用两栏布局：

- 左侧题面和 LeetCode 原题入口。
- 右侧 ChatGPT 式 AI 教练聊天区。

工作台不再把站内代码草稿作为主卡片。用户代码主要通过聊天中的代码 review 进入系统；当训练流程进入 `review_code` 且本轮消息包含明确代码时，系统自动生成代码尝试记录。
```

In section `13.2 AI 教练区`, add:

```markdown
AI 教练区顶部展示轻量状态：当前阶段、提示档位、训练模式和“代码尝试记录”入口。代码尝试记录中的红灯、绿灯和灰色状态只表示 AI 对代码质量的判断，不代表 LeetCode 判题结果。感叹号悬停展示 AI 对该代码版本的一句短评。

聊天输入区提供“LeetCode 已 AC”动作。用户点击后表示已经在 LeetCode 官网通过本题，系统进入复盘流程；MVP 不要求填写运行时间或内存消耗。
```

- [x] **Step 2: Update foundation architecture**

In `docs/architecture/foundation.md`, replace the current workspace sentence that says “左侧展示题目与代码草稿” with:

```markdown
计划题训练工作台使用 `/workspace/items/:itemId` 路由作为学习计划项入口。前端会通过 practice API 创建或恢复同一个训练会话，左侧展示题面，右侧展示 ChatGPT 式 AI 教练聊天区、训练阶段、提示档位、代码尝试记录入口和 LeetCode 已 AC 动作。代码尝试记录来自 `review_code` 阶段的聊天代码提取，AI 教练消息和复盘通过统一 LLM Run SSE 层执行，前端不直接调用模型。
```

- [x] **Step 3: Update project todo**

In `docs/project-todolist.md`, update the T2/T3/T5 frontend bullets so they mention:

```markdown
- [x] 工作台采用题面 + Chat-first AI 教练两栏布局。
- [x] 工作台展示训练模式、提示档位、AI 教练对话区、代码尝试记录入口和 LeetCode 已 AC 动作。
- [x] 代码尝试记录从 `review_code` 阶段的聊天代码自动提取。
```

- [x] **Step 4: Review docs diff**

Run:

```bash
git diff -- docs/prd/ai-coach-workbench-prd.md docs/architecture/foundation.md docs/project-todolist.md
```

Expected: Diff only updates product and architecture text for the Chat-first workspace.

- [x] **Step 5: Commit Task 6**

```bash
git add docs/prd/ai-coach-workbench-prd.md docs/architecture/foundation.md docs/project-todolist.md
git commit -m "docs: align workspace chat-first flow"
```

---

### Task 7: Full Verification

**Files:**
- Verify all changed files from Tasks 1-6.

- [x] **Step 1: Run backend focused tests**

Run:

```bash
uv run pytest backend/tests/test_practice_session_service.py backend/tests/test_learning_flows.py backend/tests/test_coach_guard.py -q
```

Expected: PASS.

- [x] **Step 2: Run frontend focused tests**

Run:

```bash
cd frontend && corepack pnpm test -- WorkspacePage.test.tsx CoachPanel.test.tsx CodeAttemptDrawer.test.tsx
```

Expected: PASS.

- [x] **Step 3: Run frontend typecheck**

Run:

```bash
cd frontend && corepack pnpm exec tsc -b
```

Expected: PASS.

- [x] **Step 4: Run repository build check**

Run:

```bash
make build
```

Expected: PASS.

- [x] **Step 5: Inspect final git diff**

Run:

```bash
git status --short
git diff --stat
```

Expected: only intended implementation files are modified. Existing unrelated user changes must not be reverted.

---

## Self-review Notes

- Spec coverage: two-column layout is covered by Task 5; ChatGPT-style coach is covered by Task 4; code attempt record generation only in `review_code` is covered by Task 2; red/green/gray status and hover comment are covered by Task 3; LeetCode AC without runtime/memory is covered by Tasks 1 and 4; docs sync is covered by Task 6.
- Database scope: the plan avoids a migration by storing quality status/comment in existing `practice_event.payload_json` and exposing a response model. This is sufficient for MVP and keeps the change reversible.
- Risk to watch during execution: the current worktree already contains unrelated modified files. Stage only files listed in each task.
