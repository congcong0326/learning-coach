# LangGraph Basic Demo Design

## Goal

Create an entry-level LangGraph demo under `demo/graph` that helps a learner understand graph state, nodes, normal edges, conditional edges, compilation, and invocation.

## Scope

The demo is a single Python file with detailed Chinese comments. It does not call a real LLM or any network service, so it can run with only the project's existing dependencies.

## User Experience

Running `uv run python demo/graph/basic_learning_graph.py` prints a small learning plan workflow. The workflow uses a fixed example topic by default and can also accept a topic from the command line.

## Architecture

The file exposes `build_learning_graph()` for tests and reuse, plus `run_demo()` and `main()` for command-line execution. Nodes are plain Python functions that receive and return pieces of a shared `TypedDict` state.

## Graph Flow

1. `START` enters `initialize_learning_goal`.
2. `initialize_learning_goal` normalizes the topic and initializes lists.
3. `classify_difficulty` assigns beginner or advanced difficulty using simple keyword rules.
4. `create_learning_plan` generates ordered learning steps.
5. A conditional edge decides whether to run `add_review_materials`.
6. `summarize_result` creates a final summary.
7. The graph exits through `END`.

## Testing

Tests cover the beginner branch, the advanced branch, and the command-line helper. The tests should run through `uv run pytest`.
