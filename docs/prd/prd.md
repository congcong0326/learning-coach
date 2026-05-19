# PRD v0.2：Agentic Coding Learning Coach

## 0. 文档信息

| 字段       | 内容                                                         |
| ---------- | ------------------------------------------------------------ |
| 产品名称   | Agentic Coding Learning Coach                                |
| 当前版本   | PRD v0.2                                                     |
| 产品形态   | Web 应用                                                     |
| 面向场景   | LeetCode / 算法刷题训练                                      |
| 核心定位   | AI 教练，而不是答案生成器                                    |
| 第一版目标 | 跑通“选题 → 思路诊断 → 分层提示 → 代码 review → 提交回填 → 复盘画像”的完整学习闭环 |

------

## 1. 背景与问题

很多用户刷 LeetCode 时存在两个典型问题：

1. **不会开始**：看完题目后没有思路，不知道该从暴力解法、题型识别、数据结构选择还是边界条件入手。
2. **依赖答案**：遇到卡点后直接看题解，短期能通过题目，但没有形成可迁移的分析能力。
3. **缺少复盘**：做完一道题后，很少系统记录自己卡在哪里、用了多少提示、错误类型是什么、下次应该练什么。
4. **普通 ChatGPT 缺少约束**：直接问大模型，很容易得到完整答案，无法保证“启发式训练”的学习过程。

因此，本产品希望把刷题过程从“看答案”改造成“被 AI 教练引导着独立做出来”。

------

## 2. 产品定位

Agentic Coding Learning Coach 是一个面向算法刷题的 AI 训练教练。它不直接替用户解题，而是通过 **卡点诊断、分层提示、代码审查、错误归因、复盘画像和个性化推荐**，训练用户独立分析题目、实现代码并进行面试表达的能力。

一句话定位：

> 用 LangGraph 编排刷题状态机，用本地教程语料增强 RAG 教练知识，用代码执行工具形成反馈闭环，把 LeetCode 刷题从“看题解”变成“可诊断、可追踪、可复盘的训练过程”。

------

## 3. 目标用户

### 3.1 A 类用户：刷题入门者

用户特征：

- 刚开始刷题，面对题目没有思路。
- 不知道如何从暴力解法推导到优化解法。
- 对常见题型、数据结构和算法模式不熟悉。

核心需求：

- 题意解释。
- 思路拆解。
- 题型提示。
- 边界条件提醒。
- 不直接给答案的启发式引导。

### 3.2 B 类用户：刷过一轮但想提升者

用户特征：

- 已经做过一批题，但独立解题不稳定。
- 能看懂题解，但面试时表达不清。
- 常在边界条件、复杂度、代码实现细节上出错。

核心需求：

- 更克制的提示。
- 面试官式追问。
- 代码 review。
- 复杂度分析。
- 错因归纳。
- 同类题推荐。

------

## 4. 核心目标

第一版要完成一个完整学习闭环：

```text
选题
-> 阅读中文题面
-> 用户描述思路
-> AI 判断卡点
-> AI 追问或给分层提示
-> 用户写代码
-> AI review 代码
-> 本地样例运行 / 用户去 LeetCode 官网提交
-> 回填提交结果
-> AI 复盘并更新学习画像
-> 推荐下一题
```

第一版不追求复杂推荐算法，不追求完整在线判题系统，不追求替代 LeetCode，而是证明一个核心闭环：

> 给定一道算法题，系统能在不泄露完整答案的前提下，诊断用户卡点，动态控制提示层级，review 用户代码，记录过程数据，并把本次训练转化为用户画像。

------

## 5. MVP 范围

### 5.1 第一版必须完成

1. 题库初始化与题目浏览。
2. 中文 Markdown 题面渲染。
3. 做题工作台：题面、代码编辑器、AI 教练对话。
4. 两种训练模式：入门引导、独立训练。
5. AI 教练分层提示。
6. 用户代码 review。
7. 本地代码运行工具，至少支持 Python。
8. 用户手动回填 LeetCode 提交结果。
9. 单题复盘总结。
10. 用户学习画像更新。
11. Agent 执行 trace 记录。
12. 本地教程语料导入与 RAG 教练知识库接入。

### 5.2 第一版不做

1. 不做完整在线判题系统。
2. 不抓取 LeetCode 隐藏测试用例。
3. 不自动提交 LeetCode。
4. 不做复杂推荐算法。
5. 不公开提交完整题面数据到自己的 Git 仓库。
6. 不优先做复杂排行榜、社区、分享等社交功能。
7. 不支持多语言代码运行，第一版只支持 Python。

------

## 6. 页面结构

### 6.1 题库列表页

功能：

- 展示题目列表。
- 支持难度筛选。
- 支持关键词搜索。
- 支持题型标签筛选。
- 支持优先级排序。
- 支持训练状态过滤：未开始、进行中、已完成、待复盘。

字段展示：

- 题号。
- 标题。
- 难度。
- 标签。
- 用户状态。
- 最近训练时间。
- 平均提示等级。

### 6.2 做题工作台

页面布局：

