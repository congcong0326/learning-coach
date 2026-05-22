# AI 教练工作台与用户画像编码规格

## 1. 结论

`docs/prd/ai-coach-workbench-prd.md` 和 `docs/prd/ai-coach-user-profile-prd.md` 的产品设计是融洽的。

两者的分工清晰：

- 工作台 PRD 定义“训练会话怎么发生”：计划题身份、聊天框复用、训练状态、提示档位、LeetCode 回填、复盘沉淀。
- 用户画像 PRD 定义“AI 教练为什么这样教”：画像指标、证据来源、增量更新、LLM 与后端职责边界、画像如何影响第一问和 review 重点。

编码时应把两者合并为一个主链路：

```text
计划题进入工作台
-> 创建或恢复 practice_session
-> ProfileProvider 读取用户画像快照
-> AI 教练根据画像、计划、题目和训练事实生成第一问或下一轮回复
-> 训练事件结构化落库
-> LeetCode 回填和复盘生成 session_summary
-> LLM 生成 profile_patch
-> 后端校验合并为新的 user_profile_snapshot
```

## 2. 融合检查

### 2.1 一致点

| 主题 | 工作台 PRD | 用户画像 PRD | 编码结论 |
| --- | --- | --- | --- |
| 产品定位 | 工作台不是普通聊天，是单题训练控制台 | 画像不是用户档案，是教练决策记忆 | 工作台只消费决策型画像，不做通用聊天和泛画像 |
| 第一问 | 必须根据画像、计划和题目生成 | 画像提供起手阶段、追问重点和默认提示策略 | `practice_session` 创建时保存 `profile_snapshot_json` 并用于起手 |
| 状态跳转 | LLM 提建议，后端守卫跳转 | LLM 给画像建议，后端守卫合并 | 所有状态变化和画像更新都采用“模型建议 + 后端校验” |
| 训练事实 | 聊天、代码、提交、复盘要结构化沉淀 | 画像必须基于事实和证据 | 训练事件、复盘和画像 patch 分表保存 |
| 历史召回 | 不直接塞完整聊天原文 | 不把完整聊天当画像 | Prompt 优先使用画像、复盘和关键事件摘要 |
| 提示边界 | 低提示档位不能泄露完整答案 | 画像不能绕过提示档位边界 | `CoachGuard` 同时校验 phase 和 hint level |

### 2.2 需要统一的表述

工作台 PRD 中“历史最高提示档位、独立完成比例、最近训练结果”属于画像输入维度；用户画像 PRD 中“能力维度、题型掌握度、教练策略建议”属于画像决策结构。

编码时统一为：

```text
训练事实指标
  -> 复盘摘要
  -> profile_patch
  -> user_profile_snapshot.strategy_json / ability_profile_json / skill_profile_json
```

也就是说，最高提示档位和独立完成比例不直接作为孤立画像标签，而是作为生成画像和策略建议的证据。

### 2.3 需要避免的冲突

不要让训练过程中的临时诊断直接覆盖长期画像。

编码时区分：

- `coach_turn.response_json.profile_signals`：本轮模型观察到的临时信号。
- `session_summary.profile_signals_json`：本题复盘确认后的画像信号。
- `profile_delta.patch_json`：可合并的长期画像增量。
- `user_profile_snapshot`：合并后的长期画像版本。

## 3. MVP 编码范围

第一轮编码目标不是一次性完成 LangGraph、RAG 和复杂推荐，而是跑通可验证的训练闭环。

必须实现：

- 从学习计划题目进入工作台并创建或恢复训练会话。
- 同一 `user_id + study_plan_id + problem_id` 复用同一个会话。
- 学习计划版本变化只更新追溯字段，不改变会话身份。
- 保存用户消息、AI 消息、业务事件、代码版本和 LeetCode 回填。
- 提供 `ProfileProvider`，先从目标校准、计划标签、计划项推荐理由和最近画像快照生成画像摘要。
- AI 教练起手和后续回复能读取画像摘要。
- 后端守卫基础状态跳转和提示档位边界。
- 生成单题复盘，并产生可追溯的 `profile_delta`。
- 合并 `profile_delta` 为新的 `user_profile_snapshot`。

第一轮可以简化：

- LangGraph 暂不强制落地，先用 service 编排有限状态。
- RAG 暂不接真实向量检索。
- 画像分数先用 `low | medium | high` 和 JSON 证据摘要，不做复杂评分模型。
- 用户可见画像变化先展示在复盘结果中，不单独做画像仪表盘。

