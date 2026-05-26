# 画像驱动的学习计划补强设计

## 1. 背景

当前项目已经具备非 RAG 第一版训练闭环：

```text
目标校准
-> 生成学习计划
-> 计划题训练工作台
-> AI 教练引导
-> LeetCode AC / 非 AC 反馈
-> 单题复盘
-> 更新用户画像
-> 推荐下一题
```

这个闭环解决了“做完一题后知道下一步练什么”，但学习计划页仍主要展示静态计划。用户需要一个更明确的入口，查看当前学习画像，并在确认后基于画像、计划进度和自身意愿向原计划追加补强题。

本设计定义 `profile_plan_enrichment`：画像驱动的计划补强生成能力。

## 2. 参考文档

- `docs/index.md`：文档维护映射和目录职责。
- `docs/prd/prd.md`：第一版训练闭环、学习计划页、复盘页和学习仪表盘的产品边界。
- `docs/prd/ai-coach-user-profile-prd.md`：画像结构、证据追溯和画像更新边界。
- `docs/prd/ai-coach-workbench-prd.md`：画像如何影响做题工作台、复盘和下一步建议。
- `docs/architecture/foundation.md`：当前 API、service、model、LLM Run 和计划调整边界。
- `docs/project-todolist.md`：T7/T10 已完成闭环，以及后续个性化推荐增强方向。

## 3. 目标

实现学习计划页上的“画像补强计划”能力：

1. 用户可以从学习计划页查看当前画像，展示类似学习仪表盘的结构化指标和老师式说明文案。
2. 用户可以输入本次补强意愿，并选择新增题目数量和难度倾向。
3. 系统调用大模型，结合用户意愿、当前画像、训练事实、当前计划和题库候选池，生成补强题预览。
4. 补强题预览不会直接写入正式计划，用户确认后才追加到原 active 学习计划中。
5. 新增题目必须附带清晰理由、对应薄弱点、建议第一问和 code review 重点。

## 4. 非目标

- 不自动重写整个学习计划。
- 不删除、移动或改写已完成题。
- 不在用户确认前修改数据库中的正式计划项。
- 不让大模型直接任意选择全量题库；后端先筛候选池，大模型只在候选池内选择和排序。
- 不把完整聊天记录、完整用户代码、完整题解或敏感数据放入大模型上下文。
- 不做复杂全局推荐系统、趋势图、同类用户对比或学习时长预测。
- 不把 RAG 作为本功能前置条件；RAG/T6 仍可延后。

## 5. 核心产品决策

### 5.1 第一版采用 B 方案

第一版采用“画像页 + 补强题预览 + 用户确认加入原计划”。

流程：

```text
学习计划页
-> 点击“基于画像补强计划”
-> 查看画像摘要与操作说明
-> 输入用户意愿，选择数量和难度倾向
-> 调用 LLM Run 生成补强题预览
-> 用户审核预览
-> 用户确认加入计划
-> 后端追加计划题并刷新学习计划页
```

### 5.2 这是重量级操作

按钮和弹窗必须明确说明：

```text
这会调用大模型分析你的当前画像、训练记录和学习计划，可能需要较长时间。
生成结果会先进入预览，不会直接修改当前计划。
```

原因：

- 加题会改变用户接下来的学习路径。
- 大模型需要较完整上下文，调用成本和耗时都高于普通推荐。
- 用户意愿和确认步骤必须被尊重。

### 5.3 用户意愿是高优先级输入

用户意愿不只是备注，而是 LLM 决策上下文中的高优先级约束。

第一版支持：

- 自由文本框：`这次你希望怎么补强？`
- 新增数量：`2 / 3 / 5`，默认 `3`。
- 难度倾向：`降低难度打基础 / 保持当前难度 / 稍微加难`，默认 `保持当前难度`。

示例：

```text
我下周面试，希望多加面试高频 Medium，不要再加太偏动态规划的题。
```

LLM 应在用户意愿和画像薄弱点之间寻找交集。例如画像显示边界薄弱，而用户希望练面试高频 Medium，则优先选择能训练边界意识的面试高频 Medium 题。

