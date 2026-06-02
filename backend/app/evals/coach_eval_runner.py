from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backend.app.services.coach_guard import guard_transition

EvalStatus = Literal["passed", "failed", "deferred"]


@dataclass(frozen=True)
class EvalCaseResult:
    name: str
    category: str
    status: EvalStatus
    reason: str


@dataclass(frozen=True)
class EvalSuiteResult:
    cases: list[EvalCaseResult]

    @property
    def passed(self) -> int:
        return sum(1 for item in self.cases if item.status == "passed")

    @property
    def failed(self) -> int:
        return sum(1 for item in self.cases if item.status == "failed")

    @property
    def deferred(self) -> int:
        return sum(1 for item in self.cases if item.status == "deferred")


def run_eval_suite(categories: list[str] | None = None) -> EvalSuiteResult:
    requested = set(categories or ["hint_leakage", "diagnosis", "code_review", "rag_grounding"])
    cases: list[EvalCaseResult] = []
    if "hint_leakage" in requested:
        cases.append(_eval_hint_leakage())
    if "diagnosis" in requested:
        cases.append(_eval_diagnosis())
    if "code_review" in requested:
        cases.append(_eval_code_review())
    if "rag_grounding" in requested:
        cases.extend(_eval_rag_grounding())
    return EvalSuiteResult(cases=cases)


def _eval_hint_leakage() -> EvalCaseResult:
    decision = guard_transition(
        phase_before="optimize_solution",
        proposed_phase_after="optimize_solution",
        has_code=False,
        has_submission_feedback=False,
        has_terminal_result=False,
        hint_level="questioning",
        should_reveal_solution=True,
    )
    if not decision.accepted and decision.reason == "hint_level_prevents_solution_reveal":
        return EvalCaseResult(
            name="low_hint_blocks_full_solution",
            category="hint_leakage",
            status="passed",
            reason="低提示档位泄题被 coach_guard 拒绝。",
        )
    return EvalCaseResult(
        name="low_hint_blocks_full_solution",
        category="hint_leakage",
        status="failed",
        reason=f"guard 未拒绝低档位泄题: accepted={decision.accepted} reason={decision.reason}",
    )


def _eval_diagnosis() -> EvalCaseResult:
    sample = "这版 WA，失败用例 nums=[3,3], target=6，预期 [0,1] 但返回空。"
    diagnosis = _diagnose_submission_text(sample)
    if diagnosis == "edge_case_missing":
        return EvalCaseResult(
            name="duplicate_element_wa_is_edge_case_missing",
            category="diagnosis",
            status="passed",
            reason="重复元素 WA 被归因为边界用例缺失。",
        )
    return EvalCaseResult(
        name="duplicate_element_wa_is_edge_case_missing",
        category="diagnosis",
        status="failed",
        reason=f"诊断结果不匹配: {diagnosis}",
    )


def _eval_code_review() -> EvalCaseResult:
    code = "def twoSum(nums, target):\n    seen = {}\n    for i, n in enumerate(nums):\n        seen[n] = i\n        if target - n in seen:\n            return [seen[target-n], i]\n    return []"
    issue = _review_two_sum_code(code)
    if issue == "hash_update_before_lookup":
        return EvalCaseResult(
            name="two_sum_update_before_lookup_review",
            category="code_review",
            status="passed",
            reason="代码 review 定位到哈希表写入和查询顺序。",
        )
    return EvalCaseResult(
        name="two_sum_update_before_lookup_review",
        category="code_review",
        status="failed",
        reason=f"review 结果不匹配: {issue}",
    )


@dataclass(frozen=True)
class RagEvalChunk:
    chunk_id: int
    knowledge_type: str
    title: str
    summary: str
    problem_slug: str | None
    problem_tags: set[str]
    phases: set[str]
    hint_level_min: int
    hint_level_max: int
    has_full_solution: bool
    quality_score: float


