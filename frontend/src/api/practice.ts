import { requestJson } from './client'

export type HintLevel = 'questioning' | 'direction' | 'key_hint' | 'reflection'
export type UserIntent =
  | 'describe_idea'
  | 'stuck'
  | 'request_hint'
  | 'code_review'
  | 'submit_feedback'
  | 'request_summary'
  | 'unknown'
export type SubmissionResult = 'ac' | 'wa' | 'tle' | 're' | 'mle' | 'ce' | 'unknown'
export type CodeSnapshotSource =
  | 'paste'
  | 'manual_save'
  | 'before_review'
  | 'before_submit'
  | 'final'

export type PracticeEvent = {
  id: number
  event_type: string
  role: string
  phase: string
  intent: UserIntent | null
  content_md: string
  payload: Record<string, unknown>
  hint_level: HintLevel | null
  visible_hint_gear: HintLevel | null
  created_at: string
}

export type PracticeSession = {
  id: number
  study_plan_id: number
  problem_id: number
  problem_slug: string
  latest_plan_version_id: number
  latest_plan_item_id: number
  training_mode: string
  phase: string
  status: string
  current_hint_level: HintLevel
  visible_hint_gear: HintLevel
  max_hint_level_used: HintLevel | null
  attempt_count: number
  final_result: SubmissionResult | null
  profile_snapshot: {
    id: number | null
    version: string
    source: string
    confidence: string
    overall_level: string
    preferred_training_mode: string
    weak_stuck_points: string[]
    strong_skill_tags: string[]
    weak_skill_tags: string[]
    recent_summary: string
    hint_policy_hint: string
    coach_strategy: Record<string, unknown>
    evidence: Array<Record<string, unknown>>
  }
  events: PracticeEvent[]
  created_at: string
  updated_at: string
}

export type PracticeMessagePayload = {
  intent?: UserIntent
  content_md: string
  requested_hint_level?: HintLevel | null
}

export type PracticeMessageResponse = {
  event_id: number
  run_id: number
  session_id: number
}

export type CodeSnapshotPayload = {
  language: 'c' | 'go' | 'python3' | 'javascript' | 'java'
  code_text: string
  source?: CodeSnapshotSource
  client_revision: number
}

export type CodeSnapshotResponse = {
  id: number
  language: string
  source: string
  client_revision: number
  code_hash: string
  created_at: string
}

export type SubmissionFeedbackPayload = {
  code_snapshot_id?: number | null
  result: SubmissionResult
  failed_case_text?: string
  error_message?: string
  runtime_ms?: number | null
  memory_kb?: number | null
}

export type SubmissionFeedbackResponse = {
  id: number
  result: SubmissionResult
  event_id: number
  code_snapshot_id: number | null
  created_at: string
}

export function createPracticeSessionForItem(itemId: number) {
  return requestJson<PracticeSession>(`/api/study-plan/items/${itemId}/practice-session`, {
    method: 'POST',
  })
}

export function getPracticeSession(sessionId: number) {
  return requestJson<PracticeSession>(`/api/practice-sessions/${sessionId}`)
}

export function getPracticeEvents(sessionId: number) {
  return requestJson<PracticeEvent[]>(`/api/practice-sessions/${sessionId}/events`)
}

export function sendPracticeMessage(sessionId: number, payload: PracticeMessagePayload) {
  return requestJson<PracticeMessageResponse>(`/api/practice-sessions/${sessionId}/messages`, {
    method: 'POST',
    body: payload,
  })
}

export function saveCodeSnapshot(sessionId: number, payload: CodeSnapshotPayload) {
  return requestJson<CodeSnapshotResponse>(
    `/api/practice-sessions/${sessionId}/code-snapshots`,
    {
      method: 'POST',
      body: payload,
    },
  )
}

export function submitLeetCodeFeedback(
  sessionId: number,
  payload: SubmissionFeedbackPayload,
) {
  return requestJson<SubmissionFeedbackResponse>(
    `/api/practice-sessions/${sessionId}/submission-feedback`,
    {
      method: 'POST',
      body: payload,
    },
  )
}

export function requestPracticeSummary(sessionId: number) {
  return requestJson<Record<string, unknown>>(`/api/practice-sessions/${sessionId}/summary`, {
    method: 'POST',
  })
}
