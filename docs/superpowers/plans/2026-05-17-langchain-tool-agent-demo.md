# LangChain Tool Agent Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a beginner-friendly LangChain tool agent demo that shows how `@tool` and `create_agent()` replace hand-written tool registration and ReAct loops.

**Architecture:** Create one focused module under `demo/langchain` that defines a deterministic local learning-material tool, builds a LangChain agent, invokes it with a `messages` payload, and extracts the final assistant text. Tests use direct tool invocation and fake injected agents so no real model or network call is required.

**Tech Stack:** Python 3.12, uv, LangChain 1.3, langchain-core, pytest.

---

## File Structure

- Create: `demo/langchain/tool_agent.py`
  - Owns the Tool Agent learning demo.
  - Reuses `build_chat_model()` from `demo/langchain/basic_chain.py`.
  - Defines the local `@tool` learning material tool.
  - Builds a LangChain agent with `create_agent()`.
  - Extracts and prints final assistant text.
- Create: `tests/test_langchain_tool_agent.py`
  - Verifies the local tool through `.invoke(...)`.
  - Verifies final text extraction from LangChain-style results.
  - Verifies `run_demo()` with an injected fake agent.
  - Verifies `main()` joins command-line arguments.

---

### Task 1: Tests For The Tool Agent Contract

**Files:**
- Create: `tests/test_langchain_tool_agent.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_langchain_tool_agent.py` with:

```python
import sys
from pathlib import Path

from langchain_core.messages import AIMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from demo.langchain.tool_agent import (
    DEFAULT_QUESTION,
    extract_final_text,
    get_learning_material,
    run_demo,
)
import demo.langchain.tool_agent as tool_agent


def test_learning_material_tool_returns_topic_specific_content():
    result = get_learning_material.invoke({"topic": "LangChain"})

    assert "LangChain" in result
    assert "LCEL" in result
    assert "Tool Agent" in result


def test_extract_final_text_reads_last_ai_message():
    result = {
        "messages": [
            {"role": "user", "content": "我想入门 LangChain"},
            AIMessage(content="先理解 Chain，再学习 Tool Agent。"),
        ]
    }

    assert extract_final_text(result) == "先理解 Chain，再学习 Tool Agent。"


def test_extract_final_text_handles_missing_messages():
    assert extract_final_text({}) == "未能从 Agent 结果中读取最终回答。"


def test_run_demo_invokes_injected_agent_and_prints_final_text(capsys):
    received_payloads = []

    class FakeAgent:
        def invoke(self, payload):
            received_payloads.append(payload)
            return {"messages": [AIMessage(content="工具已调用，建议先看 basic_chain.py。")]}

    result = run_demo("我想学习 LangChain 工具", agent=FakeAgent())

    captured = capsys.readouterr()
    assert result == "工具已调用，建议先看 basic_chain.py。"
    assert "工具已调用" in captured.out
    assert received_payloads == [
        {"messages": [{"role": "user", "content": "我想学习 LangChain 工具"}]}
    ]


def test_main_uses_cli_question(monkeypatch):
    received_questions = []

    def fake_run_demo(question=DEFAULT_QUESTION):
        received_questions.append(question)
        return "ok"

    monkeypatch.setattr(sys, "argv", ["tool_agent.py", "LangChain", "工具", "入门"])
    monkeypatch.setattr(tool_agent, "run_demo", fake_run_demo)

    tool_agent.main()

    assert received_questions == ["LangChain 工具 入门"]
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```bash
uv run pytest tests/test_langchain_tool_agent.py -q
```

Expected: FAIL with an import error because `demo.langchain.tool_agent` does not exist yet.

---

### Task 2: Implement The Tool Agent Demo

**Files:**
- Create: `demo/langchain/tool_agent.py`

- [ ] **Step 1: Add the implementation**

Create `demo/langchain/tool_agent.py` with:

```python
import sys
from typing import Any

from langchain.agents import create_agent
from langchain_core.tools import tool

from demo.langchain.basic_chain import build_chat_model

DEFAULT_QUESTION = "我想入门 LangChain，有什么资料？"
SYSTEM_PROMPT = (
    "你是一位 Python/AI Agent 学习教练。"
    "当用户询问学习资料、入门路线或主题材料时，优先调用可用工具，"
    "再把工具结果整理成简洁的中文建议。"
)
NO_FINAL_MESSAGE = "未能从 Agent 结果中读取最终回答。"


