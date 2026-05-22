# 研发数据流程备注

本文用于按需记录研发排查时关心的数据流。它不是强维护契约；后续由研发提问或调试需要驱动补充。

## 目标校准：首次输入到追问结果

### 触发入口

前端页面：`frontend/src/pages/GoalCalibrationPage.tsx`

用户在目标校准表单填写目标后点击“开始校准”，前端执行：

```ts
calibrationRun.startRun('goal_followup', normalisePayload(values))
```

请求体进入统一 LLM Run 接口：

```http
POST /api/llm-runs
```

示例请求：

```json
{
  "kind": "goal_followup",
  "payload": {
    "goal_type": "interview_sprint",
    "target_timeline": "within_1_month",
    "preferred_language": "java",
    "weekly_days": 5,
    "session_minutes": 60,
    "current_level": "round_done_unstable",
    "self_reported_weaknesses": ["edge_case", "interview_expression"],
    "training_preference": "independent_first",
    "extra_notes": "目前leetcode hot 100已经刷了一遍，主要聚焦hot 100的题型"
  }
}
```

### 第一步：创建 llm_run

后端入口：`backend/app/api/llm_runs.py`

`create_llm_run_route` 会调用 `_related_from_payload`。首次目标校准还没有 `draft_id`，因此：

```text
related_type = ""
related_id = null
```

然后 `backend/app/services/llm_run_service.py:create_llm_run` 插入一条 `llm_run`。

首次写入 `llm_run` 的主要字段：

| 字段 | 写入内容 |
| --- | --- |
| `user_id` | 当前登录用户 ID |
| `kind` | `goal_followup` |
| `input_json` | 前端传入的目标校准 payload |
| `related_type` | 空字符串，后续创建 draft 后补回 |
| `related_id` | `null`，后续创建 draft 后补回 |
| `status` | 默认 `pending` |
| `stage` | 默认 `queued` |
| `result_json` | 默认 `{}` |
| `display_text_md` | 默认空字符串 |
| `error_code` / `error_message` | 默认空字符串 |
| `cancel_requested` | 默认 `false` |

接口立即返回：

```json
{
  "run_id": 1,
  "kind": "goal_followup",
  "status": "pending",
  "stage": "queued",
  "stream_url": "/api/llm-runs/1/stream"
}
```

此时还没有调用模型。前端随后用 `stream_url` 打开 SSE。

### 第二步：打开 stream 后执行模型任务

前端 hook：`frontend/src/hooks/useLlmRun.ts`

前端收到 `stream_url` 后创建：

```ts
new EventSource(streamUrl)
```

后端入口：

```http
GET /api/llm-runs/{run_id}/stream
```

`stream_llm_run_route` 发现 run 仍是 `pending` 时，会启动后台任务：

```python
execute_llm_run(async_session_factory, run_id, user_id)
```

`backend/app/services/llm_orchestrator.py:execute_llm_run` 会：

1. 读取 `llm_run` 和当前用户。
2. 发布 SSE `started`。
3. 选择用户可用的 `llm_credential`，解密 API key。
4. 调用 `mark_llm_run_running` 更新 `llm_run`。

此时 `llm_run` 会被更新：

| 字段 | 更新内容 |
| --- | --- |
| `status` | `running` |
| `stage` | `selecting_credential` |
| `started_at` | 当前时间 |
| `llm_credential_id` | 本次选中的模型资产 ID |
| `model_name` | 本次使用的模型名 |
| `updated_at` | 当前时间 |

因为 `kind = goal_followup`，orchestrator 会进入：

```python
run_goal_followup(...)
```

### 第三步：判断是否需要追问并创建 goal_calibration_draft

业务 flow：`backend/app/services/learning_flows/goal_calibration.py`

`run_goal_followup` 会读取 `run.input_json`。首次目标校准 payload 不包含 `draft_id/question_id/answer`，所以进入 `_run_initial_followup`。

`_run_initial_followup` 会调用模型判断是否需要追问：

```text
输入给模型 = 原始 payload + 空 history
输出期望 = null 或 {"question_id": "...", "question": "..."}
```

