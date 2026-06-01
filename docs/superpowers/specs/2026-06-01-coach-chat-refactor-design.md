# 教练聊天模块重构设计

## 背景

当前做题工作台的产品形态已经明确为 Chat-first AI 教练：用户主要在聊天中描述思路、粘贴代码、粘贴 LeetCode 未通过反馈；只有 LeetCode 已 AC 是明确的结构化终态动作。

现有后端代码仍保留较多早期“用户提交代码快照 / 提交状态 / 回填反馈”的设计痕迹，例如 `practice_session`、`practice_event`、`submission_feedback`、`save_code_snapshot`、`submit_feedback` 等命名和 API。虽然部分逻辑已经支持聊天式非 AC 识别，但代码阅读时仍像用户需要先维护结构化提交状态，再由教练处理，和当前产品主线不一致。

项目尚未上线，本次重构不保留历史兼容包袱。目标是把教练聊天模块重构为更清晰的领域模型：聊天是主入口，后端从聊天和显式 AC 动作中沉淀训练事实。

## 已参考文档

- `docs/index.md`
- `docs/prd/prd.md`
- `docs/prd/ai-coach-workbench-prd.md`
- `docs/architecture/foundation.md`

## 目标

1. 让代码命名和职责符合 Chat-first 产品形态。
2. 删除或收缩旧的“用户提交状态表单”语义。
3. 明确区分聊天消息、教练单轮决策和训练事实。
4. 保留 LeetCode 已 AC 作为唯一结构化终态动作。
5. 让非 AC 反馈通过聊天识别沉淀为训练事实。
6. 支持后续复盘、画像、Trace、RAG 继续使用稳定的结构化事实输入。

## 非目标

- 不做本地代码运行或在线判题。
- 不自动提交 LeetCode。
- 不抓取 LeetCode 隐藏用例。
- 不保留旧 `practice-sessions` / `submission-feedback` API 的长期兼容层。
- 不把完整聊天原文或完整代码复制进 Trace、画像或长期摘要。

## 产品边界

推荐并确认的用户体验是：

- 聊天是主入口：用户消息、代码、WA/TLE/RE/MLE/CE/Unknown 等非 AC 反馈都进入聊天流。
- LeetCode 已 AC 是唯一显式训练动作：用户点击按钮确认官方通过，系统据此结束本题并触发复盘。
- 非 AC 不是用户主动提交结构化状态，而是后端从聊天消息中提取出的训练事实。
- AC 是可信终态事实，不能完全交给聊天识别，避免把“如果 AC 了怎么办”“应该能 AC”误判为真实通过。

## 推荐架构

本次采用“聊天会话主模型 + 训练事实投影”的重构路径。

### 后端领域边界

#### `coach_session_service`

负责创建和恢复同一 `user + study_plan + problem` 的教练会话，并维护会话当前阶段、提示档位、完成状态、画像快照和计划项追溯。

它不负责解析用户消息、不直接调用模型、不保存代码快照。

#### `coach_message_service`

负责追加用户消息、保存教练消息、读取聊天时间线，并在用户消息保存后创建 `coach_turn` LLM Run。

它不要求前端传入用户意图；消息意图由后端抽取和模型决策共同判断。

#### `coach_fact_service`

负责把聊天或显式动作沉淀为训练事实，包括：

- 从用户聊天中抽取代码尝试。
- 从用户聊天中抽取 LeetCode 非 AC 反馈。
- 从 AC 按钮记录 LeetCode 官方通过。
- 为复盘、画像、Trace 和状态守卫提供结构化事实查询。

#### `coach_turn_flow`

负责单轮模型决策、状态守卫和教练回复保存。

它只消费当前会话、最近消息摘要、最近代码尝试、最近训练事实、画像和 RAG 摘要；不暴露“用户提交反馈表单”的概念。

#### `coach_guard`

负责最终状态裁决：

- 低提示档不能泄露完整题解。
- 无代码不能进入 `review_code`。
- 无反馈不能进入 `analyze_feedback`。
- 未 AC 不能进入 `summarize`。
- 用户贴代码或非 AC 反馈时可以快进到对应阶段。

## 数据模型

### `coach_session`

替代当前 `practice_session` 作为教练会话主表。

核心字段：

- `id`
- `user_id`
- `study_plan_id`
- `problem_id`
- `problem_slug`
- `origin_plan_version_id`
- `latest_plan_version_id`
- `latest_plan_item_id`
- `thread_id`
- `training_mode`
- `phase`
- `status`
- `current_hint_level`
- `visible_hint_gear`
- `max_hint_level_used`
- `latest_code_snapshot_id`
- `final_result`
- `profile_snapshot_id`
- `profile_snapshot_json`
- `started_at`
- `completed_at`
- `last_activity_at`
- `created_at`
- `updated_at`

唯一约束继续使用 `user_id + study_plan_id + problem_id`，保证同一计划题复用同一个聊天框。计划版本只做追溯，不参与会话身份。

