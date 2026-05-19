# LangGraph Basic Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a teaching-oriented LangGraph demo that runs locally and explains the core graph workflow.

**Architecture:** Create one focused demo module under `demo/graph` with reusable graph-building functions and a direct script entry point. Add pytest coverage that invokes the compiled graph and verifies both conditional branches.

**Tech Stack:** Python 3.12, LangGraph, pytest, uv.

---

### Task 1: Tests For The Demo Contract

**Files:**
- Create: `tests/test_basic_learning_graph.py`

- [x] **Step 1: Write failing tests**

```python
from demo.graph.basic_learning_graph import build_learning_graph, run_demo


def test_beginner_topic_skips_review_materials():
    graph = build_learning_graph()

    result = graph.invoke({"topic": "我想入门 LangGraph"})

    assert result["difficulty"] == "beginner"
    assert result["review_materials"] == []
    assert "LangGraph" in result["summary"]


def test_advanced_topic_adds_review_materials():
    graph = build_learning_graph()

    result = graph.invoke({"topic": "深入理解 LangGraph checkpoint 和 conditional edge"})

    assert result["difficulty"] == "advanced"
    assert "先复习 StateGraph 的状态传递规则" in result["review_materials"]
    assert "复习材料" in result["summary"]


def test_run_demo_returns_final_state():
    result = run_demo("LangGraph 入门")

    assert result["topic"] == "LangGraph 入门"
    assert len(result["learning_plan"]) == 4
```

- [x] **Step 2: Run tests and verify they fail**

Run: `uv run pytest tests/test_basic_learning_graph.py -q`

Expected: FAIL because `demo.graph.basic_learning_graph` does not exist yet.

### Task 2: Implement The LangGraph Demo

**Files:**
- Create: `demo/graph/basic_learning_graph.py`

- [x] **Step 1: Add the implementation**

Create `LearningState`, node functions, `build_learning_graph()`, `run_demo()`, and `main()`.

- [x] **Step 2: Run focused tests**

Run: `uv run pytest tests/test_basic_learning_graph.py -q`

Expected: 3 passed.

- [x] **Step 3: Run the script**

Run: `uv run python demo/graph/basic_learning_graph.py`

Expected: It prints the topic, difficulty, learning plan, optional review materials, and summary.

### Task 3: Full Verification

**Files:**
- Existing tests and new demo files.

- [x] **Step 1: Run all tests**

Run: `uv run pytest -q`

Expected: All tests pass.

- [x] **Step 2: Check changed files**

Run: `git status --short`

Expected: The new docs, demo file, and test file are changed for this task.

Note: Full verification also exposed an existing import/behavior mismatch in the ReAct demo tests. The implementation added `demo/ReActAgent.py` as a compatibility entry point and updated `demo/paradigm/ReActAgent.py` so time-sensitive questions cannot finish before a `Search` action.
