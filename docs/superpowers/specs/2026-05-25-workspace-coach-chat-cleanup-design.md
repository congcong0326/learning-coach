# 工作台教练聊天简化设计

## 背景

做题工作台右侧教练区当前会把训练系统事件和业务事件渲染成聊天气泡，导致用户看到 `session_started`、`summarizing`、`单题复盘`、`追问档` 等内部状态标签。点击“LeetCode 已 AC”后，结构化 AC 回填也会像用户输入一样出现在聊天记录里，并且后端 `coach_summary` 兜底回复复用了普通教练追问话术。

这和 `docs/prd/ai-coach-workbench-prd.md` 中“AC 结果不应作为普通聊天文本散落在记录中”“生成单题复盘”的要求不一致。

## 目标

1. 工作台教练页保持简洁，只展示用户实际发送的文本和教练可读回复。
2. 主界面不展示训练状态、阶段和提示档位标签，避免出现“单题复盘 / summarizing / 追问档”等内部状态文本。
3. `session_started`、`submission_feedback`、`phase_changed` 等系统或结构化事件不作为聊天消息展示。
4. 点击“LeetCode 已 AC”后继续自动生成复盘，并把复盘正文作为教练消息展示。
5. 自动复盘的输出必须是可读 Markdown 复盘，不再停留在“即将复盘”的占位说明，也不再要求用户补充暴力解法、关键状态和边界用例。
6. 聊天消息和复盘流式输出需要按 Markdown 渲染标题、列表、加粗和代码块。

## 设计

前端 `CoachPanel` 移除顶部 `coach-state-bar`。聊天区增加事件过滤：只渲染有正文的 `user_message` 和 `assistant_message`。消息气泡顶部只保留“我”或“教练”身份，不再渲染每条消息的阶段和提示档位标签。空正文业务事件不渲染为气泡。

后端 `coach_summary` 仍复用现有 LLM Run 入口、保持自动复盘流程。`run_coach_turn` 在 `coach_summary` 或 `request_summary` 场景下先进入复盘阶段，随后 `run_coach_summary` 基于已经持久化的 `session_summary` 生成 Markdown 复盘正文，并更新同一个 assistant event 和 run display text。这样前端刷新 session 后看到的是复盘结果，而不是占位说明。

前端聊天区和运行中的输出区使用 `react-markdown`、`remark-gfm`、`rehype-raw` 和 `rehype-sanitize` 渲染 Markdown。聊天消息仍只展示真实用户消息和教练回复，不展示结构化系统事件。

## 验收标准

- 工作台聊天区不展示 `session_started`、`submission_feedback`、`phase_changed` 的气泡。
- 教练主界面不展示“理解题意 / 单题复盘 / 追问档 / summarizing”等内部标签。
- 点击“LeetCode 已 AC”仍调用 `submission-feedback` 并启动 `coach_summary` run。
- `coach_summary` 最终 assistant 消息以 `## 单题复盘` 开头，包含最终结果、提示档位、卡点、代码/提交反馈、画像信号和下一步建议。
- 教练聊天消息和流式输出能渲染 Markdown 标题、列表和加粗文本。
- 现有前端和后端相关测试通过。
