# 项目进度 Todolist

本文档用于从 PRD 反向追踪 Agentic Coding Learning Coach 的总体进度、当前进度和下一步任务。产品范围以 `docs/prd/prd.md` 为准；工程边界以 `docs/architecture/foundation.md` 和实际代码为准。

## 使用规则

- 状态：`未开始`、`进行中`、`已完成`、`阻塞`。
- 优先级：`P0` 表示第一版闭环必需，`P1` 表示第一版增强或演示亮点，`P2` 表示后续扩展。
- 当前任务只标一个主线，避免同时推进太多方向。
- 每完成一个任务，应更新状态、完成说明、实际完成日期和验证命令。
- 如果实现结果和 PRD 或架构文档不一致，需要同步更新对应文档。

## 当前进度摘要

| 项目 | 当前状态 |
| --- | --- |
| 当前阶段 | 阶段 1：本地用户与模型资产基础 |
| 当前主线任务 | T0：本地用户注册登录与 OpenAI API 资产 |
| 当前任务状态 | 未开始 |
| 已完成基础能力 | 全栈工程基座、题库 seed、题库表、题库 API、题库列表、工作台题面读取 |
| 下一步建议 | 先完成 T0，再把 T1 改为 LLM 目标草稿生成与用户确认；T1/T2 完成后进入基础 AI 教练和代码运行闭环 |
| 第一版闭环状态 | 未闭环。当前只有题库与静态工作台，尚缺登录、用户级 API 资产、目标校准、训练会话、AI 教练、代码运行、复盘画像和推荐 |

## 总体阶段进度

| 阶段 | 名称 | 状态 | 进度 | 包含任务 | 阶段完成标准 |
| --- | --- | --- | --- | --- | --- |
| 阶段 0 | 工程与题库基座 | 已完成 | 100% | B0、B1 | 本地全栈可运行，题库数据可导入、查询和展示 |
| 阶段 1 | 本地用户与模型资产基础 | 未开始 | 0% | T0 | 用户可注册登录，并配置自己的 OpenAI API 资产 |
| 阶段 2 | 学习入口与训练状态底座 | 未开始 | 0% | T1、T2 | 用户可基于 LLM 草稿确认训练目标和计划，并在可恢复的训练会话中做题 |
| 阶段 3 | 基础反馈闭环 | 未开始 | 0% | T3、T5 | AI 可分层提示和 review，系统可运行 Python 代码并返回结构化结果 |
| 阶段 4 | Agent 状态机与知识增强 | 未开始 | 0% | T4、T6 | LangGraph 可恢复状态机接入，RAG 教练知识库可检索并受 hint level 控制 |
| 阶段 5 | 复盘画像与学习仪表盘 | 未开始 | 0% | T7 | 完成训练后生成复盘、画像增量、下一题推荐和仪表盘指标 |
| 阶段 6 | 面试模拟与可观测性 | 未开始 | 0% | T8、T9 | 支持轻量面试模拟，Trace 和 Eval 能展示 Agent 行为质量 |
| 阶段 7 | 第一版闭环集成 | 未开始 | 0% | T10 | PRD 第一版学习闭环可端到端跑通，构建和 smoke 验证通过 |

## 当前阶段：阶段 1

阶段 1 的目标是补齐本地用户身份和用户级模型资产。这个阶段完成前，不建议继续实现 LLM 目标生成或 AI 教练，因为后续所有大模型调用都需要知道“当前用户是谁”以及“使用哪个用户自己的 API 资产”。

### 当前任务 T0：本地用户注册登录与 OpenAI API 资产

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 未开始 |
| 前置条件 | B0、B1 已完成 |
| 主要交付 | `app_user`、`auth_session`、`llm_credential`、登录页、注册页、API 资产配置页 |
| 完成后解锁 | T1 LLM 目标校准与学习计划生成 |

**待办**

- [ ] 设计 `app_user`、`auth_session`、`llm_credential` migration 和 SQLAlchemy model。
- [ ] 实现本地注册、登录、退出和当前用户 API。
- [ ] 实现 API key 加密、mask 和覆盖更新。
- [ ] 实现 OpenAI API 资产 CRUD、测试连接和默认资产设置。
- [ ] 实现登录页、注册页和 API 资产配置页。
- [ ] 前端整体风格向 ChatGPT 的安静工作台体验靠拢，但保持本项目独立视觉身份。
- [ ] 增加后端 pytest、前端 Vitest。
- [ ] 按实现结果检查是否需要更新 `docs/prd/prd.md`、`docs/architecture/foundation.md`、`docs/index.md`。

**完成标准**

- 用户可以注册、登录、退出。
- 受保护页面和 API 能识别当前用户。
- 用户可以保存、测试和设置默认 OpenAI API 资产。
- API key 加密落库，前端和 API 不返回明文。
- 验证命令至少包含后端测试、前端测试和必要的构建检查。

## 任务进度清单

### B0：全栈工程基座

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 已完成 |
| 完成依据 | `docs/architecture/foundation.md`、`docs/superpowers/plans/2026-05-19-project-foundation.md` |
| 主要交付 | FastAPI、Vite React、PostgreSQL + pgvector、Docker Compose、Makefile、smoke test |

