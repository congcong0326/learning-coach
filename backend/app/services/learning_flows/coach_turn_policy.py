from __future__ import annotations

import json
import re
from typing import Any

from backend.app.models.practice import PracticeEvent, PracticeSession
from backend.app.prompts import get_prompt
from backend.app.services.code_attempts import ExtractedCode
from backend.app.services.learning_flows.goal_plan import LearningFlowError


_COACH_TURN_PROMPT = get_prompt("coach_turn")
PROMPT_VERSION = _COACH_TURN_PROMPT.version
SAFE_REPLY = "我已经记录你的输入。先说明你的暴力解法、你准备维护的关键状态，以及你认为必须覆盖的边界用例。"
SUMMARY_SAFE_REPLY = (
    "LeetCode AC 已记录。下面进入单题复盘：我会围绕本题最终结果、"
    "关键思路、主要卡点、提示使用和下一步训练建议做沉淀。"
)
DIAGNOSED_STUCK_POINT_MAX_LENGTH = 120
NEXT_ACTION_MAX_LENGTH = 60
CHAT_FEEDBACK_TEXT_MAX_LENGTH = 1200
USER_MESSAGE_TEXT_MAX_LENGTH = 4000
COACH_REPLY_INSTRUCTIONS = _COACH_TURN_PROMPT.instructions
COACH_PHASES = {
    "understand_problem",
    "propose_bruteforce",
    "optimize_solution",
    "define_invariant",
    "write_code",
    "review_code",
    "submit_to_leetcode",
    "analyze_feedback",
    "summarize",
}
COACH_EVENT_TRIGGERS = {
    "describe_idea",
    "stuck",
    "request_hint",
    "code_review",
    "submit_feedback",
    "request_summary",
    "unknown",
}
HINT_LEVEL_ORDER = ["questioning", "direction", "key_hint", "reflection"]
HINT_LEVEL_INDEX = {level: index for index, level in enumerate(HINT_LEVEL_ORDER)}
TARGET_CODE_LANGUAGE_LABELS = {
    "c": "C",
    "go": "Go",
    "python3": "Python3",
    "javascript": "JavaScript",
    "java": "Java",
}
CHAT_FEEDBACK_STRONG_RESULT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("wa", ("wrong answer", "答案错误")),
    ("tle", ("time limit exceeded",)),
    ("re", ("runtime error",)),
    ("mle", ("memory limit exceeded",)),
    ("ce", ("compile error", "compilation error")),
    ("unknown", ("未通过", "没通过", "not accepted")),
)
CHAT_FEEDBACK_CONTEXTUAL_RESULT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tle", ("超时",)),
    ("re", ("运行错误",)),
    ("mle", ("内存超限",)),
    ("ce", ("编译错误", "语法错误")),
)
CHAT_FEEDBACK_STATUS_CODE_RESULTS = {
    "wa": "wa",
    "tle": "tle",
    "re": "re",
    "mle": "mle",
    "ce": "ce",
}
CHAT_FEEDBACK_RESULT_CONTEXT_TERMS = (
    "leetcode",
    "力扣",
    "提交",
    "结果",
    "显示",
    "提示",
    "报错",
    "错误信息",
    "失败",
    "用例",
    "输出",
    "期望",
    "expected",
    "got",
    "actual",
    "test case",
    "case",
)
CHAT_FEEDBACK_WA_DIFF_TERMS = ("输出是", "期望", "expected", "got")
CHAT_FEEDBACK_WA_CONTEXT_TERMS = (
    "失败用例",
    "用例",
    "test case",
    "case",
    "expected",
    "got",
    "实际",
    "输出",
)
CHAT_FEEDBACK_HYPOTHETICAL_TERMS = (
    "如果",
    "假如",
    "万一",
    "要是",
    "该先",
    "怎么办",
    "what if",
)


