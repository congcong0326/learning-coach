from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.core.config import settings
from backend.app.rag.embedding import OpenAICompatibleEmbeddingProvider
from backend.app.rag.ingest import ingest_manifest
from backend.app.rag.manifest import load_source_manifest

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import local RAG knowledge materials.")
    parser.add_argument("--manifest", required=True, help="Path to source manifest JSON.")
    parser.add_argument(
        "--root-dir",
        default=".",
        help="Root directory used to resolve manifest.local_path.",
    )
    parser.add_argument(
        "--no-embeddings",
        action="store_true",
        help="Import metadata and chunks without calling an embedding provider.",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    manifest = load_source_manifest(Path(args.manifest))
    provider = None
    if not args.no_embeddings and settings.rag_embedding_api_key:
        provider = OpenAICompatibleEmbeddingProvider(
            api_key=settings.rag_embedding_api_key,
            base_url=settings.rag_embedding_base_url,
            model_name=settings.rag_embedding_model,
            dimensions=settings.rag_embedding_dimensions,
        )
    elif not args.no_embeddings:
        logger.warning(
            "rag_embedding_skipped reason=missing_rag_embedding_api_key source_name=%s",
            manifest.source_name,
        )
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            summary = await ingest_manifest(
                session,
                manifest=manifest,
                root_dir=Path(args.root_dir),
                embedding_provider=provider,
            )
            await session.commit()
            print(
                "rag_ingest_summary "
                f"source_name={manifest.source_name} "
                f"doc_id={summary.doc_id} "
                f"chunks_upserted={summary.chunks_upserted}"
            )
    finally:
        await engine.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
