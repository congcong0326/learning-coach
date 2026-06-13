import { requestJson } from './client'

export type CurrentUser = {
  id: number
  username: string
  email: string
  display_name: string
}

export type AuthUser = {
  id: number
  username: string
  email: string
  display_name: string
}

export type AuthEnvelope = {
  user: AuthUser
}

export type LoginPayload = {
  login: string
  password: string
}

export type RegisterPayload = {
  username: string
  email: string
  password: string
}

export function getCurrentUser(): Promise<CurrentUser> {
  return requestJson<CurrentUser>('/api/auth/me')
}

export function loginUser(payload: LoginPayload): Promise<AuthEnvelope> {
  return requestJson<AuthEnvelope>('/api/auth/login', {
    method: 'POST',
    body: payload,
  })
}

export function registerUser(payload: RegisterPayload): Promise<AuthEnvelope> {
  return requestJson<AuthEnvelope>('/api/auth/register', {
    method: 'POST',
    body: payload,
  })
}

export function logoutUser(): Promise<{ status: string }> {
  return requestJson<{ status: string }>('/api/auth/logout', {
    method: 'POST',
  })
}
