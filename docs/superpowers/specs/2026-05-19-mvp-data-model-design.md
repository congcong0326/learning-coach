# MVP 数据模型研发设计

## 目标

本文档基于当前 PRD、项目进度和已落地代码，给出 Agentic Coding Learning Coach 第一版 MVP 的数据模型蓝图。

本设计只关注数据建模：

- 会有哪些核心表。
- 每张表保存什么关键字段。
- 表之间怎么关联。
- 哪些表已经落地，哪些仍是后续规划。

本文档不展开 API、页面、Prompt、LangGraph 节点实现和 migration 细节。后续实施时应按阶段拆分 Alembic migration，并以实际代码和测试回填本文档。

## 参考文档与代码

- `docs/index.md`：目录职责和文档维护映射。
- `docs/prd/prd.md`：MVP 范围、AI Coach、训练闭环、RAG、工具层、画像和 Trace 要求。
- `docs/project-todolist.md`：当前阶段、已完成能力和 T1-T10 任务拆分。
- `docs/architecture/foundation.md`：当前全栈边界、数据库选型和已落地表说明。
- `docs/superpowers/specs/2026-05-19-problem-ingestion-design.md`：题库表设计。
- `docs/superpowers/specs/2026-05-19-local-auth-api-asset-design.md`：用户、session 和 LLM API 资产基础设计。
- `docs/superpowers/specs/2026-05-19-api-asset-routing-settings-design.md`：LLM API 资产池和粘性路由设计。
- `backend/app/models/problem.py`：已落地题库 SQLAlchemy 模型。
- `backend/app/models/auth.py`：已落地用户、session 和 LLM API 资产 SQLAlchemy 模型。
- `backend/app/db/migrations/versions/`：当前 Alembic migration。

## 当前完成情况

当前已经完成工程基座、题库 seed、题库表、题库 API、题库列表、工作台题面读取、本地注册登录和用户级 OpenAI API 资产池配置。

已落地的数据表包括：

- `app_metadata`
- `agent_trace` 基础版
- `retrieval_trace` 基础版
- `problem`
- `problem_category`
- `problem_category_item`
- `app_user`
- `auth_session`
- `llm_credential`

尚未落地的数据域包括：

- 目标校准草稿、用户学习目标和学习计划。
- 训练会话、事件流、代码快照和提交回填。
- AI 教练回合、LangGraph thread/checkpoint 映射和工具调用结果。
- RAG 知识源、知识文档、知识切块和向量检索。
- 单题复盘、用户画像、画像增量、推荐批次和仪表盘聚合。
- 面试模拟总结、Eval 运行记录和 Eval case 结果。

## 设计原则

1. **用户隔离**：所有用户私有数据都必须从 `app_user.id` 出发关联，包括目标、计划、训练、画像、推荐、LLM API 资产和 Trace。
2. **题库与训练解耦**：`problem` 保存静态题面；用户训练状态不写回题库主表，避免题库数据被用户行为污染。
3. **题解隔离**：第一版 `problem` 不保存完整题解；RAG 表必须标记 `has_full_solution` 和 hint level，防止低提示档位泄题。
4. **会话事件可追溯**：训练过程用 `practice_session` 表示当前状态，用 `practice_event` 记录事件流；状态用于读取，事件用于复盘、Trace 和调试。
5. **AI 输出结构化**：AI 教练回复除了用户可见文本，还要保存诊断、动作、提示等级、Prompt 版本和 token/latency 元数据。
6. **工具调用可复用**：代码运行、测试用例生成、静态分析和错误归因统一进入 `tool_run`，避免每个工具独立建一套日志模型。
7. **画像增量可审计**：用户画像当前值和每次训练带来的 `profile_delta` 分开保存，便于解释“为什么推荐下一题”。
8. **Trace 是观测层，不是业务主状态**：`agent_trace` 和 `retrieval_trace` 用于调试和评估，业务页面读取应优先依赖 session、summary、profile 和 recommendation 表。

## 全局 ASCII 图

```text
app_user
  |
  +-- auth_session
  |
  +-- llm_credential
  |      ^                         +-------------------------+
  |      |                         |                         |
  |      +-------------------- coach_turn               agent_trace
  |                                                            ^
  +-- goal_calibration_draft                                  |
  |        |                                                   |
  +-- user_learning_goal -- study_plan -- study_plan_item -- problem
  |                              |              |              |
  |                              |              +--------------+
  |                              |
  +-- practice_session ----------+
  |        | problem_id / goal_id / plan_id / plan_item_id
  |        |
  |        +-- practice_event
  |        +-- code_snapshot
  |        +-- submission_feedback
  |        +-- coach_turn
  |        +-- tool_run -- generated_test_case
  |        +-- agent_thread
  |        +-- session_summary -- profile_delta
  |        |                         |
  |        |                         +-- user_skill_profile
  |        |                         +-- user_stuck_point_profile
  |        |
  |        +-- mock_interview_summary
  |        +-- agent_trace
  |        +-- retrieval_trace -- knowledge_chunk -- knowledge_doc -- knowledge_source
  |
  +-- recommendation_batch -- recommendation_item -- problem
  |
  +-- dashboard_metric_snapshot

problem_category -- problem_category_item -- problem

eval_run -- eval_case_result
```

