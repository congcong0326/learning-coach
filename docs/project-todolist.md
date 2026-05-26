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
| 当前阶段 | 阶段 7：第一版闭环集成 |
| 当前主线任务 | T10：端到端收口和验证 |
| 当前任务状态 | 已完成 |
| 已完成基础能力 | 全栈工程基座、题库 seed、题库表、题库 API、题库列表、工作台题面读取、本地注册登录、用户级 OpenAI API 资产池配置、LLM 目标校准、版本化学习计划、统一 LLM Run 流式体验层、计划题训练会话、Chat-first 工作台、自动代码尝试记录、LeetCode AC 动作、聊天式非 AC 反馈识别、复盘读取页、最小学习仪表盘、非 RAG `CoachGraph`、真实 Trace 页和规则化 Eval runner |
| 下一步建议 | 保持 RAG/T6 延后；后续再评估持久化 checkpoint、RAG 教练知识库、更完整画像趋势图和 T8 面试模拟 |
| 第一版闭环状态 | 非 RAG Agent 工程闭环已具备：计划题进入工作台、AI 教练结构化诊断、非 AC 反馈分析、AC 后复盘画像、下一题推荐、Trace 和 Eval 均有实现与测试；RAG/T6 明确 deferred |

## 总体阶段进度

| 阶段 | 名称 | 状态 | 进度 | 包含任务 | 阶段完成标准 |
| --- | --- | --- | --- | --- | --- |
| 阶段 0 | 工程与题库基座 | 已完成 | 100% | B0、B1 | 本地全栈可运行，题库数据可导入、查询和展示 |
| 阶段 1 | 本地用户与模型资产基础 | 已完成 | 100% | T0 | 用户可注册登录，并配置自己的 OpenAI API 资产池 |
| 阶段 2 | 学习入口与训练状态底座 | 已完成 | 100% | T1、T2.5、T2 | 用户可基于 LLM 草稿确认训练目标和计划，并在可恢复的训练会话中做题 |
| 阶段 3 | 基础反馈闭环 | 已完成 | 100% | T3、T5 | AI 可分层提示和 review，用户可通过 LeetCode AC 动作、聊天式非 AC 反馈识别获得错因归因 |
| 阶段 4 | Agent 状态机与知识增强 | 进行中 | 55% | T4、T6 | 非 RAG LangGraph 状态机已接入；RAG 教练知识库延后 |
| 阶段 5 | 复盘画像与学习仪表盘 | 已完成 | 100% | T7 | 完成训练后生成复盘、画像增量、下一题推荐和最小仪表盘指标 |
| 阶段 6 | 面试模拟与可观测性 | 进行中 | 50% | T8、T9 | T9 Trace/Eval 已完成；T8 轻量面试模拟未开始 |
| 阶段 7 | 第一版闭环集成 | 已完成 | 100% | T10 | 非 RAG 第一版学习闭环可端到端跑通，验证命令已通过 |

## 当前阶段：阶段 7

阶段 7 的目标是收口非 RAG 第一版闭环：用户从目标校准和学习计划进入工作台，完成 AI 教练引导、LeetCode AC 动作、聊天式非 AC 反馈识别、复盘、画像、下一题推荐，并用 Trace/Eval 证明 Agent 行为可追踪、可评估。T6/RAG 和 T8/面试模拟不计入本轮非 RAG 收口。

### 当前任务 T10：端到端收口和验证

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 已完成 |
| 前置条件 | T1、T2、T3、T4 非 RAG 部分、T5、T7、T9 已完成 |
| 主要交付 | 端到端演示路径、文档回填、最终验证命令 |
| 完成后解锁 | RAG/T6、持久化 checkpoint、画像趋势图和面试模拟增强 |

**待办**

- [x] 编写端到端演示路径。
- [x] 更新受影响的 PRD、架构、Makefile、dev-setup、索引和实施计划文档。
- [x] 更新 T3、T4、T5、T7、T9、T10 状态，T6 明确 deferred。
- [x] 运行最终后端、前端、类型检查和 eval 验证命令。