过程中不会把模型原始 JSON 直接展示给前端，只会通过 SSE `delta` 推送安全的进度文本，并更新 `llm_run.display_text_md`。

模型返回后会创建 `goal_calibration_draft`。

首次写入 `goal_calibration_draft` 的主要字段：

| 字段 | 写入内容 |
| --- | --- |
| `user_id` | 当前登录用户 ID |
| `llm_credential_id` | 本次 run 选中的模型资产 ID |
| `input_json` | 原始目标校准 payload |
| `followup_messages_json` | 如果模型追问，则为 `[{"role":"assistant","question_id":"...","question":"..."}]`；否则为空数组 |
| `draft_goal_json` | `{}`，计划生成阶段再写 |
| `draft_plan_json` | `{}`，计划生成阶段再写 |
| `validation_report_json` | `{}`，计划生成阶段再写 |
| `repair_log_json` | `[]`，计划生成阶段再写 |
| `prompt_version` | 当前目标计划 prompt 版本 |
| `model_name` | 本次使用的模型名 |
| `status` | 有追问时为 `asking_followup`；无追问时为 `collecting_input` |
| `error_message` | 空字符串 |

创建 draft 后，首次 `llm_run` 会补上业务关联：

| 字段 | 更新内容 |
| --- | --- |
| `related_type` | `goal_calibration_draft` |
| `related_id` | 新创建的 `goal_calibration_draft.id` |

这个关联用于后续按某个 draft 反查所有 LLM run，方便页面恢复、调试和历史展示。

### 第四步：run 成功提交并返回前端 result

`_run_initial_followup` 返回给 orchestrator 的 result 结构：

```json
{
  "draft_id": 10,
  "status": "asking_followup",
  "followup_question": "你最近面试中最容易卡住的是题型识别、边界处理，还是表达完整思路？",
  "followup_question_id": "q1",
  "remaining_followups": 2
}
```

如果模型判断不需要追问，则可能返回：

```json
{
  "draft_id": 10,
  "status": "collecting_input",
  "followup_question": null,
  "followup_question_id": null,
  "remaining_followups": 0
}
```

orchestrator 调用 `succeed_llm_run` 更新 `llm_run`：

| 字段 | 更新内容 |
| --- | --- |
| `status` | `succeeded` |
| `stage` | `completed` |
| `result_json` | 上面的 result |
| `display_text_md` | 当前可展示进度文本 |
| `finished_at` | 当前时间 |
| `updated_at` | 当前时间 |

事务提交成功后才通过 SSE 发布 `result` 事件。前端收到后执行：

```ts
setDraft(result as GoalCalibrationStartResponse)
```

此后页面会显示追问，或者直接显示“生成计划草稿”按钮。

## 目标校准：提交追问回答

### 触发入口

如果首次结果包含：

```json
{
  "draft_id": 10,
  "followup_question_id": "q1",
  "followup_question": "..."
}
```

用户填写追问回答后，前端执行：

```ts
calibrationRun.startRun('goal_followup', {
  draft_id: draft.draft_id,
  question_id: draft.followup_question_id,
  answer: followupAnswer,
})
```

请求体示例：

```json
{
  "kind": "goal_followup",
  "payload": {
    "draft_id": 10,
    "question_id": "q1",
    "answer": "边界条件经常漏，面试表达时也容易说不完整。"
  }
}
```

### 第一步：为这次回答创建新的 llm_run

这一次 payload 已经有 `draft_id`，所以 `_related_from_payload` 返回：

```text
related_type = "goal_calibration_draft"
related_id = 10
```

后端会再插入一条新的 `llm_run`。注意：每次追问回答都是新的 run，不是复用首次 run。

这条新 `llm_run` 的主要字段：

| 字段 | 写入内容 |
| --- | --- |
| `user_id` | 当前登录用户 ID |
| `kind` | `goal_followup` |
| `input_json` | `{draft_id, question_id, answer}` |
| `related_type` | `goal_calibration_draft` |
| `related_id` | 对应 draft ID |
| `status` | 默认 `pending` |
| `stage` | 默认 `queued` |

接口仍返回：