### 5.4 第一版插入位置固定

第一版新增题默认插入当前阶段末尾。

定义当前阶段：

- 如果存在 `in_progress` 计划题，使用该题所在阶段。
- 否则使用最近一次完成题所在阶段。
- 否则使用第一个未完成阶段。
- 如果无法判断，使用 active version 的第一个阶段。

第一版不让用户选择插入位置，避免计划结构操作过重。后续可以增加“插入当前阶段 / 计划末尾 / 新建补强阶段”选项。

## 6. 前端设计

### 6.1 学习计划页入口

在学习计划页标题区增加按钮：

```text
查看画像与补强
```

点击后打开抽屉或独立页面。第一版推荐抽屉，原因是用户仍然需要对照当前学习计划。

抽屉包含两个区域：

1. 当前画像。
2. 生成补强题。

### 6.2 当前画像展示

画像展示采用类似学习仪表盘的紧凑布局，但语气更像老师总结。

建议字段：

- 当前训练水平。
- 最近画像摘要。
- 主要薄弱点。
- 强项标签。
- 常见卡点。
- 平均/最高提示档位。
- 完成题数。
- 最近证据摘要。
- 教练策略建议。

老师式文案示例：

```text
你最近不是完全卡在思路上，而是容易在边界条件和重复元素处理上失误。
建议接下来先练 2-3 道同类题，重点要求自己提交前列出边界用例。
```

文案来源：

- 优先使用最新 `user_profile_snapshot.recent_summary_md` 和 `strategy_json`。
- 如果画像证据不足，展示保守说明：`当前训练证据还不够，建议先完成 1-2 道计划题后再生成补强题。`

### 6.3 生成补强题表单

表单字段：

```text
user_intent_md: string
item_count: 2 | 3 | 5
difficulty_preference: foundational | keep_current | stretch
```

表单文案：

- `这次你希望怎么补强？`
- `想增加几道题？`
- `难度倾向`

按钮：

- `生成补强题预览`
- 运行中显示 LLM Run 状态和已等待时间。
- 支持取消生成。

### 6.4 补强题预览

预览展示：

- 本次补强主题。
- 计划差距判断。
- 为什么建议增加这些题。
- 每道题：
  - 标题。
  - 难度。
  - 标签。
  - 对应薄弱点。
  - 推荐理由。
  - 加入阶段。
  - 建议训练模式。
  - 第一问建议。
  - code review 重点。
- 后端校验结果。

确认按钮：

```text
确认加入当前计划
```

确认成功后：

- 关闭或保持抽屉并显示成功状态。
- 刷新当前学习计划。
- 新增计划题展示为 `pending`。
- 推荐理由中明确带有“画像补强”语义。

## 7. 后端设计

### 7.1 新增能力边界

新增 service/flow 语义命名为：

```text
profile_plan_enrichment
```

它和普通 `study_plan_adjustment` 的区别：

| 能力 | 目的 | 是否重写计划 | 是否基于画像 | 用户确认前是否写库 |
| --- | --- | --- | --- | --- |
| `study_plan_adjustment` | 用户主动调整计划版本 | 可以生成新版本 | 不一定 | 当前已有草稿/版本流程 |
| `profile_plan_enrichment` | 基于画像和用户意愿追加补强题 | 不重写，只追加 | 是 | 否 |

### 7.2 API 草案

生成补强 draft：

```text
POST /api/study-plans/{plan_id}/profile-enrichments
```

请求：

```json
{
  "user_intent_md": "我下周面试，希望多加面试高频 Medium，不要再加太偏动态规划的题。",
  "item_count": 3,
  "difficulty_preference": "keep_current"
}
```

响应通过 LLM Run 流式返回，最终 result 包含 draft ID：

```json
{
  "draft_id": 12,
  "status": "generated",
  "profile_snapshot_id": 31,
  "plan_id": 7,
  "plan_version_id": 9,
  "items": []
}
```

读取 draft：

```text
GET /api/study-plans/{plan_id}/profile-enrichments/{draft_id}
```

