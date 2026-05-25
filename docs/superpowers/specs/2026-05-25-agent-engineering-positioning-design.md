# AI Agent 工程转型包装设计

## 1. 背景

当前项目已经从早期 Agent demo 演进为 Agentic Coding Learning Coach 的全栈产品基座。现有能力包括全栈工程基座、题库导入、本地用户与模型资产池、目标校准、版本化学习计划、统一 LLM Run 流式层、计划题训练会话、Chat-first 工作台、自动代码尝试记录和 LeetCode 已 AC 入口。

这份设计的目标不是新增一个独立功能，而是明确后续产品设计和研发设计如何服务一个更清晰的职业叙事：从 Java 后端开发者转向 AI Agent 开发者。

## 2. 定位结论

项目应包装为：

> 面向算法训练场景的可恢复、可约束、可追踪、可评估 AI Agent 教练系统。

不建议把项目主叙事写成“AI 刷题助手”或“ChatGPT 刷题应用”。这些表达容易让面试官认为项目只是普通大模型调用。更好的叙事是：系统把大模型约束在一个训练状态机内，通过后端守卫、RAG、用户画像、Trace 和 Eval，让 AI 教练行为可控、可解释、可验证。

## 3. 推荐路线

推荐采用“Agent 工程优先”路线。

对比路线：

| 路线 | 重点 | 优点 | 不足 |
| --- | --- | --- | --- |
| 产品闭环优先 | 目标校准、计划、工作台、复盘、推荐 | 演示完整，适合 AI 应用全栈岗位 | Agent 技术深度不够突出 |
| Agent 工程优先 | LangGraph、状态机、守卫、RAG、Trace、Eval | 最贴近 AI Agent 开发者定位 | 需要把工程边界、测试和评估做扎实 |
| LLM 平台化优先 | LLM Run、模型资产、SSE、故障切换、可观测性 | 后端工程含金量强 | 产品故事不如 Agent 教练直接 |

本项目已经具备统一 LLM Run、用户模型资产池、训练会话和初步教练守卫，继续走 Agent 工程路线的性价比最高。

## 4. 产品设计主线

产品主线保持 PRD 中的训练闭环：

```text
目标校准
-> 生成学习计划
-> 进入计划题工作台
-> AI 诊断卡点
-> 分层提示或代码 review
-> LeetCode 提交反馈归因
-> 单题复盘
-> 画像更新
-> 下一题推荐
```

后续产品设计不应优先扩展社区、打卡、排行榜、泛面试或简历润色。所有新增能力都要服务一个核心问题：

> AI 教练是否能根据用户画像、题目上下文和训练事实，做出可控且可解释的下一步教学决策。

## 5. 研发设计主线

### 5.1 可恢复 Agent 状态机

将当前教练流程升级为 LangGraph 状态机。Graph State 应至少包含：

- 用户、学习计划、计划题和训练会话标识。
- 当前训练阶段。
- 当前提示档位和最高提示档位。
- 用户画像摘要。
- 最近训练事件摘要。
- 最新代码尝试摘要。
- 最新 LeetCode 提交反馈。
- RAG 检索上下文。
- 当前 run、trace 和错误摘要。

核心节点建议：

| 节点 | 职责 |
| --- | --- |
| `load_training_context` | 读取题目、计划、session、画像和最近事件 |
| `classify_user_input` | 判断用户输入是思路、卡点、代码、提交反馈还是复盘请求 |
| `diagnose_stuck_point` | 诊断卡点类型和阶段覆盖情况 |
| `retrieve_supporting_context` | 按提示档位检索知识卡片和历史画像 |
| `decide_next_action` | 生成结构化下一步动作 |
| `guard_transition` | 后端校验阶段跳转、提示泄露和证据要求 |
| `generate_coach_reply` | 生成用户可见回复 |
| `persist_turn` | 写入 assistant event、coach turn、trace 和 session 状态 |
| `maybe_generate_summary` | 在 AC 或复盘请求后生成复盘和画像增量 |

状态机需要支持 checkpoint 和 interrupt。用户输入是自然中断点，模型调用、RAG 检索、守卫拒绝和复盘生成都应能被 trace 追踪。

### 5.2 结构化教练决策和后端守卫

LLM 不直接决定系统状态。LLM 只输出结构化决策，例如：

```json
{
  "phase_after": "review_code",
  "diagnosed_stuck_point": "edge_case_missing",
  "next_action": "review_code_with_counterexample",
  "reply_md": "用户可见回复",
  "should_reveal_solution": false,
  "confidence": "medium"
}
```

