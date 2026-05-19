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

    # 这里的 `|` 不是普通的“按位或”，而是 LangChain Expression Language
    # 重载后的管道语法。它表示：
    #   先用 prompt 把 {"topic": "..."} 渲染成聊天消息，
    #   再把消息交给 model 调用大模型，
    #   最后用 StrOutputParser() 把模型返回的消息对象转成字符串。
    # 等价理解：chain = prompt -> model -> output_parser。
    return prompt | model | StrOutputParser()


def run_demo(topic: str = DEFAULT_TOPIC, chain: Any | None = None) -> str:
    """运行 demo，并返回模型生成的文本，方便脚本和测试复用。"""
    runnable = chain or build_chain()

    # invoke(...) 是 LangChain Runnable 的同步执行方法，意思是“用这个输入跑一次链”。
    # 这里传入的字典会先进入 chain 的第一个组件 prompt：
    #   {"topic": topic}
    # 其中 key "topic" 会对应替换 ChatPromptTemplate 里的 {topic} 占位符。
    # 后面的 model 和 StrOutputParser 会依次接收上一步的输出。
    response_text = runnable.invoke({"topic": topic})
    print(response_text)
    return response_text


def main() -> None:
    topic = " ".join(sys.argv[1:]).strip() or DEFAULT_TOPIC
    run_demo(topic)


if __name__ == "__main__":
    main()
