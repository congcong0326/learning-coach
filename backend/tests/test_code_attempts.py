from backend.app.services.code_attempts import extract_code_from_message


def test_extract_code_from_message_uses_first_fenced_block_that_looks_like_code() -> None:
    extracted = extract_code_from_message(
        "先看样例输入：\n"
        "```text\n"
        "nums = [2, 7, 11, 15]\n"
        "target = 9\n"
        "```\n"
        "真正要 review 的代码在这里：\n"
        "```python\n"
        "class Solution:\n"
        "    def twoSum(self, nums, target):\n"
        "        return []\n"
        "```"
    )

    assert extracted is not None
    assert extracted.language == "python3"
    assert extracted.code_text == (
        "class Solution:\n"
        "    def twoSum(self, nums, target):\n"
        "        return []"
    )


def test_extract_code_from_message_returns_none_for_fenced_non_code_only() -> None:
    extracted = extract_code_from_message(
        "请不要把整段消息当代码保存：\n"
        "def not_code\n"
        "```text\n"
        "nums = [2, 7, 11, 15]\n"
        "target = 9\n"
        "```\n"
        "return not_code\n"
    )

    assert extracted is None
