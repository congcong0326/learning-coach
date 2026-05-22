# LLM Run Handler Registry 重构设计

## 背景

当前 `backend/app/services/llm_orchestrator.py:execute_llm_run` 是统一 LLM Run 的核心编排入口。它已经承担了通用生命周期职责：

- 加载 `llm_run` 和用户。
- 发布 `started/progress/result/error/done` 事件。
- 选择用户模型资产、解密 API key、创建 provider。
- 根据 `run.kind` 分发到具体业务 flow。
- 成功或失败时更新 `llm_run` 终态。

目前支持的业务类型较少，`execute_llm_run` 里用 `if run.kind == "goal_followup"` 可以工作。但后续会增加 `study_plan_adjustment`、`coach_message`、`code_review`、`reflection` 等业务，继续把分发逻辑、payload 关联规则和业务执行分支写进 orchestrator，会让核心函数膨胀并难以测试。

## 目标

本次重构目标是把 `execute_llm_run` 保持为“LLM Run 生命周期模板”，把不同 `kind` 的业务执行逻辑迁移到独立 handler，并用 registry 集中管理每个 kind 的元信息。

目标包括：

- 保持现有 API、SSE 事件协议和数据库结构不变。
- 保持当前 `goal_followup` 和 `goal_plan_generate` 行为不变。
- 消除 `execute_llm_run` 中面向具体 kind 的 `if/else` 分发。
- 把 `_related_from_payload`、`SUPPORTED_RUN_KINDS` 和业务 handler 统一收敛到 registry。
- 降低新增 LLM Run kind 的改动面。

非目标：

- 不引入 Redis、Celery、任务队列或持久事件表。
- 不改变 `event_hub` 的单进程内存模型。
- 不重构具体学习 flow 的内部算法。
- 不改变前端 `useLlmRun`、SSE 事件名或响应结构。

## 推荐设计

采用 `Template Method + Strategy + Registry` 的组合。

`execute_llm_run` 继续作为模板方法，负责所有 run 的固定生命周期：

```text
load run/user
publish started
resolve handler
select credential
create provider
build context
handler.execute(context)
succeed run
publish result + done
catch error
fail run
publish error + done
```

具体业务逻辑通过 handler strategy 执行：

```python
class LlmRunHandler(Protocol):
    async def execute(self, context: LlmRunContext) -> dict[str, Any]:
        ...
```

registry 负责集中声明每个 kind 的业务元信息：

```python
RUN_KIND_SPECS = {
    "goal_followup": RunKindSpec(
        handler=GoalFollowupHandler(),
        related_type="goal_calibration_draft",
        related_id_key="draft_id",
    ),
    "goal_plan_generate": RunKindSpec(
        handler=GoalPlanGenerateHandler(),
        related_type="goal_calibration_draft",
        related_id_key="draft_id",
    ),
    "study_plan_adjustment": RunKindSpec(
        handler=None,
        related_type="study_plan",
        related_id_key="plan_id",
    ),
}
```

首次 `goal_followup` 没有 `draft_id`，因此 `related_from_payload` 仍会返回空关联；业务 flow 创建 `goal_calibration_draft` 后继续补写 `run.related_type` 和 `run.related_id`。
`study_plan_adjustment` 当前尚未接入执行 handler，但创建 run 时仍需要保留 `study_plan/plan_id` 关联，便于后续按学习计划反查 LLM Run 历史；因此它在 registry 中是 metadata-only kind，`handler_for_kind("study_plan_adjustment")` 返回 `None`，`supported_run_kinds()` 不包含它。

## 新增模块

新增 `backend/app/services/llm_run_registry.py`。

建议包含：

- `LlmRunContext`：传递 handler 所需的上下文。
- `LlmRunHandler`：业务 handler 协议。
- `RunKindSpec`：每个 kind 的 registry 元信息；`handler=None` 表示只维护关联元数据，暂不支持执行。
- `GoalFollowupHandler`：调用现有 `run_goal_followup`。
- `GoalPlanGenerateHandler`：调用现有 `run_goal_plan_generate`。
- `RUN_KIND_SPECS`：统一 kind 注册表。
- `supported_run_kinds()`：返回已接入执行 handler 的 kind 集合。
- `handler_for_kind(kind)`：查找 handler，不存在时由 orchestrator 走 `run_kind_unsupported`。
- `related_from_payload(kind, payload)`：替代 API 层当前 `_related_from_payload`。

`LlmRunContext` 字段建议：

```python
@dataclass(frozen=True)
class LlmRunContext:
    session: AsyncSession
    user_id: int
    run: LlmRun
    provider: LlmProvider
    model_name: str
    publish: Callable[[LlmRunEvent], Awaitable[None]]
```

保持 context 简洁，避免把 credential、api_key 等敏感或不必要对象传入业务 handler。

