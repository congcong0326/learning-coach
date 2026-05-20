# 首访目标校准与学习计划设计（已取代）

## 当前状态

本文档是 T1 的早期规则版设计草案，已被新的产品 PRD 取代。

新的产品设计见 `docs/superpowers/specs/2026-05-20-goal-calibration-study-plan-prd.md`。后续 T1 研发设计和实施计划应以新 PRD 为准。

本文档中关于 `local-user`、不实现登录、固定 Python、规则生成学习计划、以及生成新计划时归档旧 active 计划的表述已经不再作为后续实现依据。

## 目标

完成 T1：首访目标校准与学习计划基础。用户首次进入产品后，可以填写训练目标、时间线、每周投入、首选语言和自评弱项；系统保存当前学习目标，并基于题库静态数据生成一个可解释的基础训练计划。学习计划页展示推荐题单、建议训练模式和推荐理由，并支持跳过题目和调整题目顺序。

这个设计只覆盖目标校准、规则化学习计划、计划页和相关 API。不实现训练会话、AI 教练、代码运行、复盘画像、LangGraph、RAG 和面试模拟。

## 参考文档

- `docs/prd/prd.md`：MVP 范围、首访目标校准页、学习计划页和长期记忆表设计。
- `docs/project-todolist.md`：T1 的当前任务范围和阶段定义。
- `docs/architecture/foundation.md`：当前前后端、数据库和模块边界。
- `docs/index.md`：文档维护映射。
- `docs/superpowers/specs/2026-05-19-problem-ingestion-design.md`：题库数据、问题表和 API 的既有设计。

## 已确认决策

- 第一版没有登录系统，后端使用固定本地用户 ID `local-user` 表示当前用户；未来接入认证时，把 `user_id` 替换为真实用户 ID，不改变目标和计划的业务模型。
- 第一版首选语言只允许 `python`。前端以禁用或固定选项展示，不提供多语言选择。
- 目标校准提交后，会创建新的 `user_learning_goal` 记录，并归档该用户旧的 active `study_plan`，再生成新的 active `study_plan`。
- `user_learning_goal` 保留历史记录，不做唯一约束；当前目标取最新一条目标记录。
- `study_plan` 通过 `status` 标识当前 active 计划；同一用户只应有一个 active 计划，服务层负责归档旧计划。
- `study_plan_item.problem_slug` 引用 `problem.slug`，和 PRD、前端路由、后续 session state 保持一致。
- T1 不接 `user_skill_profile`。专项补弱计划先使用用户自评弱项调整推荐理由、训练模式和提示偏好；T7 实现画像后再把 mastery score 接入推荐规则。
- T1 不把用户训练状态写回题库列表页；题库列表仍保持静态题库视角。训练状态过滤和平均提示等级等字段留到 T2/T7。
- 学习计划页可以进入工作台，但 T1 只跳转到 `/workspace/:slug`，不负责创建训练会话。

## 非目标

- 不实现账号、登录、权限和多用户切换。
- 不实现复杂推荐算法、日历排期、打卡提醒或学习管理外围能力。
- 不实现训练会话状态、代码快照、提交回填或复盘。
- 不实现基于真实训练历史的掌握度推荐；这属于 T7。
- 不实现 AI 生成学习计划；第一版使用可测试、可解释的规则。
- 不修改题库 seed 结构，也不重新导入题库。

## 用户流程

```text
首次访问 /
  -> 检查是否已有当前学习目标
  -> 没有目标：进入 /goal-calibration
  -> 提交目标校准表单
  -> 后端保存 user_learning_goal
  -> 后端生成 active study_plan 和 study_plan_item
  -> 前端跳转 /study-plan
  -> 用户查看推荐题单、推荐理由和建议模式
  -> 用户可以调整顺序、跳过题目或进入 /workspace/:slug

已有目标时访问 /
  -> 进入 /study-plan
```

