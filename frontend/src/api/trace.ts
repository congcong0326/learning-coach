import { requestJson } from './client'

export type AgentTrace = {
  id: number
  session_id: string | null
  thread_id: string | null
  problem_slug: string | null
  node_name: string
  phase: string | null
  hint_level: number | null
  model_name: string | null
  latency_ms: number | null
  stuck_point: string | null
  should_reveal_solution: boolean | null
  retrieved_chunk_ids: unknown[]
  input_summary: Record<string, unknown>
  output_summary: Record<string, unknown>
  created_at: string
}

export function getAgentTraces(sessionId?: number | null) {
  const query = sessionId ? `?session_id=${sessionId}` : ''
  return requestJson<AgentTrace[]>(`/api/traces${query}`)
}