### B1：题库导入与静态题库浏览

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 已完成 |
| 完成依据 | `docs/superpowers/plans/2026-05-19-problem-ingestion.md` |
| 主要交付 | 题库 seed 准备、题库表、题库 API、前端题库列表和工作台题面读取 |

### T0：本地用户注册登录与 OpenAI API 资产

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 未开始 |
| 前置任务 | B0、B1 |
| 当前阶段 | 阶段 1 |
| 主要交付 | 本地注册登录、用户 session、OpenAI API 资产加密保存、测试连接、默认模型资产 |
| 完成日期 | 未完成 |

**待办**

- [ ] 设计 `app_user`、`auth_session`、`llm_credential`。
- [ ] 实现注册、登录、退出和当前用户 API。
- [ ] 实现 API key 加密存储和 mask 展示。
- [ ] 实现 OpenAI API 资产配置、测试连接和默认资产设置。
- [ ] 实现登录页、注册页和 API 资产设置页。
- [ ] 让前端形成接近 ChatGPT 的安静工作台风格。
- [ ] 增加测试。
- [ ] 完成文档影响评估。

### T1：首访目标校准与学习计划基础

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 未开始 |
| 前置任务 | T0、B1 |
| 当前阶段 | 阶段 2 |
| 主要交付 | 用户情况采集、LLM 目标和计划草稿生成、用户确认、学习计划页 |
| 完成日期 | 未完成 |

**待办**

- [ ] 设计 `user_learning_goal`、`study_plan`、`study_plan_item`。
- [ ] 实现目标校准输入 API。
- [ ] 使用当前用户默认 OpenAI API 资产生成目标和计划草稿。
- [ ] 实现用户确认草稿后落库。
- [ ] 实现学习计划读取、跳过和重排 API。
- [ ] 实现首访目标校准页。
- [ ] 实现学习计划页。
- [ ] 增加测试。
- [ ] 完成文档影响评估。

### T2：训练会话与工作台状态持久化

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 未开始 |
| 前置任务 | T1 |
| 当前阶段 | 阶段 2 |
| 主要交付 | `practice_session`、`practice_event`、`code_snapshot`、`submission_feedback`、工作台状态恢复 |
| 完成日期 | 未完成 |

**待办**

- [ ] 设计 session、event、code snapshot、submission feedback 表。
- [ ] 实现 session 创建、读取、恢复和状态更新 API。
- [ ] 实现 event 记录 API。
- [ ] 实现 code snapshot 保存和读取 API。
- [ ] 工作台接入 session 创建和恢复。
- [ ] 工作台展示训练模式、提示档位、运行结果区和提交回填入口。
- [ ] 增加测试。
- [ ] 完成文档影响评估。

### T3：基础 AI 教练闭环

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 未开始 |
| 前置任务 | T2 |
| 当前阶段 | 阶段 2 |
| 主要交付 | LLM 调用、教练 prompt、结构化输出、hint level 控制、入门引导和独立训练模式 |
| 完成日期 | 未完成 |

**待办**

- [ ] 增加 LLM 配置、模型名称、超时和 API key 读取。
- [ ] 定义 prompt 版本和教练原则。
- [ ] 实现 `StuckPointDiagnosis`、`CoachAction`、`CodeReviewResult` schema。
- [ ] 实现 hint level 到用户可见档位的映射。
- [ ] 实现训练模式下的提示升级和降级规则。
- [ ] 实现 coach API。
- [ ] 前端工作台接入 AI 教练对话。
- [ ] 增加低层级泄题测试和结构化输出测试。

### T4：LangGraph 状态机与会话恢复

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 未开始 |
| 前置任务 | T2、T3 |
| 当前阶段 | 阶段 3 |
| 主要交付 | Graph State、节点、checkpoint、interrupt、session 恢复 |
| 完成日期 | 未完成 |

**待办**

- [ ] 定义 Graph State。
- [ ] 实现核心节点：题目上下文、目标计划上下文、卡点诊断、动作决策、回复生成。
- [ ] 接入 checkpoint 和 `thread_id`。
- [ ] 实现 `WaitUserInput` interrupt。
- [ ] 把 coach API 切换为图执行入口。
- [ ] 实现 session 恢复和状态重放。
- [ ] 增加节点级测试和最小端到端测试。

### T5：Python 代码运行与错误归因

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 未开始 |
| 前置任务 | T2 |
| 当前阶段 | 阶段 2 |
| 主要交付 | code-runner 调用协议、运行 API、测试用例生成、静态分析、错误归因 |
| 完成日期 | 未完成 |

**待办**

- [ ] 定义后端到 code-runner 的输入/输出协议。
- [ ] 实现 Python 代码执行客户端。
- [ ] 实现基础测试用例生成。
- [ ] 实现静态分析。
- [ ] 实现 `classify_error_tool`。
- [ ] 增加运行代码 API，并记录工具结果。
- [ ] 前端工作台接入运行按钮和结果展示。
- [ ] 增加 sandbox smoke test。