确认加入计划：

```text
POST /api/study-plans/{plan_id}/profile-enrichments/{draft_id}/confirm
```

确认响应返回更新后的 `StudyPlanResponse`。

### 7.3 数据模型草案

新增 `profile_plan_enrichment_draft`。

字段：

```text
id
user_id
study_plan_id
study_plan_version_id
profile_snapshot_id
llm_run_id
status                 # generating / generated / confirmed / rejected / failed
user_intent_md
item_count
difficulty_preference  # foundational / keep_current / stretch
context_summary_json
candidate_problem_ids_json
model_output_json
validation_report_json
confirmed_item_ids_json
error_summary
created_at
updated_at
confirmed_at
```

设计要求：

- `user_intent_md` 可以保存用户输入，但需要限制长度。
- `context_summary_json` 只保存摘要化上下文，不保存完整聊天和完整代码。
- `candidate_problem_ids_json` 保存后端候选池，便于审计模型是否越界。
- `model_output_json` 保存模型结构化输出。
- `validation_report_json` 保存去重、题库存在性、paid only、数量、阶段合法性等校验结果。
- `confirmed_item_ids_json` 记录最终追加进计划的 `study_plan_item.id`。

### 7.4 LLM Run 类型

新增 run kind：

```text
profile_plan_enrichment
```

该 run 的行为：

1. 校验 plan 属于当前用户且是 active。
2. 读取最新 active version。
3. 读取最新画像快照。
4. 聚合训练事实和最近复盘摘要。
5. 生成候选题池。
6. 调用大模型生成结构化补强建议。
7. 后端校验和 repair。
8. 保存 draft。
9. 通过 result 返回 draft。

## 8. 大模型上下文设计

### 8.1 上下文优先级

Prompt 中必须明确以下优先级：

```text
硬约束：
- 不推荐当前 active version 已存在的题目。
- 不推荐 paid only 题目。
- 不修改、删除或移动已有题。
- 不超过用户选择的新增数量。
- 不在用户确认前写入正式计划。
- 只能从后端提供的 candidate_problems 中选择。

高优先级：
- 用户本次自由文本意愿。
- 用户选择的题目数量。
- 用户选择的难度倾向。

中高优先级：
- 当前目标、面试时间线、默认训练语言。
- 最新用户画像薄弱点和教练策略。
- 最近单题复盘证据。

中优先级：
- 当前计划阶段。
- 当前阶段未完成题。
- 题型覆盖和难度递进。

低优先级：
- 模型自己的泛化建议。
```

### 8.2 输入上下文结构

输入给模型的 JSON 建议包含：

```json
{
  "task": "profile_plan_enrichment",
  "user_request": {
    "user_intent_md": "",
    "item_count": 3,
    "difficulty_preference": "keep_current"
  },
  "goal_context": {
    "target_snapshot": {},
    "preferred_language": "java",
    "timeline": "",
    "weekly_commitment": ""
  },
  "profile_snapshot": {
    "id": 31,
    "version": "profile-snapshot-v4",
    "confidence": "medium",
    "overall_level": "advanced",
    "weak_stuck_points": [],
    "weak_skill_tags": [],
    "recent_summary": "",
    "coach_strategy": {}
  },
  "training_facts": {
    "completed_problem_count": 5,
    "common_stuck_points": [],
    "average_hint_gear": 1.7,
    "highest_hint_level": "key_hint",
    "recent_summaries": []
  },
  "current_plan": {
    "plan_id": 7,
    "version_id": 9,
    "title": "",
    "current_stage": {},
    "stages": [],
    "existing_problem_slugs": []
  },
  "candidate_problems": [
    {
      "problem_id": 1,
      "slug": "two-sum",
      "title": "Two Sum",
      "translated_title": "两数之和",
      "difficulty": "Easy",
      "tags": ["array", "hash-table"],
      "is_paid_only": false,
      "match_reasons": ["边界", "哈希表"]
    }
  ],
  "output_contract": {}
}
```

### 8.3 禁止输入

不得输入：