题库页仍可直接访问。学习计划页是推荐入口，不替代题库页。

## 数据模型

### user_learning_goal

保存用户当前和历史目标校准记录。

```text
user_learning_goal
- id
- user_id
- goal_type              # beginner / interview_sprint / strengthen_weakness / maintain
- target_timeline        # none / within_1_month / one_to_three_months / over_three_months
- weekly_days
- session_minutes
- preferred_language     # 第一版固定 python
- self_reported_weaknesses
- default_training_mode  # guided / independent
- default_hint_gear      # questioning / direction / key_hint
- created_at
- updated_at
```

字段用途：

| 字段 | 用途 |
| --- | --- |
| `id` | 目标校准记录主键，供计划表通过 `goal_id` 关联。 |
| `user_id` | 标识目标属于哪个用户；T1 固定为 `local-user`，后续接入登录后替换为真实用户 ID。 |
| `goal_type` | 用户本轮训练的主要目标，决定计划策略、默认训练模式和推荐理由。 |
| `target_timeline` | 用户准备周期，用于估算计划长度和计划结束日期。 |
| `weekly_days` | 用户每周可训练天数，用于估算首批推荐题目数量。 |
| `session_minutes` | 用户单次训练时长，用于后续 session、面试模拟和计划节奏；T1 先保存和展示。 |
| `preferred_language` | 用户首选代码语言；第一版固定为 `python`，后续扩展多语言代码运行时复用。 |
| `self_reported_weaknesses` | 用户自评薄弱点，用于补充推荐理由、默认提示偏好和后续画像初始化。 |
| `default_training_mode` | 根据目标推导出的默认训练模式，后续创建训练会话时作为初始值。 |
| `default_hint_gear` | 根据目标推导出的默认提示档位，后续 AI 教练和工作台展示复用。 |
| `created_at` | 记录目标创建时间，用于读取最新目标和展示校准时间。 |
| `updated_at` | 记录目标更新时间，用于审计和后续目标编辑能力。 |

约束和索引：

- `goal_type`、`target_timeline`、`preferred_language`、`default_training_mode`、`default_hint_gear` 使用字符串枚举约束。
- `weekly_days` 范围为 1 到 7。
- `session_minutes` 范围为 15 到 180。
- `self_reported_weaknesses` 使用 JSON 数组保存，元素只能来自约定枚举。
- 建立 `(user_id, created_at)` 索引，用于读取最新目标。

### study_plan

保存一次目标校准生成的训练计划。

```text
study_plan
- id
- user_id
- goal_id
- title
- status                 # active / completed / archived
- start_date
- end_date
- strategy               # beginner_path / interview_sprint / weakness_based / maintenance
- created_at
- updated_at
```

字段用途：

| 字段 | 用途 |
| --- | --- |
| `id` | 学习计划主键，供计划项和后续训练会话关联。 |
| `user_id` | 标识计划属于哪个用户；T1 固定为 `local-user`。 |
| `goal_id` | 关联生成该计划的目标校准记录，用于解释计划来源。 |
| `title` | 面向用户展示的计划名称，例如“刷题入门基础训练计划”。 |
| `status` | 标识计划生命周期；当前使用 `active` 和 `archived`，后续可由完成流程写入 `completed`。 |
| `start_date` | 计划开始日期，默认使用创建目标当天。 |
| `end_date` | 计划结束日期，根据时间线和计划策略生成，用于前端展示计划周期。 |
| `strategy` | 计划生成策略，解释推荐题单来自入门路径、面试冲刺、专项补弱还是保持手感。 |
| `created_at` | 记录计划创建时间，用于审计和排序。 |
| `updated_at` | 记录计划更新时间，用于审计、重排和状态变更追踪。 |

约束和索引：

- `goal_id` 外键引用 `user_learning_goal.id`。
- `status` 使用字符串枚举约束。
- 建立 `(user_id, status)` 索引，用于读取 active 计划。
- 生成新计划前，服务层把同一用户旧的 active 计划改为 `archived`。

