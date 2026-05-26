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


def test_extract_code_from_message_uses_direct_code_without_fence() -> None:
    extracted = extract_code_from_message(
        "class Solution:\n"
        "    def twoSum(self, nums, target):\n"
        "        seen = {}\n"
        "        return []"
    )

    assert extracted is not None
    assert extracted.language == "python3"
    assert extracted.code_text == (
        "class Solution:\n"
        "    def twoSum(self, nums, target):\n"
        "        seen = {}\n"
        "        return []"
    )


def test_extract_code_from_message_infers_java_from_unlabeled_fenced_block() -> None:
    extracted = extract_code_from_message(
        "请 review：\n"
        "```\n"
        "class Solution {\n"
        "    public boolean isPalindrome(String s) {\n"
        "        int left = 0;\n"
        "        int right = s.length() - 1;\n"
        "        return true;\n"
        "    }\n"
        "}\n"
        "```"
    )

    assert extracted is not None
    assert extracted.language == "java"


def test_extract_code_from_message_infers_java_from_direct_code_without_fence() -> None:
    extracted = extract_code_from_message(
        "class Solution {\n"
        "    public boolean isPalindrome(String s) {\n"
        "        int left = 0;\n"
        "        int right = s.length() - 1;\n"
        "        return true;\n"
        "    }\n"
        "}"
    )

    assert extracted is not None
    assert extracted.language == "java"


def test_extract_code_from_message_omits_surrounding_chat_without_fence() -> None:
    extracted = extract_code_from_message(
        "这是我的解答思路：\n"
        "class Solution:\n"
        "    def twoSum(self, nums, target):\n"
        "        seen = {}\n"
        "        for index, num in enumerate(nums):\n"
        "            complement = target - num\n"
        "            if complement in seen:\n"
        "                return [seen[complement], index]\n"
        "            seen[num] = index\n"
        "        return []\n"
        "请帮我看看这版代码还有没有问题。"
    )

    assert extracted is not None
    assert extracted.code_text == (
        "class Solution:\n"
        "    def twoSum(self, nums, target):\n"
        "        seen = {}\n"
        "        for index, num in enumerate(nums):\n"
        "            complement = target - num\n"
        "            if complement in seen:\n"
        "                return [seen[complement], index]\n"
        "            seen[num] = index\n"
        "        return []"
    )
    assert "这是我的解答思路" not in extracted.code_text
    assert "请帮我看看" not in extracted.code_text


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


def test_extract_code_from_message_returns_none_for_incomplete_fenced_block() -> None:
    extracted = extract_code_from_message(
        "请 review：\n"
        "```python\n"
        "class Solution:\n"
        "    def twoSum(self, nums, target):\n"
        "        return []\n"
    )

    assert extracted is None


def test_extract_code_from_message_returns_none_for_malformed_mixed_fences() -> None:
    extracted = extract_code_from_message(
        "请 review：\n"
        "```python\n"
        "class Solution:\n"
        "    def solve(self):\n"
        "        return 1\n"
        "这中间是说明文字\n"
        "```text\n"
        "不是代码\n"
        "```\n"
    )

    assert extracted is None
