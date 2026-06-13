# Agent Loop v1 设计

## 背景和目标

当前项目已经收敛为“题库 + 本地用户登录”的全栈基座，现需恢复第一个可运行的 LLM loop，用于让模型围绕题库进行查询和回答。

第一版目标是建立最小闭环：

```text
用户问题
-> LLM Responses API
-> 模型请求安全题库工具
-> 后端执行工具
-> 工具结果回灌给 LLM
-> 输出最终回答
```

## 当前代码事实

- 当前后端是 FastAPI + SQLAlchemy async + PostgreSQL。
- 当前题库能力由 `backend.app.services.problem_service` 提供。
- 当前认证使用 HttpOnly session cookie。
- 当前文档明确说明不包含 LLM Run、Agent loop 和 AI 教练能力，因此本设计是恢复该能力前的当前版本边界。

## 范围内

- 新增最小 agent 决策引擎抽象层，避免业务 loop 直接依赖 OpenAI SDK 或 LLM 专用类型。
- 新增 OpenAI Responses API provider。
- 新增题库安全工具：
  - `search_problems`
  - `get_problem_detail`
  - `list_problem_categories`
- 新增后端接口 `POST /api/coach/chat`，要求用户已登录。
- 新增基础测试覆盖 provider 抽象、loop 编排和 API 行为。
- Agent loop 维护 agent-native 的本次对话历史：
  - 普通用户/助手文本轮次。
  - 助手发起的工具调用轮次。
  - 后端工具执行结果轮次。
  决策引擎只负责把这份历史编译到 OpenAI、Claude、本地模型或规则引擎的输入格式。
- 抽象层使用 `agent_instructions` 表示 Agent 行为策略；OpenAI 适配器内部再映射为 Responses API 的 `instructions` 字段。

## 范围外

- 不开放 bash、文件读写、本地代码执行或在线判题。
- 不恢复旧版学习计划、训练工作台、复盘、画像、推荐、RAG、Trace 或 LLM Run 数据表。
- 不做前端聊天 UI。
- 不持久化对话历史、token、费用或 trace。
- 不实现多 provider 自动路由，只保留可替换 provider 接口。

## 工程边界

- `backend.app.llm` 只放模型决策引擎适配器，当前包含 OpenAI Responses 适配器。
- `backend.app.agents` 放当前题库 agent loop、agent-native 类型和工具注册。
- 工具只能通过现有 service 查询数据库，不直接拼 SQL。
- provider 协议不能要求业务 loop 传递 response id、`previous_response_id` 或其他厂商状态续接字段；这些细节必须留在具体 provider 内部。
- provider 协议不能暴露厂商字段名作为业务语义；例如业务 loop 传 `agent_instructions`，不是 OpenAI 专有的 `instructions` 参数。
- OpenAI API key、base URL 和 model 第一版放在本地配置文件，后续再迁移到 Settings 或凭据表。

## API 影响

新增：

```text
POST /api/coach/chat
```

请求：

```json
{
  "message": "帮我找几道数组入门题"
}
```

响应：

```json
{
  "answer": "模型最终回答",
  "tool_calls": [
    {
      "name": "search_problems"
    }
  ]
}
```

## 风险和安全约束

- 不记录 API key、session token、完整用户输入或完整题面。
- 日志只记录 turn、tool、status、数量和错误摘要。
- loop 必须有 `max_turns`，防止模型无限调用工具。
- 工具输出必须截断，避免一次把过长题面塞回模型。
- 未知工具、非法 JSON 参数和工具异常都必须转成可回灌的错误结果，并记录 warning/exception。

## 验收标准

- 后端可以通过抽象 provider 驱动一个工具调用循环。
- OpenAI provider 使用 Responses API 的 `responses.create`。
- loop 在模型无工具调用时返回最终回答。
- loop 在模型请求题库工具时执行工具，并把工具调用和工具结果追加到 agent-native 历史后进入下一轮。
- 未登录用户不能调用 `/api/coach/chat`。

## 验证命令

```bash
uv run ruff check backend/app/llm backend/app/agents backend/app/api/coach.py backend/tests/test_agent_loop.py backend/tests/test_openai_responses_provider.py backend/tests/test_coach_api.py
uv run pytest -q backend/tests/test_agent_loop.py backend/tests/test_openai_responses_provider.py backend/tests/test_coach_api.py
```

## 文档维护影响

- `docs/index.md` 需要加入新增模块职责。
- `docs/architecture/foundation.md` 需要说明新增的最小 Agent loop 边界。
- `docs/prd/prd.md` 当前主产品仍是题库浏览；本功能作为恢复池中的工程实验入口，不扩大到完整 AI 教练产品。
