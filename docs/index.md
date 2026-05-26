# 项目目录索引

本文档说明仓库主要目录和模块职责。更具体的架构、Docker、命令和产品设计说明见对应专题文档。

## 使用方式

修改代码前，先根据本索引确认相关目录和专题文档。修改代码后，按“代码变更后的文档维护映射”检查是否需要反向维护文档。

如果代码实现与文档描述发生冲突，应先明确冲突来源，再决定是调整代码、更新文档，还是两者都调整。

## 目录职责

- `backend/app/main.py`：FastAPI 应用工厂和路由注册。
- `backend/app/api/`：HTTP API 路由，当前包含健康检查、数据库健康检查、题库 API、本地认证 API、用户级 LLM API 资产 API、统一 LLM Run 流式 API、目标校准与学习计划 API、计划题训练工作台 API、最小学习仪表盘 API 和 Agent Trace API。
- `backend/app/core/`：配置和基础设施入口，当前使用 Pydantic Settings 读取 `.env`，包含数据库、session cookie 和 API key 加密配置。
- `backend/app/db/`：SQLAlchemy async engine、session、数据库健康检查和 Alembic migration。
- `backend/app/models/`：SQLAlchemy 模型，当前包含题目、题目分类、题目分类关系、本地用户、登录 session、LLM API 资产、LLM Run、Agent Trace、目标校准草稿、学习计划、计划版本、阶段、计划项、变更日志、训练会话、训练事件、代码快照、LeetCode 回填、教练回合、单题复盘、画像快照和画像增量。
- `backend/app/schemas/`：Pydantic 请求和响应模型，当前包含题库、认证、LLM API 资产、LLM Run、目标校准、学习计划和训练工作台相关请求响应。
- `backend/app/services/`：业务服务层，当前包含题库查询、题库 seed 导入、认证 session、API key 加密、LLM API 资产管理、粘性路由、OpenAI 连接测试、统一 LLM Run 状态与 SSE 事件、OpenAI Responses 流式 provider、目标校准/计划生成 flow、计划草稿校验、学习计划生命周期服务、训练会话服务、画像 Provider/合并服务、规则化下一题推荐、Agent Trace 写入、教练状态守卫和教练 run handler。
- `backend/app/agents/`：LangGraph / Agent 编排代码目录，当前包含非 RAG `CoachGraph` 状态机，用于承载可恢复教练状态、`thread_id`、节点摘要和 `rag_deferred` 检索占位。
- `backend/app/evals/`：本地规则化 AI Coach eval runner，当前覆盖 Hint Leakage、Diagnosis、Code Review；RAG Grounding 因 T6/RAG 延后仅报告 `deferred`。
- `backend/app/rag/`：后续知识导入、切块、embedding 和检索代码目录。
- `backend/app/tools/`：后续代码执行、静态分析、错误归因等工具客户端目录。
- `backend/tests/`：后端基座测试。
- `frontend/`：Vite React 前端，使用 Ant Design、React Router、TanStack Query 和 Monaco Editor。
- `frontend/src/pages/`：当前 SPA 页面，包括登录、注册、API 设置、题库、目标校准、学习计划、学习计划历史、计划题训练工作台、复盘、学习仪表盘和 Trace。
- `frontend/src/routes/`：前端路由、首访重定向和登录态保护。
- `frontend/src/api/`：前端 API client 与后端请求封装，所有业务请求通过后端 API 并携带 HttpOnly session cookie；大模型生成通过 `llmRuns` 创建 run 和订阅 SSE，训练工作台通过 `practice` client 创建/恢复 session、保存消息、代码快照和提交回填。
- `frontend/src/hooks/`：前端通用状态 hook，当前包含 `useLlmRun` 用于管理 LLM Run 创建、SSE 事件、取消和结果状态。
- `frontend/src/components/`：前端通用组件，当前包含 `LlmStreamingPanel` 用于展示大模型流式输出、阶段进度、错误和取消操作。
- `infra/docker/`：后端、前端、code-runner 镜像和 Nginx 配置。
- `infra/compose/`：开发、测试、生产/打包 compose 文件。
- `scripts/`：smoke test、数据库等待、题库 seed 数据准备等自动化脚本。
- `data/sources/`：本地第三方原始题库目录，必须忽略不提交。
- `data/seed/`：本地生成的题库 seed 文件目录，题面数据默认不提交公开仓库。
- `demo/`：LangChain、LangGraph 和 Agent 范式演示代码，主要用于学习和实验，不是当前产品主路径。
- `tests/`：早期 demo 的测试。
- `archive/`：归档数据或材料，修改前需要确认是否属于用户保留内容。

## 相关文档

- `docs/architecture/foundation.md`：项目基座架构和服务边界。
- `docs/architecture/docker.md`：Docker 镜像、Compose 服务和 smoke test。
- `docs/architecture/makefile.md`：根目录 `Makefile` 命令契约。
- `docs/dev-setup.md`：WSL Ubuntu 本地开发环境和常用流程。
- `docs/data-flow.md`：研发按需补充的数据流程备注，用于解释具体页面和后端服务之间的数据写入、返回和关联关系，不作为代码变更后的强维护契约。
- `docs/prd/prd.md`：产品定位、目标用户、核心训练流程、AI Coach 产品边界和 MVP 范围。
- `docs/prd/ai-coach-workbench-prd.md`：做题工作台右侧 AI 教练区专题 PRD，说明按计划题复用聊天框、画像驱动起手提问、训练状态跳转、LeetCode 回填和复盘沉淀。
- `docs/prd/ai-coach-user-profile-prd.md`：面向 AI 教练决策的用户画像专题 PRD，说明画像服务边界、画像指标、画像更新流程、证据追溯和教练策略建议。
- `docs/project-todolist.md`：从 PRD 拆分出的总体阶段、当前进度和后续任务追踪。

## 代码变更后的文档维护映射

| 变更类型 | 需要检查或更新的文档 |
| --- | --- |
| 目录结构、模块职责、工程入口变化 | `docs/index.md` |
| 系统边界、技术选型、运行架构变化 | `docs/architecture/foundation.md` |
| Dockerfile、Compose 服务、端口、volume、环境变量、部署方式变化 | `docs/architecture/docker.md` |
| `Makefile` 目标、脚本、验证命令、开发工作流变化 | `docs/architecture/makefile.md`、必要时 `docs/dev-setup.md` |
| 本地环境、启动步骤、端口说明、常见问题变化 | `docs/dev-setup.md` |
| 产品范围、页面行为、AI Coach 行为、训练模式、里程碑变化 | `docs/prd/prd.md` |
| RAG 语料来源、入库顺序、材料标注方式变化 | `docs/prd/rag-materials.md` |
| 新增功能设计或重要架构决策 | `docs/superpowers/specs/` 下新增或更新对应设计文档 |
| 已按计划实施的多步骤任务 | `docs/superpowers/plans/` 下新增或更新对应实施计划 |
| 只改变内部实现细节，不改变对外契约 | 可以不更新文档，但最终说明不更新原因 |