说明：

- `practice_session` 是训练闭环的中心表，连接用户、题目、目标、计划项和后续所有过程数据。
- `practice_event` 保存用户消息、教练回复、状态变化和关键操作；`coach_turn` 保存 AI 教练单轮结构化输出。
- `tool_run` 记录工具执行，`generated_test_case` 只保存需要复用或展示的测试用例。
- `session_summary` 是单题复盘结果；`profile_delta` 把复盘结果转化为画像增量。
- `knowledge_doc` 和 `knowledge_chunk` 是 RAG 知识库核心；`retrieval_trace` 记录某次检索实际拿到和使用了哪些 chunk。
- `agent_trace`、`retrieval_trace`、`eval_run`、`eval_case_result` 属于观测和评估域，不承担主业务状态。

## 表清单

| 数据域 | 表 | 状态 | 对应阶段 | 用途 |
| --- | --- | --- | --- | --- |
| 基础设施 | `app_metadata` | 已落地 | B0 | 保存应用级元数据。 |
| 用户与资产 | `app_user` | 已落地 | T0 | 本地用户主表。 |
| 用户与资产 | `auth_session` | 已落地 | T0 | 后端登录 session。 |
| 用户与资产 | `llm_credential` | 已落地 | T0 | 用户级 OpenAI API 资产池。 |
| 题库 | `problem` | 已落地 | B1 | 静态题目主数据。 |
| 题库 | `problem_category` | 已落地 | B1 | 题单或题目分类。 |
| 题库 | `problem_category_item` | 已落地 | B1 | 题目和分类多对多关系。 |
| 目标计划 | `goal_calibration_draft` | 规划 | T1 | LLM 生成的目标和计划草稿。 |
| 目标计划 | `user_learning_goal` | 规划 | T1 | 用户确认后的学习目标。 |
| 目标计划 | `study_plan` | 规划 | T1 | 一次目标对应的训练计划。 |
| 目标计划 | `study_plan_item` | 规划 | T1 | 计划中的推荐题目。 |
| 训练会话 | `practice_session` | 规划 | T2 | 单题训练会话主状态。 |
| 训练会话 | `practice_event` | 规划 | T2/T3 | 训练事件流和对话记录。 |
| 训练会话 | `code_snapshot` | 规划 | T2/T5 | 用户代码快照。 |
| 训练会话 | `submission_feedback` | 规划 | T2/T5 | 用户手动回填的 LeetCode 提交结果。 |
| AI 教练 | `coach_turn` | 规划 | T3/T4 | AI 教练单轮结构化输出。 |
| AI 教练 | `agent_thread` | 规划 | T4 | 应用 session 与 LangGraph thread/checkpoint 的映射。 |
| 工具层 | `tool_run` | 规划 | T5 | 代码运行、分析、归因等工具调用记录。 |
| 工具层 | `generated_test_case` | 规划 | T5 | 生成或抽取的可复用测试用例。 |
| RAG | `knowledge_source` | 规划 | T6 | 本地教程或生成卡片的来源清单。 |
| RAG | `knowledge_doc` | 规划 | T6 | 原始语料文档或派生教练知识卡。 |
| RAG | `knowledge_chunk` | 规划 | T6 | 向量检索切块。 |
| RAG | `retrieval_trace` | 已落地基础版 | B0/T6 | RAG 检索过程记录。 |
| 复盘画像 | `session_summary` | 规划 | T7 | 单题复盘总结。 |
| 复盘画像 | `profile_delta` | 规划 | T7 | 单次训练对画像的增量影响。 |
| 复盘画像 | `user_skill_profile` | 规划 | T7 | 用户在算法标签维度的长期画像。 |
| 复盘画像 | `user_stuck_point_profile` | 规划 | T7 | 用户在卡点类型维度的长期画像。 |
| 推荐仪表盘 | `recommendation_batch` | 规划 | T7 | 一次推荐生成批次。 |
| 推荐仪表盘 | `recommendation_item` | 规划 | T7 | 推荐题目和推荐理由。 |
| 推荐仪表盘 | `dashboard_metric_snapshot` | 规划 | T7 | 仪表盘聚合指标缓存。 |
| 面试模拟 | `mock_interview_summary` | 规划 | T8 | 面试模拟评分和复盘。 |
| Trace/Eval | `agent_trace` | 已落地基础版 | B0/T9 | Agent 节点、模型和工具观测记录。 |
| Trace/Eval | `eval_run` | 规划 | T9 | 一次 Eval 执行记录。 |
| Trace/Eval | `eval_case_result` | 规划 | T9 | 单个 Eval case 的输入、输出和评分。 |

## 通用字段约定

除非特别说明，业务表默认包含：

```text
- id
- created_at
- updated_at
```

用户私有表默认包含：

```text
- user_id -> app_user.id
```

训练过程表默认包含：

```text
- session_id -> practice_session.id
- user_id -> app_user.id
```

时间字段使用带时区时间。枚举字段第一版使用字符串存储，服务层和 Pydantic schema 负责校验；当枚举稳定后再评估是否使用数据库 enum 或 check constraint。

