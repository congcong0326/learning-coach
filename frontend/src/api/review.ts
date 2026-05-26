import { requestJson } from './client'
import type { HintLevel } from './practice'

export type PracticeSessionReview = {
  session_id: number
  summary_id: number
  problem_id: number
  problem_slug: string
  final_result: string
  training_mode: string
  phases_visited: string[]
  main_stuck_points: string[]
  error_types: string[]
  max_hint_level_used: HintLevel | null
  attempt_count: number
  complexity_analysis: Record<string, unknown>
  core_idea_md: string
  review_summary_md: string
  profile_signals: Record<string, unknown>
  profile_update_suggestion: Record<string, unknown>
  profile_delta: Record<string, unknown>
  next_recommendation: Record<string, unknown>
  updated_at: string
}

export function getPracticeReview(sessionId: number) {
  return requestJson<PracticeSessionReview>(`/api/practice-sessions/${sessionId}/review`)
}
