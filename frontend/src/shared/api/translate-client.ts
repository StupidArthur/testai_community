import { triggerUnauthorized } from './client'

export class ApiError extends Error {
  status: number
  body: string
  constructor(status: number, body: string) {
    super(`API Error ${status}: ${body}`)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem('token')
  const headers = new Headers(options?.headers)
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const res = await fetch(path, {
    ...options,
    headers,
  })
  if (res.status === 401) {
    triggerUnauthorized()
    throw new ApiError(401, '未认证')
  }
  if (!res.ok) {
    const body = await res.text()
    throw new ApiError(res.status, body)
  }
  return res.json() as Promise<T>
}

export async function fetchTicket(): Promise<string> {
  const { ticket } = await apiFetch<{ ticket: string; expires_in: number }>(
    '/api/translate/ticket',
    { method: 'POST' },
  )
  return ticket
}