### study_plan_item

保存计划中的推荐题目和推荐理由。

```text
study_plan_item
- id
- plan_id
- problem_slug
- skill_tags
- difficulty
- suggested_mode
- recommendation_reason
- status                 # pending / in_progress / completed / skipped
- order_index
- created_at
- updated_at
```

字段用途：

| 字段 | 用途 |
| --- | --- |
| `id` | 计划项主键，供前端更新状态、重排和后续训练会话关联。 |
| `plan_id` | 关联所属学习计划。 |
| `problem_slug` | 关联题库中的题目 slug，也是跳转 `/workspace/:slug` 的路由参数。 |
| `skill_tags` | 本计划项用于训练的算法标签，来自题目 metadata，用于推荐解释和后续画像沉淀。 |
| `difficulty` | 冗余保存计划生成时的题目难度，便于计划展示和后续分析；源数据来自 `problem.difficulty`。 |
| `suggested_mode` | 建议用户用哪种训练模式做这道题，后续创建 session 时作为默认模式。 |
| `recommendation_reason` | 面向用户展示的推荐理由，解释为什么这道题适合当前目标。 |
| `status` | 计划项进度状态；T1 支持 `pending` 和 `skipped`，后续由训练流程写入 `in_progress` 和 `completed`。 |
| `order_index` | 题目在计划中的排序位置，用于稳定展示和用户手动重排。 |
| `created_at` | 记录计划项创建时间，用于审计。 |
| `updated_at` | 记录计划项更新时间，用于审计、跳过和重排追踪。 |

约束和索引：

- `plan_id` 外键引用 `study_plan.id`。
- `problem_slug` 外键引用 `problem.slug`。
- `(plan_id, problem_slug)` 唯一，避免一个计划中重复推荐同一道题。
- `skill_tags` 使用 JSON 数组保存题目标签 slug。
- `status` 初始值为 `pending`。T1 只允许用户在 `pending` 和 `skipped` 之间切换；`in_progress` 和 `completed` 由 T2/T7 后续接入。
- 建立 `(plan_id, order_index)` 索引，用于稳定排序。

## 枚举定义

```text
goal_type:
- beginner              # 刷题入门
- interview_sprint      # 面试冲刺
- strengthen_weakness   # 专项补弱
- maintain              # 保持手感

target_timeline:
- none
- within_1_month
- one_to_three_months
- over_three_months

self_reported_weakness:
- problem_understanding
- pattern
- complexity
- implementation
- edge_case
- interview_expression

training_mode:
- guided
- independent

visible_hint_gear:
- questioning
- direction
- key_hint
```

枚举用途：