## 基础设施

### app_metadata

状态：已落地。

用途：

保存应用级键值元数据，例如 seed 版本、初始化标记或后续需要跨服务读取的轻量配置。它不是业务配置中心，不应保存用户私有数据或密钥。

核心字段：

```text
app_metadata
- key
- value
- created_at
- updated_at
```

## 用户与 LLM API 资产

### app_user

状态：已落地。

核心字段：

```text
app_user
- id
- username
- email
- password_hash
- display_name
- status                 # active / disabled
- last_login_at
- created_at
- updated_at
```

关系：

- `app_user 1:N auth_session`
- `app_user 1:N llm_credential`
- `app_user 1:N user_learning_goal`
- `app_user 1:N study_plan`
- `app_user 1:N practice_session`
- `app_user 1:N user_skill_profile`

### auth_session

状态：已落地。

核心字段：

```text
auth_session
- id
- user_id
- session_token_hash
- expires_at
- revoked_at
- created_at
- last_seen_at
```

关系：

- `auth_session.user_id -> app_user.id`

说明：

- 浏览器只保存 HttpOnly session cookie。
- 数据库只保存 session token hash，不保存明文 token。

### llm_credential

状态：已落地。

核心字段：

```text
llm_credential
- id
- user_id
- provider               # openai
- display_name
- base_url
- api_mode               # responses
- model_name
- api_key_ciphertext
- api_key_mask
- is_default             # 兼容字段，语义等同 is_preferred
- is_enabled
- is_preferred
- is_active
- failure_count
- status                 # untested / valid / invalid
- last_tested_at
- last_used_at
- last_error
- created_at
- updated_at
```

关系：

- `llm_credential.user_id -> app_user.id`
- `coach_turn.llm_credential_id -> llm_credential.id`
- `goal_calibration_draft.llm_credential_id -> llm_credential.id`

说明：

- API key 只保存 Fernet 密文和脱敏 mask。
- 同一用户的首选资产和当前通讯资产由服务层保证唯一。
- 后续所有 LLM 调用都应通过该资产池选择，不直接读取全局 API key。

## 题库与分类

### problem

状态：已落地。

核心字段：

```text
problem
- id
- frontend_id
- slug
- title
- translated_title
- difficulty             # Easy / Medium / Hard
- statement_md
- metadata_json
- leetcode_url
- is_paid_only
- created_at
- updated_at
```

关系：

- `problem 1:N problem_category_item`
- `problem 1:N study_plan_item`
- `problem 1:N practice_session`
- `problem 1:N knowledge_doc`，用于题目教练卡片。
- `problem 1:N recommendation_item`

说明：

- `statement_md` 只保存题面、示例和约束，不保存完整题解。
- `metadata_json` 可保存标签、相似题、样例、函数签名和 Python 模板等静态元数据。

### problem_category

状态：已落地。

核心字段：

```text
problem_category
- id
- slug
- name
- description
- created_at
- updated_at
```

关系：

- `problem_category 1:N problem_category_item`

### problem_category_item

状态：已落地。

核心字段：

```text
problem_category_item
- id
- category_id
- problem_id
- sort_order
- created_at
- updated_at
```

关系：

- `problem_category_item.category_id -> problem_category.id`
- `problem_category_item.problem_id -> problem.id`

约束：

- `(category_id, problem_id)` 唯一。

## 目标校准与学习计划

### goal_calibration_draft

状态：规划。

用途：

保存用户提交目标校准表单后，由 LLM 生成、但尚未确认的目标和计划草稿。该表用于支持重试、确认前编辑、错误排查和后续分析“LLM 生成计划是否合理”。

核心字段：

```text
goal_calibration_draft
- id
- user_id
- llm_credential_id
- input_json              # 用户原始表单：目标、时间线、投入、弱项等
- draft_goal_json         # LLM 生成的目标草稿
- draft_plan_json         # LLM 生成的计划草稿和推荐理由
- prompt_version
- model_name
- status                  # generated / confirmed / discarded / failed
- error_message
- confirmed_goal_id
- confirmed_plan_id
- created_at
- confirmed_at
```

关系：

- `goal_calibration_draft.user_id -> app_user.id`
- `goal_calibration_draft.llm_credential_id -> llm_credential.id`
- `goal_calibration_draft.confirmed_goal_id -> user_learning_goal.id`
- `goal_calibration_draft.confirmed_plan_id -> study_plan.id`

### user_learning_goal

状态：规划。

用途：

保存用户确认后的学习目标。保留历史记录，不只保存当前目标。

核心字段：

```text
user_learning_goal
- id
- user_id
- draft_id
- goal_type               # beginner / interview_sprint / strengthen_weakness / maintain
- target_timeline         # none / within_1_month / one_to_three_months / over_three_months
- weekly_days
- session_minutes
- preferred_language      # 第一版固定 python
- self_reported_weaknesses_json
- confirmed_goal_md
- default_training_mode   # guided / independent / mock_interview
- default_hint_gear       # questioning / direction / key_hint / review
- status                  # active / archived
- created_at
- updated_at
```

关系：