- 左侧：题目详情，渲染 Markdown 中文题面。
- 中间：Python / Java 代码编辑区。
- 右侧：AI 教练对话区。
- 顶部：题目标题、难度、标签、LeetCode 原题链接、训练模式、当前提示等级。
- 底部或侧边：运行结果、提交回填、复盘入口。

### 6.3 复盘页

展示内容：

- 本题最终结果。
- 用户主要卡点。
- 最高提示等级。
- 代码错误类型。
- 时间复杂度和空间复杂度。
- 正确解法核心不变量。
- 用户画像更新记录。
- 推荐下一题。

------

## 7. 训练模式

### 7.1 入门引导模式

适合 A 类用户。

AI 行为：

- 更主动地拆解题意。
- 可以帮助用户识别题型。
- 可以引导用户先写暴力解法。
- 可以逐步提醒数据结构和关键不变量。
- 用户连续卡住时，允许较快提升提示层级。

### 7.2 独立训练模式

适合 B 类用户。

AI 行为：

- 更克制。
- 更像面试官。
- 优先追问，不直接提示。
- 重点检查思路漏洞、复杂度、边界条件和表达能力。
- 提示层级提升更慢。

------

## 8. AI 教练行为设计

### 8.1 教练原则

AI 教练必须遵守以下原则：

1. 默认不直接给完整答案。
2. 优先追问用户当前思路。
3. 根据用户卡点决定提示层级。
4. 提示内容必须和当前 hint level 匹配。
5. 除非用户进入高提示层级或复盘阶段，否则不输出完整解法。
6. 对代码进行 review 时，优先指出问题类型和定位方向，不直接重写完整代码。
7. 复盘阶段可以总结完整思路，但仍应重点解释推导过程。

### 8.2 AI 教练阶段

AI 教练围绕以下阶段工作：

```text
理解题意
识别题型
确认暴力解法
引导优化
检查关键不变量
检查边界条件
review 代码
运行反馈归因
复盘错因
推荐下一题
```

### 8.3 提示分层

| Level   | 行为                  | 示例                                                  |
| ------- | --------------------- | ----------------------------------------------------- |
| Level 0 | 只追问，不提示        | 你现在认为暴力解法是什么？复杂度是多少？              |
| Level 1 | 提醒题型方向          | 这题可以思考是否存在“快速查找已出现元素”的需求。      |
| Level 2 | 提醒关键数据结构      | 可以考虑用哈希表记录已经遍历过的值。                  |
| Level 3 | 提醒核心思路 / 不变量 | 遍历到 i 时，只允许使用 i 之前出现过的元素。          |
| Level 4 | 给伪代码框架          | 遍历数组，计算 complement，先查 map，再写入当前元素。 |
| Level 5 | 给完整解法思路        | 系统解释完整思路，但仍不默认直接给完整代码。          |

提示层级提升条件：

- 用户明确请求更多提示。
- 用户连续多轮回答偏离关键方向。
- 用户代码多次失败且错误类型相同。
- 用户长时间停留在同一阶段。
- AI 诊断用户已无法通过追问继续推进。

提示层级降低条件：

- 用户已经给出正确方向。
- 用户开始独立修正代码。
- 用户进入独立训练模式。

------

## 9. 题库数据设计

### 9.1 数据源

第一版主数据源使用：

```text
https://github.com/fishjar/leetcode-problemset/tree/main/problemset_md
```

使用方式：

1. 程序启动时检查本地数据库是否已有题库。
2. 如果没有，则初始化拉取或读取 problemset_md。
3. 解析 Markdown，导入数据库。
4. 后续启动直接读取数据库。
5. 单独提供同步命令用于更新题库。

### 9.2 题面与题解隔离

需要重点注意：第三方题库 Markdown 中可能同时包含题面、标签、题解、代码模板或解法片段。

为了避免 AI 直接看到答案，导入时必须做内容拆分：

| 字段          | 用途                       | 是否默认进入 AI 上下文 |
| ------------- | -------------------------- | ---------------------- |
| statement_md  | 题面、示例、约束           | 是                     |
| metadata_json | 难度、标签、原链接、相似题 | 是                     |
| solution_md   | 题解、完整思路、代码       | 否                     |
| coach_notes   | 人工维护的教练提示卡片     | 按 hint level 控制     |

### 9.3 problem 表

```text
problem
- id
- problem_id
- title
- slug
- difficulty
- statement_md
- solution_md
- metadata_json
- leetcode_url
- source_repo
- source_path
- source_commit
- content_hash
- priority
- created_at
- updated_at
```

------

## 10. AI Agent 技术架构

### 10.1 总体架构

系统分为五层：

```text
1. Orchestration Layer：LangGraph 状态机、checkpoint、interrupt
2. Knowledge Layer：本地教程语料、RAG 教练知识库、题型知识库、用户历史检索
3. Tool Layer：代码执行、测试用例生成、错误归因、复杂度分析
4. Memory Layer：session 短期记忆、user profile 长期记忆
5. Evaluation & Observability：trace、hint leakage eval、diagnosis eval、review eval
```

