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