- 完整聊天历史。
- 完整用户代码。
- 完整题解。
- API key、session token、密钥密文。
- 用户完整原始失败用例文本。

必要时使用摘要：

```text
最近一次 WA 与重复元素用例有关。
最近两次提示最高到关键档。
```

## 9. 大模型输出契约

模型必须返回 JSON：

```json
{
  "enrichment_theme": "边界条件与哈希表状态维护补强",
  "plan_gap_assessment": {
    "gap_level": "medium",
    "summary_md": "当前计划已有哈希表题，但缺少针对重复元素和无解边界的连续训练。"
  },
  "overall_reason_md": "建议追加 3 道题，保持当前难度，以面试高频题强化边界检查。",
  "items": [
    {
      "problem_slug": "contains-duplicate",
      "target_stage_key": "stage-1",
      "weakness_targets": ["边界", "哈希表"],
      "difficulty": "Easy",
      "recommendation_reason_md": "这题能强化你提交前先排查重复元素和哈希表语义的习惯。",
      "first_question_hint": "先说明你准备用 set 维护什么，以及什么时候可以提前返回。",
      "review_focus": "重点检查空数组、重复元素和返回条件。",
      "suggested_mode": "independent"
    }
  ],
  "not_added_reason_md": ""
}
```

约束：

- `items.length` 必须等于或小于用户选择数量。
- `problem_slug` 必须来自 `candidate_problems`。
- `weakness_targets` 必须能追溯到画像、复盘或用户意愿。
- `recommendation_reason_md` 必须面向用户展示。
- `first_question_hint` 和 `review_focus` 会进入后续训练上下文。
- 如果证据不足，可以返回空 `items`，并在 `not_added_reason_md` 说明原因。

## 10. 后端校验与 repair

### 10.1 校验规则

生成后必须校验：

- JSON schema 合法。
- 数量不超过 `item_count`。
- 题目存在于 `candidate_problems`。
- 题目不在当前 active version 中。
- 题目非 paid only。
- 题目 slug 不重复。
- 难度与 `difficulty_preference` 不明显冲突，除非模型给出强理由。
- `target_stage_key` 能映射到当前阶段；第一版最终仍插入当前阶段末尾。
- 推荐理由、第一问和 review 重点非空。

### 10.2 Repair 策略

如果模型输出不合法：

1. 将 validation report 和原输出返回给同一模型做 repair。
2. repair 最多 2 次。
3. 仍失败则保存 failed draft，并向前端返回明确错误。

失败文案示例：

```text
本次补强建议没有通过题库校验，未修改学习计划。你可以减少题目数量或调整意愿后重试。
```

### 10.3 证据不足

如果用户还没有足够训练事实：

- 允许展示画像。
- 允许用户输入意愿。
- 生成时可以返回空 draft。
- 前端展示：`当前训练证据不足，建议先完成 1-2 道计划题后再生成补强题。`

是否足够的保守判断：

- 至少有 1 个 `session_summary`，或
- 最新 profile snapshot 不是纯初始画像，或
- 用户意愿非常明确且候选池充足。

## 11. 候选题池生成

后端先筛候选，再交给模型。

候选来源：

- 当前题库 `problem`。
- 排除 paid only。
- 排除当前 active version 已存在题。
- 排除缺少 slug 或基础元数据异常的题。

排序/筛选信号：

- 用户意愿文本命中的标签或难度。
- 最新画像弱项标签。
- 最近复盘中的 `main_stuck_points` 和 `error_types`。
- 当前阶段重点标签。
- 当前阶段难度。
- 面试高频或基础高频标记，如果题库已有相关分类。

候选数量：

- 第一版建议最多传给模型 30-60 道。
- 候选不足时可以传更少，并在上下文中说明。

## 12. 确认加入计划

确认时后端执行：