核心思想：

- LangGraph 负责编排学习流程。
- RAG 以本地算法教程语料为知识底座，优先提供抽取后的教练知识，不直接提供答案。
- Tool 提供代码运行和错误反馈。
- Memory 记录用户当前状态和长期能力画像。
- Eval 和 Trace 保证 Agent 行为可控、可观测、可改进。

------

## 11. LangGraph 状态机设计

### 11.1 状态流转

```text
ProblemSelected
-> BuildProblemContext
-> RetrieveCoachContext
-> DiagnoseStuckPoint
-> DecideNextAction
-> GenerateCoachResponse
-> WaitUserInput
-> ReviewReasoning / ReviewCode
-> RunCodeTool
-> ClassifyError
-> UpdateUserProfile
-> SummarizeSession
```

### 11.2 核心节点说明

| 节点                  | 职责                                   |
| --------------------- | -------------------------------------- |
| ProblemSelected       | 用户选择题目，初始化 session           |
| BuildProblemContext   | 加载题面、标签、用户历史记录           |
| RetrieveCoachContext  | 从 RAG 中检索教练知识和历史相似卡点    |
| DiagnoseStuckPoint    | 判断用户当前卡点                       |
| DecideNextAction      | 决定追问、提示、review、运行代码或复盘 |
| GenerateCoachResponse | 生成符合 hint level 的教练回复         |
| WaitUserInput         | 暂停状态机，等待用户输入               |
| ReviewReasoning       | 审查用户思路                           |
| ReviewCode            | 审查用户代码                           |
| RunCodeTool           | 调用代码执行工具                       |
| ClassifyError         | 对运行结果和提交结果做错误归因         |
| UpdateUserProfile     | 更新用户学习画像                       |
| SummarizeSession      | 生成本题复盘                           |

### 11.3 Graph State

```json
{
  "session_id": "string",
  "thread_id": "string",
  "user_id": "string",
  "problem_slug": "string",
  "phase": "UNDERSTAND | PLAN | IMPLEMENT | DEBUG | REVIEW | SUMMARY",
  "training_mode": "guided | independent",
  "current_hint_level": 0,
  "max_hint_level_used": 0,
  "attempt_count": 0,
  "user_message": "string",
  "user_claimed_idea": "string",
  "code_snapshot": "string",
  "detected_stuck_point": "problem_understanding | pattern | invariant | implementation | edge_case",
  "retrieved_context": [],
  "tool_results": [],
  "leetcode_result": "AC | WA | TLE | RE | UNKNOWN",
  "profile_delta": {},
  "next_action": "ask_question | give_hint | review_code | run_code | summarize"
}
```

------

## 12. RAG 知识层设计

### 12.1 RAG 的定位

本项目中的 RAG 不用于检索完整答案，而用于检索“教练知识”。

第一版采用“本地教程语料 + 派生教练知识”的混合方案：

```text
Raw Tutorial Corpus
-> Derived Coach Knowledge
-> Problem Coach Card
-> Hint-Level Controlled Coach Response
```

其中本地教程语料用于承载热门算法书籍、教程、课程讲义、博客文章或个人笔记；派生教练知识用于把原文中的算法思想转化为更适合 AI 教练使用的结构化卡片。做题过程中，系统优先检索派生教练知识，只有在需要深入解释概念、补充背景或复盘表达时，才回查原始教程片段。

正确用途：

- 检索算法模式知识。
- 检索从本地教程中抽取出的概念卡片、模式卡片、不变量卡片和常见错误卡片。
- 检索题目教练卡片。
- 检索常见错误。
- 检索面试表达模板。
- 检索用户历史相似卡点。

错误用途：

- 直接检索完整题解并喂给模型。
- 直接把原始教程的大段内容拼进 prompt。
- 直接把 solution_md 放进 prompt。
- 在低提示层级中暴露完整思路或代码。

### 12.2 知识库类型

#### 12.2.1 本地教程原始语料

用于存储用户下载到本地的热门算法书籍、教程、课程讲义、博客文章或个人整理笔记。

支持的原始格式：

- Markdown。
- HTML。
- PDF。
- EPUB。
- 纯文本。

原始语料不直接等同于教练知识。导入后需要经过清洗、切块和元数据标注，作为后续抽取结构化教练知识的底座。

字段内容：

- 来源名称。
- 章节标题。
- 原始文件路径。
- 文档格式。
- 章节层级。
- 原文片段。
- 代码块标记。
- 例题标记。
- 算法标签。
- 内容 hash。

#### 12.2.2 派生教练知识

派生教练知识是从本地教程原始语料中抽取出的结构化知识卡片，是做题时 RAG 的主要检索对象。

卡片类型：

- concept_card：解释一个基础概念，例如前缀和、递归、状态转移。
- pattern_card：解释一种题型模式，例如滑动窗口、二分答案、单调栈。
- invariant_card：解释一个关键不变量，例如窗口内始终满足某个约束。
- common_bug_card：解释常见错误，例如二分边界、DP 初始化、重复元素处理。
- hint_card：按 hint level 编排的提示素材。
- interview_expression_card：复盘和面试表达模板。

