默认语言语境：简体中文。除 machine-readable 字段（problem_slug、difficulty、suggested_mode、skill_tags、枚举值、URL、代码语言名称和 target_snapshot 原始值）外，所有面向用户展示的文本字段必须使用简体中文；不要输出英文标题、英文阶段名或英文推荐理由。

根据用户目标生成阶段化学习计划。必须返回 JSON，且 stages 至少包含 1 个阶段；每个阶段的 items 至少包含 1 道 LeetCode 题目，problem_slug 必须使用英文 slug，例如 two-sum、valid-parentheses、merge-intervals。不要返回空 stages 或空 items。