- `user_learning_goal.user_id -> app_user.id`
- `user_learning_goal.draft_id -> goal_calibration_draft.id`
- `user_learning_goal 1:N study_plan`
- `user_learning_goal 1:N practice_session`

说明：

- 同一用户同时只应有一个 active goal，由服务层归档旧目标。
- 自评弱项用于 T1 计划生成和 T7 画像初始化，但不能替代真实训练画像。

### study_plan

状态：规划。

用途：

保存一次目标对应的训练计划。用户重新校准目标时会创建新计划，旧 active 计划归档。

核心字段：

```text
study_plan
- id
- user_id
- goal_id
- draft_id
- title
- status                  # active / completed / archived
- strategy                # beginner_path / interview_sprint / weakness_based / maintenance
- start_date
- end_date
- plan_summary_md
- created_at
- updated_at
```

关系：

- `study_plan.user_id -> app_user.id`
- `study_plan.goal_id -> user_learning_goal.id`
- `study_plan.draft_id -> goal_calibration_draft.id`
- `study_plan 1:N study_plan_item`
- `study_plan 1:N practice_session`

### study_plan_item

状态：规划。

用途：

保存计划中的推荐题目、排序、建议训练模式和推荐理由。

核心字段：

```text
study_plan_item
- id
- plan_id
- problem_id
- problem_slug            # 冗余保存，便于路由和 trace
- skill_tags_json
- difficulty
- suggested_mode          # guided / independent / mock_interview
- recommendation_reason
- status                  # pending / in_progress / completed / skipped
- order_index
- created_at
- updated_at
```

关系：

- `study_plan_item.plan_id -> study_plan.id`
- `study_plan_item.problem_id -> problem.id`
- `study_plan_item 1:N practice_session`

约束：

- `(plan_id, problem_id)` 唯一。
- `(plan_id, order_index)` 用于稳定排序。

## 训练会话与工作台状态

### practice_session

状态：规划。

用途：

单题训练的主状态表。工作台恢复、训练模式、提示档位、当前阶段和最终结果都从这里读取。

核心字段：

```text
practice_session
- id
- user_id
- problem_id
- problem_slug
- goal_id
- study_plan_id
- plan_item_id
- thread_id               # LangGraph thread id
- training_mode           # guided / independent / mock_interview
- phase                   # understand / plan / implement / debug / review / summary
- status                  # active / paused / completed / abandoned
- current_hint_level      # 0-5
- visible_hint_gear       # questioning / direction / key_hint / review
- max_hint_level_used
- attempt_count
- latest_code_snapshot_id
- final_result            # ac / wa / tle / re / unknown / not_submitted
- started_at
- completed_at
- last_activity_at
- created_at
- updated_at
```

关系：

- `practice_session.user_id -> app_user.id`
- `practice_session.problem_id -> problem.id`
- `practice_session.goal_id -> user_learning_goal.id`
- `practice_session.study_plan_id -> study_plan.id`
- `practice_session.plan_item_id -> study_plan_item.id`
- `practice_session 1:N practice_event`
- `practice_session 1:N code_snapshot`
- `practice_session 1:N submission_feedback`
- `practice_session 1:N coach_turn`
- `practice_session 1:N tool_run`
- `practice_session 1:1 session_summary`
- `practice_session 1:1 mock_interview_summary`

说明：

- `practice_session` 是可恢复的当前状态，不替代事件流。
- T2 创建训练会话后，计划项状态可从 `pending` 变为 `in_progress`。

### practice_event

状态：规划。

用途：

保存训练过程中的事件流。它是复盘、会话回放、上下文重建和 Trace 页的重要来源。

核心字段：

```text
practice_event
- id
- session_id
- user_id
- event_type              # user_message / coach_message / code_saved / tool_run / submission_feedback / phase_changed
- role                    # user / assistant / system / tool
- phase
- content_md
- payload_json
- hint_level
- visible_hint_gear
- created_at
```

关系：

- `practice_event.session_id -> practice_session.id`
- `practice_event.user_id -> app_user.id`
- `coach_turn.user_event_id -> practice_event.id`
- `coach_turn.assistant_event_id -> practice_event.id`
- `tool_run.event_id -> practice_event.id`

### code_snapshot

状态：规划。

用途：

保存用户代码版本，支持工作台恢复、代码 review、运行工具、复盘和面试模拟评分。

核心字段：

```text
code_snapshot
- id
- session_id
- user_id
- event_id
- language                # python
- code_text
- source                  # autosave / manual_save / before_run / before_submit / final
- client_revision
- created_at
```

关系：

- `code_snapshot.session_id -> practice_session.id`
- `code_snapshot.event_id -> practice_event.id`
- `tool_run.code_snapshot_id -> code_snapshot.id`
- `practice_session.latest_code_snapshot_id -> code_snapshot.id`

说明：

- 第一版只支持 Python，但字段保留语言维度，便于后续扩展。
- 自动保存频率应由前端和服务层控制，避免每次键入都写数据库。

### submission_feedback

状态：规划。

用途：

保存用户从 LeetCode 手动回填的提交结果。第一版不自动提交 LeetCode。

核心字段：