## 4. 后端数据模型

### 4.1 枚举约定

后端可以先用 `String` 字段配合 Pydantic Literal 校验，保持迁移简单。

```text
PracticePhase:
  understand_problem
  propose_bruteforce
  optimize_solution
  define_invariant
  write_code
  review_code
  submit_to_leetcode
  analyze_feedback
  summarize

HintLevel:
  questioning
  direction
  key_hint
  reflection

PracticeSessionStatus:
  active
  waiting_user
  waiting_leetcode
  summarizing
  completed
  archived

PracticeEventType:
  session_started
  user_message
  assistant_message
  code_saved
  submission_feedback
  phase_changed
  summary_generated
  profile_updated

UserIntent:
  describe_idea
  stuck
  request_hint
  code_review
  submit_feedback
  request_summary
  unknown

SubmissionResult:
  ac
  wa
  tle
  re
  mle
  ce
  unknown

ProfileSource:
  initial_goal_plan
  mock_from_goal_and_plan
  summary_patch
  manual_repair

ProfileConfidence:
  low
  medium
  high
```

### 4.2 `practice_session`

保存一个计划题训练聊天框和当前业务状态。

核心字段：

```text
id
user_id
study_plan_id
problem_id
problem_slug
origin_plan_version_id
latest_plan_version_id
latest_plan_item_id
thread_id
training_mode
phase
status
current_hint_level
visible_hint_gear
max_hint_level_used
attempt_count
latest_code_snapshot_id
final_result
profile_snapshot_id
profile_snapshot_json
started_at
completed_at
last_activity_at
created_at
updated_at
```

关键约束：

```text
unique(user_id, study_plan_id, problem_id)
index(user_id, status, last_activity_at)
index(study_plan_id, problem_id)
index(thread_id)
```

设计要求：

- `origin_plan_version_id` 记录第一次进入时的计划版本。
- `latest_plan_version_id` 和 `latest_plan_item_id` 每次从计划进入时更新。
- `profile_snapshot_json` 只保存用于决策的摘要，不保存完整聊天和完整代码。

### 4.3 `practice_event`

保存训练时间线。

核心字段：

```text
id
session_id
user_id
llm_run_id
event_type
role
phase
intent
content_md
payload_json
hint_level
visible_hint_gear
created_at
```

设计要求：

- 用户消息、AI 回复、代码保存、提交回填、状态变化和画像更新都写成事件。
- `content_md` 用于展示；业务判断优先读 `payload_json` 和关联表。
- 日志不得记录完整 `content_md`。

### 4.4 `code_snapshot`

保存用户代码版本。

核心字段：

```text
id
session_id
user_id
event_id
language
code_text
code_hash
source
client_revision
created_at
```

设计要求：

- `code_text` 可以落库，但不得进入普通日志、错误摘要和长期画像摘要。
- `code_hash` 用于去重和排查。

### 4.5 `submission_feedback`

保存用户手动回填的 LeetCode 结果。

核心字段：

```text
id
session_id
user_id
event_id
code_snapshot_id
source
result
runtime_ms
memory_kb
failed_case_text
error_message
raw_feedback_json
submitted_at
created_at
```

设计要求：

- `source` 第一版固定为 `leetcode_manual`。
- `failed_case_text` 和 `error_message` 只在必要时进入 Prompt；日志只记录长度、hash、结果类型。

### 4.6 `coach_turn`

保存一次 AI 教练结构化判断和回复。

核心字段：

```text
id
session_id
user_id
llm_run_id
user_event_id
assistant_event_id
prompt_version
model_name
phase_before
phase_after
training_mode
diagnosed_stuck_point
user_intent
next_action
hint_level_before
hint_level_after
visible_hint_gear
should_reveal_solution
transition_reason
response_json
context_snapshot_json
input_tokens
output_tokens
latency_ms
created_at
```

设计要求：

- `response_json.profile_signals` 是本轮临时信号，不直接更新长期画像。
- `context_snapshot_json` 记录画像版本、最近事件 id、题目标签和计划项，不保存完整 Prompt。

### 4.7 `session_summary`

保存单题复盘。

核心字段：