### `coach_message`

替代聊天类 `practice_event`，只表达聊天时间线和必要系统消息。

核心字段：

- `id`
- `session_id`
- `user_id`
- `llm_run_id`
- `role`
- `phase`
- `content_md`
- `metadata_json`
- `hint_level`
- `visible_hint_gear`
- `created_at`

`coach_message` 不承担训练事实语义。是否包含代码、是否包含 WA、是否触发状态变化，都由 `coach_fact` 或 `coach_turn` 表达。

### `coach_fact`

新增统一训练事实表，替代 `submission_feedback` 的旧语义，并承接代码尝试、非 AC 反馈和 AC 结果等结构化事实。

核心字段：

- `id`
- `session_id`
- `user_id`
- `message_id`
- `code_snapshot_id`
- `fact_type`
- `source`
- `result`
- `payload_json`
- `created_at`

建议事实类型：

- `code_attempt`
- `leetcode_feedback`
- `leetcode_accepted`
- `phase_transition`
- `summary_generated`
- `profile_updated`

建议来源：

- `chat_extracted`
- `explicit_action`
- `coach_decision`
- `system`

示例：

```json
{
  "fact_type": "leetcode_feedback",
  "source": "chat_extracted",
  "result": "wa",
  "payload_json": {
    "has_failed_case": true,
    "has_error_message": true,
    "text_excerpt": "失败用例 nums=[3,3], target=6..."
  }
}
```

### `code_snapshot`

保留为完整代码文本的专用存储，但归属改为 `coach_session`。

代码快照只由聊天代码提取或教练 review 流程产生，不再作为前端手动代码草稿保存 API 的主路径。完整代码只留在 `code_snapshot`，普通日志、Trace、画像和 RAG query 只使用摘要。

### `coach_turn`

保留作为模型单轮决策审计表，但引用改为 `coach_message` 和 `coach_fact`。

职责：

- 记录模型建议阶段、守卫裁决、提示档位、诊断卡点和最终回复摘要。
- 关联本轮用户消息和教练消息。
- 关联本轮生成的代码尝试或非 AC 训练事实。

它不表示用户提交状态。

### `session_summary`、画像相关表

保留现有职责，但外键改为新的 `coach_session`。复盘输入优先来自 `coach_fact`、`coach_turn` 和摘要化消息上下文。

## API 设计

### 创建或恢复会话

`POST /api/study-plan/items/{item_id}/coach-session`

返回当前教练会话、聊天消息、代码尝试和训练事实摘要。

### 读取会话

`GET /api/coach-sessions/{session_id}`

返回：

- 会话状态。
- 聊天时间线。
- 代码尝试记录。
- 最近 LeetCode 非 AC 反馈事实。
- AC 状态。
- 画像摘要。

### 发送聊天消息

`POST /api/coach-sessions/{session_id}/messages`

请求：

```json
{
  "content_md": "用户自然语言、代码或 LeetCode 反馈"
}
```

后端保存用户消息并创建 `coach_turn` LLM Run。前端不传 `intent`，也不传非 AC 结构化结果。

### 记录 AC

`POST /api/coach-sessions/{session_id}/accepted`

唯一结构化训练动作。后端写入 `coach_fact(fact_type=leetcode_accepted, result=ac, source=explicit_action)`，更新会话和计划项状态，并创建 `coach_summary` LLM Run。

### 停用旧接口

以下接口不再作为主路径保留：

- `POST /api/practice-sessions/{session_id}/submission-feedback`
- `POST /api/practice-sessions/{session_id}/code-snapshots`

如果短期测试或页面仍引用，直接改到新 API，不做长期兼容。

## 单轮聊天数据流

1. 前端发送自然语言消息到 `POST /api/coach-sessions/{id}/messages`。
2. 后端保存 `coach_message(role=user)`。
3. 后端创建 `coach_turn` LLM Run，payload 只包含 `session_id`、`user_message_id` 和 `trigger=user_message`。
4. `coach_turn_flow` 加载当前会话、题目、计划目标、画像摘要、最近消息摘要、最近代码尝试、最近训练事实和 RAG 摘要。
5. 后端本地先做轻量抽取：
   - 代码块 -> pending code candidate。
   - WA/TLE/RE/MLE/CE/Unknown -> pending LeetCode feedback fact。
6. 模型输出诊断和回复建议：
   - `phase_after`
   - `next_action`
   - `reply_md`
   - 代码质量判断
   - 是否建议提交到 LeetCode
7. 后端守卫裁决阶段和提示档位。
8. 后端保存：
   - `coach_message(role=assistant)`
   - `coach_turn`
   - 必要时保存 `code_snapshot + coach_fact(code_attempt)`
   - 必要时保存 `coach_fact(leetcode_feedback)`
   - 更新 `coach_session.phase/status/hint_level`
9. 前端刷新会话，临时消息由正式聊天时间线接管。

## AC 数据流

