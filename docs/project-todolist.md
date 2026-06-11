# 项目进度 Todolist

本文档用于从 PRD 反向追踪 Agentic Coding Learning Coach 的总体进度、当前进度和下一步任务。产品范围以 `docs/prd/prd.md` 为准；工程边界以 `docs/architecture/foundation.md` 和实际代码为准。

## 使用规则

- 状态：`未开始`、`进行中`、`已完成`、`阻塞`。
- 优先级：`P0` 表示当前 MVP 闭环必需，`P1` 表示当前 MVP 增强或演示亮点，`P2` 表示后续扩展。
- 当前任务只标一个主线，避免同时推进太多方向。
- 每完成一个任务，应更新状态、完成说明、实际完成日期和验证命令。
- 如果实现结果和 PRD 或架构文档不一致，需要同步更新对应文档。

## 当前进度摘要

| 项目 | 当前状态 |
| --- | --- |
| 当前阶段 | 极简 MVP 重置 |
| 当前主线任务 | 收敛核心训练闭环，移除未成熟扩展能力 |
| 当前任务状态 | 代码与文档正在对齐 |
| 已保留基础能力 | 全栈工程基座、题库 seed、题库表、题库 API、题库列表、工作台题面读取、本地注册登录、用户级 OpenAI API 资产池配置、LLM 目标校准、当前学习计划、统一 LLM Run 流式体验层、手写 Agent loop 内核、计划题训练会话、Chat-first 工作台、自动代码尝试记录、LeetCode AC 动作、聊天式非 AC 反馈识别、复盘读取页、基础画像沉淀和规则化下一题建议 |
| 已移出当前主线 | RAG、Trace 页面、学习仪表盘、备份恢复、code-runner、画像驱动计划补强、学习计划历史/版本 UI |
| 下一步建议 | 先把目标校准 -> 当前学习计划 -> 工作台 -> AC/非 AC 反馈 -> 单题复盘的稳定性和 eval 覆盖做扎实，再决定恢复哪一个 AI 扩展能力。 |
| 第一版闭环状态 | 核心闭环保留，扩展能力降级为后续演进。 |

## 总体阶段进度

| 阶段 | 名称 | 状态 | 包含任务 | 阶段完成标准 |
| --- | --- | --- | --- | --- |
| 阶段 0 | 工程与题库基座 | 已完成 | B0、B1 | 本地全栈可运行，题库数据可导入、查询和展示 |
| 阶段 1 | 本地用户与模型资产基础 | 已完成 | T0 | 用户可注册登录，并配置自己的 OpenAI API 资产池 |
| 阶段 2 | 学习入口与训练状态底座 | 已完成 | T1、T2.5、T2 | 用户可基于 LLM 草稿确认训练目标和计划，并在可恢复的训练会话中做题 |
| 阶段 3 | 基础反馈闭环 | 已完成 | T3、T5、T7-core | AI 可分层提示和 review，用户可通过 LeetCode AC 动作、聊天式非 AC 反馈识别获得错因归因和单题复盘 |
| 阶段 4 | 极简 MVP 收口 | 进行中 | T10-lite | 移除未成熟扩展能力，保持核心训练闭环可运行、可测试、可继续叠加 |
| 阶段 5 | 后续 AI 能力演进 | 未开始 | T6、T8、T9、T11、T12 | 在核心闭环稳定后逐项恢复 RAG、Trace、仪表盘、计划补强、code-runner 等能力 |

## 任务进度清单

### B0：全栈工程基座

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 已完成 |
| 完成依据 | `docs/architecture/foundation.md`、`docs/superpowers/plans/2026-05-19-project-foundation.md` |
| 主要交付 | FastAPI、Vite React、PostgreSQL、Docker Compose、Makefile、smoke test |

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
| 主要交付 | 本地注册登录、用户 session、OpenAI API 资产加密保存、测试连接、首选模型资产和粘性路由 |
| 完成日期 | 2026-05-19 |

**验证命令**

- `uv run pytest backend/tests/test_auth_api.py backend/tests/test_llm_credentials_api.py backend/tests/test_llm_credential_routing.py backend/tests/test_credential_crypto.py -q`
- `cd frontend && corepack pnpm test -- ApiKeySettingsPage.test.tsx App.test.tsx`

### T1：首访目标校准与当前学习计划

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 已完成，当前 MVP 只保留当前 active 计划入口 |
| 前置任务 | T0、B1 |
| 主要交付 | 结构化目标校准、LLM 追问、计划草稿生成与校验、用户确认、当前学习计划页 |
| 当前收口 | 学习计划历史页、计划列表页、版本切换 UI 和用户触发的调整草稿已移出当前 MVP |

**验证命令**

- `uv run pytest backend/tests/test_learning_plan_validator.py backend/tests/test_learning_plan_service.py backend/tests/test_learning_llm_generation.py backend/tests/test_learning_api.py -q`
- `cd frontend && corepack pnpm test -- GoalCalibrationPage.test.tsx StudyPlanPage.test.tsx App.test.tsx`

