import sys
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class LearningState(TypedDict, total=False):
    """图在节点之间传递的共享状态。

    LangGraph 的每个节点都会收到当前 state，并返回一个 dict 来更新 state。
    total=False 表示初始输入可以只给一部分字段，例如只传入 topic。
    """

    topic: str
    difficulty: Literal["beginner", "advanced"]
    learning_plan: list[str]
    review_materials: list[str]
    summary: str


def initialize_learning_goal(state: LearningState) -> LearningState:
    """第一个节点：清洗输入，并准备后续节点要使用的基础字段。"""
    topic = state.get("topic", "").strip() or "LangGraph 入门"

    return {
        "topic": topic,
        "learning_plan": [],
        "review_materials": [],
    }


def classify_difficulty(state: LearningState) -> LearningState:
    """第二个节点：根据关键词模拟一个简单的难度判断。

    真实项目里，这一步通常可以换成 LLM 调用、分类模型或业务规则。
    入门 demo 里先用确定性规则，方便你专注理解图的流转。

    注意：节点返回的新 dict 不会把整个 state 替换掉。
    在 LangGraph 中，节点返回的是“本节点想更新的字段”。
    例如这里返回 {"difficulty": "beginner"}，LangGraph 会把它合并回原 state：

        原 state:
            {"topic": "我想入门 LangGraph", "learning_plan": [], "review_materials": []}

        本节点返回:
            {"difficulty": "beginner"}

        合并后的 state:
            {
                "topic": "我想入门 LangGraph",
                "learning_plan": [],
                "review_materials": [],
                "difficulty": "beginner",
            }
    """
    # state["topic"] 表示从共享 state 里取出 topic 字段。
    # .lower() 会把英文转成小写，这样 "Checkpoint" 和 "checkpoint" 都能匹配。
    topic = state["topic"].lower()

    # 元组 tuple，保存一组“看起来更偏高级主题”的关键词。
    advanced_keywords = (
        "深入",
        "checkpoint",
        "conditional",
        "条件",
        "持久化",
        "状态管理",
        "stream",
    )

    # difficulty: Literal["beginner", "advanced"] 是类型注解。
    # 它告诉编辑器和类型检查工具：difficulty 只应该是这两个字符串之一。
    #
    # 下面这段是 Python 的条件表达式，格式是：
    #     A if 条件 else B
    # 含义是：
    #     如果条件成立，结果就是 A；否则结果就是 B。
    #
    # any(...) 会检查括号里的多个判断，只要有一个为 True，结果就是 True。
    #
    # keyword in topic for keyword in advanced_keywords 是生成器表达式：
    #     依次从 advanced_keywords 里取出 keyword，
    #     判断这个 keyword 是否出现在 topic 字符串中。
    #
    # 合起来就是：
    #     如果 topic 包含任意一个高级关键词，difficulty 就是 "advanced"；
    #     否则 difficulty 就是 "beginner"。
    difficulty: Literal["beginner", "advanced"] = (
        "advanced"
        if any(keyword in topic for keyword in advanced_keywords)
        else "beginner"
    )

    # 这里只返回本节点新增或修改的字段。LangGraph 会负责把它合并回完整 state。
    return {"difficulty": difficulty}


def create_learning_plan(state: LearningState) -> LearningState:
    """第三个节点：根据当前 state 生成学习步骤。"""
    topic = state["topic"]

    return {
        "learning_plan": [
            f"明确学习目标：{topic}",
            "理解 State：图中所有节点共享并逐步更新的数据结构",
            "理解 Node：每个节点都是一个接收 state、返回局部更新的函数",
            "理解 Edge：普通边负责顺序流转，条件边负责分支选择",
        ]
    }


def route_by_difficulty(
    state: LearningState,
) -> Literal["needs_review", "ready_to_summarize"]:
    """条件边的路由函数：只决定下一步走哪条边，不直接修改 state。"""
    if state["difficulty"] == "advanced":
        return "needs_review"
    return "ready_to_summarize"


def add_review_materials(state: LearningState) -> LearningState:
    """高级主题会额外经过这个节点，补充复习材料。"""
    return {
        "review_materials": [
            "先复习 StateGraph 的状态传递规则",
            "再看 add_conditional_edges 如何把路由结果映射到节点",
            "最后理解 checkpoint 如何保存和恢复图的执行状态",
        ]
    }


def summarize_result(state: LearningState) -> LearningState:
    """最后一个节点：把前面节点写入 state 的内容汇总成最终输出。"""
    summary = f"已为「{state['topic']}」生成 {state['difficulty']} 难度学习计划。"
    if state["review_materials"]:
        summary += " 该主题包含复习材料。"

    return {"summary": summary}


def build_learning_graph() -> Any:
    """构建并编译 LangGraph。

    这部分展示 LangGraph 最核心的 API：
    1. StateGraph(LearningState)：声明图使用哪种 state
    2. add_node：注册节点
    3. add_edge：注册固定流转关系
    4. add_conditional_edges：注册条件分支
    5. compile：编译成可执行对象

    这个 demo 的图结构如下：

        START
          |
          v
        initialize_learning_goal
          |
          v
        classify_difficulty
          |
          v
        create_learning_plan
          |
          +-- difficulty == advanced --> add_review_materials --+
          |                                                      |
          +-- difficulty == beginner ----------------------------+
                                                                 |
                                                                 v
                                                        summarize_result
                                                                 |
                                                                 v
                                                                END

    注意：route_by_difficulty 不是一个节点，它只是条件边使用的路由函数。
    """
    graph_builder = StateGraph(LearningState)

    graph_builder.add_node("initialize_learning_goal", initialize_learning_goal)
    graph_builder.add_node("classify_difficulty", classify_difficulty)
    graph_builder.add_node("create_learning_plan", create_learning_plan)
    graph_builder.add_node("add_review_materials", add_review_materials)
    graph_builder.add_node("summarize_result", summarize_result)

    graph_builder.add_edge(START, "initialize_learning_goal")
    graph_builder.add_edge("initialize_learning_goal", "classify_difficulty")
    graph_builder.add_edge("classify_difficulty", "create_learning_plan")
    graph_builder.add_conditional_edges(
        "create_learning_plan",
        route_by_difficulty,
        {
            "needs_review": "add_review_materials",
            "ready_to_summarize": "summarize_result",
        },
    )
    graph_builder.add_edge("add_review_materials", "summarize_result")
    graph_builder.add_edge("summarize_result", END)

    return graph_builder.compile()


def print_result(final_state: LearningState) -> None:
    """把最终 state 打印出来，方便直接运行脚本时观察结果。"""
    print("主题:", final_state["topic"])
    print("难度:", final_state["difficulty"])
    print("\n学习计划:")
    for index, step in enumerate(final_state["learning_plan"], start=1):
        print(f"{index}. {step}")

    if final_state["review_materials"]:
        print("\n复习材料:")
        for index, material in enumerate(final_state["review_materials"], start=1):
            print(f"{index}. {material}")

    print("\n总结:", final_state["summary"])


def run_demo(topic: str = "我想入门 LangGraph") -> LearningState:
    """运行 demo。

    invoke 的入参就是初始 state。这里故意只传 topic，让你看到其他字段
    是如何被不同节点一步步补充出来的。
    """
    graph = build_learning_graph()
    final_state = graph.invoke({"topic": topic})
    print_result(final_state)
    return final_state


def main() -> None:
    topic = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "我想深入 LangGraph"
    run_demo(topic)


if __name__ == "__main__":
    main()