```json
{
  "run_id": 2,
  "kind": "goal_followup",
  "status": "pending",
  "stage": "queued",
  "stream_url": "/api/llm-runs/2/stream"
}
```

### 第二步：stream 执行并定位旧 draft

前端再次打开 `/api/llm-runs/2/stream`。

orchestrator 仍然选择模型资产、更新 `llm_run.status = running`，然后进入 `run_goal_followup`。

这一次 `run.input_json` 包含 `draft_id/question_id/answer`，所以进入 `_run_followup_answer`。

`_run_followup_answer` 会先读取原 draft：

```text
select goal_calibration_draft
where id = payload.draft_id
  and user_id = 当前用户
```

这样可以保证用户只能回答自己的 draft。

### 第三步：把用户回答接到原追问历史后面

旧 draft 中已有：

```json
[
  {
    "role": "assistant",
    "question_id": "q1",
    "question": "..."
  }
]
```

后端会把用户回答转换成：

```json
{
  "role": "user",
  "question_id": "q1",
  "answer": "边界条件经常漏，面试表达时也容易说不完整。"
}
```

新的 prompt history 会变成：

```json
[
  {
    "role": "assistant",
    "question_id": "q1",
    "question": "..."
  },
  {
    "role": "user",
    "question_id": "q1",
    "answer": "边界条件经常漏，面试表达时也容易说不完整。"
  }
]
```

如果追问次数还没达到 `MAX_FOLLOWUPS = 3`，后端会再次调用模型判断是否还需要一个追问：

```text
输入给模型 = draft.input_json 原始目标 + 当前 history
输出期望 = null 或下一条 assistant question
```

如果模型继续追问，会追加：

```json
{
  "role": "assistant",
  "question_id": "q2",
  "question": "..."
}
```

如果模型返回 `null`，说明信息已足够，后续可以生成计划草稿。

### 第四步：更新 goal_calibration_draft

提交追问回答时不会新建 draft，而是更新原 `goal_calibration_draft`。

主要更新字段：

| 字段 | 更新内容 |
| --- | --- |
| `followup_messages_json` | 旧追问历史 + 用户回答 + 可选的新追问 |
| `status` | 如果还有新追问，则为 `asking_followup`；否则为 `collecting_input` |
| `prompt_version` | 当前目标计划 prompt 版本 |
| `model_name` | 本次使用的模型名 |
| `llm_credential_id` | 本次 run 选中的模型资产 ID |
| `updated_at` | 当前时间 |

新 `llm_run` 最终也会被更新为成功：

| 字段 | 更新内容 |
| --- | --- |
| `status` | `succeeded` |
| `stage` | `completed` |
| `result_json` | 本轮追问后的 draft 摘要 |
| `finished_at` | 当前时间 |

### 返回给前端的字段

追问回答后的 SSE `result` 仍然是 `GoalCalibrationStartResponse` 形状：

```json
{
  "draft_id": 10,
  "status": "collecting_input",
  "followup_question": null,
  "followup_question_id": null,
  "remaining_followups": 0
}
```

如果还有下一问：

```json
{
  "draft_id": 10,
  "status": "asking_followup",
  "followup_question": "下一条追问文本",
  "followup_question_id": "q2",
  "remaining_followups": 1
}
```

前端用这个结果覆盖当前 `draft` 状态。关联方式是：

| 字段 | 作用 |
| --- | --- |
| `draft_id` | 把后续追问回答、跳过追问、生成计划草稿都绑定到同一个 `goal_calibration_draft` |
| `followup_question_id` | 把用户回答绑定到上一条 assistant 追问 |
| `llm_run.related_type + related_id` | 允许从 run 反查它属于哪个 draft |
| `goal_calibration_draft.followup_messages_json` | 保存完整追问上下文，下一次模型判断继续基于它生成 |

## LLM Run 内存事件中转站 event_hub

### 它要解决什么需求

目标校准和计划生成不是普通的短请求。一次 LLM 调用可能持续数秒到几十秒，期间前端需要看到：

```text
started
progress
delta
result
error
canceled
done
```

同时后端还要满足几个约束：