### T2.5：统一 LLM Run 流式体验层

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 已完成 |
| 前置任务 | T1、T0 |
| 主要交付 | LLM Run 状态表、SSE 事件协议、停止生成、OpenAI Responses 流式 provider、目标校准和计划生成流式体验 |

**验证命令**

- `uv run pytest backend/tests/test_llm_run_model.py backend/tests/test_llm_run_events.py backend/tests/test_llm_run_service.py backend/tests/test_llm_runs_api.py backend/tests/test_openai_responses_provider.py backend/tests/test_learning_flows.py -q`
- `cd frontend && corepack pnpm test -- useLlmRun.test.tsx LlmStreamingPanel.test.tsx GoalCalibrationPage.test.tsx`

### T2：训练会话与工作台状态持久化

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 已完成 |
| 前置任务 | T1、T2.5 |
| 主要交付 | `practice_session`、`practice_event`、`submission_feedback`、工作台状态恢复 |

### T3：基础 AI 教练闭环

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 已完成 |
| 前置任务 | T2 |
| 主要交付 | LLM 调用、教练 prompt、结构化输出、hint level 控制、入门引导和独立训练模式 |

### T4：手写 Agent loop 与会话恢复

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 已完成，当前为极简 `CoachLoop` |
| 前置任务 | T2、T3 |
| 主要交付 | loop state、节点函数、`thread_id`、自然中断等价机制、session 恢复 |
| 当前收口 | `retrieve_supporting_context` 和 RAG 上下文已移出当前 MVP |

### T5：LeetCode AC 动作、聊天式非 AC 反馈识别与错因归因

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 已完成 |
| 前置任务 | T2 |
| 主要交付 | LeetCode 已 AC 入口、聊天式非 AC 反馈识别、结果状态管理、AI 错因归因、后续引导 |

### T7-core：复盘、用户画像和下一题建议

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 已完成，仪表盘页面已移出当前 MVP |
| 前置任务 | T1、T2、T3、T5 |
| 主要交付 | `session_summary`、`profile_delta`、`user_profile_snapshot`、规则化下一题推荐、复盘页 API 和页面 |
| 当前收口 | 学习仪表盘 API 内部服务可保留，但公开 API 和前端页面不属于当前 MVP |

### T10-lite：极简 MVP 收口

| 字段 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 状态 | 进行中 |
| 前置任务 | T0-T7-core |
| 主要交付 | 移除未成熟功能入口、同步工程边界、跑通验证 |

**待办**

- [x] 移除 RAG 运行时、模型、迁移、CLI、配置和工作台上下文接入。
- [x] 移除 Trace API、Trace 前端页面和相关服务。
- [x] 移除备份恢复 API、前端页面、环境变量和后端镜像 PostgreSQL client 依赖。
- [x] 移除 code-runner Dockerfile、Compose 服务和 smoke 检查。
- [x] 移除学习仪表盘前端入口和公开 API。
- [x] 移除画像驱动计划补强 flow、prompt、API 和前端抽屉。
- [x] 移除学习计划历史/版本 UI 和公开 API。
- [x] 保留题库完整能力。
- [ ] 完成后端、前端和 Compose 验证。

**验证命令**

- `uv run pytest -q`
- `cd frontend && corepack pnpm test`
- `uv run ruff check .`
- `uv run mypy backend`
- `cd frontend && corepack pnpm lint`
- `cd frontend && corepack pnpm build`
- `docker compose -f infra/compose/docker-compose.dev.yml config`

## 后续演进池

### T6：RAG 教练知识库

| 字段 | 内容 |
| --- | --- |
| 优先级 | P2 |
| 状态 | 暂停，已从当前 MVP 移出 |
| 恢复条件 | 核心工作台对话稳定、评估集足够覆盖提示泄露和代码 review，再引入语料、embedding、检索和 grounding 评估 |

### T8：轻量面试模拟模式

| 字段 | 内容 |
| --- | --- |
| 优先级 | P2 |
| 状态 | 未开始，待产品形态澄清 |

### T9：Trace、Eval 与可观测性

| 字段 | 内容 |
| --- | --- |
| 优先级 | P2 |
| 状态 | Trace 页面已移出当前 MVP；规则化 Eval runner 保留 Hint Leakage、Diagnosis、Code Review 三类 |

### T11：画像驱动计划补强

| 字段 | 内容 |
| --- | --- |
| 优先级 | P2 |
| 状态 | 暂停，已从当前 MVP 移出 |

### T12：本地 code-runner 和工具层

| 字段 | 内容 |
| --- | --- |
| 优先级 | P2 |
| 状态 | 暂停，已从当前 MVP 移出 |
| 恢复条件 | 明确安全隔离、资源限制、语言范围和前后端协议后再重新设计 |
