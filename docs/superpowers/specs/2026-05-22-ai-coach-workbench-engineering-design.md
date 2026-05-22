# AI 教练工作台研发设计

## 1. 文档目的

本文档基于 `docs/prd/ai-coach-workbench-prd.md`，给出右侧 AI 教练工作台的研发设计。

重点覆盖：

- 表结构设计。
- LangGraph 状态流转。
- Prompt 与上下文管理。
- 用户画像依赖策略。
- 在用户画像模块尚未完整落地时，如何先跑通 AI 教练闭环。

本文档不直接替代实施计划。后续进入开发前，应再拆分为 migration、后端 API、LangGraph、前端工作台和测试计划。

## 2. 设计结论

### 2.1 总体架构

AI 教练工作台按以下主链路实现：

```text
study_plan + problem
  -> practice_session        # 一个计划题的训练聊天框和主状态
    -> practice_event        # 用户消息、AI 消息和业务事件
    -> code_snapshot         # 用户代码版本
    -> submission_feedback   # LeetCode 回填结果
    -> coach_turn            # 一次 AI 教练结构化判断和回复
    -> session_summary       # 单题复盘
      -> profile_delta       # 本次训练对画像的增量
```

核心身份规则：

```text
unique(user_id, study_plan_id, problem_id)
```

同一用户、同一学习计划、同一道题复用同一个 `practice_session`。学习计划版本只用于追溯，不参与聊天框身份。

### 2.2 用户画像策略

用户画像模块建议采用：

```text
并行设计，分阶段 mock
```

含义：

- 研发设计阶段同时定义画像输入契约、画像表、画像增量和上下文格式，避免 AI 教练后续返工。
- 第一阶段不等待完整画像模块落地，先实现 `ProfileProvider` 接口。
- `ProfileProvider` 初期返回 mock 画像快照，来源包括目标校准、自评弱项、学习计划标签、计划项推荐理由和已有复盘摘要。
- mock 画像必须显式标记 `source=mock`、`confidence=low|medium`、`version=profile-snapshot-v1`。
- 后续真实画像表落地后，替换 `ProfileProvider` 内部实现，AI 教练和 Prompt 组装层不需要改接口。

不建议先完整实现画像模块再做 AI 教练。原因是画像质量依赖训练事件和复盘数据，而这些数据本身来自 AI 教练闭环；先等画像会形成依赖死锁。

也不建议临时在 Prompt 里手写一段“用户很强/很弱”。这种 mock 不可追踪、不可测试，后续很难替换为真实画像。

## 3. 现有约束

### 3.1 已落地能力

当前已经具备：

- 本地用户、登录 session 和用户级 LLM API 资产。
- 题库表和题库 API。
- 目标校准草稿。
- 版本化学习计划。
- `llm_run` 统一流式层。
- 基础 `agent_trace` 和 `retrieval_trace`。

相关已落地表包括：

- `app_user`
- `auth_session`
- `llm_credential`
- `problem`
- `problem_category`
- `problem_category_item`
- `goal_calibration_draft`
- `study_plan`
- `study_plan_version`
- `study_plan_stage`
- `study_plan_item`
- `plan_change_log`
- `llm_run`
- `agent_trace`
- `retrieval_trace`

### 3.2 关键产品约束

AI 教练工作台必须满足：

- 不提供脱离题目和计划的全局聊天。
- 同一计划题复用聊天框。
- 学习计划版本变化不导致新聊天框。
- AI 第一问根据画像和题目上下文生成。
- 用户输入高质量思路、代码或提交结果时，可以快进状态。
- 低提示档位不能泄露完整答案。
- LeetCode 结果必须结构化回填。
- 聊天过程必须沉淀为复盘和画像输入。

## 4. 表结构设计

### 4.1 practice_session

用途：

保存一个计划题的训练主状态，也就是用户看到的“聊天框”。页面刷新、再次进入计划题、状态机恢复都从这里开始。

核心字段：

```text
practice_session
- id
- user_id
- study_plan_id
- problem_id
- problem_slug
- origin_plan_version_id
- latest_plan_version_id
- latest_plan_item_id
- thread_id
- training_mode
- phase
- status
- current_hint_level
- visible_hint_gear
- max_hint_level_used
- attempt_count
- latest_code_snapshot_id
- final_result
- profile_snapshot_json
- started_at
- completed_at
- last_activity_at
- created_at
- updated_at
```

