from __future__ import annotations

from backend.app.cli.rag_ingest import build_parser


def test_rag_ingest_cli_parser_accepts_manifest_and_no_embeddings() -> None:
    args = build_parser().parse_args(
        ["--manifest", "data/sources/rag/manifest.json", "--no-embeddings"]
    )

    assert args.manifest == "data/sources/rag/manifest.json"
    assert args.no_embeddings is True