```text
submission_feedback
- id
- session_id
- user_id
- code_snapshot_id
- source                  # leetcode_manual / local_run
- result                  # ac / wa / tle / re / mle / ce / unknown
- runtime_ms
- memory_kb
- failed_case_text
- error_message
- raw_feedback_json
- submitted_at
- created_at
```

关系：

- `submission_feedback.session_id -> practice_session.id`
- `submission_feedback.code_snapshot_id -> code_snapshot.id`

## AI 教练与 LangGraph 状态

### coach_turn

状态：规划。

用途：

保存一次 AI 教练交互的业务级结构化结果。它比 `agent_trace` 更适合给复盘、仪表盘和低层级泄题评估使用。

核心字段：

```text
coach_turn
- id
- session_id
- user_id
- user_event_id
- assistant_event_id
- llm_credential_id
- prompt_version
- model_name
- phase
- training_mode
- diagnosed_stuck_point   # problem_understanding / pattern / invariant / implementation / edge_case / complexity / expression
- next_action             # ask_question / give_hint / review_code / run_code / summarize
- hint_level
- visible_hint_gear
- should_reveal_solution
- response_json           # 结构化输出，包含可见回复、追问、提示、review 点等
- input_tokens
- output_tokens
- latency_ms
- created_at
```

关系：

- `coach_turn.session_id -> practice_session.id`
- `coach_turn.user_event_id -> practice_event.id`
- `coach_turn.assistant_event_id -> practice_event.id`
- `coach_turn.llm_credential_id -> llm_credential.id`

说明：

- `should_reveal_solution` 应默认 false，只有复盘档或明确允许场景才可能为 true。
- 低提示等级是否泄题可以从 `hint_level`、`response_json` 和 Eval 结果联合分析。

### agent_thread

状态：规划。

用途：

保存应用训练会话和 LangGraph thread/checkpoint 的映射。真实 checkpoint 可以使用 LangGraph 官方持久化表或独立 schema；本表只保存业务入口需要的映射和最新状态摘要。

核心字段：

```text
agent_thread
- id
- session_id
- user_id
- thread_id
- checkpoint_namespace
- latest_checkpoint_id
- graph_version
- state_summary_json
- status                  # active / interrupted / completed / failed
- created_at
- updated_at
```

关系：

- `agent_thread.session_id -> practice_session.id`

## 工具层

### tool_run

状态：规划。

用途：

统一保存工具调用结果，包括运行 Python 代码、生成测试用例、静态分析、错误归因、推荐下一题和面试评分。

核心字段：

```text
tool_run
- id
- session_id
- user_id
- event_id
- code_snapshot_id
- tool_name               # run_python_code / generate_test_cases / analyze_code / classify_error / recommend_next_problem / score_mock_interview
- status                  # success / failed / timeout / skipped
- input_json
- output_json
- error_type
- error_message
- elapsed_ms
- created_at
```

关系：

- `tool_run.session_id -> practice_session.id`
- `tool_run.event_id -> practice_event.id`
- `tool_run.code_snapshot_id -> code_snapshot.id`

说明：

- `run_python_code` 的输出应包含通过数量、失败数量、stdout、stderr、elapsed_ms 和失败样例。
- 工具输入输出可能包含用户代码，应按本地开发数据处理，不进入公开日志。

### generated_test_case

状态：规划。

用途：

保存需要展示或复用的测试用例。临时工具输出如果不需要复用，可以只保存在 `tool_run.output_json`。

核心字段：

```text
generated_test_case
- id
- session_id
- problem_id
- tool_run_id
- source                  # statement_example / llm_generated / user_added / edge_case
- input_json
- expected_output_json
- explanation
- is_active
- created_at
```

关系：

- `generated_test_case.session_id -> practice_session.id`
- `generated_test_case.problem_id -> problem.id`
- `generated_test_case.tool_run_id -> tool_run.id`

## RAG 知识库

### knowledge_source

状态：规划。

用途：

保存本地教程、课程讲义、博客、个人笔记或生成卡片的来源信息。

核心字段：

```text
knowledge_source
- id
- source_type             # book / tutorial / blog / course_note / personal_note / generated_card
- source_name
- source_path
- source_url
- license_note
- content_hash
- imported_at
- created_at
- updated_at
```

关系：

- `knowledge_source 1:N knowledge_doc`

### knowledge_doc

状态：规划。

用途：

保存原始教程文档或派生教练知识卡片。派生卡片是做题时 RAG 的主要检索对象。

核心字段：

```text
knowledge_doc
- id
- source_id
- parent_doc_id
- doc_type                # raw_tutorial / concept / pattern / invariant / problem_coach_card / common_bug / hint / interview_expression
- title
- content
- tags_json
- problem_id
- problem_slug
- difficulty
- phase                   # understand / plan / implement / debug / review / summary
- stuck_point
- hint_level_min
- hint_level_max
- is_solution
- has_full_solution
- source_locator
- content_hash
- created_at
- updated_at
```

关系：

- `knowledge_doc.source_id -> knowledge_source.id`
- `knowledge_doc.parent_doc_id -> knowledge_doc.id`
- `knowledge_doc.problem_id -> problem.id`
- `knowledge_doc 1:N knowledge_chunk`