```text
id
session_id
user_id
problem_id
result
final_submission_result
training_mode
phases_visited_json
transitions_json
main_stuck_points_json
error_types_json
max_hint_level_used
avg_hint_level
attempt_count
time_spent_seconds
complexity_analysis_json
invariant_summary_md
review_summary_md
profile_signals_json
profile_update_suggestion_json
next_recommendation_json
created_at
updated_at
```

设计要求：

- `profile_signals_json` 是画像更新的主要事实输入。
- `profile_update_suggestion_json` 可以来自 LLM，但必须经后端校验后才写入长期画像。

### 4.8 `user_profile_snapshot`

保存长期画像版本。

核心字段：

```text
id
user_id
version_number
source
confidence
overall_level
preferred_training_mode
ability_profile_json
skill_profile_json
stuck_point_profile_json
strategy_json
recent_summary_md
evidence_summary_json
created_from_summary_id
created_at
```

关键约束：

```text
unique(user_id, version_number)
index(user_id, created_at)
index(user_id, source)
```

设计要求：

- 它是面向 AI 教练读取的查询快照，不是唯一事实来源。
- 第一版可以用 JSON 表达能力维度、题型掌握度、卡点和策略建议。
- 不把完整用户输入、完整代码和完整题解写入画像。

### 4.9 `profile_delta`

保存一次复盘对长期画像的增量影响。

核心字段：

```text
id
user_id
session_id
summary_id
previous_snapshot_id
next_snapshot_id
status
patch_json
evidence_json
merge_result_json
rejection_reason
created_at
applied_at
```

`status` 可选：

```text
proposed
accepted
rejected
```

合并规则：

- 没有证据的 patch 必须拒绝。
- 低置信度 patch 不能大幅改变长期画像。
- 单题负向信号不能直接覆盖长期稳定正向信号。
- 合并后必须生成新的 `user_profile_snapshot`，不能原地覆盖旧版本。

## 5. 后端服务边界

### 5.1 `practice_session_service`

职责：

- 根据计划项创建或恢复 `practice_session`。
- 写入 `practice_event`。
- 保存代码版本和提交反馈。
- 构造前端需要的 session payload。
- 维护 `phase`、`status`、`hint_level` 和 `last_activity_at`。

关键函数：

```text
get_or_create_session_for_plan_item(session, user, item_id) -> PracticeSessionPayload
get_session_payload(session, user, session_id) -> PracticeSessionPayload
list_session_events(session, user, session_id) -> PracticeEventListResponse
append_user_message(session, user, session_id, payload) -> PracticeMessageResult
save_code_snapshot(session, user, session_id, payload) -> CodeSnapshotResponse
record_submission_feedback(session, user, session_id, payload) -> SubmissionFeedbackResponse
```

### 5.2 `profile_service`

职责：

- 从目标校准和学习计划生成初始画像。
- 查询最新长期画像。
- 校验并合并 `profile_delta`。
- 生成新的 `user_profile_snapshot`。

关键函数：

```text
ensure_initial_profile_snapshot(session, user_id, plan_id) -> UserProfileSnapshot
latest_profile_snapshot(session, user_id) -> UserProfileSnapshot | None
propose_profile_delta_from_summary(session, summary_id, patch_json) -> ProfileDelta
apply_profile_delta(session, delta_id) -> UserProfileSnapshot
```

### 5.3 `profile_provider`

AI 教练不直接读画像表，只依赖 Provider。

接口：

```text
get_snapshot(user_id, problem_id, study_plan_id, plan_item_id=None) -> ProfileSnapshot
```

`ProfileSnapshot` 字段：

```text
version
source
confidence
overall_level
preferred_training_mode
weak_stuck_points
strong_skill_tags
weak_skill_tags
recent_summary
hint_policy_hint
coach_strategy
evidence
```

第一版来源优先级：

1. 最新 `user_profile_snapshot`。
2. 目标校准和学习计划推导出的低置信初始画像。
3. 空画像兜底：`source=mock_from_goal_and_plan`、`confidence=low`。

### 5.4 `coach_guard`

职责：

- 校验 LLM 建议的状态跳转是否合法。
- 校验提示档位是否允许当前回复内容。
- 决定是否接受快进、回退和升档。

基本规则：

- 没有代码时不能进入 `review_code`，除非用户明确要求伪代码 review。
- 没有提交反馈时不能进入 `analyze_feedback`。
- `ac` 可以进入 `summarize`。
- 低提示档位下 `should_reveal_solution=true` 必须拒绝或降级。
- 用户请求复盘但证据不足时，只能生成阶段性复盘，不能标记完整完成。

