from __future__ import annotations

from backend.app.schemas.llm_run import LlmRunCreateRequest
from backend.app.services.llm_run_events import LlmRunEvent, encode_sse


def test_llm_run_create_request_accepts_known_kind() -> None:
    payload = LlmRunCreateRequest(
        kind="goal_plan_generate",
        payload={"draft_id": 3},
    )

    assert payload.kind == "goal_plan_generate"
    assert payload.payload["draft_id"] == 3


def test_encode_sse_formats_named_event() -> None:
    event = LlmRunEvent(
        name="progress",
        data={"run_id": 7, "stage": "validating", "message": "正在校验题库"},
    )

    assert encode_sse(event) == (
        'event: progress\n'
        'data: {"run_id":7,"stage":"validating","message":"正在校验题库"}\n\n'
    )
