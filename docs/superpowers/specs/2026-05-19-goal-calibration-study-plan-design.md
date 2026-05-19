# 首访目标校准与学习计划设计

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