### 5.5 `coach_flow`

第一版可以先用 service 编排，不强制 LangGraph。

步骤：

```text
load_session_context
classify_user_input
load_profile_snapshot
build_prompt_context
call_coach_model
validate_model_output
guard_transition
persist_coach_turn
maybe_generate_summary
maybe_update_profile
```

后续接 LangGraph 时，以上步骤可映射为 graph nodes。

## 6. API 设计

### 6.1 计划题进入工作台

```text
POST /api/study-plan/items/{item_id}/practice-session
```

行为：

- 校验计划项属于当前用户。
- 按 `user_id + study_plan_id + problem_id` 查找或创建会话。
- 更新 `latest_plan_version_id` 和 `latest_plan_item_id`。
- 调用 `ProfileProvider` 并保存本次使用的画像摘要。
- 返回 session、problem、plan context、profile snapshot 和最近事件。

### 6.2 获取会话

```text
GET /api/practice-sessions/{session_id}
GET /api/practice-sessions/{session_id}/events
```

行为：

- 只允许读取当前用户自己的会话。
- 不返回完整内部 Prompt。
- 代码内容只在代码面板需要时返回最新版本。

### 6.3 用户消息和 AI 教练运行

```text
POST /api/practice-sessions/{session_id}/messages
```

请求体：

```json
{
  "intent": "describe_idea",
  "content_md": "我的思路是先暴力枚举，再用哈希表优化。",
  "requested_hint_level": "questioning"
}
```

返回：

```json
{
  "event_id": 12,
  "run_id": 34,
  "session_id": 9
}
```

前端继续复用现有 SSE：

```text
GET /api/llm-runs/{run_id}/stream
```

### 6.4 代码版本

```text
POST /api/practice-sessions/{session_id}/code-snapshots
```

请求体：

```json
{
  "language": "python3",
  "code_text": "class Solution:\\n    def twoSum(self, nums, target):\\n        return []",
  "source": "manual_save",
  "client_revision": 3
}
```

### 6.5 LeetCode 回填

```text
POST /api/practice-sessions/{session_id}/submission-feedback
```

请求体：

```json
{
  "code_snapshot_id": 5,
  "result": "wa",
  "failed_case_text": "nums = [3,3], target = 6",
  "error_message": "",
  "runtime_ms": null,
  "memory_kb": null
}
```

行为：

- 写入 `submission_feedback`。
- 写入 `practice_event(event_type=submission_feedback)`。
- 更新 session 状态为 `analyze_feedback` 或 `summarize`。

### 6.6 复盘

```text
POST /api/practice-sessions/{session_id}/summary
```

行为：

- 创建 `llm_run(kind=coach_summary)`。
- 复盘成功后写 `session_summary`。
- 生成 `profile_delta`。
- 后端校验并合并为新的 `user_profile_snapshot`。

## 7. LLM Run 集成

继续复用现有 `llm_run` 统一流式层。

新增 run kind：

```text
coach_turn
coach_summary
```

建议注册关系：

```text
coach_turn:
  related_type=practice_session
  related_id_key=session_id

coach_summary:
  related_type=practice_session
  related_id_key=session_id
```

`coach_turn` handler 负责普通消息、代码 review 和提交反馈分析。具体触发类型放在 run input payload 中：

```json
{
  "session_id": 9,
  "trigger": "user_message",
  "user_event_id": 12
}
```

## 8. Prompt 上下文

Prompt 输入固定由以下部分组成：

```text
system_policy
coach_behavior_rules
session_state
problem_context
plan_context
profile_snapshot
recent_events
latest_code_snapshot
submission_feedback
output_schema
```

上下文预算：

- 题面和约束固定保留。
- 计划上下文只保留当前计划、阶段和计划项推荐理由。
- 画像摘要不超过 800 中文字。
- 最近对话保留 8-12 条事件。
- 代码只保留最新代码或本轮代码。
- 提交反馈只保留最近一次或本轮相关反馈。

禁止进入 Prompt 的内容：

- API key。
- session token。
- 完整历史聊天。
- 无关题目的完整代码。
- 未经过提示档位过滤的完整题解。

## 9. 前端编码规格

### 9.1 路由

保留现有题库自由入口：

```text
/workspace/:slug
```