后端守卫负责：

- 低提示档位禁止完整题解或完整可提交代码。
- 没有代码证据时不能进入 `review_code`。
- 没有提交反馈时不能进入 `analyze_feedback`。
- 没有 AC 或等价终态证据时不能进入正式复盘。
- 模型输出 schema 无效时回退到安全追问。
- 守卫拒绝必须写入 `coach_turn` 和 trace，便于后续评估。

这一层是简历亮点之一：不是“让模型自由聊天”，而是用工程约束把模型纳入业务状态机。

### 5.3 RAG 和学习记忆

RAG 不应粗暴召回完整聊天记录。优先级应为：

1. 用户长期画像。
2. 最近单题复盘摘要。
3. 画像增量和证据摘要。
4. 当前计划目标和阶段目标。
5. 题型知识卡片。
6. 必要的关键训练事件。

知识库需要支持元数据过滤：

| 字段 | 用途 |
| --- | --- |
| `knowledge_type` | 区分题型概念、复杂度、调试技巧、面试表达、完整题解等 |
| `hint_level` | 控制追问档、方向档、关键档、复盘档能召回什么 |
| `has_full_solution` | 防止低提示档位召回完整解法 |
| `source` | 标记资料来源和版本 |
| `problem_tags` | 按题型和标签召回 |

RAG 检索结果必须写入 `retrieval_trace`，至少记录 query 摘要、过滤条件、命中 chunk、被过滤原因和最终注入上下文的片段。

### 5.4 Trace 和 Eval

Trace 和 Eval 是项目从“能跑”升级为“可证明 Agent 质量”的关键。

最小评估集包括：

| Eval | 目标 | 典型样例 |
| --- | --- | --- |
| Hint Leakage Eval | 检查低提示档位是否泄露完整答案 | 用户请求“直接给代码”，当前档位为追问档 |
| Diagnosis Eval | 检查卡点诊断是否准确 | 用户描述不变量不清、边界遗漏、复杂度错误 |
| Code Review Eval | 检查 review 是否定位到正确问题区域 | 用户粘贴含边界 bug 的代码 |
| RAG Grounding Eval | 检查回复是否基于允许召回材料 | 低档位召回时不能引用完整题解 |

Trace 至少覆盖：

- LLM Run 生命周期。
- Graph 节点输入输出摘要。
- RAG 检索和过滤。
- 守卫接受或拒绝原因。
- 最终回复、阶段迁移和错误摘要。

评估 runner 可以先使用固定样例和规则断言，不必一开始接复杂自动评分。重点是让项目能展示“我如何评估和改进 Agent 行为”。

## 6. 阶段路线

### 阶段 1：补齐基础教练闭环

对应当前 T3 / T5。

交付：

- `StuckPointDiagnosis`、`CoachAction`、`CodeReviewResult` 等结构化 schema。
- hint level 到用户可见档位的明确映射。
- 训练模式下的提示升级和降级规则。
- 非 AC 提交反馈入口或聊天识别。
- 基于用户思路、代码和提交结果的错因归因。
- 低档位泄题测试。

完成标准：

- 用户能从计划题进入工作台，描述思路或粘贴代码。
- AI 能生成结构化诊断和下一步动作。
- 后端守卫能拒绝非法跳转和低档位泄题。
- WA/TLE/RE 等非 AC 反馈能推动下一轮引导。

### 阶段 2：接入 LangGraph 状态机

对应 T4。

交付：

- Graph State。
- 核心节点和条件边。
- checkpoint 和 thread id。
- Wait User Input interrupt。
- 现有 `coach_turn` flow 迁移到图执行入口。
- 图执行 trace。

完成标准：

- 一次训练过程能跨多轮用户输入恢复。
- 中断、取消、失败后能保留可解释状态。
- 节点级测试覆盖快进、回退、守卫拒绝和复盘触发。

### 阶段 3：接入 RAG 和画像记忆

对应 T6 / T7。

交付：

- `knowledge_doc`、`knowledge_chunk` 和 source manifest。
- Markdown/txt 语料导入、清洗、切块和 embedding。
- hint level、knowledge_type、has_full_solution 过滤。
- `retrieval_trace` 写入。
- 单题复盘、画像增量、下一题推荐。

完成标准：

- 教练回复能使用允许的知识片段增强。
- 低提示档位不会召回完整解法。
- 复盘和画像能影响下一题第一问、提示策略和 review 重点。

### 阶段 4：补齐 Trace、Eval 和演示材料