@tool
def get_learning_material(topic: str) -> str:
    """根据学习主题返回推荐学习材料。"""
    return (
        f"主题：{topic}\n"
        "推荐顺序：\n"
        "1. 先阅读 demo/langchain/basic_chain.py，理解 Prompt -> Model -> Parser。\n"
        "2. 再阅读本 Tool Agent demo，理解 @tool 和 create_agent。\n"
        "3. 最后对照 demo/paradigm/ReActAgent.py，理解 LangChain 如何接管 ReAct 循环。\n"
        "关键词：LCEL、Tool Agent、messages、invoke。"
    )


def build_agent(chat_model: Any | None = None, tools: list[Any] | None = None) -> Any:
    """创建 LangChain Agent。

    在 `demo/paradigm/ToolExecutor.py` 中，工具需要手动注册到字典里；
    在 LangChain 中，`@tool` 会把普通 Python 函数包装成工具对象。

    在 `demo/paradigm/ReActAgent.py` 中，我们手写了 Thought/Action 解析、
    工具查找和 Observation 拼接；`create_agent()` 会负责这类 agent 循环。
    """
    model = chat_model or build_chat_model()
    agent_tools = tools or [get_learning_material]

    return create_agent(
        model=model,
        tools=agent_tools,
        system_prompt=SYSTEM_PROMPT,
    )


def extract_final_text(agent_result: Any) -> str:
    """从 LangChain Agent 的返回结果中取出最后一条消息文本。"""
    if not isinstance(agent_result, dict):
        return NO_FINAL_MESSAGE

    messages = agent_result.get("messages")
    if not messages:
        return NO_FINAL_MESSAGE

    final_message = messages[-1]
    content = getattr(final_message, "content", None)
    if content is None and isinstance(final_message, dict):
        content = final_message.get("content")

    if isinstance(content, str) and content.strip():
        return content

    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                text_parts.append(item["text"])

        joined_text = "".join(text_parts).strip()
        if joined_text:
            return joined_text

    return NO_FINAL_MESSAGE


def run_demo(question: str = DEFAULT_QUESTION, agent: Any | None = None) -> str:
    """运行 Tool Agent demo，并返回最终回答文本。"""
    runnable_agent = agent or build_agent()

    # agent.invoke(...) 和 basic_chain.py 里的 chain.invoke(...) 一样，
    # 都表示“同步跑一次 Runnable”。
    #
    # Agent 的输入使用 messages，是因为 Agent 面向多轮对话。
    # 这里的 user 消息会交给模型；模型可以根据工具名称、参数类型和 docstring
    # 决定是否调用 get_learning_material。
    agent_result = runnable_agent.invoke(
        {"messages": [{"role": "user", "content": question}]}
    )
    final_text = extract_final_text(agent_result)
    print(final_text)
    return final_text


def main() -> None:
    question = " ".join(sys.argv[1:]).strip() or DEFAULT_QUESTION
    run_demo(question)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run focused tests and verify they pass**

Run:

```bash
uv run pytest tests/test_langchain_tool_agent.py -q
```

Expected:

```text
5 passed
```

---

### Task 3: Full Verification

**Files:**
- Existing test suite
- `demo/langchain/tool_agent.py`
- `tests/test_langchain_tool_agent.py`

- [ ] **Step 1: Run all tests**

Run:

```bash
uv run pytest -q
```

Expected: all tests pass, including existing ReAct, LangGraph, basic LangChain chain, and new Tool Agent tests.

- [ ] **Step 2: Run a no-network import smoke test**

Run:

```bash
uv run python -c "from demo.langchain.tool_agent import DEFAULT_QUESTION, get_learning_material; print(DEFAULT_QUESTION); print(get_learning_material.invoke({'topic': 'LangChain'}).splitlines()[0])"
```

Expected:

```text
我想入门 LangChain，有什么资料？
主题：LangChain
```

- [ ] **Step 3: Check changed files**

Run:

```bash
git status --short
```

Expected: changed files for this task include `demo/langchain/tool_agent.py`, `tests/test_langchain_tool_agent.py`, and this implementation plan.

- [ ] **Step 4: Run the real model demo only when external API usage is acceptable**

Run:

```bash
uv run python demo/langchain/tool_agent.py "我想入门 LangChain，有什么资料？"
```

Expected: prints a concise Chinese answer generated by the configured chat model, potentially after calling the local `get_learning_material` tool.