## orchestrator 调整

`llm_orchestrator.py` 调整为只依赖 registry：

- 删除 `SUPPORTED_RUN_KINDS` 常量。
- 删除对 `run_goal_followup` 和 `run_goal_plan_generate` 的直接 import。
- 使用 `handler_for_kind(run.kind)` 解析 handler。
- 未注册 kind 仍然返回 `run_kind_unsupported`。
- provider 创建、credential 选择、错误映射、终态提交和事件发布保持不变。

核心分发逻辑由：

```python
if run.kind == "goal_followup":
    result = await run_goal_followup(...)
else:
    result = await run_goal_plan_generate(...)
```

变为：

```python
handler = handler_for_kind(run.kind)
if handler is None:
    await _fail_and_publish(..., error_code="run_kind_unsupported")
    return
result = await handler.execute(context)
```

## API 层调整

`backend/app/api/llm_runs.py` 不再维护 `_related_from_payload` 的硬编码映射。

改为：

```python
from backend.app.services.llm_run_registry import related_from_payload
```

`create_llm_run_route` 继续在创建 run 前解析 `related_type/related_id`，因此 API 响应行为不变。

保留 API 层关于 `related_type/related_id` 用途的中文注释，但把具体表含义放到 registry 侧或 `docs/data-flow.md`，避免注释和注册表重复漂移。

## 错误处理

错误处理保持现状：

- `LearningFlowError` 映射为它自己的 `code`。
- `LlmRunError`、`LlmCredentialError` 映射为 `detail`。
- `CredentialEncryptionError` 映射为对应加密错误。
- 未知异常映射为 `llm_provider_error`。

handler 不负责写 `llm_run` 终态，也不直接发布 `result/done`。handler 只负责业务流程并返回 result。终态提交必须仍由 orchestrator 统一执行，确保“正式 result 只在成功提交后发布”的约束不被绕过。

## 测试策略

后端测试需要覆盖：

- `related_from_payload("goal_followup", 初次 payload)` 返回空关联。
- `related_from_payload("goal_followup", {"draft_id": 1})` 返回 `goal_calibration_draft/1`。
- `related_from_payload("goal_plan_generate", {"draft_id": 1})` 返回 `goal_calibration_draft/1`。
- `related_from_payload("study_plan_adjustment", {"plan_id": 1})` 返回 `study_plan/1`，但 `handler_for_kind("study_plan_adjustment")` 为空，并由 orchestrator 发布 `run_kind_unsupported`。
- `related_from_payload` 对 `draft_id/plan_id` 只接受真正的 `int`，需要拒绝 Python 中属于 `int` 子类的 `bool`。
- 未注册 kind 返回空关联或 handler 为空，并由 orchestrator 发布 `run_kind_unsupported`。
- `execute_llm_run` 对 `goal_followup` 仍调用目标校准 handler。
- `execute_llm_run` 对 `goal_plan_generate` 仍调用计划生成 handler。
- 现有 LLM Run API、SSE、学习 flow 测试继续通过。

推荐验证命令：

```bash
uv run pytest backend/tests/test_llm_run_events.py backend/tests/test_llm_run_service.py backend/tests/test_llm_runs_api.py backend/tests/test_learning_flows.py -q
```

如果只改 registry 和 orchestrator，前端无需改动。

## 迁移步骤

1. 新增 `llm_run_registry.py`，注册现有两个可执行 kind，并保留 `study_plan_adjustment` 的 metadata-only 关联规则。
2. 把 API 层 `_related_from_payload` 替换为 registry 函数。
3. 把 orchestrator 的 kind 分发替换为 handler registry。
4. 补 registry 单元测试和调整现有 orchestrator 测试。
5. 运行相关后端测试。

## 风险与控制

| 风险 | 控制 |
| --- | --- |
| handler 过度抽象导致阅读成本上升 | 只抽取 kind 分发和上下文，保留现有 flow 函数主体 |
| 首次 `goal_followup` 没有 `draft_id` 的关联语义被误改 | registry 测试覆盖空关联场景 |
| result 发布时机被 handler 绕过 | handler 不允许发布正式 `result/done`，只返回业务 result |
| 测试替身需要调整 | handler 协议简单，测试可 monkeypatch registry 或 handler |
| registry 与 Pydantic `LlmRunKind` 不一致 | 当前保持 `LlmRunKind` 不变；后续可考虑从 registry 派生校验 |

## 验收标准

- 目标校准首次追问流程行为不变。
- 追问回答流程行为不变。
- 计划草稿生成流程行为不变。
- `execute_llm_run` 不再直接 import 具体学习 flow。
- 新增 kind 时主要改 registry 和对应 handler，不需要修改 orchestrator 主流程。
- 相关后端测试通过。
