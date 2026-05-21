# AGENTS.md

## 项目环境说明

当前项目运行在 WSL Ubuntu 环境中，主要用于 Python / AI Agent 方向的开发与实验。

本项目使用 `uv` 作为 Python 项目管理工具，负责 Python 版本管理、虚拟环境创建、依赖安装、依赖锁定和命令运行。

请优先使用 `uv` 相关命令，不要默认使用系统级 `pip` 或全局 Python 环境。

当前项目已经从早期 Agent demo 演进为 Agentic Coding Learning Coach 的全栈基座。开发时应同时关注后端、前端、数据库、Docker Compose 和文档之间的契约。

## 基础环境

- 操作系统：WSL Ubuntu
- Python 版本：Python 3.12
- Python 管理工具：uv
- 虚拟环境目录：`.venv/`
- 项目依赖配置：`pyproject.toml`
- 依赖锁定文件：`uv.lock`
- Python 版本固定文件：`.python-version`

## 依赖管理规则

运行依赖应写入 `pyproject.toml` 的项目依赖中。

添加运行依赖时使用：

```bash
uv add <package-name>
```

前端依赖位于 `frontend/package.json`，通过 Corepack 调用项目声明的 pnpm 版本：

```bash
cd frontend && corepack pnpm install
```

不要默认使用全局 `pnpm`、`npm` 或 `yarn` 替代项目命令。

## 代码注释与日志规则

新增或修改代码时，应为复杂业务规则、状态机、数据修复、外部服务调用、安全边界和跨模块契约添加简洁注释。注释应说明“为什么这样做”和“需要遵守的约束”，注释需要使用中文，不要逐行复述代码做了什么。

关键流程必须添加关键日志打印，优先使用模块级 `logger = logging.getLogger(__name__)` 和标准 `logging`，避免直接使用 `print`。CLI 或一次性脚本可以使用 `print` 输出最终摘要，但核心处理过程仍应优先使用日志。

日志要求：

- 关键流程开始、完成、失败、拒绝执行、状态迁移、外部 API 调用结果和重要 repair / fallback 分支都应记录。
- 日志内容使用稳定的 `key=value` 字段，便于检索，例如 `user_id=%s draft_id=%s status=%s`。
- 日志级别保持克制：正常生命周期用 `info`，可恢复异常、校验失败和拒绝执行用 `warning`，未预期异常用 `exception`。
- 不得记录密码、API key、session token、完整用户输入、完整题解、密钥密文或其他敏感内容；需要定位问题时记录脱敏 ID、数量、状态和错误摘要。

## 当前项目架构

当前运行架构是一个本地优先的全栈训练应用基座：

```text
Browser
  -> Vite dev server / Nginx static frontend
  -> FastAPI backend
  -> PostgreSQL + pgvector
  -> isolated code-runner container
```

核心边界：

- 前端是 Vite + React + TypeScript SPA，负责题库、做题工作台、复盘和 Trace 等页面壳层。
- 前端通过 HTTP API 与后端交互，不直接连接数据库、不直接调用 LLM、不直接执行用户代码。
- 后端是业务和 AI 能力边界，负责 API、配置、数据库访问、后续 LangGraph Agent 编排、RAG 检索和工具调用。
- PostgreSQL + pgvector 同时承担业务数据、训练记录、Agent trace、RAG 文档和向量检索的基础存储。
- 用户代码执行应通过独立 `code-runner` 容器隔离，不能放进后端主进程直接执行。
- Docker Compose 是本地开发、测试和打包验证的统一运行入口；根目录 `Makefile` 是常用命令契约。

## docs 文档作用

`docs/` 是产品、架构和实施过程的知识库。新增或调整功能前，优先检查相关文档，避免和既有设计冲突。

- `docs/index.md`：项目目录索引，说明仓库主要目录和模块职责。
- `docs/dev-setup.md`：WSL Ubuntu 本地开发环境说明，包含前置条件、`make` 工作流、端口、环境变量、常见问题和最近一次基座验证记录。
- `docs/prd/prd.md`：产品需求和目标架构主文档，描述 Agentic Coding Learning Coach 的用户、MVP 范围、AI 教练行为、LangGraph 状态机、RAG、工具层、记忆层、评估与里程碑。
- `docs/prd/rag-materials.md`：RAG 语料候选清单，说明优先引入的算法、刷题、面试表达材料及入库标注建议。
- `docs/architecture/foundation.md`：当前项目基座架构说明，是理解服务边界、技术选型、模块职责和后续里程碑的首要架构文档。
- `docs/architecture/docker.md`：Docker 镜像、Compose 服务、端口、volume、环境变量和 smoke test 说明。
- `docs/architecture/makefile.md`：根目录 `Makefile` 的命令契约，说明每个 `make` 目标的执行内容和成功标准。
- `docs/superpowers/specs/`：功能或基座实施前的设计规格，用于记录目标、范围、架构决策、验收标准和风险控制。
- `docs/superpowers/plans/`：按步骤执行的实施计划，用于记录任务拆分、文件范围、验证命令和完成标准。

文档优先级建议：

- 判断产品目标和范围时，以 `docs/prd/prd.md` 为准。
- 判断当前工程基座和服务边界时，以 `docs/architecture/foundation.md` 和实际代码为准。
- 判断本地命令怎么运行时，以 `docs/dev-setup.md`、`docs/architecture/makefile.md` 和 `Makefile` 为准。
- 判断 Docker 行为时，以 `docs/architecture/docker.md` 和 `infra/` 下实际文件为准。
- `docs/superpowers/` 下的 specs 和 plans 记录设计与执行过程，可能带有历史上下文；如果和当前代码不一致，应先读代码再同步相关文档。

## 文档驱动开发规则

修改代码前，必须先检查相关文档，确认当前需求是否已有产品、架构、命令、目录或模块约束。优先从 `docs/index.md` 查找相关文档入口。

如果代码需求与文档不一致，不得静默按猜测修改；应先指出冲突，并让用户确认是修改代码、修改文档，还是同时调整。

修改代码后，必须做文档影响评估，并按 `docs/index.md` 中的“代码变更后的文档维护映射”反向维护文档：

- 如果变更影响目录结构、模块职责或工程入口，更新 `docs/index.md`。
- 如果变更影响系统边界、技术选型或运行架构，更新 `docs/architecture/foundation.md`。
- 如果变更影响 Docker、Compose、端口、环境变量或部署方式，更新 `docs/architecture/docker.md`。
- 如果变更影响 `Makefile` 命令、脚本或验证流程，更新 `docs/architecture/makefile.md` 和必要时更新 `docs/dev-setup.md`。
- 如果变更影响产品行为、AI Coach 行为、RAG、工具层、记忆层、评估或里程碑，更新 `docs/prd/prd.md` 或 `docs/prd/rag-materials.md`。
- 如果只是内部实现细节且不改变对外契约，可以不改文档，但最终回复必须说明“不需要更新文档”的理由。

涉及代码修改的最终回复必须包含：

- 已参考的文档。
- 修改的代码文件。
- 修改的文档文件，或不需要修改文档的理由。
- 执行过的验证命令。

## 文档语言规则

研发设计文档默认使用中文编写。除非用户明确要求英文，新增或更新的设计文档、实施计划、架构说明和开发流程文档应优先使用中文。
