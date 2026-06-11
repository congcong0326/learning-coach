# 项目进度 Todolist

本文档用于从 PRD 反向追踪当前 MVP 进度和后续恢复池。产品范围以 `docs/prd/prd.md` 为准；工程边界以 `docs/architecture/foundation.md` 和实际代码为准。

## 当前进度摘要

| 项目 | 当前状态 |
| --- | --- |
| 当前阶段 | 极简 MVP 收口 |
| 当前主线 | 稳定目标校准 -> 当前学习计划 -> 工作台 -> AC/非 AC 反馈 -> 单题复盘 |
| 当前状态 | 核心闭环已保留，文档已按当前代码重写 |
| 已保留能力 | 全栈工程基座、题库 seed、题库 API、题库列表、工作台题面读取、本地注册登录、用户级模型 API 资产池、LLM 目标校准、当前学习计划、统一 LLM Run 流式层、手写 Agent loop、计划题训练会话、Chat-first 工作台、自动代码尝试记录、LeetCode AC 动作、聊天式非 AC 反馈识别、复盘页、基础画像沉淀、规则化下一题建议 |
| 已移出当前主线 | RAG、Trace 页面、学习仪表盘、备份恢复、code-runner、画像驱动计划补强、学习计划历史/版本 UI |
| 下一步建议 | 先扩大核心教练 eval 和端到端回归覆盖，再决定恢复哪一个扩展能力 |

## 阶段进度

| 阶段 | 名称 | 状态 | 完成标准 |
| --- | --- | --- | --- |
| 阶段 0 | 工程与题库基座 | 已完成 | 本地全栈可运行，题库数据可导入、查询和展示 |
| 阶段 1 | 本地用户与模型资产基础 | 已完成 | 用户可注册登录，并配置自己的模型 API 资产池 |
| 阶段 2 | 学习入口与训练状态底座 | 已完成 | 用户可基于 LLM 草稿确认训练目标和计划，并在可恢复训练会话中做题 |
| 阶段 3 | 基础反馈闭环 | 已完成 | AI 可分层提示和 review，用户可通过 LeetCode AC 动作和聊天式非 AC 反馈获得归因与复盘 |
| 阶段 4 | 极简 MVP 收口 | 进行中 | 移除未成熟扩展能力，保持核心训练闭环可运行、可测试、可继续叠加 |
| 阶段 5 | 后续 AI 能力演进 | 未开始 | 核心闭环稳定后逐项恢复 RAG、Trace、仪表盘、计划补强、code-runner 等能力 |

## 已完成主线任务

### B0：全栈工程基座

- 优先级：P0
- 状态：已完成
- 主要交付：FastAPI、Vite React、PostgreSQL、Docker Compose、Makefile、smoke test。

### B1：题库导入与静态题库浏览

- 优先级：P0
- 状态：已完成
- 主要交付：题库 seed 准备、题库表、题库 API、前端题库列表和工作台题面读取。

### T0：本地用户注册登录与模型 API 资产

- 优先级：P0
- 状态：已完成
- 主要交付：本地注册登录、用户 session、模型 API 资产加密保存、测试连接、首选模型资产和粘性路由。

### T1：目标校准与当前学习计划

- 优先级：P0
- 状态：已完成，当前 MVP 只保留当前 active 计划入口。
- 主要交付：结构化目标校准、LLM 追问、计划草稿生成与校验、用户确认、当前学习计划页。
- 当前收口：学习计划历史页、计划列表页、版本切换 UI 和用户触发的调整草稿已移出当前 MVP。

### T2：统一 LLM Run 流式体验层

- 优先级：P0
- 状态：已完成
- 主要交付：LLM Run 状态表、SSE 事件协议、停止生成、OpenAI Responses 流式 provider、目标校准和计划生成流式体验。

### T3：训练会话与工作台状态持久化

- 优先级：P0
- 状态：已完成
- 主要交付：`practice_session`、`practice_event`、`submission_feedback`、工作台状态恢复。

### T4：基础 AI 教练闭环

- 优先级：P0
- 状态：已完成
- 主要交付：LLM 调用、教练 prompt、结构化输出、hint level 控制、入门引导和独立训练模式。

### T5：手写 Agent loop 与会话恢复

- 优先级：P0
- 状态：已完成，当前为极简 `CoachLoop`。
- 主要交付：loop state、节点函数、`thread_id`、session 恢复。
- 当前收口：RAG 上下文和复杂图编排已移出当前 MVP。

### T6：LeetCode AC 动作、聊天式非 AC 反馈识别与错因归因

- 优先级：P0
- 状态：已完成
- 主要交付：LeetCode 已 AC 入口、聊天式非 AC 反馈识别、结果状态管理、AI 错因归因、后续引导。

### T7：复盘、用户画像和下一题建议

- 优先级：P0
- 状态：已完成，仪表盘页面已移出当前 MVP。
- 主要交付：`session_summary`、`profile_delta`、`user_profile_snapshot`、规则化下一题推荐、复盘页 API 和页面。

## 当前收口任务

### T8：极简 MVP 文档与验证收口

- 优先级：P0
- 状态：进行中
- 主要交付：删除过期文档、重写当前文档、跑通基础验证。

待办：

- [x] 移除旧 RAG 专题文档。
- [x] 移除过期数据流长备注。
- [x] 清空已完成/已回退的旧 `superpowers` 计划与规格。
- [x] 重写主线产品、架构、Docker、Makefile 和开发环境文档。
- [ ] 完成后端、前端和 Compose 验证。

建议验证命令：

```bash
uv run pytest -q
cd frontend && corepack pnpm test
uv run ruff check .
uv run mypy backend
cd frontend && corepack pnpm lint
cd frontend && corepack pnpm build
docker compose -f infra/compose/docker-compose.dev.yml config
```

## 后续恢复池

这些能力已移出当前 MVP。恢复时必须先新增当前版本 PRD 或设计文档，不能直接按旧计划实现。

| 能力 | 优先级 | 状态 | 恢复条件 |
| --- | --- | --- | --- |
| RAG 教练知识库 | P2 | 暂停 | 核心工作台对话稳定，eval 足够覆盖提示泄露和代码 review |
| Trace 与研发观测 | P2 | 暂停 | 需要跨 run 调试和评估时，先定义脱敏、存储和展示边界 |
| 学习仪表盘 | P2 | 暂停 | 画像和复盘数据稳定后再做可视化 |
| 画像驱动计划补强 | P2 | 暂停 | 下一题建议和画像合并足够稳定后再做计划级修改 |
| 学习计划历史/版本 UI | P2 | 暂停 | 当前 active 计划体验稳定后再恢复 |
| 本地 code-runner 和工具层 | P2 | 暂停 | 明确安全隔离、资源限制、语言范围和前后端协议 |
| 轻量面试模拟模式 | P2 | 未开始 | 产品形态和评分标准明确后再设计 |