字段说明：

- `study_plan_id` 和 `problem_id` 参与聊天框唯一身份。
- `origin_plan_version_id` 记录第一次创建会话时的计划版本。
- `latest_plan_version_id` 记录最近一次从哪个计划版本进入。
- `latest_plan_item_id` 记录最近一次对应的计划项，便于展示推荐理由和当前计划位置。
- `thread_id` 对应 LangGraph checkpoint thread。
- `phase` 是业务训练阶段，例如 `understand_problem`、`review_code`、`summarize`。
- `profile_snapshot_json` 保存最近一次用于起手或状态判断的画像快照摘要，方便解释和调试。

约束与索引：

```text
unique(user_id, study_plan_id, problem_id)
index(user_id, status, last_activity_at)
index(study_plan_id, problem_id)
index(thread_id)
```

外键：

- `user_id -> app_user.id`
- `study_plan_id -> study_plan.id`
- `problem_id -> problem.id`
- `origin_plan_version_id -> study_plan_version.id`
- `latest_plan_version_id -> study_plan_version.id`
- `latest_plan_item_id -> study_plan_item.id`
- `latest_code_snapshot_id -> code_snapshot.id`

注意：

- `latest_plan_item_id` 不参与唯一身份。计划调整后，同一道题可能在新版本中对应新的 plan item，但聊天框仍应复用。
- `profile_snapshot_json` 只保存用于决策的摘要，不保存完整用户历史聊天。

### 4.2 practice_event

用途：

保存训练时间线。前端聊天记录、业务事件回放、复盘和 Trace 排查都依赖它。

核心字段：

```text
practice_event
- id
- session_id
- user_id
- llm_run_id
- event_type
- role
- phase
- intent
- content_md
- payload_json
- hint_level
- visible_hint_gear
- created_at
```

字段说明：

- `event_type`：`session_started`、`user_message`、`assistant_message`、`code_saved`、`submission_feedback`、`phase_changed`、`summary_generated`。
- `role`：`user`、`assistant`、`system`、`tool`。
- `intent`：用户输入意图，例如 `describe_idea`、`stuck`、`request_hint`、`code_review`、`submit_feedback`、`request_summary`。
- `payload_json` 保存结构化事件数据，例如提交结果、代码 snapshot id、阶段变化原因。
- `content_md` 用于展示，不能作为唯一业务来源。

约束与索引：

```text
index(session_id, created_at)
index(user_id, created_at)
index(llm_run_id)
```

### 4.3 code_snapshot

用途：

保存用户代码版本。AI review、LeetCode 回填、复盘和后续画像分析都应指向明确代码版本。

核心字段：

```text
code_snapshot
- id
- session_id
- user_id
- event_id
- language
- code_text
- code_hash
- source
- client_revision
- created_at
```

字段说明：

- `source`：`paste`、`manual_save`、`before_review`、`before_submit`、`final`。
- `code_hash` 用于检测重复保存和日志排查。
- `code_text` 可以保存完整用户代码，但不得写入普通日志、Trace prompt 明文或错误摘要。

索引：

```text
index(session_id, created_at)
index(user_id, created_at)
index(code_hash)
```

### 4.4 submission_feedback

用途：

保存用户手动回填的 LeetCode 提交结果。第一版不自建判题，不自动提交 LeetCode。

核心字段：

```text
submission_feedback
- id
- session_id
- user_id
- event_id
- code_snapshot_id
- source
- result
- runtime_ms
- memory_kb
- failed_case_text
- error_message
- raw_feedback_json
- submitted_at
- created_at
```

字段说明：

- `source` 第一版固定为 `leetcode_manual`。
- `result`：`ac`、`wa`、`tle`、`re`、`mle`、`ce`、`unknown`。
- `failed_case_text` 和 `error_message` 可能包含用户提交内容，日志只能记录长度、hash 和错误类型摘要。

索引：

```text
index(session_id, created_at)
index(user_id, result, created_at)
index(code_snapshot_id)
```

### 4.5 coach_turn

用途：

保存一次 AI 教练交互的结构化结果。它是业务评估、状态跳转解释、泄题检查和复盘的重要来源。

核心字段：