**完成标准**

- 非 RAG 第一版学习闭环可按端到端路径演示。
- RAG/T6 未实现，所有相关节点、eval 和文档均标记为 `deferred`。
- 验证命令至少包含后端测试、前端测试、前端类型检查和 eval。

**最近验证命令**

- `uv run ruff check .`
- `uv run mypy backend`
- `uv run pytest backend/tests/test_practice_schema.py backend/tests/test_coach_guard.py backend/tests/test_practice_session_service.py backend/tests/test_learning_flows.py backend/tests/test_coach_graph.py backend/tests/test_agent_trace_service.py backend/tests/test_coach_eval_runner.py backend/tests/test_recommendation_service.py -q`
- `cd frontend && corepack pnpm exec vitest run src/pages/workspace/CoachPanel.test.tsx src/pages/workspace/CodeAttemptDrawer.test.tsx src/pages/ReviewPage.test.tsx src/pages/TracePage.test.tsx src/pages/DashboardPage.test.tsx`
- `cd frontend && corepack pnpm exec tsc -p tsconfig.app.json --noEmit --pretty false`
- `uv run python -m backend.app.evals.coach_eval_runner`
- `make eval`

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
| 状态 | 已完成 |
| 前置任务 | B0、B1 |
| 当前阶段 | 阶段 1 |
| 主要交付 | 本地注册登录、用户 session、OpenAI API 资产加密保存、测试连接、首选模型资产和粘性路由 |
| 完成日期 | 2026-05-19 |

**待办**

- [x] 设计 `app_user`、`auth_session`、`llm_credential`。
- [x] 实现注册、登录、退出和当前用户 API。
- [x] 实现 API key 加密存储和 mask 展示。
- [x] 实现 OpenAI API 资产配置、测试连接、默认/首选资产设置和覆盖更新。
- [x] 实现 API 设置页列表化，新增/编辑使用弹窗。
- [x] 实现 API 资产启用/禁用、首选资产、当前通讯资产和连续失败 3 次后的粘性切换策略。
- [x] 实现登录页、注册页和 API 资产设置页。
- [x] 让前端形成接近 ChatGPT 的安静工作台风格。
- [x] 增加测试。
- [x] 完成文档影响评估。

**验证命令**

- `uv run pytest backend/tests/test_auth_api.py backend/tests/test_llm_credentials_api.py backend/tests/test_llm_credential_routing.py backend/tests/test_credential_crypto.py -q`
- `cd frontend && corepack pnpm test -- ApiKeySettingsPage.test.tsx App.test.tsx`
- `make build`

### T1：首访目标校准与学习计划基础

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 已完成 |
| 前置任务 | T0、B1 |
| 当前阶段 | 阶段 2 |
| 主要交付 | 结构化目标校准、LLM 追问、计划草稿生成与校验、用户确认、多计划/版本化学习计划、学习计划页和历史页 |
| 完成日期 | 2026-05-20 |

**待办**

- [x] 设计 `goal_calibration_draft`、`study_plan`、`study_plan_version`、`study_plan_stage`、`study_plan_item`、`plan_change_log`。
- [x] 实现目标校准输入、追问回答、计划生成、计划确认 API。
- [x] 使用当前用户首选/当前通讯 OpenAI API 资产生成目标和计划草稿。
- [x] 实现本地题库校验和 repair loop，过滤缺失、重复和 paid only 题目。
- [x] 实现用户确认草稿后落库，并保证同一用户唯一 active 计划。
- [x] 实现学习计划读取、跳过、重排、历史计划激活 API。
- [x] 实现用户触发的调整草稿和计划版本激活。
- [x] 实现首访目标校准页。
- [x] 实现学习计划页和计划历史页。
- [x] 增加测试。
- [x] 完成文档影响评估。

**验证命令**

- `uv run pytest backend/tests/test_learning_plan_validator.py backend/tests/test_learning_plan_service.py backend/tests/test_learning_llm_generation.py backend/tests/test_learning_api.py -q`
- `cd frontend && corepack pnpm test -- GoalCalibrationPage.test.tsx StudyPlanPage.test.tsx StudyPlanHistoryPage.test.tsx App.test.tsx`
- `make build`