| 枚举 | 值 | 用途说明 |
| --- | --- | --- |
| `goal_type` | `beginner` | 刷题入门，推荐 Easy 和基础题型，默认入门引导模式。 |
| `goal_type` | `interview_sprint` | 面试冲刺，优先高频题集或高频基础标签，默认独立训练模式。 |
| `goal_type` | `strengthen_weakness` | 专项补弱，根据用户自评弱项生成更聚焦的推荐理由，默认入门引导模式。 |
| `goal_type` | `maintain` | 保持手感，推荐 Easy/Medium 混合题，默认独立训练模式。 |
| `target_timeline` | `none` | 没有明确时间线，生成默认周期计划。 |
| `target_timeline` | `within_1_month` | 1 个月内冲刺，生成较密集的首批推荐。 |
| `target_timeline` | `one_to_three_months` | 1 到 3 个月准备周期，生成中等规模计划。 |
| `target_timeline` | `over_three_months` | 3 个月以上长期准备，生成节奏更平缓的计划。 |
| `self_reported_weakness` | `problem_understanding` | 题意理解弱项，后续教练应更关注题意澄清。 |
| `self_reported_weakness` | `pattern` | 题型识别弱项，推荐理由和后续提示应强调模式识别。 |
| `self_reported_weakness` | `complexity` | 复杂度优化弱项，后续教练应关注暴力到优化的推导。 |
| `self_reported_weakness` | `implementation` | 代码实现弱项，推荐理由应提示实现细节训练。 |
| `self_reported_weakness` | `edge_case` | 边界条件弱项，推荐理由应提示边界条件覆盖。 |
| `self_reported_weakness` | `interview_expression` | 面试表达弱项，后续复盘和面试模拟应关注表达结构。 |
| `training_mode` | `guided` | 入门引导模式，AI 教练可以更主动地拆解和提示。 |
| `training_mode` | `independent` | 独立训练模式，AI 教练更克制，优先追问。 |
| `visible_hint_gear` | `questioning` | 追问档，只追问和澄清，不提示题型或数据结构。 |
| `visible_hint_gear` | `direction` | 方向档，允许提示题型方向或关键数据结构。 |
| `visible_hint_gear` | `key_hint` | 关键档，允许提示核心不变量或伪代码框架。 |
| `study_plan.status` | `active` | 当前正在使用的学习计划，同一用户同时只保留一个 active 计划。 |
| `study_plan.status` | `completed` | 已完成的学习计划，T1 不写入，后续闭环完成后使用。 |
| `study_plan.status` | `archived` | 被新目标或新计划替换的历史计划。 |
| `study_plan.strategy` | `beginner_path` | 入门路径策略，优先 Easy 和基础高频标签。 |
| `study_plan.strategy` | `interview_sprint` | 面试冲刺策略，优先高频题集或高频基础标签。 |
| `study_plan.strategy` | `weakness_based` | 专项补弱策略，根据自评弱项生成推荐说明。 |
| `study_plan.strategy` | `maintenance` | 保持手感策略，覆盖 Easy/Medium 常见题型。 |
| `study_plan_item.status` | `pending` | 计划项待训练，是 T1 创建计划项后的默认状态。 |
| `study_plan_item.status` | `in_progress` | 计划项训练中，T1 不写入，后续训练会话接入。 |
| `study_plan_item.status` | `completed` | 计划项已完成，T1 不写入，后续复盘闭环接入。 |
| `study_plan_item.status` | `skipped` | 用户暂时跳过该题，T1 支持用户写入和取消。 |

## 后端模块

新增文件：

```text
backend/app/models/learning.py
backend/app/schemas/learning.py
backend/app/services/learning_goal_service.py
backend/app/services/study_plan_service.py
backend/app/api/learning.py
backend/app/db/migrations/versions/20260519_0003_learning_goal_plan.py
backend/tests/test_learning_api.py
backend/tests/test_study_plan_service.py
```

修改文件：

```text
backend/app/main.py
backend/app/models/__init__.py
docs/project-todolist.md
```

`backend/app/api/learning.py` 负责 HTTP 路由和状态码。`learning_goal_service.py` 负责目标保存和当前目标读取。`study_plan_service.py` 负责计划生成、当前计划读取、跳过题目和重排。推荐规则不放在 API 层。

## API 设计

### GET /api/learning-goal/current

读取当前用户最新目标。

成功响应：

```json
{
  "id": 1,
  "user_id": "local-user",
  "goal_type": "beginner",
  "target_timeline": "one_to_three_months",
  "weekly_days": 4,
  "session_minutes": 45,
  "preferred_language": "python",
  "self_reported_weaknesses": ["pattern", "edge_case"],
  "default_training_mode": "guided",
  "default_hint_gear": "direction",
  "created_at": "2026-05-19T00:00:00Z",
  "updated_at": "2026-05-19T00:00:00Z"
}
```

没有目标时返回 404：

```json
{"detail":"learning_goal_not_found"}
```

### POST /api/learning-goal

保存目标校准，并生成新的 active 学习计划。

请求：

