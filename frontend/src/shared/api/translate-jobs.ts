import { apiFetch, fetchTicket } from './translate-client'
import { triggerUnauthorized } from './client'

export interface JobView {
  job_id: string
  name: string
  username: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  created_at: string
  updated_at: string
  current_phase: string
  current_step: number
  total_steps: number
  message: string
  queue_ahead: number
  queue_total: number
  error: string | null
}

export interface UploadResponse {
  job_id: string
  status: string
  queue_ahead: number
  queue_total: number
  total_steps: number
  current_step: number
}

export function uploadJob(
  file: File,
  name?: string,
): Promise<UploadResponse> {
  return new Promise((resolve, reject) => {
    const token = localStorage.getItem('token')
    const xhr = new XMLHttpRequest()
    const formData = new FormData()
    formData.append('file', file)
    if (name) {
      formData.append('name', name)
    }

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText))
      } else if (xhr.status === 401) {
        triggerUnauthorized()
        reject(new Error('未认证'))
      } else {
        try {
          const detail = JSON.parse(xhr.responseText)?.detail
          reject(new Error(detail || `上传失败: ${xhr.status}`))
        } catch {
          reject(new Error(`上传失败: ${xhr.status}`))
        }
      }
    })

    xhr.addEventListener('error', () => reject(new Error('Network error')))

    xhr.open('POST', '/api/translate/upload')
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    }
    xhr.send(formData)
  })
}

export async function listJobs(): Promise<JobView[]> {
  return apiFetch<JobView[]>('/api/translate/jobs')
}

export async function getJob(jobId: string): Promise<JobView> {
  return apiFetch<JobView>(`/api/translate/jobs/${encodeURIComponent(jobId)}`)
}

export async function cancelJob(jobId: string): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(`/api/translate/jobs/${encodeURIComponent(jobId)}`, {
    method: 'DELETE',
  })
}

export async function deleteJobRecord(jobId: string): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/api/translate/jobs/${encodeURIComponent(jobId)}/record`, {
    method: 'DELETE',
  })
}

export function getPromptsDownloadUrl(): string {
  const token = localStorage.getItem('token')
  return `/api/translate/prompts${token ? `?token=${encodeURIComponent(token)}` : ''}`
}

export async function getDownloadUrl(jobId: string): Promise<string> {
  const ticket = await fetchTicket()
  return `/api/translate/jobs/${encodeURIComponent(jobId)}/download?ticket=${encodeURIComponent(ticket)}`
}

export async function getFileUrl(jobId: string, path: string): Promise<string> {
  const ticket = await fetchTicket()
  return `/api/translate/jobs/${encodeURIComponent(jobId)}/file?p=${encodeURIComponent(path)}&ticket=${encodeURIComponent(ticket)}`
}
