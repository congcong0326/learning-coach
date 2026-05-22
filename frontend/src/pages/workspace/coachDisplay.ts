import type { HintLevel } from '../../api/practice'

const phaseLabels: Record<string, string> = {
  understand_problem: '理解题意',
  brute_force: '暴力解法',
  optimize_solution: '推导优化',
  invariant_or_state: '关键不变量',
  coding: '编写代码',
  code_review: '代码 Review',
  submit_to_leetcode: 'LeetCode 提交',
  submission_feedback: '提交反馈分析',
  reflection: '单题复盘',
}

const hintLevelLabels: Record<HintLevel, string> = {
  questioning: '追问档',
  direction: '方向档',
  key_hint: '关键提示档',
  reflection: '复盘档',
}

export function phaseLabel(phase: string | null | undefined) {
  if (!phase) {
    return '未开始'
  }
  return phaseLabels[phase] ?? phase
}

export function hintLevelLabel(level: HintLevel | null | undefined) {
  if (!level) {
    return '未使用'
  }
  return hintLevelLabels[level] ?? level
}