```json
{
  "goal_type": "beginner",
  "target_timeline": "one_to_three_months",
  "weekly_days": 4,
  "session_minutes": 45,
  "preferred_language": "python",
  "self_reported_weaknesses": ["pattern", "edge_case"]
}
```

响应：

```json
{
  "goal": {
    "id": 1,
    "user_id": "local-user",
    "goal_type": "beginner",
    "target_timeline": "one_to_three_months",
    "weekly_days": 4,
    "session_minutes": 45,
    "preferred_language": "python",
    "self_reported_weaknesses": ["pattern", "edge_case"],
    "default_training_mode": "guided",
    "default_hint_gear": "direction",
    "created_at": "2026-05-19T00:00:00Z",
    "updated_at": "2026-05-19T00:00:00Z"
  },
  "plan": {
    "id": 10,
    "title": "刷题入门基础训练计划",
    "status": "active",
    "strategy": "beginner_path",
    "start_date": "2026-05-19",
    "end_date": "2026-06-16",
    "items": [
      {
        "id": 100,
        "problem_slug": "two-sum",
        "frontend_id": "1",
        "title": "Two Sum",
        "translated_title": "两数之和",
        "difficulty": "Easy",
        "skill_tags": ["array", "hash-table"],
        "suggested_mode": "guided",
        "recommendation_reason": "适合作为哈希表 complement 查找的入门题",
        "status": "pending",
        "order_index": 1
      }
    ]
  }
}
```

如果数据库中没有可推荐题目，返回 409：

```json
{"detail":"study_plan_requires_problem_seed"}
```

### GET /api/study-plan/current

读取 active 学习计划和计划项。

响应中的计划项包含题目摘要，避免前端再逐题请求题库详情。

```json
{
  "id": 10,
  "title": "刷题入门基础训练计划",
  "status": "active",
  "strategy": "beginner_path",
  "start_date": "2026-05-19",
  "end_date": "2026-06-16",
  "items": [
    {
      "id": 100,
      "problem_slug": "two-sum",
      "frontend_id": "1",
      "title": "Two Sum",
      "translated_title": "两数之和",
      "difficulty": "Easy",
      "skill_tags": ["array", "hash-table"],
      "suggested_mode": "guided",
      "recommendation_reason": "适合作为哈希表 complement 查找的入门题",
      "status": "pending",
      "order_index": 1
    }
  ]
}
```

计划项响应字段用途：

| 字段 | 用途 |
| --- | --- |
| `id` | 计划项 ID，用于跳过、取消跳过、重排和后续创建训练会话。 |
| `problem_slug` | 题目 slug，用于跳转工作台和关联题库详情。 |
| `frontend_id` | LeetCode 题号，用于计划页列表展示。 |
| `title` | 英文题名，用于计划页列表展示。 |
| `translated_title` | 中文题名，用于计划页列表展示。 |
| `difficulty` | 题目难度，用于计划页筛读和解释推荐顺序。 |
| `skill_tags` | 推荐训练的算法标签，用于说明这道题训练什么能力。 |
| `suggested_mode` | 建议训练模式，后续进入工作台或创建 session 时作为默认值。 |
| `recommendation_reason` | 推荐理由，必须能解释当前目标和该题之间的关系。 |
| `status` | 计划项当前状态，用于展示待训练、已跳过等进度。 |
| `order_index` | 当前排序，用于稳定渲染和重排后保存顺序。 |

没有 active 计划时返回 404：

```json
{"detail":"active_study_plan_not_found"}
```

### PATCH /api/study-plan/items/{item_id}

更新单个计划项状态。T1 只用于跳过题目或取消跳过。

请求：

```json
{"status":"skipped"}
```

允许值：

```text
pending
skipped
```

### POST /api/study-plan/current/reorder

更新当前 active 计划的题目顺序。

请求：

```json
{"item_ids":[100,101,102]}
```

