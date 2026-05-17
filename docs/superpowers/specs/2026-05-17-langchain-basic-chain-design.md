# LangChain Basic Chain Demo Design

## Goal

Create an entry-level LangChain demo that helps the learner compare the existing direct model API style in `demo/paradigm/HelloAgentsLLM.py` with LangChain's basic chain style.

The demo should focus on the smallest useful LangChain mental model:

```text
ChatPromptTemplate -> ChatOpenAI -> StrOutputParser
```

## Scope

The demo is a single Python module under `demo/langchain`. It demonstrates prompt construction, model invocation, output parsing, and the `|` pipe operator. It does not introduce tools, agents, memory, retrieval, vector stores, or LangGraph.

## User Experience

Running the script prints a short learning suggestion for a topic:

```bash
uv run python demo/langchain/basic_chain.py LangChain入门
```

If no topic is provided, the script uses a default beginner topic.

## Configuration

The demo reuses the project's current OpenAI-compatible environment variables:

- `LLM_MODEL_ID`
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_TIMEOUT`

This keeps the LangChain demo aligned with the existing direct API examples and avoids requiring separate `OPENAI_API_KEY` configuration.

## Architecture

The module exposes three public helpers:

- `build_chat_model()` creates a `ChatOpenAI` instance from the existing environment variables.
- `build_chain()` creates the runnable chain from a prompt, chat model, and string output parser.
- `run_demo()` invokes the chain for a topic and returns the generated text.

The implementation should allow dependency injection for tests, so tests can pass a fake runnable instead of calling a real model.

## Teaching Points

Chinese comments in the demo should explain these comparisons:

- Direct API examples manually build `messages`; LangChain uses `ChatPromptTemplate`.
- Direct API examples manually call the client and read response content; LangChain wraps the chat model as a runnable.
- Direct API examples manually normalize returned text; LangChain can use `StrOutputParser`.
- The `|` operator connects runnable components into one chain.

## Dependencies

Add runtime dependencies with `uv`:

```bash
uv add langchain langchain-openai
```

## Testing

Add tests that do not call a real model. Tests should verify:

- `build_chain()` can compose a fake runnable model and return generated text.
- `run_demo()` can invoke an injected fake chain and return text.
- The demo keeps the reusable function structure instead of only working as a script.
