# 项目文档索引

本文档是 `docs/` 的入口。修改代码前先从这里确认应该阅读哪些文档；修改代码后按文末映射检查是否需要同步维护文档。

## 当前文档结构

```text
docs/
  index.md
  dev-setup.md
  project-todolist.md
  architecture/
    foundation.md
    docker.md
    makefile.md
  prd/
    prd.md
    ai-coach-workbench-prd.md
    ai-coach-user-profile-prd.md
  superpowers/
    README.md
```

已删除的历史文档包括旧 RAG 专题、数据流长备注和已完成/已回退的 `superpowers` 计划。它们曾记录中间方案，但在本轮重构后不再代表当前代码能力，继续保留会误导实现。

## 当前产品边界

当前项目是本地优先的 Agentic Coding Learning Coach 极简 MVP。主线闭环是：

```text
注册登录
-> 配置用户自己的模型 API 资产
-> 目标校准
-> AI 生成并确认当前学习计划
-> 从计划题进入工作台
-> Chat-first AI 教练追问、提示、代码 review、提交反馈分析
-> 用户用 LeetCode 官网提交并通过 AC 动作结束训练
-> 单题复盘、画像增量和下一题建议
```

当前不属于可运行主线：

- RAG 知识库和向量检索。
- Trace 页面和研发观测面板。
- 数据库备份恢复页面。
- 本地 code-runner 或在线判题。
- 学习仪表盘。
- 画像驱动计划补强。
- 学习计划历史页、计划列表页和版本切换 UI。

如果要恢复这些能力，需要先新增当前版本的 PRD 或设计文档，再实施。

## 目录职责

- `backend/app/main.py`：FastAPI 应用工厂和路由注册。
- `backend/app/api/`：HTTP API 路由，当前包含健康检查、数据库健康检查、认证、模型 API 资产、统一 LLM Run、目标校准/学习计划、训练工作台和题库。
- `backend/app/core/`：配置入口，使用 Pydantic Settings 读取环境变量。
- `backend/app/db/`：SQLAlchemy async engine、session、健康检查和 Alembic migration。
- `backend/app/models/`：SQLAlchemy 模型，覆盖题库、用户、模型资产、LLM Run、学习计划、训练会话、复盘和画像。
- `backend/app/schemas/`：Pydantic 请求和响应模型。
- `backend/app/services/`：业务服务层，包括认证、模型资产路由、LLM Run、学习计划、训练会话、教练守卫、画像、推荐和题库服务。
- `backend/app/services/learning_flows/`：可流式执行的学习业务 flow，包括目标校准、计划生成、教练单轮回复和单题复盘。
- `backend/app/prompts/`：静态大模型提示词资源和 registry。
- `backend/app/agents/`：手写 Agent loop 内核、workflow registry 和 `CoachLoop` 编排。
- `backend/app/evals/`：本地规则化 AI Coach eval runner。
- `backend/app/tools/`：后续工具能力预留目录；当前不接入本地代码执行。
- `backend/tests/`：后端主测试。
- `frontend/`：Vite React TypeScript SPA。
- `frontend/src/pages/`：登录、注册、API 设置、题库、目标校准、学习计划、工作台和复盘页面。
- `frontend/src/routes/`：前端路由、首访重定向和登录态保护。
- `frontend/src/api/`：前端 API client 与后端请求封装。
- `frontend/src/hooks/`：通用状态 hook，当前主要包含 `useLlmRun`。
- `frontend/src/components/`：通用组件，当前主要包含 `LlmStreamingPanel`。
- `infra/docker/`：后端、前端镜像和 Nginx 配置。
- `infra/compose/`：开发、测试和生产/打包 Compose 文件。
- `scripts/`：smoke test、数据库等待和题库 seed 准备脚本。
- `data/sources/`：本地第三方原始题库目录，默认忽略不提交。
- `data/seed/`：本地生成的题库 seed 文件目录，题面数据默认不提交公开仓库。
- `demo/`：早期 Agent 范式演示目录；当前主线不依赖。
- `tests/`：早期 demo 测试目录；当前后端主测试在 `backend/tests/`。
- `archive/`：归档材料，修改前确认是否属于用户保留内容。

## 推荐阅读顺序

- 判断产品目标和 MVP 范围：读 `docs/prd/prd.md`。
- 判断工作台或画像行为：读 `docs/prd/ai-coach-workbench-prd.md`、`docs/prd/ai-coach-user-profile-prd.md`。
- 判断工程边界和模块职责：读 `docs/architecture/foundation.md`，再读实际代码。
- 判断 Docker 行为：读 `docs/architecture/docker.md` 和 `infra/compose/`。
- 判断命令怎么跑：读 `docs/dev-setup.md`、`docs/architecture/makefile.md` 和根目录 `Makefile`。
- 追踪当前进度：读 `docs/project-todolist.md`。
- 需要新增大功能设计：先在 `docs/superpowers/` 下按 `README.md` 新建当前版本设计。

## 代码变更后的文档维护映射

| 变更类型 | 需要检查或更新的文档 |
| --- | --- |
| 目录结构、模块职责、工程入口变化 | `docs/index.md` |
| 系统边界、技术选型、运行架构变化 | `docs/architecture/foundation.md` |
| Dockerfile、Compose 服务、端口、volume、环境变量、部署方式变化 | `docs/architecture/docker.md` |
| `Makefile` 目标、脚本、验证命令、开发工作流变化 | `docs/architecture/makefile.md`、必要时 `docs/dev-setup.md` |
| 本地环境、启动步骤、端口说明、常见问题变化 | `docs/dev-setup.md` |
| 产品范围、页面行为、AI Coach 行为、训练模式、里程碑变化 | `docs/prd/prd.md` |
| 工作台交互、教练状态、提示档位、提交反馈识别变化 | `docs/prd/ai-coach-workbench-prd.md` |
| 用户画像结构、画像输入、画像更新或画像驱动策略变化 | `docs/prd/ai-coach-user-profile-prd.md` |
| 任务进度、后续恢复池、阶段状态变化 | `docs/project-todolist.md` |
| 新增大功能或重要架构决策 | `docs/superpowers/` 下新增当前版本设计 |
| 只改变内部实现细节，不改变对外契约 | 可以不更新文档，但最终说明不更新原因 |