说明：

- `problem_coach_card` 可以关联具体 `problem`。
- 低 hint level 检索必须过滤 `has_full_solution = true` 的内容。

### knowledge_chunk

状态：规划。

用途：

保存可向量检索的切块。

核心字段：

```text
knowledge_chunk
- id
- doc_id
- chunk_text
- embedding               # pgvector
- metadata_json
- knowledge_type          # concept / pattern / invariant / bug / code_template / example / expression
- hint_level_min
- hint_level_max
- has_full_solution
- source_locator
- created_at
```

关系：

- `knowledge_chunk.doc_id -> knowledge_doc.id`
- `retrieval_trace.selected_chunk_ids` 记录被选入 prompt 的 chunk id 列表。

### retrieval_trace

状态：已落地基础版，T6 需要接入真实检索。

核心字段：

```text
retrieval_trace
- id
- session_id
- problem_slug
- query
- retrieved_doc_ids
- selected_chunk_ids
- current_hint_level
- retrieval_intent
- filtered_out_chunk_ids
- used_in_prompt
- created_at
```

后续增强：

- 将 `session_id` 从字符串语义收敛为 `practice_session.id` 或保存双字段：业务 session id 与 LangGraph thread id。
- 增加 `user_id`，便于 Trace 页面按用户隔离。
- 对 `selected_chunk_ids` 保持 JSON 数组即可，避免检索日志和 chunk 表形成过重写入耦合。

## 复盘、画像与推荐

### session_summary

状态：规划。

用途：

保存单题训练完成后的复盘总结，是复盘页和画像更新的输入。

核心字段：

```text
session_summary
- id
- session_id
- user_id
- problem_id
- result                  # solved / partially_solved / failed / abandoned
- final_submission_result # ac / wa / tle / re / unknown / not_submitted
- main_stuck_points_json
- error_types_json
- max_hint_level_used
- avg_hint_level
- attempt_count
- time_spent_seconds
- complexity_analysis_json
- invariant_summary_md
- review_summary_md
- improvement_suggestions_json
- next_recommendation_json
- created_at
- updated_at
```

关系：

- `session_summary.session_id -> practice_session.id`
- `session_summary 1:N profile_delta`

### profile_delta

状态：规划。

用途：

保存一次训练对用户画像造成的增量影响。它用于解释画像变化，而不是只保存最终分数。

核心字段：

```text
profile_delta
- id
- user_id
- session_id
- summary_id
- skill_tag
- stuck_point
- delta_json              # mastery_delta / confidence_delta / evidence 等
- before_json
- after_json
- reason
- created_at
```

关系：

- `profile_delta.user_id -> app_user.id`
- `profile_delta.session_id -> practice_session.id`
- `profile_delta.summary_id -> session_summary.id`
- `profile_delta.skill_tag` 对应题目 metadata 中的算法标签。

### user_skill_profile

状态：规划。

用途：

保存用户在算法标签维度上的长期掌握度，用于仪表盘和推荐。

核心字段：

```text
user_skill_profile
- id
- user_id
- skill_tag
- mastery_score           # 0-100
- confidence_score        # 0-100
- solved_count
- attempted_count
- failed_count
- avg_hint_level
- last_practiced_at
- evidence_json
- created_at
- updated_at
```

关系：

- `user_skill_profile.user_id -> app_user.id`

约束：

- `(user_id, skill_tag)` 唯一。

### user_stuck_point_profile

状态：规划。

用途：

保存用户在卡点类型维度上的长期画像，例如题意理解、题型识别、不变量、边界条件、实现细节和面试表达。

核心字段：

```text
user_stuck_point_profile
- id
- user_id
- stuck_point
- occurrence_count
- severity_score          # 0-100
- recent_session_ids_json
- last_seen_at
- created_at
- updated_at
```

关系：

- `user_stuck_point_profile.user_id -> app_user.id`

约束：

- `(user_id, stuck_point)` 唯一。

### recommendation_batch

状态：规划。

用途：

保存一次推荐生成结果。学习计划初始题单可以由 `study_plan_item` 表承载；训练后的下一组推荐使用 `recommendation_batch` 和 `recommendation_item`，避免覆盖原计划。

核心字段：

```text
recommendation_batch
- id
- user_id
- goal_id
- study_plan_id
- source_session_id
- source_type             # initial_plan / after_session / dashboard_refresh / manual_refresh
- strategy
- rationale_md
- status                  # active / dismissed / consumed
- created_at
- updated_at
```

关系：

- `recommendation_batch.user_id -> app_user.id`
- `recommendation_batch.goal_id -> user_learning_goal.id`
- `recommendation_batch.study_plan_id -> study_plan.id`
- `recommendation_batch.source_session_id -> practice_session.id`
- `recommendation_batch 1:N recommendation_item`

### recommendation_item

状态：规划。

用途：

保存推荐批次中的具体题目、原因和状态。

核心字段：

```text
recommendation_item
- id
- batch_id
- problem_id
- skill_tags_json
- suggested_mode
- priority
- reason
- status                  # pending / accepted / skipped / converted_to_plan_item
- converted_plan_item_id
- created_at
- updated_at
```

