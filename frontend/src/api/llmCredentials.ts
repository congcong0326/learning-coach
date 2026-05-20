import { requestJson } from './client'

export type LlmCredentialStatus = 'untested' | 'valid' | 'invalid'

export type LlmCredential = {
  id: number
  provider: 'openai'
  display_name: string
  base_url: string
  api_mode: 'responses'
  model_name: string
  api_key_mask: string
  is_default: boolean
  is_enabled: boolean
  is_preferred: boolean
  is_active: boolean
  failure_count: number
  status: LlmCredentialStatus
  last_used_at: string | null
  last_tested_at: string | null
  last_error: string
}

export type LlmCredentialListResponse = {
  items: LlmCredential[]
}

export type LlmCredentialPayload = {
  display_name: string
  provider: 'openai'
  base_url: string
  api_mode: 'responses'
  model_name: string
  api_key: string
  is_enabled: boolean
  is_preferred: boolean
  is_default?: boolean
}

export type LlmCredentialUpdatePayload = {
  display_name?: string
  base_url?: string
  api_mode?: 'responses'
  model_name?: string
  api_key?: string
  is_enabled?: boolean
}

export type LlmCredentialTestResponse = {
  status: LlmCredentialStatus
  message: string
  model_name: string
}

export function listLlmCredentials(): Promise<LlmCredentialListResponse> {
  return requestJson<LlmCredentialListResponse>('/api/me/llm-credentials')
}

export function createLlmCredential(
  payload: LlmCredentialPayload,
): Promise<LlmCredential> {
  return requestJson<LlmCredential>('/api/me/llm-credentials', {
    method: 'POST',
    body: payload,
  })
}

export function updateLlmCredential(
  id: number,
  payload: LlmCredentialUpdatePayload,
): Promise<LlmCredential> {
  return requestJson<LlmCredential>(`/api/me/llm-credentials/${id}`, {
    method: 'PATCH',
    body: payload,
  })
}

export function setDefaultLlmCredential(id: number): Promise<LlmCredential> {
  return requestJson<LlmCredential>(`/api/me/llm-credentials/${id}/default`, {
    method: 'POST',
  })
}

export function setPreferredLlmCredential(id: number): Promise<LlmCredential> {
  return requestJson<LlmCredential>(
    `/api/me/llm-credentials/${id}/preferred`,
    {
      method: 'POST',
    },
  )
}

export function testLlmCredential(
  id: number,
): Promise<LlmCredentialTestResponse> {
  return requestJson<LlmCredentialTestResponse>(
    `/api/me/llm-credentials/${id}/test`,
    {
      method: 'POST',
    },
  )
}

export function deleteLlmCredential(id: number): Promise<{ status: string }> {
  return requestJson<{ status: string }>(`/api/me/llm-credentials/${id}`, {
    method: 'DELETE',
  })
}
