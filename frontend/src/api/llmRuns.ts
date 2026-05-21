import { requestJson } from './client'

export type LlmRunKind =
  | 'goal_followup'
  | 'goal_plan_generate'
  | 'study_plan_adjustment'
  | 'coach_message'
  | 'code_review'
  | 'reflection'

export type LlmRunStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'canceled'

export type CreateLlmRunRequest = {
  kind: LlmRunKind
  payload: Record<string, unknown>
}

export type CreateLlmRunResponse = {
  run_id: number
  kind: LlmRunKind
  status: LlmRunStatus
  stage: string
  stream_url: string
}

export type LlmRunStatusResponse = {
  run_id: number
  kind: LlmRunKind
  status: LlmRunStatus
  stage: string
  display_text_md: string
  result: unknown | null
  error_code: string | null
  error_message: string | null
  can_retry: boolean
  created_at?: string
  finished_at?: string | null
}

export function createLlmRun(kind: LlmRunKind, payload: Record<string, unknown>) {
  return requestJson<CreateLlmRunResponse>('/api/llm-runs', {
    method: 'POST',
    body: { kind, payload },
  })
}

export function getLlmRunStatus(runId: number) {
  return requestJson<LlmRunStatusResponse>(`/api/llm-runs/${runId}`)
}

export function cancelLlmRun(runId: number) {
  return requestJson<LlmRunStatusResponse>(`/api/llm-runs/${runId}/cancel`, {
    method: 'POST',
  })
}