关系：

- `recommendation_item.batch_id -> recommendation_batch.id`
- `recommendation_item.problem_id -> problem.id`
- `recommendation_item.converted_plan_item_id -> study_plan_item.id`

### dashboard_metric_snapshot

状态：规划。

用途：

保存仪表盘聚合指标缓存，避免每次打开仪表盘都扫描完整事件和画像明细。

核心字段：

```text
dashboard_metric_snapshot
- id
- user_id
- window_start
- window_end
- metric_type             # overview / skill_mastery / stuck_point / hint_usage / trend
- metrics_json
- generated_at
- created_at
```

关系：

- `dashboard_metric_snapshot.user_id -> app_user.id`

说明：

- 这是派生缓存表，真实来源仍是 session、summary、profile 和 recommendation。

## 面试模拟

### mock_interview_summary

状态：规划。

用途：

保存面试模拟模式结束后的结构化评分和改进建议。

核心字段：

```text
mock_interview_summary
- id
- session_id
- user_id
- overall_score
- dimension_scores_json   # problem_understanding / reasoning / complexity_analysis / code_quality / communication
- strengths_json
- improvements_json
- transcript_event_ids_json
- final_code_snapshot_id
- created_at
- updated_at
```

关系：

- `mock_interview_summary.session_id -> practice_session.id`
- `mock_interview_summary.final_code_snapshot_id -> code_snapshot.id`

说明：

- 面试模拟仍复用 `practice_session`、`practice_event`、`code_snapshot`、`tool_run` 和 `session_summary`。
- `mock_interview_summary` 只保存面试特有评分维度。

## Trace 与 Eval

### agent_trace

状态：已落地基础版，T4/T9 需要增强接入。

核心字段：

```text
agent_trace
- id
- session_id
- thread_id
- problem_slug
- node_name
- phase
- prompt_version
- model_name
- input_tokens
- output_tokens
- latency_ms
- retrieved_chunk_ids
- tool_calls
- hint_level
- stuck_point
- should_reveal_solution
- created_at
```

后续增强：

- 增加 `user_id`，保证 Trace 页面按用户隔离。
- 增加 `trace_run_id` 或 `request_id`，串联同一次图执行。
- 对敏感 prompt 和模型输出只保存摘要或脱敏片段，避免把 API key、完整用户代码或不应公开的题面扩散到日志。

### eval_run

状态：规划。

用途：

保存一次评估任务，例如 Hint Leakage Eval、Diagnosis Eval、Review Eval 或 RAG Grounding Eval。

核心字段：

```text
eval_run
- id
- eval_type               # hint_leakage / diagnosis / review / rag_grounding
- dataset_name
- dataset_version
- prompt_version
- model_name
- status                  # running / completed / failed
- metrics_json
- started_at
- completed_at
- created_at
```

关系：

- `eval_run 1:N eval_case_result`

### eval_case_result

状态：规划。

用途：

保存单个评估 case 的输入、输出、评分和失败原因。

核心字段：

```text
eval_case_result
- id
- eval_run_id
- case_id
- session_id
- input_json
- expected_json
- output_json
- score_json
- passed
- failure_reason
- created_at
```

关系：

- `eval_case_result.eval_run_id -> eval_run.id`
- `eval_case_result.session_id -> practice_session.id`，可为空；离线 eval 不一定有真实训练会话。

## 关键枚举

```text
goal_type:
- beginner
- interview_sprint
- strengthen_weakness
- maintain

training_mode:
- guided
- independent
- mock_interview

session_phase:
- understand
- plan
- implement
- debug
- review
- summary

visible_hint_gear:
- questioning
- direction
- key_hint
- review

hint_level:
- 0   # 只追问
- 1   # 题型方向
- 2   # 关键数据结构
- 3   # 核心不变量
- 4   # 伪代码框架
- 5   # 完整思路复盘

stuck_point:
- problem_understanding
- pattern
- invariant
- implementation
- edge_case
- complexity
- interview_expression

submission_result:
- ac
- wa
- tle
- re
- mle
- ce
- unknown
- not_submitted

tool_status:
- success
- failed
- timeout
- skipped
```

## 关键关联与索引建议

