# LangChain Tool Agent Demo Design

## Goal

Create a beginner-friendly LangChain tool agent demo that contrasts with the existing hand-written ReAct and tool execution examples in `demo/paradigm`.

The demo should help the learner understand how LangChain turns ordinary Python functions into tools and how `create_agent()` replaces the manually written loop in `demo/paradigm/ReActAgent.py`.

## Scope

The demo is a single Python module under `demo/langchain`. It introduces a local tool and a LangChain agent. It does not introduce web search, external tool APIs, RAG, vector stores, memory, or LangGraph.

The first version intentionally uses a deterministic local learning-material tool so the learner can focus on the agent/tool abstraction instead of network behavior.

## User Experience

Running the script asks the configured model to answer a learning question and gives it access to a local tool:

```bash
uv run python demo/langchain/tool_agent.py "我想入门 LangChain，有什么资料？"
```

If no question is provided, the script uses a default LangChain beginner question.

## Configuration

The demo reuses the same model setup as `demo/langchain/basic_chain.py`:

- `LLM_MODEL_ID`
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_TIMEOUT`

The module should import and reuse `build_chat_model()` from `demo/langchain/basic_chain.py` instead of duplicating environment parsing.

## Architecture

The module exposes these public helpers:

- `get_learning_material(topic: str) -> str` is decorated with `@tool` and returns local recommended learning material.
- `build_agent()` creates a LangChain agent with `create_agent()`, the chat model, and the local tool.
- `extract_final_text()` pulls the final assistant message text out of the agent result.
- `run_demo()` invokes the agent for a question and returns the final answer text.
- `main()` provides the command-line entry point.

The implementation should allow dependency injection for tests, so tests can pass a fake agent instead of calling a real model.

## Agent Flow

The conceptual flow is:

1. User question enters `agent.invoke()` as a `messages` list.
2. The agent sees the available local tool and its docstring.
3. The model decides whether to call the tool.
4. LangChain executes the selected tool.
5. The agent returns a final assistant message.
6. `extract_final_text()` converts the result into a plain string for printing and tests.

## Teaching Points

Chinese comments in the demo should explain these comparisons:

- In `ToolExecutor.py`, tools are manually registered; in LangChain, `@tool` wraps a function as a tool.
- A tool function's name, type hints, and docstring matter because the model uses them to understand when and how to call it.
- In `ReActAgent.py`, the code manually parses `Thought` and `Action`; in LangChain, `create_agent()` owns the agent loop.
- `agent.invoke({"messages": [...]})` receives chat history because agents are conversation-oriented.
- The final result contains messages; the helper function extracts the last assistant message content.

## Error Handling

If the agent result does not contain a readable final message, `extract_final_text()` should return a clear fallback string rather than raising an unclear indexing error.

`build_agent()` should rely on `build_chat_model()` for missing environment-variable validation.

## Testing

Add tests that do not call a real model. Tests should verify:

- The local learning-material tool can be invoked directly and returns content related to the topic.
- `extract_final_text()` can read a final assistant message from a LangChain-style result dictionary.
- `run_demo()` invokes an injected fake agent with the expected `messages` payload and prints the returned final text.
- `main()` joins command-line arguments into one question.

## References

- LangChain agents documentation: https://docs.langchain.com/oss/python/langchain/agents
- LangChain tools documentation: https://docs.langchain.com/oss/python/langchain/tools