```text
coach_turn
- id
- session_id
- user_id
- llm_run_id
- user_event_id
- assistant_event_id
- prompt_version
- model_name
- phase_before
- phase_after
- training_mode
- diagnosed_stuck_point
- user_intent
- next_action
- hint_level_before
- hint_level_after
- visible_hint_gear
- should_reveal_solution
- transition_reason
- response_json
- context_snapshot_json
- input_tokens
- output_tokens
- latency_ms
- created_at
```

字段说明：

- `llm_run_id` 关联统一 LLM Run 流式层。
- `phase_before` 和 `phase_after` 记录状态跳转。
- `transition_reason` 用于解释为什么快进、回退或保持当前阶段。
- `response_json` 保存模型结构化输出，包括用户可见回复、诊断、下一步动作和画像信号。
- `context_snapshot_json` 保存安全上下文摘要，例如画像版本、最近事件 id、问题标签、RAG chunk id，不保存完整 Prompt。

索引：

```text
index(session_id, created_at)
index(session_id, phase_after)
index(session_id, hint_level_after)
index(llm_run_id)
```

### 4.6 session_summary

用途：

保存单题复盘。它是复盘页、画像增量和后续 RAG 历史召回的主要输入。

核心字段：

```text
session_summary
- id
- session_id
- user_id
- problem_id
- result
- final_submission_result
- training_mode
- phases_visited_json
- transitions_json
- main_stuck_points_json
- error_types_json
- max_hint_level_used
- avg_hint_level
- attempt_count
- time_spent_seconds
- complexity_analysis_json
- invariant_summary_md
- review_summary_md
- profile_signals_json
- next_recommendation_json
- created_at
- updated_at
```

约束与索引：

```text
unique(session_id)
index(user_id, created_at)
index(problem_id)
```

### 4.7 profile_delta

用途：

保存一次训练对用户画像的增量影响。它不是第一阶段 AI 教练的硬依赖，但需要提前设计，避免复盘和画像脱节。

核心字段：

```text
profile_delta
- id
- user_id
- session_id
- summary_id
- skill_tag
- stuck_point
- delta_json
- before_json
- after_json
- evidence_json
- reason
- created_at
```

索引：

```text
index(user_id, created_at)
index(session_id)
index(skill_tag)
index(stuck_point)
```

### 4.8 user_skill_profile

用途：

保存用户在算法标签维度上的长期画像快照。

核心字段：

```text
user_skill_profile
- id
- user_id
- skill_tag
- mastery_score
- confidence_score
- solved_count
- attempted_count
- failed_count
- avg_hint_level
- last_practiced_at
- evidence_json
- created_at
- updated_at
```

约束：

```text
unique(user_id, skill_tag)
```

### 4.9 user_stuck_point_profile

用途：

保存用户在卡点维度上的长期画像。

核心字段：

```text
user_stuck_point_profile
- id
- user_id
- stuck_point
- severity_score
- occurrence_count
- recent_problem_ids_json
- evidence_json
- last_seen_at
- created_at
- updated_at
```

约束：

```text
unique(user_id, stuck_point)
```

## 5. LangGraph 状态设计

### 5.1 Graph State

AI 教练图的状态建议定义为业务状态快照，而不是简单消息列表。

```text
CoachGraphState
- user_id
- session_id
- thread_id
- study_plan_id
- problem_id
- phase
- training_mode
- current_hint_level
- visible_hint_gear
- latest_user_event_id
- latest_code_snapshot_id
- latest_submission_feedback_id
- problem_context
- plan_context
- profile_snapshot
- recent_events
- session_summary_brief
- user_input
- user_intent
- diagnosis
- transition_proposal
- transition_decision
- retrieval_context
- prompt_context
- model_output
- persisted_ids
```

原则：

- `practice_session` 是业务主状态。
- LangGraph checkpoint 用于恢复图执行过程。
- `thread_id` 使用 `practice_session.thread_id`。
- 图状态中可以带最近消息和上下文摘要，但长期事实以数据库表为准。

### 5.2 核心节点

第一版建议节点：

```text
load_session_context
classify_user_input
load_profile_snapshot
diagnose_learning_state
guard_state_transition
retrieve_supporting_context
build_prompt_context
call_coach_model
validate_model_output
persist_coach_turn
maybe_generate_summary
```

节点职责：