def should_persist_code_attempt(
    *,
    decision_phase_after: str,
    decision_accepted: bool,
    model_phase_after: str,
) -> bool:
    if decision_accepted and decision_phase_after == "review_code":
        return True
    # 模型已经完成代码 review 并建议去 LeetCode 提交时，即使阶段守卫不允许
    # 从早期阶段直接快进，也要沉淀本轮代码尝试，避免用户看到“可提交”但记录为空。
    return model_phase_after == "submit_to_leetcode"


def parse_coach_json(final_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(strip_json_fence(final_text))
    except json.JSONDecodeError as exc:
        raise LearningFlowError("coach_output_invalid") from exc
    if not isinstance(parsed, dict):
        raise LearningFlowError("coach_output_invalid")
    phase_after = parsed.get("phase_after")
    diagnosed_stuck_point = parsed.get("diagnosed_stuck_point")
    next_action = parsed.get("next_action")
    reply_md = parsed.get("reply_md")
    should_reveal_solution = parsed.get("should_reveal_solution")
    code_quality_status = parsed.get("code_quality_status")
    code_quality_comment = parsed.get("code_quality_comment")
    if not isinstance(phase_after, str) or phase_after not in COACH_PHASES:
        raise LearningFlowError("coach_output_invalid")
    if not isinstance(diagnosed_stuck_point, str) or not diagnosed_stuck_point.strip():
        raise LearningFlowError("coach_output_invalid")
    if not isinstance(next_action, str) or not next_action.strip():
        raise LearningFlowError("coach_output_invalid")
    if not isinstance(reply_md, str) or not reply_md.strip():
        raise LearningFlowError("coach_output_invalid")
    if not isinstance(should_reveal_solution, bool):
        raise LearningFlowError("coach_output_invalid")
    if code_quality_status is not None:
        if not isinstance(code_quality_status, str) or code_quality_status not in {
            "pending",
            "needs_fix",
            "ready_to_submit",
        }:
            raise LearningFlowError("coach_output_invalid")
    if code_quality_comment is not None and not isinstance(code_quality_comment, str):
        raise LearningFlowError("coach_output_invalid")
    diagnosed_stuck_point = diagnosed_stuck_point.strip()
    next_action = next_action.strip()
    if len(diagnosed_stuck_point) > DIAGNOSED_STUCK_POINT_MAX_LENGTH:
        raise LearningFlowError("coach_output_invalid")
    if len(next_action) > NEXT_ACTION_MAX_LENGTH:
        raise LearningFlowError("coach_output_invalid")
    return {
        "phase_after": phase_after,
        "diagnosed_stuck_point": diagnosed_stuck_point,
        "next_action": next_action,
        "reply_md": reply_md.strip(),
        "should_reveal_solution": should_reveal_solution,
        "code_quality_status": code_quality_status,
        "code_quality_comment": code_quality_comment.strip()
        if isinstance(code_quality_comment, str)
        else "",
        "generation_mode": "llm",
    }


def strip_json_fence(final_text: str) -> str:
    text = final_text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def fallback_coach_decision(trigger_context: dict[str, str]) -> dict[str, Any]:
    # 复盘 run 允许不依赖模型资产执行，兜底文案必须保持复盘语境，
    # 不能复用普通教练回合的前置追问。
    reply_md = (
        SUMMARY_SAFE_REPLY
        if trigger_context["trigger"] == "request_summary"
        or trigger_context["next_action"] == "summarize_session"
        else SAFE_REPLY
    )
    return {
        "phase_after": trigger_context["proposed_phase"],
        "diagnosed_stuck_point": trigger_context["diagnosed_stuck_point"],
        "next_action": trigger_context["next_action"],
        "reply_md": reply_md,
        "should_reveal_solution": False,
        "generation_mode": "fallback",
        "error_summary": "",
    }


def reply_after_guard(
    coach_decision: dict[str, Any],
    *,
    decision_reason: str,
) -> str:
    if decision_reason == "hint_level_prevents_solution_reveal":
        return SAFE_REPLY
    return str(coach_decision["reply_md"])


def hint_level_after_turn(
    current_hint_level: str,
    *,
    trigger: str,
    proposed_phase_after: str,
) -> str:
    if proposed_phase_after == "summarize" or trigger == "request_summary":
        return "reflection"
    current_index = HINT_LEVEL_INDEX.get(current_hint_level, 0)
    if trigger == "request_hint":
        return HINT_LEVEL_ORDER[min(current_index + 1, HINT_LEVEL_INDEX["key_hint"])]
    if trigger in {"describe_idea", "code_review", "submit_feedback"} and current_index > 0:
        return HINT_LEVEL_ORDER[current_index - 1]
    return current_hint_level if current_hint_level in HINT_LEVEL_INDEX else "questioning"


def hint_level_index(hint_level: str) -> int:
    return HINT_LEVEL_INDEX.get(hint_level, 0)


def max_hint_level(current: str, candidate: str) -> str:
    current_index = HINT_LEVEL_INDEX.get(current, 0)
    candidate_index = HINT_LEVEL_INDEX.get(candidate, 0)
    return HINT_LEVEL_ORDER[max(current_index, candidate_index)]


def trigger_context(
    payload: dict[str, Any],
    practice_session: PracticeSession,
    *,
    user_event: PracticeEvent | None,
    has_submission_feedback: bool,
    force_summary: bool,
    extracted_code: ExtractedCode | None,
    chat_feedback_context: dict[str, Any] | None,
) -> dict[str, str]:
    payload_trigger = payload.get("trigger")
    if payload_trigger is not None and not isinstance(payload_trigger, str):
        raise LearningFlowError("coach_output_invalid")

    if force_summary:
        if payload_trigger is not None and payload_trigger != "request_summary":
            raise LearningFlowError("coach_output_invalid")
        trigger = "request_summary"
    else:
        if user_event is None:
            raise LearningFlowError("coach_output_invalid")
        event_trigger = user_event.intent or "unknown"
        if payload_trigger is not None and payload_trigger != event_trigger:
            raise LearningFlowError("coach_output_invalid")
        trigger = event_trigger

    if trigger not in COACH_EVENT_TRIGGERS:
        raise LearningFlowError("coach_output_invalid")

    if trigger == "request_summary" or practice_session.final_result == "ac" or practice_session.status == "summarizing":
        return {
            "trigger": trigger,
            "proposed_phase": "summarize",
            "next_action": "summarize_session",
            "diagnosed_stuck_point": "reflection_requested",
        }
    if trigger == "submit_feedback":
        return {
            "trigger": trigger,
            "proposed_phase": "analyze_feedback",
            "next_action": "analyze_submission_feedback",
            "diagnosed_stuck_point": "submission_feedback_analysis",
        }
    if chat_feedback_context is not None:
        return {
            "trigger": trigger,
            "proposed_phase": "analyze_feedback",
            "next_action": "analyze_submission_feedback",
            "diagnosed_stuck_point": "chat_submission_feedback_analysis",
        }
    if trigger == "code_review":
        return {
            "trigger": trigger,
            "proposed_phase": "review_code",
            "next_action": "review_code",
            "diagnosed_stuck_point": "code_review_requested",
        }
    if trigger in {"unknown", "describe_idea"} and extracted_code is not None:
        return {
            "trigger": trigger,
            "proposed_phase": "review_code",
            "next_action": "review_code",
            "diagnosed_stuck_point": "code_review_candidate",
        }
    if trigger == "request_hint":
        return {
            "trigger": trigger,
            "proposed_phase": practice_session.phase,
            "next_action": "offer_questioning_hint",
            "diagnosed_stuck_point": "needs_hint",
        }
    if trigger == "stuck":
        return {
            "trigger": trigger,
            "proposed_phase": practice_session.phase,
            "next_action": "diagnose_stuck_point",
            "diagnosed_stuck_point": "user_reported_stuck",
        }
    if trigger == "describe_idea":
        proposed_phase = "analyze_feedback" if has_submission_feedback else practice_session.phase
        return {
            "trigger": trigger,
            "proposed_phase": proposed_phase,
            "next_action": "ask_bruteforce_state_and_edges",
            "diagnosed_stuck_point": "bruteforce_state_unclear",
        }
    return {
        "trigger": trigger,
        "proposed_phase": practice_session.phase,
        "next_action": "ask_clarifying_question",
        "diagnosed_stuck_point": "intent_unclear",
    }


def user_intent(user_event: PracticeEvent | None) -> str:
    if user_event is None:
        return ""
    return user_event.intent or ""


def chat_feedback_result(normalized_content: str) -> str | None:
    normalized_content = normalized_content.lower()
    has_result_context = chat_feedback_has_result_context(normalized_content)
    for status_code, result in CHAT_FEEDBACK_STATUS_CODE_RESULTS.items():
        if chat_feedback_status_code_matches(
            normalized_content,
            status_code,
            has_result_context=has_result_context,
        ):
            return result
    for result, keywords in CHAT_FEEDBACK_STRONG_RESULT_KEYWORDS:
        for keyword in keywords:
            if keyword not in normalized_content:
                continue
            if result == "unknown" and not (
                has_result_context
                or chat_feedback_keyword_is_standalone_result(
                    normalized_content,
                    keyword,
                )
                or (
                    keyword == "not accepted"
                    and not chat_feedback_is_hypothetical(normalized_content)
                )
            ):
                continue
            return result
    if has_result_context:
        for result, keywords in CHAT_FEEDBACK_CONTEXTUAL_RESULT_KEYWORDS:
            for keyword in keywords:
                if keyword in normalized_content:
                    return result
    if chat_feedback_looks_like_wa_diff(normalized_content):
        return "wa"
    return None


def chat_feedback_has_result_context(normalized_content: str) -> bool:
    return any(term in normalized_content for term in CHAT_FEEDBACK_RESULT_CONTEXT_TERMS)


def chat_feedback_is_hypothetical(normalized_content: str) -> bool:
    return any(term in normalized_content for term in CHAT_FEEDBACK_HYPOTHETICAL_TERMS)


def chat_feedback_keyword_is_standalone_result(
    normalized_content: str,
    keyword: str,
) -> bool:
    return (
        re.fullmatch(
            rf"\s*{re.escape(keyword)}\s*(?:了|啦|:|：|。|!|！|\.)?\s*",
            normalized_content,
        )
        is not None
    )


def chat_feedback_status_code_matches(
    normalized_content: str,
    status_code: str,
    *,
    has_result_context: bool,
) -> bool:
    if chat_feedback_short_status_code_matches(normalized_content, status_code):
        return True
    if not has_result_context:
        return False
    return (
        re.search(
            rf"(?<![a-z0-9]){re.escape(status_code)}(?![a-z0-9])",
            normalized_content,
        )
        is not None
    )


def chat_feedback_short_status_code_matches(
    normalized_content: str,
    status_code: str,
) -> bool:
    return (
        re.fullmatch(
            rf"\s*{re.escape(status_code)}\s*(?:了|啦|:|：|。|!|！|\.)?\s*",
            normalized_content,
        )
        is not None
    )


def chat_feedback_looks_like_wa_diff(normalized_content: str) -> bool:
    # “期望/输出”也常出现在解法讨论里，只有和失败用例或 expected/got 结构共现时才视为提交反馈。
    diff_terms = {
        term for term in CHAT_FEEDBACK_WA_DIFF_TERMS if term in normalized_content
    }
    context_terms = {
        term for term in CHAT_FEEDBACK_WA_CONTEXT_TERMS if term in normalized_content
    }
    return bool(diff_terms and context_terms and len(diff_terms | context_terms) >= 2)