1. 前端调用 `POST /api/coach-sessions/{id}/accepted`。
2. 后端写入 `coach_fact(fact_type=leetcode_accepted, result=ac, source=explicit_action)`。
3. 后端更新：
   - `coach_session.final_result=ac`
   - `coach_session.status=summarizing`
   - 当前计划项状态为 `completed`
4. 后端创建 `coach_summary` LLM Run。
5. 复盘成功后保存 `session_summary` 和画像增量。
6. 后端将 `coach_session.status` 更新为 `completed`。

## 前端调整

工作台保留：

- 聊天时间线。
- 文本输入框。
- 请求提示按钮。
- 代码尝试记录抽屉。
- LeetCode 已 AC 按钮。
- LLM Run 状态行和临时教练气泡。

工作台移除或不再使用：

- 非 AC 反馈表单。
- 手动代码快照保存入口。
- 用户 intent 选择或隐藏式分类负担。

前端 API 命名在本次实现中直接改为 `coach`，例如新增 `frontend/src/api/coach.ts` 并移除工作台对旧 `practice` API 的依赖。如果页面仍叫 `WorkspacePage` 可以保留；业务 API 不再使用 submission-first 命名。

## 迁移策略

项目未上线，本次不做历史数据兼容。

建议新建 migration，直接落目标结构：

1. 删除或重命名旧 `practice_*` / `submission_feedback` 表。
2. 创建 `coach_session`、`coach_message`、`coach_fact`。
3. 调整 `code_snapshot`、`coach_turn`、`session_summary`、画像相关外键。
4. 更新 SQLAlchemy 模型、Pydantic schema、service、API 和测试 fixture。

如果实现时发现 Alembic 直接删除表会影响现有未提交 RAG/Trace migration，应以当前 migration 链为准，保持 migration 顺序可执行。

## 日志与安全

新增和修改的核心流程必须记录中文项目要求中的稳定日志字段：

- 创建或恢复会话。
- 保存用户消息。
- 启动教练 run。
- 抽取代码尝试。
- 抽取 LeetCode 非 AC 反馈。
- 记录 AC。
- 状态守卫拒绝或接受。
- 复盘生成成功或失败。

日志不得记录完整用户输入、完整代码、完整题解、API key、session token 或密钥信息。需要定位问题时记录 ID、状态、长度、哈希、结果枚举和错误类型。

## 测试策略

后端重点测试：

- 同一 `user + study_plan + problem` 复用同一 `coach_session`。
- 用户消息不需要 intent 也能保存并创建 coach turn run。
- 聊天中粘贴 WA/TLE/RE/MLE/CE 能生成 `coach_fact(leetcode_feedback)`。
- 聊天中粘贴代码能在 review 流程生成 `code_snapshot + coach_fact(code_attempt)`。
- AC 按钮生成 `coach_fact(leetcode_accepted)`，推进计划项完成并触发 summary run。
- 守卫拒绝低提示档泄题、无代码 review、无反馈分析、未 AC 复盘。
- Trace 不保存完整用户输入或完整代码。

前端重点测试：

- 聊天输入只发送 `content_md`。
- 请求提示仍作为聊天消息进入同一流程。
- LeetCode 已 AC 按钮调用新 accepted API。
- AC 后按钮禁用并展示复盘运行状态。
- 代码尝试抽屉读取后端事实投影。
- 页面不再调用旧 submission feedback 或 manual code snapshot API。

## 文档影响

本次实现完成后需要同步维护：

- `docs/index.md`：更新后端模块职责和前端 API 职责。
- `docs/architecture/foundation.md`：更新训练工作台后端边界、API 列表和数据库模型说明。
- `docs/prd/ai-coach-workbench-prd.md`：如产品语义需更精确，补充“非 AC 是聊天抽取事实、AC 是显式终态动作”。
- `docs/prd/prd.md`：如 API 或页面行为描述发生变化，更新做题工作台和 AI 教练边界。

如果实现只改内部命名但不改变产品行为，也仍需要更新架构文档，因为表结构、API 和模块职责发生变化。

## 风险

- 改动面大，涉及后端模型、migration、API、LLM flow、前端 API 和测试。
- 当前工作区已有大量未提交变更，实现时必须避免回滚与本任务无关的改动。
- 现有测试大量引用 `practice_session`、`submission_feedback` 等旧命名，需要集中更新。
- RAG、Trace、复盘和画像逻辑依赖旧模型字段，实现时需要先保持事实输入契约稳定，再调整引用。

## 验收标准

1. 代码中用户主路径不再呈现“提交非 AC 状态表单”的设计。
2. 前端非 AC 只通过聊天输入进入系统。
3. AC 只能通过显式按钮记录官方通过。
4. 后端领域模型能清晰区分 `coach_session`、`coach_message`、`coach_fact` 和 `coach_turn`。
5. 单轮教练回复、代码尝试、非 AC 反馈、AC 复盘都能跑通。
6. 相关后端测试、前端测试和类型检查通过。
7. 文档同步反映新的模块职责、API 和数据模型。
