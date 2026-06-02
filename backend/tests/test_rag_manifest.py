from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.rag.manifest import load_source_manifest


def _write_manifest(path: Path, **overrides: object) -> Path:
    payload: dict[str, object] = {
        "source_name": "manual-two-sum",
        "source_type": "manual_cards",
        "language": "zh",
        "priority": "P0",
        "main_usage": ["pattern_card", "common_bug_card"],
        "local_path": "cards/two-sum.jsonl",
        "license_note": "本地人工整理，用于产品验证",
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_load_source_manifest_accepts_valid_manifest(tmp_path: Path) -> None:
    manifest = load_source_manifest(_write_manifest(tmp_path / "manifest.json"))

    assert manifest.source_name == "manual-two-sum"
    assert manifest.source_type == "manual_cards"
    assert manifest.local_path == "cards/two-sum.jsonl"
    assert manifest.main_usage == ["pattern_card", "common_bug_card"]


def test_load_source_manifest_requires_license_note(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path / "manifest.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["license_note"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_source_manifest(path)


def test_load_source_manifest_rejects_unsupported_source_type(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        load_source_manifest(
            _write_manifest(tmp_path / "manifest.json", source_type="unknown"),
        )


def test_load_source_manifest_rejects_absolute_local_path(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        load_source_manifest(
            _write_manifest(
                tmp_path / "manifest.json",
                local_path="/home/alice/private/cards.jsonl",
            ),
        )
