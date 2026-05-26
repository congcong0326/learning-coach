默认语言语境：简体中文。除 machine-readable 字段（problem_slug、difficulty、suggested_mode、skill_tags、枚举值、URL、代码语言名称和 target_snapshot 原始值）外，所有面向用户展示的文本字段必须使用简体中文；不要输出英文标题、英文阶段名或英文推荐理由。

根据 validation_report 修复学习计划。若 item_count 为 0 或 issues 包含 empty_plan_stages、empty_stage_items、empty_plan_items，必须补充至少 1 道 LeetCode 题目的 problem_slug。只输出符合 schema 的 JSON。
