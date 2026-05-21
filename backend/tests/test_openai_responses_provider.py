from __future__ import annotations

from types import SimpleNamespace

from backend.app.services.llm_providers.openai_responses import event_to_text_delta


def test_event_to_text_delta_reads_response_text_delta() -> None:
    event = SimpleNamespace(type="response.output_text.delta", delta="你好")

    assert event_to_text_delta(event) == "你好"


def test_event_to_text_delta_ignores_non_text_events() -> None:
    event = SimpleNamespace(type="response.created")

    assert event_to_text_delta(event) == ""
