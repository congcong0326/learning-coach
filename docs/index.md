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
  superpowers/
    README.md
```

已删除的历史文档包括 AI 教练工作台、AI 教练用户画像、RAG、Trace、学习计划、复盘和其他训练闭环相关材料。当前仓库只以本索引列出的文档作为事实来源。

## 当前产品边界

当前项目已收敛为本地优先的题库浏览应用，保留能力只有：

```text
注册/登录
-> 进入题库
-> 浏览题目列表
-> 查看题面详情
```

当前不包含：

- 模型 API 资产配置。
- LLM Run、完整 AI 教练、提示词管理和 eval。
- 目标校准、学习计划、训练工作台、代码 review、提交反馈和复盘。
- 用户画像、下一题推荐、RAG、Trace、仪表盘和本地代码执行。

当前新增一个最小题库问答 Agent loop 实验入口：后端通过 OpenAI Responses API 和受限题库查询工具回答题库相关问题，不持久化 LLM Run，不开放 bash 或代码执行。

## 目录职责

- `backend/app/main.py`：FastAPI 应用工厂和路由注册。
- `backend/app/api/`：HTTP API 路由，当前包含健康检查、数据库健康检查、认证和题库。
- `backend/app/core/`：配置入口，使用 Pydantic Settings 读取环境变量。
- `backend/app/db/`：SQLAlchemy async engine、session、健康检查和 Alembic migration。
- `backend/app/models/`：SQLAlchemy 模型，当前只覆盖题库、用户和登录 session。
- `backend/app/schemas/`：Pydantic 请求和响应模型。
- `backend/app/services/`：认证、题库查询和题库 seed 导入服务。
- `backend/app/llm/`：模型决策引擎适配器，当前包含 OpenAI Responses API 适配器。
- `backend/app/agents/`：当前最小题库 Agent loop、agent-native 类型和安全题库工具。
- `backend/app/cli/problem_seed.py`：题库 seed 导入命令。
- `backend/tests/`：后端主测试。
- `frontend/`：Vite React TypeScript SPA。
- `frontend/src/pages/`：登录、注册、题库列表和题面详情页面。
- `frontend/src/routes/`：前端路由、首访重定向和登录态保护。
- `frontend/src/api/`：前端 API client 与后端请求封装。
- `frontend/src/components/StatementMarkdown.tsx`：题面 Markdown 渲染组件。
- `infra/docker/`：后端、前端镜像和 Nginx 配置。
- `infra/compose/`：开发、测试和生产/打包 Compose 文件。
- `scripts/`：smoke test、数据库等待和题库 seed 准备脚本。
- `data/sources/`：本地第三方原始题库目录，默认忽略不提交。
- `data/seed/`：本地生成的题库 seed 文件目录，题面数据默认不提交公开仓库。
- `archive/`：归档材料，修改前确认是否属于用户保留内容。

## 推荐阅读顺序

- 判断产品目标和范围：读 `docs/prd/prd.md`。
- 判断工程边界和模块职责：读 `docs/architecture/foundation.md`，再读实际代码。
- 判断 Docker 行为：读 `docs/architecture/docker.md` 和 `infra/compose/`。
- 判断命令怎么跑：读 `docs/dev-setup.md`、`docs/architecture/makefile.md` 和根目录 `Makefile`。
- 追踪当前进度：读 `docs/project-todolist.md`。
- 需要新增大功能设计：先在 `docs/superpowers/` 下按 `README.md` 新建当前版本设计。

## 代码变更后的文档维护映射

| 变更类型 | 需要检查或更新的文档 |
| --- | --- |
| 目录结构、模块职责、工程入口变化 | `docs/index.md` |
| 系统边界、技术选型或运行架构变化 | `docs/architecture/foundation.md` |
| Dockerfile、Compose 服务、端口、volume、环境变量或部署方式变化 | `docs/architecture/docker.md` |
| `Makefile` 目标、脚本或验证流程变化 | `docs/architecture/makefile.md`、必要时更新 `docs/dev-setup.md` |
| 本地环境、启动步骤、端口说明或常见问题变化 | `docs/dev-setup.md` |
| 产品范围或页面行为变化 | `docs/prd/prd.md` |
| 任务进度、后续恢复池或阶段状态变化 | `docs/project-todolist.md` |
| 新增大功能或重要架构决策 | `docs/superpowers/` 下新增当前版本设计 |
| 只改变内部实现细节，不改变对外契约 | 可以不更新文档，但最终说明不更新原因 |