- `load_session_context`：读取 session、problem、plan item、最近事件、最新代码、最近提交结果。
- `classify_user_input`：识别用户本轮意图，例如描述思路、卡住、请求提示、贴代码、回填结果。
- `load_profile_snapshot`：通过 `ProfileProvider` 获取画像快照。第一阶段可以返回 mock。
- `diagnose_learning_state`：让 LLM 或规则判断当前阶段、卡点和下一步建议。
- `guard_state_transition`：后端守卫状态跳转和提示泄露边界。
- `retrieve_supporting_context`：后续接 RAG，按提示档位过滤知识片段。
- `build_prompt_context`：组装安全上下文。
- `call_coach_model`：调用模型生成结构化输出。
- `validate_model_output`：校验输出 schema、提示档位、是否泄题。
- `persist_coach_turn`：写入 `coach_turn`、`practice_event`，更新 `practice_session`。
- `maybe_generate_summary`：当进入复盘阶段时生成或更新 `session_summary`。

### 5.3 状态流转

业务阶段：

```text
understand_problem
propose_bruteforce
optimize_solution
define_invariant
write_code
review_code
submit_to_leetcode
analyze_feedback
summarize
```

标准流转：

```text
understand_problem
  -> propose_bruteforce
  -> optimize_solution
  -> define_invariant
  -> write_code
  -> review_code
  -> submit_to_leetcode
  -> analyze_feedback
  -> summarize
```

快进规则：

```text
用户输入包含清晰最优思路和复杂度
  -> write_code 或 review_code

用户直接贴代码
  -> review_code

用户贴代码并提供 WA/TLE/RE
  -> analyze_feedback

用户贴代码并提供 AC
  -> summarize
```

回退规则：

```text
代码 review 发现核心不变量错误
  -> define_invariant

提交结果 WA 且失败用例暴露边界问题
  -> review_code 或 define_invariant

用户无法解释复杂度
  -> optimize_solution
```

### 5.4 后端守卫规则

LLM 只能提出跳转建议，后端必须校验：

- 低提示档位不能进入完整题解输出。
- 没有代码时不能进入代码 review，除非用户明确请求伪代码层面的 review。
- 没有提交结果时不能进入 `analyze_feedback`。
- AC 可以进入 `summarize`，但复盘必须要求用户说明最终复杂度或由 AI 引导确认。
- 用户请求复盘但缺少训练证据时，可以生成“阶段性复盘”，不能标记完整完成。
- 任意状态都可以在用户明确请求时进入更高提示档位，但必须记录原因和最高提示档位。

## 6. Prompt 与上下文管理

### 6.1 Prompt 分类

建议拆分 Prompt 版本：

```text
coach_start_v1          # 新会话第一问
coach_turn_v1           # 普通训练轮次
coach_code_review_v1    # 代码 review
coach_feedback_v1       # LeetCode 结果分析
coach_summary_v1        # 单题复盘
```

每次模型调用都必须记录 `prompt_version`。

### 6.2 Prompt 输入结构

Prompt 上下文按固定结构组装：

```text
system_policy
coach_behavior_rules
session_state
problem_context
plan_context
profile_snapshot
recent_conversation
latest_code_snapshot
submission_feedback
retrieval_context
output_schema
```

说明：

- `system_policy` 定义 AI 教练不是答案生成器。
- `coach_behavior_rules` 定义提示档位、状态跳转和禁止泄题规则。
- `session_state` 包含当前 phase、training mode、hint level、最高提示档位。
- `problem_context` 只包含题面、难度、标签和必要约束，不包含完整题解。
- `plan_context` 包含计划阶段、推荐理由和训练目标。
- `profile_snapshot` 来自 `ProfileProvider`。
- `recent_conversation` 使用最近 N 条事件和摘要，不直接塞完整历史。
- `latest_code_snapshot` 只在代码 review 或提交反馈阶段加入。
- `retrieval_context` 必须按 hint level 过滤。
- `output_schema` 要求模型返回结构化 JSON。

### 6.3 上下文预算

第一版上下文预算建议：

```text
题面和约束：固定保留
计划上下文：保留当前计划、阶段和计划项推荐理由
画像快照：保留摘要，不超过 800 中文字
最近对话：最近 8-12 条事件
历史摘要：优先使用 session_summary 或阶段摘要
代码：只保留最新代码或用户本轮代码
提交反馈：只保留最近一次或本轮相关反馈
RAG：最多 3-5 个片段，且受提示档位过滤
```

### 6.4 模型输出 Schema

模型输出建议统一为：