### T2.5：统一 LLM Run 流式体验层

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 已完成 |
| 前置任务 | T1、T0 |
| 当前阶段 | 阶段 2 |
| 主要交付 | LLM Run 状态表、SSE 事件协议、停止生成、OpenAI Responses 流式 provider、目标校准和计划生成流式体验 |
| 完成日期 | 2026-05-21 |

**待办**

- [x] 设计 `llm_run` 状态表和终态并发保护。
- [x] 实现 LLM Run 创建、状态查询、SSE 订阅和取消 API。
- [x] 实现 `started`、`progress`、`delta`、`result`、`error`、`canceled`、`done` 事件协议。
- [x] 实现 OpenAI Responses 流式 provider。
- [x] 将目标校准、追问回答和学习计划草稿生成迁移到 LLM Run flow。
- [x] 前端目标校准页展示流式输出、阶段进度、失败状态和取消生成入口。
- [x] 保证正式计划草稿只在本地题库校验、repair 和 run 成功提交后展示。
- [x] 增加测试。
- [x] 完成文档影响评估。

**验证命令**

- `uv run pytest backend/tests/test_llm_run_model.py backend/tests/test_llm_run_events.py backend/tests/test_llm_run_service.py backend/tests/test_llm_runs_api.py backend/tests/test_openai_responses_provider.py backend/tests/test_learning_flows.py -q`
- `cd frontend && corepack pnpm test -- useLlmRun.test.tsx LlmStreamingPanel.test.tsx GoalCalibrationPage.test.tsx`
- `cd frontend && corepack pnpm exec tsc -b`
- `make build`

### T2：训练会话与工作台状态持久化

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 已完成 |
| 前置任务 | T1、T2.5 |
| 当前阶段 | 阶段 2 |
| 主要交付 | `practice_session`、`practice_event`、`submission_feedback`、工作台状态恢复 |
| 完成日期 | 2026-05-26 |

**待办**

- [x] 设计 session、event、submission feedback 表。
- [x] 实现 session 创建、读取、恢复和状态更新 API。
- [x] 实现 event 记录 API。
- [x] 工作台接入 session 创建和恢复。
- [x] 工作台展示提示档位、AI 教练对话区、代码尝试记录入口和 LeetCode 已 AC 入口。
- [x] 增加测试。
- [x] 完成文档影响评估。

### T3：基础 AI 教练闭环

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 已完成 |
| 前置任务 | T2 |
| 当前阶段 | 阶段 2 |
| 主要交付 | LLM 调用、教练 prompt、结构化输出、hint level 控制、入门引导和独立训练模式 |
| 完成日期 | 2026-05-26 |

**待办**

- [x] 为 `coach_turn` 增加用户模型资产路由读取和模型名称传递。
- [x] 定义 `coach_turn` 结构化 prompt 版本和教练原则。
- [x] 实现 `StuckPointDiagnosis`、`CoachAction`、`CodeReviewResult` schema。
- [x] 实现 hint level 到用户可见档位的映射。
- [x] 实现训练模式下的提示升级和降级规则。
- [x] 实现 coach API。
- [x] 前端工作台接入 Chat-first AI 教练对话。
- [x] 增加 `coach_turn` 结构化输出和模型资产编排测试。
- [x] 增加低层级泄题测试。

### T4：LangGraph 状态机与会话恢复

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 进行中（非 RAG Agent 范围已完成，T6/RAG 延后） |
| 前置任务 | T2、T3 |
| 当前阶段 | 阶段 3 |
| 主要交付 | Graph State、节点、checkpoint、interrupt、session 恢复 |
| 完成日期 | 非 RAG 部分 2026-05-26；T6/RAG 未完成 |

**待办**