对应 T9 / T10。

交付：

- Agent Trace 页接真实数据。
- Hint Leakage、Diagnosis、Code Review、RAG Grounding Eval。
- `make eval` 或独立 eval 命令。
- 端到端演示路径。
- 简历项目描述、架构图说明和面试讲解提纲。

完成标准：

- 能展示一次完整训练闭环。
- 能展示 Agent 决策、守卫、RAG、复盘和画像如何被追踪。
- 能用 eval 样例证明系统不是只靠主观体验判断质量。

## 7. 简历包装

### 7.1 项目标题

推荐标题：

> Agentic Coding Learning Coach - 面向算法训练的 AI Agent 教练系统

### 7.2 一句话描述

设计并实现面向算法训练的可恢复 AI Agent 教练系统，基于 FastAPI、React、PostgreSQL/pgvector、OpenAI Responses 和 LangGraph，支持目标校准、学习计划生成、状态机式做题引导、分层提示、代码 review、提交反馈归因、复盘画像和 Trace/Eval 评估。

### 7.3 简历要点

- 设计统一 LLM Run 编排层，封装模型资产选择、SSE 流式输出、取消、状态持久化和失败回退，避免前端直接接触 API key 和模型调用细节。
- 构建画像驱动的单题训练 Agent，将用户输入、题目上下文、学习计划、代码尝试和提交反馈转化为结构化教练决策。
- 引入后端 `coach_guard` 约束 Agent 行为，对阶段跳转、提示档位、泄题风险和证据缺失进行校验，降低模型直接给答案或错误快进的风险。
- 规划 LangGraph 可恢复状态机，支持训练阶段快进、回退、checkpoint、interrupt 和跨轮 session 恢复。
- 设计 RAG 知识库和学习记忆召回策略，通过 `hint_level`、`knowledge_type` 和 `has_full_solution` 元数据过滤，控制不同提示档位的知识注入边界。
- 设计 Agent Trace 和 Eval 体系，覆盖 Hint Leakage、Diagnosis、Code Review 和 RAG Grounding，形成可验证的 Agent 行为质量闭环。

### 7.4 面试讲解结构

1. 先讲业务问题：普通大模型容易直接给答案，学习过程不可诊断。
2. 再讲产品抽象：把刷题变成目标、计划、训练、反馈、复盘和画像闭环。
3. 再讲 Agent 架构：LLM 做判断，后端状态机和 guard 做约束。
4. 再讲数据闭环：训练事件、代码尝试、提交反馈、复盘和画像如何沉淀。
5. 最后讲质量保障：Trace 和 Eval 如何发现泄题、误诊、错误 review 和 RAG 失真。

## 8. 非目标

本路线短期不做：

- 泛化聊天助手。
- 自动提交 LeetCode。
- 自建在线判题系统。
- 抓取 LeetCode 隐藏用例。
- 社区、排行榜、打卡提醒。
- 简历润色、行为面试、系统设计面试等泛面试模块。

这些能力会稀释 Agent 工程主线，不利于转型简历表达。

## 9. 风险和控制

| 风险 | 控制方式 |
| --- | --- |
| 功能越做越多，Agent 主线不清晰 | 所有功能必须能回答“是否提升教练决策质量” |
| LangGraph 过早接入导致复杂度上升 | 先完成有限状态和 guard，再迁移图执行入口 |
| RAG 召回完整题解导致泄题 | chunk 元数据必须支持 hint level 和 full solution 过滤 |
| Eval 变成形式化测试 | 样例必须覆盖真实失败模式，例如泄题、误诊、错误 review |
| 简历表达过度包装 | 每个亮点都要能对应代码、文档、测试或演示证据 |

## 10. 验收标准

这条路线完成后，应能同时满足三类验收：

产品验收：

- 用户能完成从目标校准到单题复盘的训练闭环。
- AI 教练默认不直接给完整答案，而是根据阶段和提示档位引导。
- 复盘和画像能影响下一次训练策略。

工程验收：

- 大模型调用统一通过 LLM Run 层。
- Agent 决策有结构化 schema、状态机、后端 guard 和 trace。
- RAG 检索有 metadata 过滤和 retrieval trace。
- Eval runner 能覆盖关键 Agent 质量风险。

简历验收：

- 项目标题、技术栈、架构图、核心难点和量化验证可以清晰讲述。
- 每个简历亮点都有对应模块或文档证据。
- 面试中能解释为什么这不是普通 Prompt 项目，而是 Agent 工程项目。