```text
CoachModelOutput
- visible_reply_md
- user_intent
- diagnosed_stuck_point
- phase_before
- proposed_phase_after
- next_action
- hint_level_after
- visible_hint_gear
- should_reveal_solution
- transition_reason
- confidence
- profile_signals
- needs_user_action
- suggested_user_action
- safety_flags
```

后端只把 `visible_reply_md` 展示给用户；其他字段用于状态跳转、复盘、画像和质量评估。

### 6.5 安全与日志

不得进入日志的内容：

- API key、session token。
- 完整用户代码。
- 完整用户输入。
- 完整题解。
- 密钥密文。

可以记录：

- 用户 id、session id、run id。
- phase、hint level、prompt version。
- 代码长度、hash、语言。
- 提交结果类型。
- 错误摘要。
- 模型输出 schema 校验结果。

## 7. 用户画像模块设计

### 7.1 ProfileProvider 接口

AI 教练不直接读取画像表，而是依赖服务接口：

```text
ProfileProvider.get_snapshot(user_id, problem_id, study_plan_id) -> ProfileSnapshot
```

`ProfileSnapshot` 建议包含：

```text
ProfileSnapshot
- version
- source
- confidence
- overall_level
- preferred_training_mode
- weak_stuck_points
- strong_skill_tags
- weak_skill_tags
- recent_summary
- hint_policy_hint
- evidence
```

### 7.2 第一阶段 mock 实现

mock 画像来源：

- 目标校准输入和自评弱项。
- `study_plan_version.target_snapshot_json`。
- `study_plan_stage.focus_tags_json`。
- `study_plan_item.skill_tags_json`。
- `study_plan_item.suggested_mode`。
- 已有 `session_summary`，如果该表已落地。

mock 输出示例：

```json
{
  "version": "profile-snapshot-v1",
  "source": "mock_from_goal_and_plan",
  "confidence": "medium",
  "overall_level": "intermediate",
  "preferred_training_mode": "independent",
  "weak_stuck_points": ["edge_case", "invariant"],
  "weak_skill_tags": ["hash-table"],
  "hint_policy_hint": "先追问边界和不变量，不直接给完整流程"
}
```

### 7.3 真实画像实现

真实画像模块落地后：

```text
session_summary
  -> profile_delta
  -> user_skill_profile
  -> user_stuck_point_profile
  -> ProfileProvider.get_snapshot()
```

要求：

- `profile_delta` 必须保存证据和前后变化。
- `user_skill_profile` 和 `user_stuck_point_profile` 是查询快照，不是唯一事实来源。
- ProfileProvider 输出格式保持不变。
- Prompt 层不关心画像来自 mock 还是正式表。

## 8. LLM Run 与 LangGraph 的关系

现有 `llm_run` 是统一流式层，应继续复用。

建议关系：

```text
用户触发一次 AI 教练动作
  -> create llm_run(kind = coach_message / code_review / reflection)
  -> llm_orchestrator 启动对应 handler
  -> handler 调用 CoachGraph
  -> Graph 写 practice_event / coach_turn / session_summary
  -> llm_run 记录状态、展示文本和最终 result
```

`llm_run` 负责：

- 流式状态。
- 取消。
- 模型资产选择。
- 前端 SSE。
- 最终结果恢复。

`practice_session` 和 `coach_turn` 负责：

- 业务状态。
- 聊天框恢复。
- 状态跳转。
- 复盘和画像输入。

不要把业务状态只放在 `llm_run.result_json` 里。`llm_run` 是一次模型调用，`practice_session` 才是长期训练会话。

## 9. API 边界建议

第一版建议 API：

```text
POST /api/practice-sessions
GET  /api/practice-sessions/{session_id}
GET  /api/practice-sessions/{session_id}/events
POST /api/practice-sessions/{session_id}/messages
POST /api/practice-sessions/{session_id}/code-snapshots
POST /api/practice-sessions/{session_id}/submission-feedback
POST /api/practice-sessions/{session_id}/summary
```

也可以提供计划项快捷入口：

```text
POST /api/study-plan/items/{item_id}/practice-session
```

该接口按 `user_id + study_plan_id + problem_id` 查找或创建 session，并更新 `latest_plan_version_id` 和 `latest_plan_item_id`。

## 10. 分阶段实施建议

### 阶段 A：训练会话底座

目标：

- 落地 `practice_session`、`practice_event`、`code_snapshot`、`submission_feedback`。
- 实现从计划题进入工作台并恢复同一聊天框。
- 暂不接真实 AI 教练，可以先写用户事件和提交回填。