每张卡片都应保留来源引用信息，便于在需要时回查原始教程片段。

#### 12.2.3 算法模式知识

示例：滑动窗口、双指针、哈希表、二分、单调栈、DFS、BFS、回溯、动态规划。

字段内容：

- 适用场景。
- 识别信号。
- 常见题目特征。
- 核心不变量。
- 常见错误。
- 边界条件。
- 分层提示。
- 面试表达方式。

#### 12.2.4 题目教练卡片

以 Two Sum 为例：

```text
problem_slug: two-sum
pattern: hash_table
level_1_hint: 思考是否存在“快速查找已出现元素”的需求。
level_2_hint: 可以考虑用哈希表记录已经遍历过的值。
level_3_hint: 遍历到 i 时，哈希表只应该保存 i 之前的元素。
level_4_hint: 遍历数组，先查 complement，再写入当前元素。
common_mistakes: 先把所有元素放入 map，导致可能使用同一个元素两次。
edge_cases: 重复数字、负数、同一个值出现两次。
```

题目教练卡片可以引用派生教练知识中的 pattern_card、invariant_card 和 common_bug_card，但不应直接复制完整题解。它的职责是把通用算法知识映射到具体题目的提示层级。

#### 12.2.5 常见错误知识库

示例：

- 二分边界错误。
- 滑动窗口收缩条件错误。
- DP 初始化错误。
- 递归终止条件错误。
- 哈希表覆盖重复值错误。
- 使用同一元素两次。
- Python 下标越界。

#### 12.2.6 面试表达知识库

用于复盘阶段，帮助用户把解题过程转化为面试表达：

- 我为什么想到这个题型。
- 暴力解法是什么。
- 优化点在哪里。
- 数据结构为什么合适。
- 不变量是什么。
- 复杂度是多少。

### 12.3 本地教程导入与知识抽取流程

本地教程进入 RAG 的流程：

```text
导入本地文件
-> 解析文档结构
-> 清洗目录、页眉页脚、广告、重复内容
-> 保留标题层级、代码块、公式和列表结构
-> 按知识单元切块
-> 生成 chunk metadata
-> embedding 入库
-> 抽取派生教练知识卡片
-> 人工或规则校验 hint level 和知识类型
```

切块原则：

- 优先按章节、标题、算法概念和完整语义段落切块。
- 避免简单按固定 token 数硬切，防止一个算法解释被拆散。
- 代码块应作为独立 chunk，并标记为 code_template 或 example_code。
- 包含完整题目解法的片段要标记 `has_full_solution=true`。
- 每个 chunk 都要保留 source_name、chapter、section、source_path 和 content_hash。

派生卡片抽取策略：

- 从教程章节中抽取通用算法模式，不抽取某一道题的完整代码答案。
- 从代码示例中抽取实现注意点、边界条件和常见错误。
- 从讲解文字中抽取识别信号、核心不变量和复杂度分析。
- 对同一算法模式的多份教程内容进行合并去重，形成更稳定的 pattern_card。
- 原始教程 chunk 可以保留在向量库中，但默认不作为低 hint level 的直接回答依据。

### 12.4 RAG 检索输入

```json
{
  "problem_slug": "two-sum",
  "problem_tags": ["array", "hash_table"],
  "difficulty": "easy",
  "current_phase": "PLAN",
  "user_message": "我想用双重循环找两个数",
  "user_code": "",
  "detected_stuck_point": "pattern",
  "current_hint_level": 1,
  "training_mode": "guided",
  "user_profile": {},
  "retrieval_intent": "hint | concept_explain | code_review | debug | summary"
}
```

### 12.5 RAG 检索策略

检索采用两阶段策略：

第一阶段优先检索结构化教练知识：

1. 根据题目标签检索算法模式知识。
2. 根据 problem_slug 检索题目教练卡片。
3. 根据 stuck_point 检索常见错误知识。
4. 根据 user_profile 检索用户历史相似失败记录。
5. 根据 phase 检索对应阶段的表达模板或追问模板。

第二阶段按需回查原始教程语料：

1. 当用户需要概念解释时，检索对应 concept_card 及其来源 chunk。
2. 当用户在同一算法模式上持续卡住时，补充原始教程中的更完整解释。
3. 当进入复盘阶段时，检索教程中的表达方式和推导过程，用于帮助用户形成面试表达。
4. 当检索结果冲突时，优先使用派生教练知识；原始教程只作为解释依据。

最终进入 prompt 的内容必须经过重排和过滤：

- 优先选择 problem_coach_card。
- 其次选择 pattern_card、invariant_card、common_bug_card。
- 再选择 interview_expression_card。
- 最后才选择 raw_tutorial_chunk。
- 过滤掉超过当前 hint level 的 chunk。
- 过滤掉和当前题目无关的完整题解、完整代码和大段模板。

### 12.6 Hint Level 权限控制

RAG 检索结果必须受 hint level 控制：