- [x] 定义 Graph State。
- [x] 实现核心节点：题目上下文、目标计划上下文、输入分类、卡点诊断、动作决策、守卫摘要、回复生成、持久化摘要和复盘触发；`retrieve_supporting_context` 暂返回 `rag_deferred`。
- [x] 接入 `thread_id` 并与 `practice_session.thread_id` 对齐；当前使用 LangGraph checkpointer 和 DB session 事实恢复，跨进程持久化 checkpoint 后续增强。
- [x] 实现用户输入自然中断等价机制：用户消息和提交反馈作为下一轮图执行入口；未接独立 `WaitUserInput` 原语。
- [x] 把 `coach_turn` run 接入 `CoachGraph` 执行入口，保持前端 SSE 体验不变。
- [x] 实现 session 恢复和状态重放的等价路径：`practice_session.thread_id`、事件、代码尝试和提交反馈进入图 state。
- [x] 增加节点级测试和 `coach_turn` 图入口测试，覆盖快进、回退、守卫拒绝、非 AC 反馈和复盘触发。

### T5：LeetCode AC 动作、聊天式非 AC 反馈识别与错因归因

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 已完成 |
| 前置任务 | T2 |
| 当前阶段 | 阶段 2 |
| 主要交付 | LeetCode 已 AC 入口、LeetCode AC 动作、聊天式非 AC 反馈识别、结果状态管理、AI 错因归因、后续引导 |
| 完成日期 | 2026-05-26 |

**待办**

- [x] 定义提交结果状态：AC、WA、TLE、RE、CE、UNKNOWN。
- [x] 实现提交结果回填 API，并关联训练会话、题目和计划项。
- [x] 前端工作台接入“LeetCode 已 AC”入口，AC 可不要求运行时间、内存或代码快照。
- [x] 允许用户补充 LeetCode 错误摘要、失败用例摘要或提交备注。
- [x] 将用户思路、粘贴代码和最新提交结果写入 AI 教练上下文，支持错因归因。
- [x] AI 根据聊天中识别出的非 AC 反馈摘要进入提交反馈分析；继续追问、建议修改、要求再次提交的动作集仍需扩大 eval 覆盖。
- [x] 前端工作台移除非 AC 主路径表单，保留聊天式失败反馈主路径。
- [x] 增加提交回填、错因归因和状态流转测试。

### T6：RAG 教练知识库

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 未开始（本轮非 RAG Agent 范围延后） |
| 前置任务 | B0；接入教练上下文依赖 T3、T4 |
| 当前阶段 | 阶段 3 |
| 主要交付 | `knowledge_doc`、`knowledge_chunk`、语料导入、embedding、检索、hint 过滤、`retrieval_trace` |
| 完成日期 | 未完成，RAG/T6 已明确 deferred |

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
| 状态 | 已完成 |
| 前置任务 | T1、T2、T3、T5 |
| 当前阶段 | 阶段 4 |
| 主要交付 | `SessionSummary`、`profile_delta`、`user_skill_profile`、规则推荐、仪表盘 |
| 完成日期 | 2026-05-26 |

**待办**

- [x] 设计 `user_profile_snapshot`、`profile_delta` 和 `SessionSummary` 等价存储结构。
- [x] 实现 `SessionSummary` 生成与保存。
- [x] 实现 `profile_delta` 生成和合并规则。
- [x] 实现规则化下一题推荐工具。
- [x] 实现复盘页 API 和页面。
- [x] 实现学习仪表盘 API。
- [x] 实现仪表盘页面。
- [x] 增加推荐可解释性和画像更新测试。

### T8：轻量面试模拟模式

| 字段 | 内容 |
| --- | --- |
| 优先级 | P1 |
| 状态 | 未开始 |
| 前置任务 | T2、T3；画像沉淀依赖 T7 |
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
| 状态 | 已完成（RAG Grounding 按 T6 延后标记 deferred） |
| 前置任务 | T3；完整闭环依赖 T4、T6、T7 |
| 当前阶段 | 阶段 5 |
| 主要交付 | `agent_trace` 接入、Trace 页、Hint Leakage / Diagnosis / Review / RAG Grounding Eval |
| 完成日期 | 2026-05-26 |