新增计划题入口：

```text
/workspace/items/:itemId
```

MVP 优先实现计划题入口。题库自由入口可以继续只展示题面，后续再接 active plan 或临时训练上下文。

### 9.2 页面结构

`WorkspacePage` 拆为以下内部区域：

- 题面面板：展示中文题面、难度、标签、LeetCode 链接。
- 代码面板：选择语言、编辑或粘贴代码、保存代码版本。
- 教练面板：展示当前计划、阶段、训练模式、提示档位、画像摘要、事件时间线和操作入口。
- 提交回填入口：结构化录入 AC、WA、TLE、RE、MLE、CE、Unknown。

### 9.3 前端 API

新增文件：

```text
frontend/src/api/practice.ts
```

核心函数：

```text
createPracticeSessionForItem(itemId)
getPracticeSession(sessionId)
getPracticeEvents(sessionId)
sendPracticeMessage(sessionId, payload)
saveCodeSnapshot(sessionId, payload)
submitLeetCodeFeedback(sessionId, payload)
requestPracticeSummary(sessionId)
```

### 9.4 交互约束

- 用户没有 session 时不能发送教练消息。
- 用户未保存代码也可以描述思路，但不能提交 LeetCode 回填关联代码版本。
- 回填 AC 后优先展示“进入复盘”操作。
- SSE 中的 delta 只追加到当前 AI 回复草稿，result 后再刷新 session/events。
- 错误态必须展示可恢复操作，不丢失用户已经输入的代码。

## 10. 测试策略

### 10.1 后端模型和迁移

必须覆盖：

- 同一用户、同一计划、同一题只创建一个 session。
- 同一用户、新计划、同一题创建新 session。
- 计划版本变化不创建新 session，只更新 latest version 和 latest item。
- `user_profile_snapshot` 版本号按用户递增。
- `profile_delta` 无证据时被拒绝。

### 10.2 后端 API

必须覆盖：

- 未登录用户不能访问 practice API。
- 用户不能读取或写入他人的 session。
- 计划题进入接口返回 problem、plan context、profile snapshot。
- 用户消息写入 event 并创建 llm_run。
- 代码保存不把完整代码写入日志字段。
- LeetCode 回填写入结构化反馈和事件。

### 10.3 Coach Guard

必须覆盖：

- 贴代码进入 `review_code`。
- WA 进入 `analyze_feedback`。
- AC 进入 `summarize`。
- 没有提交结果时拒绝进入 `analyze_feedback`。
- 低提示档位下拒绝完整题解输出。

### 10.4 ProfileProvider

必须覆盖：

- 没有真实画像时从目标校准和计划生成低置信 snapshot。
- 有长期画像时优先使用最新 `user_profile_snapshot`。
- snapshot 中不包含完整代码和完整聊天。
- 最近复盘可以影响 `weak_stuck_points` 和 `coach_strategy`。

### 10.5 前端

必须覆盖：

- 计划题路由能创建或恢复 session。
- 教练面板能展示画像来源和置信度。
- 发送消息后能拿到 run id 并订阅 SSE。
- 回填 LeetCode 结果时请求体包含结构化 result。
- AC 后展示进入复盘按钮。

## 11. 实施顺序

推荐按以下顺序编码：

1. 数据模型和 migration。
2. Pydantic schemas。
3. `ProfileProvider` 和初始画像服务。
4. `practice_session_service` 与 practice API。
5. 前端 `practice.ts` 和计划题工作台入口。
6. `coach_guard` 与最小 `coach_turn` run handler。
7. 单题复盘、`profile_delta` 和画像合并。
8. 文档、测试和 smoke 验证。

## 12. 验收标准

编码完成后必须满足：

- 从学习计划题目进入 `/workspace/items/:itemId` 可以创建或恢复同一个训练会话。
- 同一计划题反复打开不会生成多个聊天框。
- 学习计划版本变化后，同一计划同一题仍复用原 session。
- 工作台能展示画像摘要，并且画像来源和置信度可见。
- 用户发送思路、代码、提交反馈后，系统能保存结构化事件。
- AI 教练回复能记录 `llm_run`、`coach_turn` 和 assistant event。
- 复盘生成后能写入 `session_summary`、`profile_delta` 和新的 `user_profile_snapshot`。
- 低提示档位不能输出完整可提交答案。
- 完整聊天和完整代码不会进入长期画像摘要。