| Hint Level | 允许使用的知识 | 原始教程使用规则 |
| ---------- | -------------- | ---------------- |
| Level 0 | 追问模板、题意澄清模板 | 不使用原始教程片段 |
| Level 1 | 题型方向、识别信号 | 只使用抽象 pattern_card，不直接引用教程代码或例题解法 |
| Level 2 | 关键数据结构 | 可使用概念解释片段，但过滤代码模板和完整例题 |
| Level 3 | 核心不变量、关键边界 | 可使用不变量解释和常见错误片段 |
| Level 4 | 伪代码框架 | 可使用抽象伪代码，不使用可直接提交的完整代码 |
| Level 5 | 完整思路，但仍不默认输出完整代码 | 可使用完整推导过程和复盘表达，完整代码仍需用户明确请求或进入复盘阶段 |

### 12.7 知识表设计

```text
knowledge_doc
- id
- doc_type              # raw_tutorial / concept / pattern / invariant / problem_coach_card / common_bug / hint / interview_expression
- title
- content
- tags                  # json array
- problem_slug
- difficulty
- phase                 # understand / plan / implement / debug / review / summary
- stuck_point           # pattern / invariant / implementation / edge_case
- hint_level_min
- hint_level_max
- is_solution
- has_full_solution
- source_type           # book / tutorial / blog / course_note / personal_note / generated_card
- source_name
- source_path
- source_locator        # chapter / section / page / heading
- parent_doc_id         # derived card 对应的 raw_tutorial 文档
- content_hash
- created_at
- updated_at
knowledge_chunk
- id
- doc_id
- chunk_text
- embedding
- metadata_json
- knowledge_type        # concept / pattern / invariant / bug / code_template / example / expression
- hint_level_min
- hint_level_max
- has_full_solution
- source_locator
- created_at
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

------

## 13. Tool Layer 设计

### 13.1 工具清单

第一版至少实现以下工具：

| 工具                     | 说明                                           |
| ------------------------ | ---------------------------------------------- |
| run_python_code_tool     | 运行用户 Python 代码，限制 CPU、内存和超时时间 |
| generate_test_cases_tool | 根据题面生成基础样例和边界样例                 |
| analyze_code_tool        | 对代码做静态分析和复杂度初判                   |
| classify_error_tool      | 根据运行结果、用户反馈和代码判断错误类型       |

### 13.2 run_python_code_tool

输入：

```json
{
  "code": "string",
  "function_name": "twoSum",
  "test_cases": []
}
```

输出：

```json
{
  "success": false,
  "passed_count": 2,
  "failed_count": 1,
  "error_type": "wrong_answer | runtime_error | timeout | syntax_error",
  "failed_case": {},
  "stdout": "string",
  "stderr": "string",
  "elapsed_ms": 32
}
```

安全要求：

- 禁止文件系统危险操作。
- 禁止网络访问。
- 限制执行时间。
- 限制内存。
- 最好使用独立容器或沙箱进程运行。

### 13.3 generate_test_cases_tool

用途：

- 生成题面样例。
- 生成边界条件样例。
- 生成反例帮助用户定位错误。

注意：

- 不抓取 LeetCode 隐藏测试。
- 不声称等价于 LeetCode 官方判题。
- 只作为本地辅助验证。

### 13.4 analyze_code_tool

第一版可以使用规则 + LLM 结合：

规则检查：

- 是否存在语法错误。
- 是否存在明显死循环。
- 是否存在未定义变量。
- 是否存在越界风险。
- 是否存在递归无终止条件风险。

LLM 分析：

- 思路是否匹配题型。
- 复杂度是否合理。
- 是否遗漏边界条件。
- 是否存在可读性问题。

### 13.5 classify_error_tool

错误类型：

```text
problem_understanding_error
pattern_error
invariant_error
edge_case_error
implementation_error
complexity_error
syntax_error
runtime_error
unknown_error
```

------

## 14. Memory Layer 设计

### 14.1 短期记忆

短期记忆保存当前 session 状态：

- 当前题目。
- 当前阶段。
- 用户思路。
- 用户代码快照。
- 已经给过的提示。
- 当前 hint level。
- 当前工具调用结果。

短期记忆由 LangGraph state 和 checkpoint 管理。

### 14.2 长期记忆

长期记忆保存用户跨题目的能力画像：

```text
user_skill_profile
- id
- user_id
- skill_tag
- mastery_score
- solved_count
- failed_count
- avg_hint_level
- common_stuck_points
- last_practiced_at
- created_at
- updated_at
```

### 14.3 profile_delta

每次复盘生成画像增量：

```json
{
  "skill_tag": "sliding_window",
  "mastery_delta": 3,
  "weakness_added": ["窗口收缩条件不清晰", "边界条件遗漏"],
  "evidence": "用户在代码 review 阶段两次遗漏 right 指针边界",
  "next_recommendation": "继续练习 2 道固定窗口和可变窗口题"
}
```

------

## 15. 结构化输出设计

### 15.1 StuckPointDiagnosis

```json
{
  "stuck_point": "problem_understanding | pattern | invariant | implementation | edge_case",
  "confidence": 0.86,
  "evidence": "用户只描述了双层循环，没有想到快速查找 complement",
  "recommended_hint_level": 2
}
```

### 15.2 CoachAction

```json
{
  "intent": "ask_question | give_hint | review_code | run_code | summarize",
  "hint_level": 2,
  "should_reveal_solution": false,
  "message": "你现在的双重循环可以工作，但复杂度是 O(n^2)。有没有办法让查找 target - nums[i] 更快？",
  "next_state": "WAIT_USER_INPUT"
}
```

### 15.3 CodeReviewResult

```json
{
  "is_correct": false,
  "error_type": "edge_case_error",
  "complexity": "O(n^2)",
  "issues": ["可能使用同一个下标两次", "没有说明重复元素如何处理"],
  "next_hint_level": 3
}
```

### 15.4 SessionSummary

```json
{
  "final_result": "AC",
  "max_hint_level_used": 3,
  "main_stuck_points": ["pattern", "invariant"],
  "learned_concepts": ["hash_table", "complement lookup"],
  "wrong_reasons": ["没有先明确哈希表中保存的是已遍历元素"],
  "profile_delta": {},
  "next_problem_recommendations": []
}
```

------

## 16. 提交回填设计

第一版不自动提交 LeetCode。

用户流程：

1. 用户在本系统写代码并 review。
2. 用户点击 LeetCode 原题链接。
3. 用户去 LeetCode 官网提交。
4. 用户回到系统，手动选择提交结果：AC、WA、TLE、RE、未提交。
5. 用户可粘贴错误信息或失败样例。
6. AI 根据提交结果进行复盘或继续 debug。

提交结果表：

```text
submission_feedback
- id
- session_id
- user_id
- problem_slug
- result              # AC / WA / TLE / RE / UNKNOWN
- runtime_ms
- memory_mb
- failed_case
- error_message
- created_at
```

------

## 17. 学习记录与会话表

### 17.1 practice_session

```text
practice_session
- id
- user_id
- problem_slug
- training_mode
- status              # started / coding / submitted / reviewed / completed
- current_phase
- current_hint_level
- max_hint_level_used
- attempt_count
- final_result
- started_at
- completed_at
- created_at
- updated_at
```

### 17.2 practice_event

```text
practice_event
- id
- session_id
- event_type          # user_message / ai_message / tool_call / hint_used / code_run / submit_feedback
- phase
- hint_level
- content
- metadata_json
- created_at
```

### 17.3 code_snapshot

```text
code_snapshot
- id
- session_id
- language
- code
- source              # user_edit / ai_review / final
- created_at
```

------

## 18. Evaluation & Observability

### 18.1 为什么需要评估

Agent 项目容易被质疑：

> 这个系统相比直接问 ChatGPT，有什么可证明的优势？

因此第一版就需要记录和评估以下内容：

- AI 是否遵守不泄题约束。
- AI 是否准确判断用户卡点。
- AI 提示是否符合 hint level。
- AI review 是否能识别真实代码问题。
- 用户是否在较低提示等级下完成题目。
- 用户同类题后续表现是否改善。

### 18.2 评估类型

#### 18.2.1 Hint Leakage Eval

评估 AI 是否提前泄露答案：

- Level 0 是否只追问。
- Level 1 是否只提示方向。
- Level 2 是否只提示数据结构。
- Level 3 是否暴露了完整流程。
- Level 4 是否只给伪代码，不给完整代码。
- Level 5 是否仍避免无条件贴完整代码。

#### 18.2.2 Diagnosis Eval

给定用户输入，判断 AI 是否正确识别卡点。

示例：

```text
用户输入：我准备用双层循环枚举两个数。
期望卡点：pattern / optimization
```

#### 18.2.3 Review Eval

给定用户代码，判断 AI 是否识别：

- 语法错误。
- 边界条件错误。
- 复杂度问题。
- 不变量错误。
- 实现细节错误。

#### 18.2.4 RAG Grounding Eval

评估 AI 回复是否基于检索到的教练知识，是否引用了不该使用的 solution 内容。

### 18.3 Trace 记录

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

### 18.4 可视化展示

在开发模式或管理页中展示：

- 当前 LangGraph 节点。
- 当前 hint level。
- 本次检索到的知识片段。
- 本次调用的工具。
- 本次输出是否触发泄题风险。
- 本次耗时和 token 消耗。

这可以作为项目演示时的重要亮点。

------

## 19. 安全与合规

### 19.1 题库内容合规

- 不把第三方完整题面和题解提交进自己的公开仓库。
- 本地初始化时从数据源同步。
- 数据库记录 source_repo、source_path、source_commit 和 content_hash。
- 对外展示时保留 LeetCode 原题链接。
- 不抓取隐藏测试用例。
- 不自动提交 LeetCode。

### 19.2 代码执行安全

- 用户代码必须在沙箱中执行。
- 限制执行时间。
- 限制内存。
- 禁止网络访问。
- 禁止危险文件操作。
- 捕获异常并返回结构化结果。

### 19.3 AI 输出安全

- 对 AI 输出做 hint level 检查。
- 对低层级提示做泄题检测。
- 对 solution_md 做上下文隔离。
- 对 raw_tutorial_chunk 做 hint level 过滤，低提示层级只允许使用抽象后的教练卡片。
- 高风险输出进入降级策略：改为追问或更抽象提示。

### 19.4 本地教程语料处理

本地教程语料用于个人知识库增强，不作为公开内容分发。

处理要求：

- 原始文件保留在本地目录，不提交到公开仓库。
- 数据库记录 source_name、source_path、source_locator 和 content_hash。
- 派生教练卡片保留 parent_doc_id，便于追溯来源。
- 进入 prompt 前按 hint level、knowledge_type 和 has_full_solution 做过滤。
- 默认不在低提示层级引用原始教程中的完整例题、完整代码或完整题解。

------

## 20. 非功能需求

### 20.1 性能

- 题库列表查询响应时间小于 500ms。
- 单次 AI 回复首包时间目标小于 3s。
- 代码运行默认超时时间 2s～5s。
- RAG 检索目标小于 1s。

### 20.2 可恢复性

- 用户刷新页面后，可以恢复当前做题进度。
- AI 对话状态可通过 thread_id 恢复。
- LangGraph 每个关键节点都应 checkpoint。

### 20.3 可观测性

- 每次 Agent 调用都记录 trace。
- 每次 RAG 检索都记录 retrieval_trace。
- 每次工具调用都记录输入摘要、输出摘要、耗时和错误。

### 20.4 可扩展性

- 代码运行语言后续可以从 Python 扩展到 Java、C++。
- 题库数据源后续可以支持多数据源。
- RAG 知识库可以持续补充。
- 用户画像可以从规则更新升级为模型辅助更新。

------

## 21. 成功标准

第一版跑通后，用户应该能完成：

1. 浏览题库。
2. 打开一道题并看到中文 Markdown 题面。
3. 和 AI 教练围绕这道题进行启发式对话。
4. AI 能判断用户当前卡点。
5. AI 能根据 hint level 控制提示粒度。
6. 用户能在系统内写 Python 代码。
7. AI 能 review 用户代码。
8. 系统能运行基础样例并返回结构化结果。
9. 用户能跳转 LeetCode 提交。
10. 用户能回填提交结果。
11. AI 能基于提交结果进行复盘。
12. 系统能记录用户薄弱点、提示使用情况和题目进度。
13. 系统能展示一次 Agent 执行 trace。
14. 系统能从本地教程语料中检索算法概念或派生教练卡片。

### 21.1 可量化指标

| 指标               | 目标                               |
| ------------------ | ---------------------------------- |
| 低层级泄题率       | Level 0-2 不出现完整解法           |
| 复盘生成率         | 完成训练后 100% 生成复盘           |
| 代码 review 可用率 | 能指出至少一个有效问题或确认正确性 |
| 用户画像更新率     | 完成训练后 100% 生成 profile_delta |
| session 可恢复     | 刷新页面后能恢复当前题目和对话状态 |
| trace 完整率       | 每次 AI 回复都有对应 trace         |
| RAG 命中可解释性   | 每次 RAG 回复都能追溯到 doc_id 或 chunk_id |

------

## 22. 里程碑规划

### Milestone 1：题库与基础 Web 工作台

目标：完成基本做题界面。

任务：

- 题库初始化。
- Markdown 题面解析。
- 题库列表页。
- 做题工作台。
- Python 编辑器。
- LeetCode 原题跳转。

### Milestone 2：基础 AI 教练闭环

目标：AI 能围绕题目对话，但还不接复杂 RAG 和工具。

任务：

- LangChain LLM 调用。
- 教练 prompt。
- 结构化输出。
- hint level 控制。
- 两种训练模式。
- practice_session 和 practice_event 记录。

### Milestone 3：LangGraph 状态机

目标：把刷题过程建模为可恢复状态机。

任务：

- Graph state 设计。
- 节点实现。
- checkpoint。
- interrupt 等待用户输入。
- session 恢复。

### Milestone 4：RAG 教练知识库

目标：引入本地教程语料、派生教练知识和题目教练卡片。

任务：

- knowledge_doc 表。
- knowledge_chunk 表。
- 本地 Markdown / HTML / PDF / EPUB / txt 文件导入。
- 教程内容清洗、章节解析和语义切块。
- chunk metadata 标注。
- 派生 concept_card / pattern_card / invariant_card / common_bug_card。
- embedding 生成。
- 向量检索。
- hint level 权限过滤。
- retrieval_trace 记录。

### Milestone 5：代码执行与错误归因

目标：形成代码反馈闭环。

任务：

- Python 沙箱执行。
- 测试用例生成。
- 静态代码分析。
- 错误归因。
- CodeReviewResult 结构化输出。

### Milestone 6：复盘、画像和推荐

目标：训练结果沉淀为用户画像。

任务：

- SessionSummary。
- user_skill_profile。
- profile_delta。
- 简单下一题推荐。
- 用户历史训练记录。

### Milestone 7：评估与可观测性

目标：证明系统不是普通 ChatGPT 套壳。

任务：

- agent_trace。
- Hint Leakage Eval。
- Diagnosis Eval。
- Review Eval。
- 管理页展示 trace。

------

## 23. 技术选型建议

### 23.1 前端

- React / Next.js。
- Monaco Editor 作为代码编辑器。
- Markdown 渲染组件。
- SSE 或 WebSocket 接收 AI 流式输出。

### 23.2 后端

- Python FastAPI。
- LangChain。
- LangGraph。
- SQLAlchemy。
- PostgreSQL。

### 23.3 RAG

第一版可选：

- PostgreSQL + pgvector。
- 或 Chroma / Qdrant。

建议优先使用 pgvector，方便和业务数据放在一起，降低部署复杂度。

本地教程语料处理：

- Markdown / txt：优先直接解析。
- HTML：保留标题层级、正文、列表和代码块，清理导航与重复内容。
- PDF / EPUB：第一版可先支持基础文本抽取，后续再优化目录识别和公式保留。
- 长文档切块时优先按标题和语义段落切分，再做 token 长度控制。

### 23.4 代码执行

第一版：

- 独立 Python 子进程 + 超时控制。

更安全版本：

- Docker sandbox。
- 禁止网络。
- 限制 CPU / 内存。

### 23.5 可观测性

第一版：

- 自研 agent_trace 表。
- 管理页展示 trace。

后续：

- 接入 LangSmith 或 OpenTelemetry。

------

## 24. 主要风险与应对

### 24.1 AI 提前泄露答案

风险：破坏产品定位。

应对：

- solution_md 不默认进入上下文。
- RAG 知识按 hint level 权限过滤。
- AI 输出后做泄题检测。
- 低层级提示只允许追问或抽象方向。

### 24.2 RAG 变成题解检索

风险：项目退化为“题解问答”。

应对：

- 知识库以 coach card 和 pattern card 为核心。
- 原始教程语料只作为知识底座，默认先抽取成派生教练卡片再使用。
- 完整题解只在复盘阶段或 Level 5 后可用。
- 检索阶段过滤 raw_tutorial_chunk 中的完整代码、完整例题和超过当前 hint level 的内容。
- retrieval_trace 记录每次使用了哪些 chunk。

### 24.3 本地教程语料噪声影响检索质量

风险：热门教程来源多、风格不同，直接入库后可能出现重复、过长、上下文断裂或检索命中不准。

应对：

- 导入时清洗目录、页眉页脚、广告、重复段落和无关导航。
- 优先按章节、标题和算法概念切块。
- 对同一算法模式的多来源内容做合并去重。
- 检索时先查派生教练卡片，再按需回查原始教程 chunk。
- 在 retrieval_trace 中记录 filtered_out_chunk_ids，方便调试召回质量。

### 24.4 代码运行安全

风险：用户代码执行危险操作。

应对：

- 沙箱运行。
- 限制权限。
- 限制资源。
- 捕获异常。

### 24.5 项目范围过大

风险：第一版做不完。

应对：

- 第一版只支持 Python。
- 第一版只做基础样例运行，不做完整 OJ。
- 本地教程导入第一版只要求跑通少量高质量资料，不追求全量自动化清洗。
- 派生教练卡片第一版可以半自动生成，必要时人工修正。
- 推荐算法先用规则。
- 题库可全量导入，但演示题集控制在 20～50 题。

### 24.6 普通 ChatGPT 也能做到类似效果

风险：项目差异化不足。

应对：

- 强调状态机。
- 强调本地教程语料沉淀出的可追溯教练知识。
- 强调 hint level 控制。
- 强调代码运行工具。
- 强调用户画像。
- 强调 trace 和 eval。
- 展示同一道题从卡点诊断到复盘的完整闭环。

------

## 25. 项目亮点总结

本项目不是普通的 LeetCode 刷题网站，也不是简单的 ChatGPT 套壳。

核心亮点包括：

1. **LangGraph 状态机**：将刷题过程建模为可恢复、可观测、可中断的学习流程。
2. **本地教程增强 RAG**：把热门算法教程沉淀为可追溯的概念卡片、模式卡片、常见错误卡片和题目教练卡片，而不是直接检索完整答案。
3. **分层提示控制**：通过 hint level 控制 AI 暴露信息的粒度，避免用户直接看答案。
4. **工具调用闭环**：通过代码执行、测试用例生成、错误归因和代码 review，把 AI 对话变成可反馈的训练过程。
5. **长期学习画像**：记录用户在题型、边界条件、实现细节上的薄弱点。
6. **评估与可观测性**：通过 trace 和 eval 证明 Agent 行为可控、可分析、可优化。

最终主线：

> 用完整中文题库和本地算法教程做内容底座，用 LangGraph 做刷题教练状态机，用 RAG 和工具系统增强教练能力，用用户画像沉淀训练结果，把“看答案”变成“被引导着独立想出来”。
