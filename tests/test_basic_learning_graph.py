import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