1. `POST /api/llm-runs` 要尽快返回 `run_id` 和 `stream_url`，不能在这个请求里一直等模型完成。
2. `GET /api/llm-runs/{run_id}/stream` 要持续把后端进度推给浏览器的 `EventSource`。
3. LLM 执行逻辑在后台任务 `execute_llm_run` 里，HTTP stream 响应在 `stream_llm_run_route` 里，两者不是同一个调用栈。
4. 用户可能取消、刷新页面或重复打开 stream，后端需要用 `run_id` 把事件归到同一次 LLM 任务上。

因此项目需要一个“中转站”把后台任务产生的事件交给正在等待的 SSE 连接。

### 它是什么

代码位置：`backend/app/services/llm_run_events.py`

`event_hub` 是一个进程内的 `LlmRunEventHub` 单例。它主要维护两个内存字典：

```python
self._subscribers: dict[int, set[asyncio.Queue[LlmRunEvent]]]
self._tasks: dict[int, asyncio.Task[None]]
```

可以理解成：

| 内存结构 | 含义 |
| --- | --- |
| `_subscribers[run_id]` | 当前正在订阅这个 run 的 SSE 连接队列集合 |
| `_tasks[run_id]` | 当前进程里正在执行这个 run 的后台任务 |

这里的 `asyncio.Queue` 是事件缓冲队列。后台任务把事件放进去，`/stream` 响应从队列里取事件并推给浏览器。

### 为什么不是直接在 execute_llm_run 里返回 HTTP 响应

`execute_llm_run` 是后台任务，不直接持有浏览器 HTTP 连接。它只负责：

```text
读取 run
选择模型资产
调用业务 flow
更新 DB
发布事件
```

`stream_llm_run_route` 才负责：

```text
验证当前用户
创建 StreamingResponse
把事件编码成 text/event-stream
推给浏览器 EventSource
```

这两个职责分开后，后端可以先创建 run，再由 stream 连接启动和承载事件；也可以在 run 已完成后，从 DB 直接回放最终结果。

### 事件如何流动

一次首次目标校准的典型流程：

```text
浏览器
  -> POST /api/llm-runs
  -> DB 插入 llm_run(status=pending)
  <- run_id + stream_url

浏览器
  -> GET /api/llm-runs/{run_id}/stream
  -> event_hub.subscribe(run_id)
  -> 如果 run 是 pending 且 event_hub.has_task(run_id) 为 false
     -> asyncio.create_task(execute_llm_run(...))
     -> event_hub.set_task(run_id, task)

execute_llm_run 后台任务
  -> event_hub.publish(run_id, started)
  -> event_hub.publish(run_id, progress)
  -> 业务 flow 里 event_hub.publish(run_id, delta)
  -> DB 写入 goal_calibration_draft / llm_run.result_json
  -> event_hub.publish(run_id, result)
  -> event_hub.publish(run_id, done)

stream_events
  -> 从 event_hub.subscribe(run_id) 的 queue 取事件
  -> encode_sse(event)
  -> yield 给 StreamingResponse
  -> 浏览器 EventSource 收到事件
```

### subscribe 做了什么

`event_hub.subscribe(run_id)` 会：

1. 为当前 SSE 连接创建一个新的 `asyncio.Queue`。
2. 把这个 queue 放进 `_subscribers[run_id]`。
3. 一直等待 `queue.get()`。
4. 每取到一个事件就 `yield event` 给 `stream_events`。
5. 如果事件名是 `done`，结束订阅。
6. 连接结束或异常时，从 `_subscribers` 里移除这个 queue。

所以同一个 run 可以有多个订阅者。后台任务发布一次事件，`publish` 会把事件放进这个 run 的每个订阅队列。

### publish 做了什么

`event_hub.publish(run_id, event)` 会找到所有订阅了这个 run 的 queue：

```python
for queue in self._subscribers[run_id]:
    await queue.put(event)
```

它不直接写 HTTP 响应，也不访问前端。它只负责把事件放入对应队列。

真正写给浏览器的是 `stream_events`：

```python
yield encode_sse(event)
```

### 为什么 stream 里先 subscribe 再启动任务