1. 锁定 plan/version/draft。
2. 确认 draft 属于当前用户和当前 active plan。
3. 确认 draft 状态是 `generated`。
4. 重新校验题目仍未重复，避免并发确认。
5. 找到当前阶段末尾 order index。
6. 创建新的 `study_plan_item`。
7. `status` 为 `pending`。
8. `recommendation_reason` 写入模型理由，并标记画像补强来源。
9. `skill_tags_json` 使用题库标签和模型 `weakness_targets` 的安全交集。
10. 写入变更日志。
11. draft 状态改为 `confirmed`。
12. 返回新的 `StudyPlanResponse`。

确认失败时不做部分写入。

## 13. Trace、日志与安全

日志要求：

- 生成开始、完成、失败、repair、确认加入计划都记录。
- 使用稳定 key=value。
- 不记录完整聊天、完整代码、密钥或完整用户意愿。
- 用户意愿在数据库 draft 中按长度限制保存；日志只记录长度、hash 或截断摘要。

建议日志：

```text
profile_plan_enrichment_started user_id=%s plan_id=%s count=%s difficulty=%s
profile_plan_enrichment_generated user_id=%s plan_id=%s draft_id=%s item_count=%s
profile_plan_enrichment_confirmed user_id=%s plan_id=%s draft_id=%s added_count=%s
profile_plan_enrichment_failed user_id=%s plan_id=%s draft_id=%s reason=%s
```

Trace：

- 可写入 `agent_trace` 或 LLM Run 相关 trace。
- trace 只保存节点摘要、候选数量、校验结果和推荐摘要。
- 不保存完整 prompt 或完整候选题上下文。

## 14. 测试策略

后端测试：

- 用户无 active plan 时拒绝生成。
- 用户无权限访问 plan 时拒绝生成。
- 初始画像且无训练事实时返回证据不足或低置信 draft。
- 用户意愿、数量、难度倾向进入 LLM input。
- 候选题池排除当前计划已有题和 paid only 题。
- 模型输出越界 slug 时触发 repair 或失败。
- 模型输出重复题时触发 repair 或失败。
- confirm 后追加计划题，并保持已完成题不变。
- confirm 并发重复请求不会重复加题。
- 追加题目的推荐理由、第一问、review 重点被保存到计划项可读 payload。

前端测试：

- 学习计划页显示 `查看画像与补强` 入口。
- 抽屉展示画像摘要和证据不足状态。
- 表单包含自由文本、数量、难度倾向。
- 生成时显示 LLM Run 状态和取消入口。
- 预览展示补强主题、计划差距和题目列表。
- 确认加入后刷新学习计划。
- 生成失败时不显示“已修改计划”的误导文案。

Eval：

- 用户明确说“不想加 DP”时，模型不得推荐 DP 题，除非候选题和画像证据给出强约束且输出解释。
- 用户要求“面试高频 Medium”时，推荐理由需要解释面试高频和薄弱点的交集。
- 低证据画像时，模型应保守，不编造长期弱点。

## 15. 文档影响

实现本功能时需要更新：

- `docs/index.md`：如果新增 API/service/model 目录职责描述。
- `docs/architecture/foundation.md`：新增 `profile_plan_enrichment` API、service、LLM Run 和 draft 表。
- `docs/prd/prd.md`：学习计划页新增画像与补强入口。
- `docs/prd/ai-coach-user-profile-prd.md`：画像新增服务对象：用户可见画像和计划补强。
- `docs/project-todolist.md`：新增 P1 或 P0.5 任务，说明不属于原 T10 非 RAG MVP 闭环。

如果第一版只新增内部 service 且 API/页面可见行为发生变化，仍必须更新 PRD 和架构文档。

## 16. 验收标准

- 用户可以在学习计划页查看当前画像摘要和老师式薄弱点说明。
- 用户可以填写自由意愿，并选择新增数量和难度倾向。
- 系统通过 LLM Run 生成补强题预览，且不会直接修改计划。
- 预览中每道题都有薄弱点、推荐理由、第一问和 review 重点。
- 用户确认后，题目追加到当前 active 学习计划的当前阶段末尾。
- 已有题、已完成题和计划历史不被破坏。
- 题目重复、paid only、越界候选和 schema 错误会被后端拦截。
- 相关后端、前端和 eval 测试通过。