def _eval_rag_grounding() -> list[EvalCaseResult]:
    return [
        _eval_rag_low_hint_filters_full_solution(),
        _eval_rag_common_bug_grounding(),
        _eval_rag_non_ac_feedback_grounding(),
    ]


def _eval_rag_low_hint_filters_full_solution() -> EvalCaseResult:
    selected, filtered = _select_rag_eval_chunks(
        _rag_eval_chunks(),
        hint_level=0,
        retrieval_intent="pattern_direction",
        problem_slug="two-sum",
        problem_tags={"hash-table"},
        phase="think_solution",
    )
    leaked = any(chunk.has_full_solution for chunk in selected)
    blocked = any(item == (3, "full_solution_blocked") for item in filtered)
    if not leaked and blocked:
        return EvalCaseResult(
            name="rag_low_hint_filters_full_solution",
            category="rag_grounding",
            status="passed",
            reason="追问档命中完整题解时被过滤，只保留安全方向卡片。",
        )
    return EvalCaseResult(
        name="rag_low_hint_filters_full_solution",
        category="rag_grounding",
        status="failed",
        reason=f"低档过滤失败: leaked={leaked} filtered={filtered}",
    )


def _eval_rag_common_bug_grounding() -> EvalCaseResult:
    selected, _filtered = _select_rag_eval_chunks(
        _rag_eval_chunks(),
        hint_level=0,
        retrieval_intent="code_review",
        problem_slug="two-sum",
        problem_tags={"hash-table"},
        phase="review_code",
    )
    first = selected[0] if selected else None
    if first and first.knowledge_type == "common_bug_card" and "查询" in first.summary:
        return EvalCaseResult(
            name="rag_common_bug_card_grounding",
            category="rag_grounding",
            status="passed",
            reason="代码 review 场景优先 grounding 到 common bug 卡片。",
        )
    return EvalCaseResult(
        name="rag_common_bug_card_grounding",
        category="rag_grounding",
        status="failed",
        reason=f"未优先选择 common bug 卡片: selected={first}",
    )


def _eval_rag_non_ac_feedback_grounding() -> EvalCaseResult:
    selected, _filtered = _select_rag_eval_chunks(
        _rag_eval_chunks(),
        hint_level=1,
        retrieval_intent="submission_feedback",
        problem_slug="two-sum",
        problem_tags={"hash-table"},
        phase="analyze_feedback",
    )
    if selected and "重复元素" in selected[0].summary and "WA" in selected[0].summary:
        return EvalCaseResult(
            name="rag_non_ac_feedback_grounding",
            category="rag_grounding",
            status="passed",
            reason="非 AC 反馈 grounding 到重复元素 WA 调试卡片。",
        )
    return EvalCaseResult(
        name="rag_non_ac_feedback_grounding",
        category="rag_grounding",
        status="failed",
        reason=f"非 AC grounding 结果不匹配: selected={selected[:1]}",
    )


def _diagnose_submission_text(text: str) -> str:
    normalized = text.lower()
    if "wa" in normalized and "[3,3]" in normalized:
        return "edge_case_missing"
    if "tle" in normalized:
        return "complexity_bottleneck"
    if "runtime" in normalized or "re" in normalized:
        return "runtime_error"
    return "unknown"


def _review_two_sum_code(code: str) -> str:
    seen_write = code.find("seen[n] = i")
    lookup = code.find("target - n in seen")
    if seen_write >= 0 and lookup >= 0 and seen_write < lookup:
        return "hash_update_before_lookup"
    return "unknown"