`stream_events` 的顺序是：

```text
先 event_hub.subscribe(run_id)
再 asyncio.create_task(execute_llm_run(...))
```

这样设计是为了避免丢事件。

如果先启动后台任务，模型很快失败或很快返回，后台任务可能立刻发布 `started/result/done`。此时 SSE 连接还没订阅，事件没有 queue 可以接收，就会丢掉。

先订阅再启动任务，至少可以保证当前这个 stream 连接能收到后续发布的事件。

### _tasks 为什么存在

`_tasks` 用来记录当前进程里已经启动的后台任务：

```text
run_id -> asyncio.Task
```

`stream_events` 启动任务前会判断：

```python
if status == "pending" and not event_hub.has_task(run_id):
    ...
```

这个判断避免同一个 run 在单进程内被重复执行。

例如浏览器重复打开 `/api/llm-runs/18/stream`：

```text
第一个 stream 发现 pending，启动 execute_llm_run(18)
第二个 stream 也发现 pending，但 event_hub.has_task(18) 为 true
第二个 stream 只订阅事件，不再启动第二次模型调用
```

任务结束后，`_observe_llm_task` 会调用 `event_hub.clear_task(run_id)` 清掉记录。

### 终态 run 为什么不走 event_hub

如果打开 stream 时发现 run 已经是：

```text
succeeded
failed
canceled
```

后端不会再启动任务，也不会等内存事件，而是从 `llm_run` 表里的终态字段直接构造事件：

```text
succeeded -> result + done
failed    -> error + done
canceled  -> canceled + done
```

这样做的原因是：最终结果已经持久化在 DB，页面刷新后即使内存里的 `event_hub` 已经没有订阅者或任务记录，也能恢复最终状态。

### 这样设计的好处

| 好处 | 说明 |
| --- | --- |
| 首次请求响应快 | `POST /api/llm-runs` 只落库，立即返回 `run_id` 和 `stream_url` |
| 支持流式进度 | 后台任务可以持续发布 `progress/delta/result`，前端无需轮询 |
| 前后端边界清晰 | 前端只看 SSE 事件；后端内部负责模型资产、业务 flow、DB 状态 |
| 支持取消和恢复 | run 状态持久化在 DB，取消和终态回放都有稳定依据 |
| 避免重复执行 | `_tasks` 在单进程内防止同一 run 被重复启动 |
| 实现成本低 | 第一版不需要 Redis、消息队列或持久事件表，适合本地优先开发 |

### 这个设计的限制

`event_hub` 是进程内内存对象，不是跨进程基础设施。

它的限制：

| 限制 | 影响 |
| --- | --- |
| 后端进程重启会丢内存订阅和 `_tasks` | 正在执行的流式事件不能继续从内存恢复 |
| 多 worker 之间不共享 event_hub | A worker 启动的任务，B worker 的 stream 连接收不到内存事件 |
| 不保存完整事件日志 | 只能从 DB 恢复终态 result/error/canceled，不能恢复完整中间 token 流 |

因此当前文档和架构都把它定位为“单进程开发环境中的第一版 SSE fan-out”。如果后续要多 worker 部署或更强恢复能力，需要引入 Redis pub/sub、任务队列或持久事件表。

## 当前阶段涉及的数据表

| 表 | 首次目标校准 | 追问回答 | 说明 |
| --- | --- | --- | --- |
| `llm_run` | 插入并更新 | 每次回答都会插入并更新一条新的 run | 统一记录 LLM 任务、状态、输入、输出和业务关联 |
| `goal_calibration_draft` | 插入 | 更新同一条 draft | 保存目标输入、追问历史和后续计划草稿 |
| `llm_credential` | 读取 | 读取 | 用于选择模型资产和解密 API key；正常成功路径不写入 |
| `app_user` | 读取 | 读取 | 当前用户归属和权限校验 |
| `auth_session` | 读取 | 读取 | 从 HttpOnly cookie 解析当前用户 |

`study_plan`、`study_plan_version`、`study_plan_stage`、`study_plan_item` 在“确认创建计划”之后才会写入。目标校准和追问阶段不会创建正式学习计划。