| 表 | 建议索引或约束 | 用途 |
| --- | --- | --- |
| `app_user` | `username` 唯一，`email` 唯一 | 登录和用户隔离。 |
| `auth_session` | `session_token_hash` 唯一，`(user_id, expires_at)` | session 查询和清理。 |
| `llm_credential` | `(user_id, is_preferred)`、`(user_id, is_active)`、`(user_id, is_enabled)` | API 资产选择。 |
| `problem` | `frontend_id` 唯一，`slug` 唯一，`difficulty` | 题库列表和详情。 |
| `problem_category_item` | `(category_id, problem_id)` 唯一，`(category_id, sort_order)` | 分类题单展示。 |
| `user_learning_goal` | `(user_id, status)`、`(user_id, created_at)` | 当前目标和历史目标读取。 |
| `study_plan` | `(user_id, status)`、`goal_id` | 当前计划读取。 |
| `study_plan_item` | `(plan_id, problem_id)` 唯一，`(plan_id, order_index)` | 计划项排序和去重。 |
| `practice_session` | `(user_id, status, last_activity_at)`、`(user_id, problem_id)`、`thread_id` | 工作台恢复和历史记录。 |
| `practice_event` | `(session_id, created_at)` | 会话回放。 |
| `code_snapshot` | `(session_id, created_at)` | 代码版本读取。 |
| `coach_turn` | `(session_id, created_at)`、`(session_id, hint_level)` | 对话和泄题评估。 |
| `tool_run` | `(session_id, created_at)`、`(tool_name, status)` | 工具结果查询。 |
| `knowledge_doc` | `(doc_type, problem_slug)`、`(hint_level_min, hint_level_max)` | RAG 过滤。 |
| `knowledge_chunk` | pgvector ivfflat/hnsw 索引，`doc_id` | 向量检索。 |
| `session_summary` | `session_id` 唯一，`(user_id, created_at)` | 复盘页和历史记录。 |
| `user_skill_profile` | `(user_id, skill_tag)` 唯一 | 画像读取。 |
| `user_stuck_point_profile` | `(user_id, stuck_point)` 唯一 | 弱项分布。 |
| `recommendation_item` | `(batch_id, priority)` | 推荐排序。 |
| `agent_trace` | `(session_id, created_at)`、`(thread_id, created_at)` | Trace 页面。 |
| `retrieval_trace` | `(session_id, created_at)` | RAG Trace 页面。 |
| `eval_case_result` | `(eval_run_id, case_id)` | Eval 报告。 |

## 分阶段落地建议

### T1：目标校准与学习计划

新增：

- `goal_calibration_draft`
- `user_learning_goal`
- `study_plan`
- `study_plan_item`

验收重点：

- 用户确认后才创建 active goal 和 active plan。
- 同一用户只保留一个 active goal 和一个 active plan。
- 学习计划项能引用真实 `problem`。

### T2：训练会话与工作台持久化

新增：

- `practice_session`
- `practice_event`
- `code_snapshot`
- `submission_feedback`

验收重点：

- 进入工作台能创建或恢复 session。
- 刷新页面能恢复训练模式、提示档位、当前代码和提交回填。

### T3-T4：AI 教练与 LangGraph

新增：

- `coach_turn`
- `agent_thread`

增强：

- `agent_trace` 接入真实图节点。

验收重点：

- AI 回复、诊断、动作和 hint level 可追溯。
- LangGraph thread 能和业务 session 双向定位。

### T5：代码运行与错误归因

新增：

- `tool_run`
- `generated_test_case`

验收重点：

- 本地运行结果、静态分析和错误归因都能回写到 session。
- 工具失败不会破坏训练主状态。

### T6：RAG 教练知识库

新增：

- `knowledge_source`
- `knowledge_doc`
- `knowledge_chunk`

增强：

- `retrieval_trace` 接入真实检索。

验收重点：

- 检索结果受 hint level、knowledge type 和 `has_full_solution` 过滤。
- Trace 能解释哪些 chunk 被过滤、哪些 chunk 被使用。

### T7：复盘、画像、推荐和仪表盘

新增：

- `session_summary`
- `profile_delta`
- `user_skill_profile`
- `user_stuck_point_profile`
- `recommendation_batch`
- `recommendation_item`
- `dashboard_metric_snapshot`

验收重点：

- 单题复盘能更新画像。
- 推荐理由能引用目标、计划、画像和最近训练证据。

### T8：轻量面试模拟

新增：

- `mock_interview_summary`

验收重点：

- 面试模拟复用训练会话主链路。
- 面试评分沉淀到复盘和画像。

### T9：Trace 与 Eval

新增：

- `eval_run`
- `eval_case_result`

增强：

- `agent_trace`
- `retrieval_trace`

验收重点：

- 支持 Hint Leakage、Diagnosis、Review 和 RAG Grounding 的最小评估闭环。

## 与当前实现的差异

- 当前 `agent_trace.session_id` 和 `retrieval_trace.session_id` 是字符串语义；后续 `practice_session` 落地后，需要明确是否迁移为外键，或保留字符串并增加 `practice_session_id`。
- 当前 `llm_credential.is_default` 仍保留兼容；新代码应逐步以 `is_preferred` 为主。
- 当前 T1 早期设计文档仍包含过时的 `local-user` 假设；后续 T1 实施应以本地用户和 API 资产池为前提。
- 当前没有存储 LLM 目标校准草稿的表；本设计新增 `goal_calibration_draft`，用于匹配 PRD 中“生成草稿、用户确认后落库”的流程。
- 当前 RAG 只在 PRD 中完成概念设计；`knowledge_source` 是本文档对 `knowledge_doc` / `knowledge_chunk` 的来源归档补充，便于后续导入和审计。

## 文档维护规则

后续每完成一个阶段的 migration，应同步维护本文档：

- 如果字段名、表名或外键和本文档不同，更新对应表设计。
- 如果某个规划表被证明可以合并或不需要，保留删除原因，避免后续重复设计。
- 如果新增表影响系统边界、Docker、Makefile 或 PRD 行为，应同步更新对应架构和产品文档。
