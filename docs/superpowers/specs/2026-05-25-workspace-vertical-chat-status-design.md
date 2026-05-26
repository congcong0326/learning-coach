# 做题工作台上下布局与轻量运行状态设计

## 背景

当前做题工作台已经从早期“题面 + 代码编辑器 + 教练信息”收敛为 Chat-first 训练入口，但桌面端仍采用左侧题面、右侧教练的两栏布局。用户希望进一步靠近 ChatGPT 式聊天体验：题面先完整展示在页面上方，用户向下进入教练聊天区；发送消息后，只需要轻量知道后端当前执行到哪一步，不希望系统执行步骤污染聊天记录。

本设计基于以下文档与代码现状：

- `docs/index.md`
- `docs/architecture/foundation.md`
- `docs/prd/ai-coach-workbench-prd.md`
- `frontend/src/pages/WorkspacePage.tsx`
- `frontend/src/pages/workspace/CoachPanel.tsx`
- `frontend/src/hooks/useLlmRun.ts`
- `backend/app/services/llm_orchestrator.py`
- `backend/app/services/learning_flows/coach_turn.py`

## 目标

- 将计划题工作台调整为上下单列布局：题面在上，教练聊天区在下。
- 题面默认自然展开，不做固定高度、折叠或内部滚动。
- 教练区保持聊天主体验，聊天历史只展示用户消息和教练回复。
- 发送消息或生成复盘时，在输入区附近显示一行当前运行状态。
- 后端补充教练 run 的稳定 `progress` 事件，让前端能显示“准备上下文、调用大模型、校验阶段、保存回复”等真实执行阶段。

## 非目标

- 不新增独立代码编辑器或代码草稿主面板。
- 不把系统执行步骤写入 `practice_event` 聊天历史。
- 不改变 `coach_turn`、`coach_summary` 的 API 创建方式。
- 不引入新的前端状态管理库。
- 不改变模型输出 JSON 契约、教练阶段枚举或数据库表结构。

## 用户体验

工作台页面结构从上到下为：

```text
页面标题与题目信息
题面
教练聊天区
```

题面区域使用现有 `ProblemPane` 渲染中文题面。由于用户选择“自然展开”，题面高度由内容决定；用户读完题面后继续向下滚动进入教练区。

教练区保持类似 ChatGPT 的交互结构：

- 中间为聊天记录，只展示 `user_message` 和 `assistant_message`。
- 底部为输入框与操作按钮。
- “代码尝试记录”和“LeetCode 已 AC”仍放在教练区标题右侧；代码尝试记录打开为居中悬浮框，完整代码默认折叠。
- 运行中可以取消当前 run。

运行状态采用极简一行展示，位置在输入框操作区附近。例如：

```text
正在调用大模型
```

该状态只反映当前 SSE `progress` 或 run stage，不进入聊天历史；run 完成、取消或失败后隐藏，失败信息仍使用现有错误提示。

## 前端设计

### WorkspacePage

`WorkspacePage` 移除当前桌面端左右两栏布局，改为垂直内容流：

- 保留现有无效路由、训练会话加载、题目加载和错误提示。
- 顶部 `page-heading` 保留题名、难度和 LeetCode 原题链接。
- `ProblemPane` 放在 `CoachPanel` 之前。
- 对计划题入口，如果没有 session，继续显示“从学习计划进入后启用 AI 教练”的占位。

CSS 使用新的垂直布局类或复用现有 `workspace-*` 类，但需要避免继续表达“column/row 两栏”语义。页面仍应在移动端和桌面端使用同一上下结构。

### CoachPanel

`CoachPanel` 继续使用 `useLlmRun`，但运行状态显示改为轻量一行：

- 文案来源优先使用 `llmRun.stage`，即现有 hook 从 `progress.message` 写入的用户可读状态。
- 运行中显示状态行和取消按钮。
- 不把状态插入 `chatEvents`。
- `llmRun.displayText` 仍可作为正在生成的临时教练回复预览显示，完成后通过 `onSessionRefresh` 拉取正式 assistant event。

需要保持既有行为：

- 普通发送仍以 `unknown` intent 创建用户消息，再启动 `coach_turn`。
- 请求提示仍以 `request_hint` intent 启动 `coach_turn`。
- LeetCode 已 AC 先记录提交反馈，再启动 `coach_summary`。
- 代码尝试记录居中悬浮框保持可用，代码默认折叠，展开单条尝试后查看完整代码。

## 后端设计

### 现有 SSE 契约

无需新增事件类型。继续使用统一 LLM Run SSE：

```text
started -> progress* -> delta* -> result/error/canceled -> done
```

前端当前已经把 `progress.message` 写入 `stage`，因此后端只需要发布更清晰的 `progress` message。

### Coach Turn 进度点

`coach_turn` flow 增加稳定进度：

- `loading_context`：正在准备训练上下文。
- `calling_model`：正在调用大模型。
- `guarding_transition`：正在校验教练阶段。
- `saving_reply`：正在保存教练回复。

这些状态必须满足：

- 不包含完整用户输入、完整代码、题解或密钥。
- 用中文用户可读文案作为 `message`。
- 日志继续使用结构化 `key=value` 风格，不记录敏感内容。
- 模型失败走 fallback 时仍可继续显示后续状态。

`llm_orchestrator` 仍负责模型资产选择，并保留现有“正在选择模型资产”进度。由于用户只要求极简状态，前端直接显示最新一条即可，不需要维护步骤列表。

## 测试策略

前端测试：

- 更新 `WorkspacePage.test.tsx`，断言计划题入口渲染为上下布局，不再期待两个 `.workspace-content-column`。
- 更新 `CoachPanel.test.tsx`，断言运行中显示轻量状态行，且状态不进入聊天历史。
- 保留现有发送消息、请求提示、AC 复盘和流式输出测试。

后端测试：

- 更新 `backend/tests/test_learning_flows.py` 中 coach turn / summary 相关事件序列断言，允许或精确验证新增 `progress` 事件。
- 验证新增进度事件的 `message` 是用户可读状态，且不携带敏感文本。
- 如 orchestrator 事件序列测试只覆盖模型资产选择，不需要改变语义；若断言过窄，则同步更新。

文档维护：

- 更新 `docs/architecture/foundation.md` 中训练工作台布局说明。
- 更新 `docs/prd/ai-coach-workbench-prd.md` 中进入工作台的体验描述，从左右布局改为上题面、下教练。
- `docs/index.md` 当前目录职责不变，除非实现新增或移动模块，否则不需要更新。

## 验收标准

- 从 `/workspace/items/:itemId` 进入时，题面完整显示在教练区上方。
- 教练聊天区仍能发送消息、请求提示、取消运行、查看代码尝试记录、记录 LeetCode AC。
- run 进行中只显示一行当前状态，不出现持久化系统消息。
- 后端 `coach_turn` 和 `coach_summary` 执行时能通过 SSE 推送可理解的进度。
- 前后端相关测试通过。
