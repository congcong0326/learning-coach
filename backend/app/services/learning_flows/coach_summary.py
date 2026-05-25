from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.llm_run import LlmRun
from backend.app.models.practice import CoachTurn, PracticeEvent, SessionSummary
from backend.app.services.learning_flows.coach_turn import run_coach_turn
from backend.app.services.llm_providers.base import LlmProvider
from backend.app.services.llm_run_events import LlmRunEvent
from backend.app.services.profile_service import persist_session_summary_profile_update


async def run_coach_summary(
    session: AsyncSession,
    *,
    user_id: int,
    run: LlmRun,
    provider: LlmProvider,
    model_name: str,
    publish: Callable[[LlmRunEvent], Awaitable[None]],
) -> dict[str, Any]:
    result = await run_coach_turn(
        session,
        user_id=user_id,
        run=run,
        provider=provider,
        model_name=model_name,
        publish=publish,
    )
    summary_result = await persist_session_summary_profile_update(
        session,
        user_id=user_id,
        session_id=result["session_id"],
    )
    summary = await session.get(SessionSummary, summary_result.summary_id)
    if summary is not None:
        reply_md = _summary_reply_markdown(summary)
        assistant_event = await session.get(PracticeEvent, result["assistant_event_id"])
        coach_turn = await session.get(CoachTurn, result["coach_turn_id"])
        if assistant_event is not None:
            assistant_event.content_md = reply_md
        if coach_turn is not None:
            coach_turn.response_json = {
                **coach_turn.response_json,
                "content_md": reply_md,
            }
        run.display_text_md = reply_md
        result["reply_md"] = reply_md
        await session.flush()
    result.update(
        {
            "summary_status": "completed",
            "summary_id": summary_result.summary_id,
            "profile_delta_id": summary_result.delta_id,
            "profile_delta_status": (
                "accepted" if summary_result.accepted else "rejected"
            ),
            "profile_snapshot_id": summary_result.next_snapshot_id,
            "profile_rejection_reason": summary_result.rejection_reason,
        }
    )
    return result


def _summary_reply_markdown(summary: SessionSummary) -> str:
    final_result = _result_label(summary.final_submission_result)
    phases = _phase_list(summary.phases_visited_json)
    stuck_points = _markdown_list(
        (_stuck_point_label(point) for point in summary.main_stuck_points_json),
        empty_text="本次没有记录明确卡点。",
    )
    error_types = _markdown_list(
        (_result_label(item) for item in summary.error_types_json),
        empty_text="本次没有记录未通过提交错误类型。",
    )

    return "\n\n".join(
        [
            "## 单题复盘",
            "\n".join(
                [
                    f"- **本题最终结果**：{final_result}",
                    f"- **当前训练模式**：{summary.training_mode}",
                    f"- **提交/回填次数**：{summary.attempt_count}",
                    f"- **使用过的最高提示档位**：{_hint_label(summary.max_hint_level_used)}",
                    f"- **经历阶段**：{phases}",
                ]
            ),
            "### 主要卡点\n" + stuck_points,
            "### 代码与提交反馈\n" + error_types,
            (
                "### 复杂度与核心思路\n"
                "- 当前记录已进入 AC 复盘，但还没有稳定记录你的复杂度口述。\n"
                "- 下一步建议你用自己的话补充：核心状态维护什么、为什么能覆盖所有候选答案、时间和空间复杂度是多少。"
            ),
            (
                "### 画像信号\n"
                f"- 本题结果={final_result}，最高提示档位={_hint_label(summary.max_hint_level_used)}，"
                f"尝试次数={summary.attempt_count}。"
            ),
            "### 下一步训练建议\n" + _next_recommendation(summary),
        ]
    )


def _result_label(value: str | None) -> str:
    labels = {
        "ac": "AC",
        "accepted": "AC",
        "wa": "WA",
        "tle": "TLE",
        "re": "RE",
        "mle": "MLE",
        "ce": "CE",
        "unknown": "Unknown",
        "not_submitted": "未提交",
    }
    return labels.get((value or "unknown").lower(), value or "Unknown")


def _hint_label(value: str | None) -> str:
    labels = {
        "questioning": "追问档",
        "direction": "方向档",
        "key_hint": "关键提示档",
        "reflection": "复盘档",
    }
    return labels.get(value or "", value or "未记录")


def _phase_list(values: list[str]) -> str:
    if not values:
        return "未记录"
    labels = {
        "understand_problem": "理解题意",
        "propose_bruteforce": "提出暴力解法",
        "optimize_solution": "推导优化方案",
        "define_invariant": "明确关键不变量",
        "write_code": "编写代码",
        "review_code": "代码 review",
        "submit_to_leetcode": "引导 LeetCode 提交",
        "analyze_feedback": "分析提交反馈",
        "summarize": "单题复盘",
    }
    return " -> ".join(labels.get(value, value) for value in values)


def _stuck_point_label(value: str) -> str:
    labels = {
        "user_reported_stuck": "用户主动表达卡住，需要后续继续定位卡点类型。",
        "reflection_requested": "已进入复盘阶段，需要沉淀可迁移经验。",
    }
    return labels.get(value, value)


def _markdown_list(values: Any, *, empty_text: str) -> str:
    items = [str(value).strip() for value in values if str(value).strip()]
    if not items:
        return f"- {empty_text}"
    return "\n".join(f"- {item}" for item in items)


def _next_recommendation(summary: SessionSummary) -> str:
    recommendation = summary.next_recommendation_json
    if not isinstance(recommendation, dict):
        return "- 继续下一题前，先口头复述本题关键状态、边界用例和复杂度。"
    review_focus = recommendation.get("review_focus")
    if not isinstance(review_focus, str) or not review_focus.strip():
        review_focus = "继续下一题前，先口头复述本题关键状态、边界用例和复杂度。"
    return f"- {review_focus.strip()}"


class CoachSummaryHandler:
    async def execute(self, context: Any) -> dict[str, Any]:
        return await run_coach_summary(
            context.session,
            user_id=context.user_id,
            run=context.run,
            provider=context.provider,
            model_name=context.model_name,
            publish=context.publish,
        )
