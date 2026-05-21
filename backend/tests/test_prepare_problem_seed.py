import json
from pathlib import Path

from scripts.prepare_problem_seed import prepare_problem_seed, split_statement_markdown


def test_split_statement_markdown_removes_solution_section() -> None:
    markdown = "# Two Sum\n\nstatement\n\n## solution 题解\n\nanswer"

    result = split_statement_markdown(markdown)

    assert result.statement_md == "# Two Sum\n\nstatement"
    assert result.had_solution_section is True


def test_split_statement_markdown_keeps_full_text_without_solution() -> None:
    markdown = "# Title\n\nstatement only"

    result = split_statement_markdown(markdown)

    assert result.statement_md == markdown
    assert result.had_solution_section is False


def test_prepare_problem_seed_writes_static_problem_jsonl(tmp_path: Path) -> None:
    source = tmp_path / "leetcode-problemset"
    md_dir = source / "problemset_md"
    json_dir = source / "problemset"
    md_dir.mkdir(parents=True)
    json_dir.mkdir(parents=True)
    (source / ".git").mkdir()
    (source / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (md_dir / "0000001.two-sum.md").write_text(
        "# Two Sum 两数之和\n\n题面\n\n## solution 题解\n\n答案",
        encoding="utf-8",
    )
    (json_dir / "0000001.two-sum.json").write_text(
        json.dumps(
            {
                "data": {
                    "question": {
                        "questionFrontendId": "1",
                        "title": "Two Sum",
                        "translatedTitle": "两数之和",
                        "titleSlug": "two-sum",
                        "difficulty": "Easy",
                        "isPaidOnly": False,
                        "topicTags": [
                            {
                                "name": "Array",
                                "slug": "array",
                                "translatedName": "数组",
                            }
                        ],
                        "similarQuestions": "[]",
                        "codeSnippets": [
                            {
                                "langSlug": "python3",
                                "code": "class Solution:\n    def twoSum(self):",
                            }
                        ],
                        "sampleTestCase": "[2,7,11,15]\n9",
                        "metaData": '{"name":"twoSum"}',
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "seed"

    stats = prepare_problem_seed(source, output)

    assert stats.problem_count == 1
    problem = json.loads((output / "problems.jsonl").read_text().splitlines()[0])
    assert problem["slug"] == "two-sum"
    assert problem["statement_md"] == "# Two Sum 两数之和\n\n题面"
    assert "solution" not in problem
    assert problem["metadata"]["python3_snippet"].startswith("class Solution")
    assert (output / "problem_categories.jsonl").read_text() == ""
    assert (output / "problem_category_items.jsonl").read_text() == ""


def test_prepare_problem_seed_treats_null_code_snippets_as_empty(
    tmp_path: Path,
) -> None:
    source = tmp_path / "leetcode-problemset"
    md_dir = source / "problemset_md"
    json_dir = source / "problemset"
    md_dir.mkdir(parents=True)
    json_dir.mkdir(parents=True)
    (md_dir / "0001724.customer-who-visited.md").write_text(
        "# Customer Who Visited\n\n题面",
        encoding="utf-8",
    )
    (json_dir / "0001724.customer-who-visited.json").write_text(
        json.dumps(
            {
                "data": {
                    "question": {
                        "questionFrontendId": "1724",
                        "title": "Customer Who Visited",
                        "translatedTitle": "访问客户",
                        "titleSlug": "customer-who-visited",
                        "difficulty": "Easy",
                        "isPaidOnly": False,
                        "topicTags": [],
                        "similarQuestions": "[]",
                        "codeSnippets": None,
                        "sampleTestCase": "",
                        "metaData": "{}",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "seed"

    stats = prepare_problem_seed(source, output)

    assert stats.problem_count == 1
    problem = json.loads((output / "problems.jsonl").read_text().splitlines()[0])
    assert problem["metadata"]["python3_snippet"] == ""