**待办**

- [x] 完善 `agent_trace` 写入。
- [x] 前端 Trace 页读取真实 trace 数据。
- [x] 实现 Hint Leakage Eval 样例和 runner。
- [x] 实现 Diagnosis Eval 样例和 runner。
- [x] 实现 Review Eval 样例和 runner。
- [x] RAG Grounding Eval 按 RAG/T6 延后报告 `deferred`，不接真实检索。
- [x] 将 eval 命令加入 Makefile 或独立脚本。

### T10：第一版闭环集成与发布校验

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 已完成 |
| 前置任务 | T1-T7；演示版可选 T8-T9 |
| 当前阶段 | 阶段 7 |
| 主要交付 | 端到端场景、smoke/build 更新、文档回填 |
| 完成日期 | 2026-05-26 |

**待办**

- [x] 编写端到端演示路径：目标校准 -> 学习计划 -> 工作台 -> AI 教练 -> LeetCode AC 动作、聊天式非 AC 反馈识别 -> 复盘 -> 画像 -> 下一题推荐 -> Trace/Eval。
- [x] 保持 smoke test 作为运行环境健康检查，关键 Agent API 由 pytest/vitest/eval 覆盖；未把需登录的训练 API 放入 shell smoke。
- [x] 更新 `make build` / `make smoke` / 必要的 eval 命令文档。
- [x] 回填 `docs/architecture/foundation.md` 的已实现模块边界。
- [x] 回填 `docs/dev-setup.md` 的新增环境变量和启动步骤。
- [x] 对照 PRD 成功标准逐项打勾。

**端到端演示路径**

1. 用户注册/登录并在 API 设置中配置首选 OpenAI API 资产。
2. 进入目标校准页，填写目标、时间线、每周投入、默认语言和弱项，使用 LLM Run 生成并确认学习计划。
3. 从学习计划页点击计划题进入 `/workspace/items/:itemId`，后端创建或恢复 `practice_session`，并绑定 `thread_id=practice-session-{id}`。
4. 用户在工作台描述思路、卡点或粘贴代码，`coach_turn` 进入非 RAG `CoachGraph`，完成输入分类、卡点诊断、动作决策、守卫和回复持久化。
5. 用户直接在聊天中粘贴 WA/TLE/RE/MLE/CE/Unknown、失败用例、错误摘要或自己的判断；`coach_turn` 在后台抽取非 AC 提交反馈摘要，下一轮 AI 教练进入提交反馈分析。
6. 用户通过“LeetCode 已 AC”记录 AC，触发 `coach_summary`，生成或更新 `session_summary`、`profile_delta` 和 `user_profile_snapshot`。
7. 复盘页展示最终结果、阶段轨迹、主要卡点、最高提示档位、代码/提交错因、复杂度/核心思路、画像变化和下一题建议。
8. 学习仪表盘展示完成题数、常见卡点、平均/最高提示档位和最近画像摘要；下一题推荐的第一问和 review 重点写入画像策略。
9. Trace 页通过 `/api/traces` 查看 LLM Run、Graph 节点、`rag_deferred`、守卫结果和最终回复摘要。
10. 运行 `make eval` 或 `uv run python -m backend.app.evals.coach_eval_runner` 验证 Hint Leakage、Diagnosis、Code Review；RAG Grounding 显示 `deferred`。

## 阶段推进顺序

1. 阶段 1：完成 T1 和 T2，建立目标、计划、session、event、submission feedback 的数据底座。
2. 阶段 2：完成 T3 和 T5，跑通基础 AI 教练和 LeetCode AC 动作、聊天式非 AC 反馈识别。
3. 阶段 3：完成 T4 和 T6，把基础流程升级为 LangGraph 状态机，并接入 RAG 教练知识。
4. 阶段 4：完成 T7，让训练结果进入复盘、画像、推荐和仪表盘。
5. 阶段 5：完成 T8 和 T9，补齐面试模拟、Trace 和 Eval。
6. 阶段 6：完成 T10，跑通第一版端到端学习闭环并更新验证流程。