要求 `item_ids` 必须正好覆盖当前 active 计划的所有 item。缺少、重复或包含其他计划的 item 都返回 400：

```json
{"detail":"invalid_plan_item_order"}
```

## 学习计划生成规则

计划生成使用确定性规则，保证可测试和可解释。

### 计划规模

```text
base_count = weekly_days * 2
plan_size = clamp(base_count, 6, 14)

if target_timeline == within_1_month:
  plan_size = max(plan_size, 12)
if target_timeline == one_to_three_months:
  plan_size = max(plan_size, 10)
```

### 默认模式和提示档位

```text
goal_type == beginner:
  default_training_mode = guided
  default_hint_gear = direction

goal_type == interview_sprint:
  default_training_mode = independent
  default_hint_gear = questioning

goal_type == strengthen_weakness:
  default_training_mode = guided
  default_hint_gear = direction

goal_type == maintain:
  default_training_mode = independent
  default_hint_gear = questioning
```

如果自评弱项包含 `implementation` 或 `edge_case`，计划项推荐理由要明确提示后续训练重点是实现细节或边界条件。T1 不直接改变题目标签，只影响推荐说明和建议训练模式。

### 候选题过滤

- 默认排除 `is_paid_only = true` 的题目。
- 默认优先有 `statement_md`、`difficulty` 和题型标签的题目。
- 如果题库数量不足，允许返回少于 `plan_size` 的题目，但不能返回重复题目。

### 目标策略

`beginner_path`：

- 优先 Easy。
- 其次选择基础高频标签：array、string、hash-table、two-pointers、stack、binary-search。
- 推荐模式为 `guided`。

`interview_sprint`：

- 如果存在 Blind 75 / Grind 75 / NeetCode 150 类分类，优先分类内题目。
- 如果没有分类，优先 Easy 和 Medium 中的高频基础标签。
- 推荐模式为 `independent`。

`weakness_based`：

- T1 没有 `user_skill_profile` 时，使用用户自评弱项生成推荐理由和训练模式。
- 题目选择先覆盖基础标签，避免只围绕一个标签推荐。
- 推荐模式默认为 `guided`。
- T7 接入画像后，再按 mastery score 低的 skill tag 排序。

`maintenance`：

- 选择 Easy 和 Medium 混合题。
- 推荐模式为 `independent`。
- 推荐理由强调保持手感和覆盖常见题型。

### 排序规则

每个候选题计算分数后按分数降序、`frontend_id` 升序排序。`frontend_id` 如果不是纯数字，按字符串稳定排序。

分数来源：

- 目标匹配难度。
- 目标匹配分类。
- 题目标签是否属于基础高频标签。
- 题目是否已在当前新计划中覆盖过相同标签；已覆盖标签的后续题目轻微降权，避免同类题过度集中。

## 前端设计

新增文件：

```text
frontend/src/api/learning.ts
frontend/src/pages/GoalCalibrationPage.tsx
frontend/src/pages/GoalCalibrationPage.test.tsx
frontend/src/pages/StudyPlanPage.tsx
frontend/src/pages/StudyPlanPage.test.tsx
```

修改文件：

```text
frontend/src/App.tsx
frontend/src/routes/AppRoutes.tsx
frontend/src/styles/app.css
```

### 路由

```text
/                    # 根据当前目标跳转 /goal-calibration 或 /study-plan
/goal-calibration    # 首访目标校准
/study-plan          # 当前学习计划
/problems            # 题库列表，继续保留
/workspace/:slug     # 从计划进入工作台
```

### 首访目标校准页

使用 Ant Design 表单控件：

- 目标：单选按钮，四个选项对应 `goal_type`。
- 时间线：单选按钮，四个选项对应 `target_timeline`。
- 每周投入：数字输入，训练天数 1 到 7。
- 单次时长：数字输入，15 到 180 分钟。
- 首选语言：固定 `Python`。
- 自评弱项：多选，六个枚举。

