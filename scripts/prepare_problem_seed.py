from __future__ import annotations

import argparse
import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SOLUTION_HEADING = "\n## solution 题解"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SplitMarkdownResult:
    statement_md: str
    had_solution_section: bool


@dataclass(frozen=True)
class PrepareStats:
    problem_count: int
    skipped_count: int


def split_statement_markdown(markdown: str) -> SplitMarkdownResult:
    # Public seed data keeps the problem statement only; solution text stays out
    # of the app so the coach can guide practice instead of leaking answers.
    index = markdown.find(SOLUTION_HEADING)
    if index < 0:
        return SplitMarkdownResult(markdown.rstrip(), False)
    return SplitMarkdownResult(markdown[:index].rstrip(), True)


def _source_commit(source_dir: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(source_dir), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def _question(json_path: Path) -> dict[str, Any]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    return payload["data"]["question"]


def _metadata(question: dict[str, Any]) -> dict[str, Any]:
    python3_snippet = ""
    code_snippets = question.get("codeSnippets") or []
    for snippet in code_snippets:
        if snippet.get("langSlug") == "python3":
            python3_snippet = snippet.get("code", "")
            break

    similar_questions = question.get("similarQuestions") or "[]"
    function_meta = question.get("metaData") or "{}"

    return {
        "topic_tags": [
            {
                "name": tag.get("name", ""),
                "slug": tag.get("slug", ""),
                "translated_name": tag.get("translatedName") or "",
            }
            for tag in question.get("topicTags", [])
        ],
        "similar_questions": json.loads(similar_questions),
        "sample_test_case": question.get("sampleTestCase") or "",
        "function_meta": json.loads(function_meta),
        "python3_snippet": python3_snippet,
    }


def _problem_record(md_path: Path, json_path: Path) -> dict[str, Any]:
    question = _question(json_path)
    split = split_statement_markdown(md_path.read_text(encoding="utf-8"))
    slug = question["titleSlug"]
    return {
        "frontend_id": question["questionFrontendId"],
        "slug": slug,
        "title": question["title"],
        "translated_title": question.get("translatedTitle") or "",
        "difficulty": question["difficulty"],
        "statement_md": split.statement_md,
        "leetcode_url": f"https://leetcode-cn.com/problems/{slug}/",
        "is_paid_only": bool(question.get("isPaidOnly", False)),
        "metadata": _metadata(question),
    }


def prepare_problem_seed(source_dir: Path, output_dir: Path) -> PrepareStats:
    md_dir = source_dir / "problemset_md"
    json_dir = source_dir / "problemset"
    if not md_dir.exists() or not json_dir.exists():
        raise FileNotFoundError(
            f"Expected problemset_md and problemset under {source_dir}"
        )

    logger.info(
        "problem seed preparation started source_dir=%s output_dir=%s",
        source_dir,
        output_dir,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    skipped_count = 0
    for md_path in sorted(md_dir.glob("*.md")):
        json_path = json_dir / f"{md_path.stem}.json"
        if not json_path.exists():
            skipped_count += 1
            continue
        records.append(_problem_record(md_path, json_path))
    logger.info(
        "problem seed preparation parsed records=%s skipped=%s",
        len(records),
        skipped_count,
    )

    with (output_dir / "problems.jsonl").open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    (output_dir / "problem_categories.jsonl").write_text("", encoding="utf-8")
    (output_dir / "problem_category_items.jsonl").write_text("", encoding="utf-8")
    manifest = {
        "dataset": "leetcode-problemset",
        "source_repo": "https://github.com/fishjar/leetcode-problemset",
        "source_commit": _source_commit(source_dir),
        "generated_at": datetime.now(UTC).isoformat(),
        "problem_count": len(records),
        "category_count": 0,
        "category_item_count": 0,
        "schema_version": 1,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info(
        "problem seed preparation completed problem_count=%s skipped=%s",
        len(records),
        skipped_count,
    )
    return PrepareStats(problem_count=len(records), skipped_count=skipped_count)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stats = prepare_problem_seed(args.source, args.output)
    print(f"Prepared {stats.problem_count} problems; skipped {stats.skipped_count}")


if __name__ == "__main__":
    main()
