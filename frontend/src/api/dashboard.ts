import { requestJson } from './client'
import type { HintLevel } from './practice'

export type PracticeDashboard = {
  completed_problem_count: number
  common_stuck_points: Array<{
    stuck_point: string
    count: number
  }>
  average_hint_gear: number | null
  highest_hint_level: HintLevel | null
  recent_profile_summary: string
  profile_snapshot_id: number | null
}

export function getPracticeDashboard() {
  return requestJson<PracticeDashboard>('/api/practice-dashboard')
}