### 阶段 B：AI 教练最小闭环

目标：

- 落地 `coach_turn`。
- 接入 `llm_run` 的 `coach_message` 和 `code_review` handler。
- 实现 ProfileProvider mock。
- 实现基础 Prompt 和结构化输出校验。
- 支持状态快进：思路清晰、贴代码、回填结果。

### 阶段 C：LangGraph 编排

目标：

- 将 AI 教练 handler 内部替换为 CoachGraph。
- 使用 `practice_session.thread_id` 做 checkpoint thread。
- 增加状态守卫和 trace。
- 支持恢复中断执行。

### 阶段 D：复盘与画像

目标：

- 落地 `session_summary`、`profile_delta`、`user_skill_profile`、`user_stuck_point_profile`。
- 用真实画像替换 mock ProfileProvider。
- 让复盘和画像进入后续 AI 起手问题和上下文召回。

### 阶段 E：RAG 增强

目标：

- 接入知识库和向量检索。
- 按 hint level、knowledge type 和 has_full_solution 过滤。
- 使用 `retrieval_trace` 记录召回和过滤结果。

## 11. 测试策略

### 11.1 表结构测试

- 同一用户、同一计划、同一题只能创建一个 `practice_session`。
- 同一用户、新计划、同一题可以创建新 `practice_session`。
- 计划版本变化不会创建新 session，只更新 latest version 字段。
- `practice_event` 按 session 时间线稳定排序。
- 提交反馈必须关联 session，尽量关联 code snapshot。

### 11.2 状态机测试

- 用户输入高质量思路后，从基础阶段快进到写代码或 review。
- 用户贴代码后进入 review。
- 用户回填 WA 后进入反馈分析。
- 用户回填 AC 后进入复盘。
- 低提示档位下模型试图泄露完整答案时，后端拒绝或降级输出。

### 11.3 Prompt 测试

- 初学用户第一问偏基础。
- 熟练用户第一问不重复基础题意。
- 边界薄弱用户第一问聚焦边界用例。
- Prompt 不包含完整历史聊天。
- Prompt 不包含完整题解。

### 11.4 画像 mock 测试

- 无真实画像表时，ProfileProvider 能返回稳定 mock snapshot。
- mock snapshot 标记 source 和 confidence。
- 有 session_summary 时，mock snapshot 能融合最近复盘摘要。
- 后续真实 ProfileProvider 替换后，Prompt 组装接口不变。

## 12. 风险与取舍

### 12.1 状态机过早复杂化

风险：

一开始接完整 LangGraph、RAG 和画像，可能拖慢训练闭环落地。

取舍：

先用有限状态和后端守卫跑通 T2/T3，再在 T4 引入 LangGraph 编排。

### 12.2 mock 画像误导 AI

风险：

mock 画像如果伪装成真实画像，会让 AI 过度自信。

取舍：

mock snapshot 必须带 `source` 和 `confidence`，Prompt 中要求模型把低置信画像当作弱信号。

### 12.3 原始聊天进入 RAG 噪声过高

风险：

直接召回完整聊天会把错误思路、大段代码和无关对话放进上下文。

取舍：

优先召回 `session_summary`、`profile_delta` 和画像快照，必要时才召回关键事件。

### 12.4 表结构过度耦合计划版本

风险：

如果把 `study_plan_version_id` 放进 session 唯一键，每次调整计划都会新建聊天框。

取舍：

唯一键只使用 `user_id + study_plan_id + problem_id`，版本字段只做追溯。

## 13. 验收标准

研发设计验收：

- 表结构能表达同一计划题复用聊天框。
- 表结构能保存用户消息、AI 消息、代码版本、LeetCode 回填和复盘。
- LangGraph 状态能支持快进、回退和提示档位守卫。
- Prompt 上下文有明确来源、预算和安全边界。
- 用户画像缺失时有可替换的 mock Provider。
- 真实画像模块落地后，不需要重写 AI 教练主流程。

第一阶段工程验收：

- 从学习计划题目进入工作台可以创建或恢复 session。
- 同一计划题重复进入不会新建聊天框。
- 新计划里的同一道题会创建新聊天框。
- 用户输入、代码和提交反馈能保存为结构化事件。
- AI 教练调用能记录 `llm_run`、`coach_turn` 和 assistant event。
- Prompt 能根据 mock profile 生成差异化第一问。
