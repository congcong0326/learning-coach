# LangChain Basic Chain Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a beginner-friendly LangChain basic chain demo that contrasts with the existing direct model API examples.

**Architecture:** Create one focused module under `demo/langchain` that exposes `build_chat_model()`, `build_chain()`, `run_demo()`, and `main()`. The chain is `ChatPromptTemplate -> chat model -> StrOutputParser`, with dependency injection so tests can use fake runnables and avoid real model calls.

**Tech Stack:** Python 3.12, uv, LangChain, langchain-openai, python-dotenv, pytest.

---

## File Structure

- Create: `demo/langchain/basic_chain.py`
  - Owns the LangChain beginner demo.
  - Reads the existing `LLM_*` environment variables.
  - Builds the prompt/model/parser chain.
  - Provides a script entry point.
- Create: `tests/test_langchain_basic_chain.py`
  - Verifies chain composition and `run_demo()` without calling a real model.
  - Verifies `main()` passes CLI text into `run_demo()`.
- Modify: `pyproject.toml`
  - Add `langchain` and `langchain-openai` as runtime dependencies through `uv add`.
- Modify: `uv.lock`
  - Let `uv add` update the lockfile.

---

### Task 1: Add LangChain Dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`

- [x] **Step 1: Add runtime dependencies with uv**

Run:

```bash
uv add langchain langchain-openai
```

Expected: `pyproject.toml` gains `langchain` and `langchain-openai` under `[project].dependencies`, and `uv.lock` is updated.

- [x] **Step 2: Verify dependency metadata**

Run:

```bash
uv run python -c "import langchain; import langchain_openai; print('langchain ready')"
```

Expected:

```text
langchain ready
```

---

### Task 2: Tests For The Basic Chain Contract

**Files:**
- Create: `tests/test_langchain_basic_chain.py`

- [x] **Step 1: Write failing tests**

Create `tests/test_langchain_basic_chain.py` with:

```python
import sys
from pathlib import Path

from langchain_core.runnables import RunnableLambda

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from demo.langchain.basic_chain import DEFAULT_TOPIC, build_chain, run_demo
import demo.langchain.basic_chain as basic_chain


def test_build_chain_composes_prompt_model_and_parser():
    def fake_model(prompt_value):
        prompt_text = prompt_value.to_string()

        assert "LangChain" in prompt_text
        assert "3 个入门步骤" in prompt_text
        return "1. 先理解 chain 的输入和输出。"

    chain = build_chain(chat_model=RunnableLambda(fake_model))

    result = chain.invoke({"topic": "LangChain"})

    assert result == "1. 先理解 chain 的输入和输出。"


def test_run_demo_invokes_injected_chain(capsys):
    received_payloads = []

    class FakeChain:
        def invoke(self, payload):
            received_payloads.append(payload)
            return f"学习建议：{payload['topic']}"

    result = run_demo("PromptTemplate", chain=FakeChain())

    captured = capsys.readouterr()
    assert result == "学习建议：PromptTemplate"
    assert "学习建议：PromptTemplate" in captured.out
    assert received_payloads == [{"topic": "PromptTemplate"}]


def test_main_uses_cli_topic(monkeypatch):
    received_topics = []

    def fake_run_demo(topic=DEFAULT_TOPIC):
        received_topics.append(topic)
        return "ok"

    monkeypatch.setattr(sys, "argv", ["basic_chain.py", "LangChain", "入门"])
    monkeypatch.setattr(basic_chain, "run_demo", fake_run_demo)

    basic_chain.main()

    assert received_topics == ["LangChain 入门"]
```

- [x] **Step 2: Run focused tests and verify they fail**

Run:

```bash
uv run pytest tests/test_langchain_basic_chain.py -q
```

Expected: FAIL with an import error because `demo.langchain.basic_chain` does not exist yet.

---

### Task 3: Implement The Basic Chain Demo

**Files:**
- Create: `demo/langchain/basic_chain.py`

- [x] **Step 1: Add the implementation**

Create `demo/langchain/basic_chain.py` with:

```python
import os
import sys
from typing import Any

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

load_dotenv()

DEFAULT_TOPIC = "LangChain 入门"


def build_chat_model() -> ChatOpenAI:
    """从现有 LLM_* 环境变量创建 LangChain 的 ChatOpenAI 模型。"""
    model = os.getenv("LLM_MODEL_ID")
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    timeout = int(os.getenv("LLM_TIMEOUT", "60"))

    if not all([model, api_key, base_url]):
        raise ValueError("模型ID、API密钥和服务地址必须被提供或在.env文件中定义。")

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        temperature=0,
    )


def build_chain(chat_model: Any | None = None) -> Runnable[dict[str, str], str]:
    """构建最基础的 LangChain 链。

    在 `demo/paradigm/HelloAgentsLLM.py` 里，我们需要手动拼 messages，
    然后调用 OpenAI 客户端，再从响应对象里取出文本。

    LangChain 把这三步拆成可组合组件：
    1. ChatPromptTemplate 负责把变量渲染成聊天消息。
    2. ChatOpenAI 负责调用兼容 OpenAI 的聊天模型。
    3. StrOutputParser 负责把模型消息解析成普通字符串。

    `|` 是 LangChain Expression Language 的管道写法，
    表示把前一个组件的输出交给下一个组件。
    """
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是一位擅长拆解学习路径的 Python/AI Agent 教练。"
                "回答要简洁、具体、适合初学者。",
            ),
            ("user", "我想学习 {topic}。请给我 3 个入门步骤，每步一句话。"),
        ]
    )
    model = chat_model or build_chat_model()

    return prompt | model | StrOutputParser()


def run_demo(topic: str = DEFAULT_TOPIC, chain: Any | None = None) -> str:
    """运行 demo，并返回模型生成的文本，方便脚本和测试复用。"""
    runnable = chain or build_chain()
    response_text = runnable.invoke({"topic": topic})
    print(response_text)
    return response_text


def main() -> None:
    topic = " ".join(sys.argv[1:]).strip() or DEFAULT_TOPIC
    run_demo(topic)


if __name__ == "__main__":
    main()
```

- [x] **Step 2: Run focused tests and verify they pass**

Run:

```bash
uv run pytest tests/test_langchain_basic_chain.py -q
```

Expected:

```text
3 passed
```

---

### Task 4: Full Verification

**Files:**
- Existing test suite
- `demo/langchain/basic_chain.py`
- `tests/test_langchain_basic_chain.py`
- `pyproject.toml`
- `uv.lock`

- [x] **Step 1: Run all tests**

Run:

```bash
uv run pytest -q
```

Expected: all tests pass, including the existing ReAct and LangGraph tests plus the new LangChain tests.

- [x] **Step 2: Run a no-network import smoke test**

Run:

```bash
uv run python -c "from demo.langchain.basic_chain import DEFAULT_TOPIC, build_chain, run_demo; print(DEFAULT_TOPIC)"
```

Expected:

```text
LangChain 入门
```

- [ ] **Step 3: Optionally run the real model demo when `.env` is configured**

Run:

```bash
uv run python demo/langchain/basic_chain.py LangChain入门
```

Expected: prints three concise Chinese beginner steps generated by the configured chat model.

- [x] **Step 4: Check changed files**

Run:

```bash
git status --short
```

Expected: changed files for this task include `pyproject.toml`, `uv.lock`, `demo/langchain/basic_chain.py`, `tests/test_langchain_basic_chain.py`, and this implementation plan.
