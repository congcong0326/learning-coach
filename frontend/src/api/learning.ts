import { requestJson } from './client'

export type PreferredLanguage = 'c' | 'go' | 'python3' | 'javascript' | 'java'
export type GoalType = 'beginner' | 'interview_sprint' | 'strengthen_weakness' | 'maintain'
export type TargetTimeline = 'none' | 'within_1_month' | 'one_to_three_months' | 'over_three_months'
export type CurrentLevel = 'new' | 'easy_started' | 'medium_partial' | 'round_done_unstable'
export type TrainingPreference = 'guided' | 'independent_first' | 'interviewer_style'

export type GoalCalibrationPayload = {
  goal_type: GoalType
  target_timeline: TargetTimeline
  weekly_days: number
  session_minutes: number
  current_level: CurrentLevel
  preferred_language: PreferredLanguage
  self_reported_weaknesses: string[]
  extra_notes: string
  training_preference: TrainingPreference
}

export type GoalCalibrationStartResponse = {
  draft_id: number
  status: string
  followup_question: string | null
  followup_question_id: string | null
  remaining_followups: number
}

export type PlanDraftResponse = {
  draft_id: number
  status: string
  target_snapshot: Record<string, unknown>
  generation_summary_md: string
  stages: Array<{
    title: string
    objective_md: string
    focus_tags: string[]
    assessment_criteria: string[]
    items: Array<{
      problem_slug: string
      title: string
      difficulty: string
      skill_tags: string[]
      suggested_mode: string
      recommendation_reason: string
      order_index: number
    }>
  }>
  validation_report: Record<string, unknown>
  repair_log: Array<Record<string, unknown>>
  uncertainty_notes: string[]
}

export type StudyPlan = {
  id: number
  title: string
  status: string
  active_version_number: number
  created_at?: string
  updated_at?: string
  active_version: StudyPlanVersion
}

export type StudyPlanVersion = {
  id: number
  version_number: number
  status: string
  target_snapshot: Record<string, unknown>
  generation_summary_md: string
  adjustment_summary_md: string
  validation_report?: Record<string, unknown>
  repair_log?: Array<Record<string, unknown>>
  stages: StudyPlanStage[]
  created_at?: string
  activated_at?: string | null
}

export type StudyPlanStage = {
  id: number
  stage_index: number
  title: string
  objective_md: string
  focus_tags: string[]
  assessment_criteria: string[]
  status: string
  items: StudyPlanItem[]
}

export type StudyPlanItem = {
  id: number
  problem_id?: number
  problem_slug: string
  frontend_id: string
  title: string
  translated_title: string
  difficulty: string
  skill_tags: string[]
  suggested_mode: string
  recommendation_reason: string
  status: string
  order_index: number
  locked: boolean
}

export function startGoalCalibration(payload: GoalCalibrationPayload) {
  return requestJson<GoalCalibrationStartResponse>('/api/goal-calibration', {
    method: 'POST',
    body: payload,
  })
}

export function answerGoalFollowup(draftId: number, questionId: string, answer: string) {
  return requestJson<GoalCalibrationStartResponse>(`/api/goal-calibration/${draftId}/followup`, {
    method: 'POST',
    body: { question_id: questionId, answer },
  })
}

export function generatePlanDraft(draftId: number) {
  return requestJson<PlanDraftResponse>(`/api/goal-calibration/${draftId}/generate`, {
    method: 'POST',
  })
}

export function confirmPlan(draftId: number) {
  return requestJson<StudyPlan>('/api/study-plans/confirm', {
    method: 'POST',
    body: { draft_id: draftId },
  })
}

export function getCurrentStudyPlan() {
  return requestJson<StudyPlan>('/api/study-plan/current')
}

export function updatePlanItemStatus(itemId: number, status: 'pending' | 'skipped') {
  return requestJson<StudyPlan>(`/api/study-plan/items/${itemId}`, {
    method: 'PATCH',
    body: { status },
  })
}

export function reorderStageItems(stageId: number, itemIds: number[]) {
  return requestJson<StudyPlan>(`/api/study-plan/stages/${stageId}/reorder`, {
    method: 'POST',
    body: { item_ids: itemIds },
  })
}