### T6：RAG 教练知识库

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 未开始 |
| 前置任务 | B0；接入教练上下文依赖 T3、T4 |
| 当前阶段 | 阶段 3 |
| 主要交付 | `knowledge_doc`、`knowledge_chunk`、语料导入、embedding、检索、hint 过滤、`retrieval_trace` |
| 完成日期 | 未完成 |

**待办**

- [ ] 设计 `knowledge_doc`、`knowledge_chunk`。
- [ ] 设计本地语料 source manifest 格式。
- [ ] 实现 Markdown/txt 第一批导入。
- [ ] 实现清洗、章节解析、语义切块和 metadata 标注。
- [ ] 实现派生卡片写入。
- [ ] 接入 embedding 和 pgvector 检索。
- [ ] 实现 hint level、knowledge_type、has_full_solution 过滤。
- [ ] 实现 retrieval API 和 `retrieval_trace` 记录。
- [ ] 将检索结果接入教练上下文。

### T7：复盘、用户画像、推荐和仪表盘

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 未开始 |
| 前置任务 | T1、T2、T3、T5 |
| 当前阶段 | 阶段 4 |
| 主要交付 | `SessionSummary`、`profile_delta`、`user_skill_profile`、规则推荐、仪表盘 |
| 完成日期 | 未完成 |

**待办**

- [ ] 设计 `user_skill_profile` 和必要的 summary 存储结构。
- [ ] 实现 `SessionSummary` 生成与保存。
- [ ] 实现 `profile_delta` 生成和合并规则。
- [ ] 实现规则化下一题推荐工具。
- [ ] 实现复盘页 API 和页面。
- [ ] 实现学习仪表盘 API。
- [ ] 实现仪表盘页面。
- [ ] 增加推荐可解释性和画像更新测试。

### T8：轻量面试模拟模式

| 字段 | 内容 |
| --- | --- |
| 优先级 | P1 |
| 状态 | 未开始 |
| 前置任务 | T2、T3、T5；画像沉淀依赖 T7 |
| 当前阶段 | 阶段 5 |
| 主要交付 | 倒计时、面试官追问、评分工具、`MockInterviewSummary` |
| 完成日期 | 未完成 |

**待办**

- [ ] 扩展 session training_mode 为 `mock_interview`。
- [ ] 实现 30-45 分钟倒计时和阶段推进。
- [ ] 实现面试官式追问 prompt。
- [ ] 实现 `score_mock_interview_tool`。
- [ ] 设计并保存 `mock_interview_summary`。
- [ ] 将面试表现沉淀到用户画像。
- [ ] 前端增加面试模拟入口和结果展示。

### T9：Trace、Eval 与可观测性

| 字段 | 内容 |
| --- | --- |
| 优先级 | P1 |
| 状态 | 未开始 |
| 前置任务 | T3；完整闭环依赖 T4、T5、T6 |
| 当前阶段 | 阶段 5 |
| 主要交付 | `agent_trace` 接入、Trace 页、Hint Leakage / Diagnosis / Review / RAG Grounding Eval |
| 完成日期 | 未完成 |

**待办**

- [ ] 完善 `agent_trace` 写入。
- [ ] 前端 Trace 页读取真实 trace 数据。
- [ ] 实现 Hint Leakage Eval 样例和 runner。
- [ ] 实现 Diagnosis Eval 样例和 runner。
- [ ] 实现 Review Eval 样例和 runner。
- [ ] 实现 RAG Grounding Eval 样例和 runner。
- [ ] 将 eval 命令加入 Makefile 或独立脚本。

### T10：第一版闭环集成与发布校验

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 未开始 |
| 前置任务 | T1-T7；演示版可选 T8-T9 |
| 当前阶段 | 阶段 6 |
| 主要交付 | 端到端场景、smoke/build 更新、文档回填 |
| 完成日期 | 未完成 |

**待办**

- [ ] 编写端到端演示路径：目标校准 -> 学习计划 -> 工作台 -> AI 教练 -> 运行代码 -> 提交回填 -> 复盘 -> 画像 -> 下一题推荐。
- [ ] 更新 smoke test 覆盖关键 API。
- [ ] 更新 `make build` / `make smoke` / 必要的 eval 命令文档。
- [ ] 回填 `docs/architecture/foundation.md` 的已实现模块边界。
- [ ] 回填 `docs/dev-setup.md` 的新增环境变量和启动步骤。
- [ ] 对照 PRD 成功标准逐项打勾。

## 阶段推进顺序

1. 阶段 1：完成 T1 和 T2，建立目标、计划、session、event、code snapshot 的数据底座。
2. 阶段 2：完成 T3 和 T5，跑通基础 AI 教练和 Python 代码运行反馈。
3. 阶段 3：完成 T4 和 T6，把基础流程升级为 LangGraph 状态机，并接入 RAG 教练知识。
4. 阶段 4：完成 T7，让训练结果进入复盘、画像、推荐和仪表盘。
5. 阶段 5：完成 T8 和 T9，补齐面试模拟、Trace 和 Eval。
6. 阶段 6：完成 T10，跑通第一版端到端学习闭环并更新验证流程。