提交成功后跳转 `/study-plan`，并让学习计划 query 失效重新拉取。

### 学习计划页

页面展示：

- 当前目标摘要：目标类型、时间线、每周投入、默认训练模式。
- 计划摘要：标题、周期、题目数量、策略。
- 推荐题单：题号、标题、难度、skill tags、建议模式、推荐理由、状态、操作。
- 操作：进入工作台、跳过、取消跳过、上移、下移。

第一版使用上移/下移按钮完成重排，不引入拖拽库。

### 导航

侧边导航新增“学习计划”，放在“题库”和“工作台”之间。工作台仍可单独访问，但没有 slug 时继续显示“请先从题库选择一道题目”。

## 错误处理

- 没有目标：`GET /api/learning-goal/current` 返回 404，前端根路由进入 `/goal-calibration`。
- 没有 active 计划：`GET /api/study-plan/current` 返回 404，学习计划页显示创建目标校准入口。
- 没有题库 seed：`POST /api/learning-goal` 返回 409，前端显示需要先导入题库数据。
- 非 Python 语言：Pydantic 校验返回 422。
- 非法弱项枚举、目标枚举、时间线枚举：Pydantic 校验返回 422。
- 非当前计划 item 操作：返回 404。
- 重排列表不完整或重复：返回 400。

## 测试策略

### 后端测试

- `test_learning_goal_create_generates_active_plan`：提交目标后创建 goal、active plan 和 plan items。
- `test_learning_goal_archives_previous_active_plan`：再次提交目标会归档旧 active plan。
- `test_learning_goal_rejects_non_python_language`：非 Python 返回 422。
- `test_study_plan_requires_problem_seed`：无可推荐题目时返回 409。
- `test_study_plan_current_returns_problem_summaries`：计划项包含题号、标题、难度、标签和推荐理由。
- `test_study_plan_item_can_be_skipped_and_restored`：计划项可在 pending/skipped 之间切换。
- `test_study_plan_reorder_requires_exact_item_set`：缺失、重复或越权 item 返回 400。
- `test_beginner_plan_prioritizes_easy_foundation_tags`：入门计划优先 Easy 和基础标签。

### 前端测试

- `GoalCalibrationPage` 渲染目标、时间线、投入、语言和弱项表单。
- 提交成功后调用 `POST /api/learning-goal` 并跳转 `/study-plan`。
- 后端 409 时显示题库 seed 缺失错误。
- `StudyPlanPage` 渲染当前目标和推荐题单。
- 点击“进入工作台”跳转 `/workspace/:slug`。
- 点击“跳过”调用计划项状态更新并刷新列表。
- 点击上移/下移调用重排 API。

### 验证命令

实现完成后至少运行：

```bash
uv run pytest backend/tests/test_learning_api.py backend/tests/test_study_plan_service.py -q
cd frontend && corepack pnpm test
make build
```

## 文档影响

实现 T1 后需要检查并可能更新：

- `docs/project-todolist.md`：把 T1 状态改为已完成，更新当前主线任务为 T2。
- `docs/index.md`：如果新增目录或模块职责需要补充，更新目录职责。
- `docs/architecture/foundation.md`：补充学习目标、学习计划和规则推荐模块已进入基座。
- `docs/prd/prd.md`：如果实际枚举、API 行为或计划生成规则与 PRD 表述存在差异，回填产品文档。

## 验收标准

- 用户可以完成首访目标校准。
- 目标校准完成后 100% 生成 active 学习计划，除非题库 seed 缺失，此时返回明确错误。
- 学习计划中每道题都有 skill tags、推荐理由、建议训练模式和稳定顺序。
- 用户可以在学习计划页跳过题目、取消跳过、调整顺序，并从推荐题进入工作台。
- 题库列表仍保持静态题库视角，不引入训练状态字段。
- T1 不依赖 LLM、LangGraph、RAG、code-runner 或训练会话。