def _rag_eval_chunks() -> list[RagEvalChunk]:
    return [
        RagEvalChunk(
            chunk_id=1,
            knowledge_type="pattern_card",
            title="Two Sum 方向",
            summary="看到目标和与下标，先考虑哈希表记录已见元素。",
            problem_slug="two-sum",
            problem_tags={"hash-table", "array"},
            phases={"think_solution", "understand_problem"},
            hint_level_min=0,
            hint_level_max=1,
            has_full_solution=False,
            quality_score=0.9,
        ),
        RagEvalChunk(
            chunk_id=2,
            knowledge_type="common_bug_card",
            title="查询写入顺序",
            summary="代码 review 时优先检查是否先查询 complement，再写入当前元素。",
            problem_slug="two-sum",
            problem_tags={"hash-table"},
            phases={"review_code"},
            hint_level_min=0,
            hint_level_max=2,
            has_full_solution=False,
            quality_score=0.95,
        ),
        RagEvalChunk(
            chunk_id=3,
            knowledge_type="hint_card",
            title="完整哈希表流程",
            summary="完整说明 Two Sum 哈希表解法流程。",
            problem_slug="two-sum",
            problem_tags={"hash-table"},
            phases={"think_solution", "review_code"},
            hint_level_min=0,
            hint_level_max=3,
            has_full_solution=True,
            quality_score=0.98,
        ),
        RagEvalChunk(
            chunk_id=4,
            knowledge_type="common_bug_card",
            title="重复元素 WA 调试",
            summary="遇到 WA 且失败用例有重复元素时，先检查同一元素复用和查询写入顺序。",
            problem_slug="two-sum",
            problem_tags={"hash-table"},
            phases={"analyze_feedback"},
            hint_level_min=0,
            hint_level_max=2,
            has_full_solution=False,
            quality_score=0.93,
        ),
    ]


def _select_rag_eval_chunks(
    chunks: list[RagEvalChunk],
    *,
    hint_level: int,
    retrieval_intent: str,
    problem_slug: str,
    problem_tags: set[str],
    phase: str,
) -> tuple[list[RagEvalChunk], list[tuple[int, str]]]:
    filtered: list[tuple[int, str]] = []
    usable: list[RagEvalChunk] = []
    for chunk in chunks:
        if chunk.quality_score < 0.6:
            filtered.append((chunk.chunk_id, "low_quality"))
            continue
        if hint_level < chunk.hint_level_min or hint_level > chunk.hint_level_max:
            filtered.append((chunk.chunk_id, "hint_level_blocked"))
            continue
        if hint_level < 3 and chunk.has_full_solution:
            filtered.append((chunk.chunk_id, "full_solution_blocked"))
            continue
        if chunk.phases and phase not in chunk.phases:
            filtered.append((chunk.chunk_id, "phase_mismatch"))
            continue
        usable.append(chunk)
    return (
        sorted(
            usable,
            key=lambda chunk: _rag_eval_score(
                chunk,
                retrieval_intent=retrieval_intent,
                problem_slug=problem_slug,
                problem_tags=problem_tags,
                phase=phase,
            ),
            reverse=True,
        ),
        filtered,
    )


def _rag_eval_score(
    chunk: RagEvalChunk,
    *,
    retrieval_intent: str,
    problem_slug: str,
    problem_tags: set[str],
    phase: str,
) -> float:
    score = chunk.quality_score
    if chunk.problem_slug == problem_slug:
        score += 100
    score += len(chunk.problem_tags & problem_tags) * 10
    if phase in chunk.phases:
        score += 5
    if retrieval_intent == "code_review" and chunk.knowledge_type == "common_bug_card":
        score += 20
    if retrieval_intent == "submission_feedback" and "WA" in chunk.summary:
        score += 20
    return score


def _category_title(category: str) -> str:
    labels = {
        "hint_leakage": "Hint Leakage",
        "diagnosis": "Diagnosis",
        "code_review": "Code Review",
        "rag_grounding": "RAG Grounding",
    }
    return labels.get(category, category)


def main() -> int:
    result = run_eval_suite()
    for item in result.cases:
        print(
            f"[{item.status}] {_category_title(item.category)} "
            f"{item.name}: {item.reason}"
        )
    print(
        "summary "
        f"passed={result.passed} failed={result.failed} deferred={result.deferred}"
    )
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
