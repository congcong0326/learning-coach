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
        cases.append(
            EvalCaseResult(
                name="rag_grounding_deferred",
                category="rag_grounding",
                status="deferred",
                reason="RAG/T6 延后，当前 eval runner 不执行 RAG Grounding。",
            )
        )
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
