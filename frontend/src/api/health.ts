import { requestJson } from './client'

export type BackendHealth = {
  status: 'ok'
  service: string
}

export function getBackendHealth(): Promise<BackendHealth> {
  return requestJson<BackendHealth>('/api/health')
}
