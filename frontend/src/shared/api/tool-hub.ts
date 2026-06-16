import { apiClient, triggerUnauthorized } from './client'

export type ToolKind = 'client' | 'platform'

export interface ToolCard {
  id: string
  slug: string
  display_name: string
  tool_kind: ToolKind
  tool_type: string
  link_url: string | null
  owner_user_id: number
  owner_username: string
  enabled: boolean
  latest_version: string | null
  has_artifact: boolean
  created_at: string
  updated_at: string
}

export interface ToolVersion {
  id: string
  version_label: string
  manual_md: string
  changelog_md: string
  artifact_filename: string | null
  created_by_user_id: number
  creator_username: string
  created_at: string
}

export interface ToolDetail extends ToolCard {
  combined_markdown: string
  versions: ToolVersion[]
  can_edit: boolean
  can_delete: boolean
}

export interface ToolCreatePayload {
  slug: string
  display_name: string
  tool_kind: ToolKind
  tool_type?: string
  link_url?: string
  version_label?: string
  manual_md: string
  artifact?: File | null
}

export interface ToolVersionPayload {
  version_label: string
  changelog_md: string
  manual_md?: string
  artifact?: File | null
}

function multipartPost<T>(url: string, fields: Record<string, string>, fileField?: { name: string; file: File }): Promise<T> {
  return new Promise((resolve, reject) => {
    const token = localStorage.getItem('token')
    const xhr = new XMLHttpRequest()
    const formData = new FormData()
    Object.entries(fields).forEach(([k, v]) => formData.append(k, v))
    if (fileField) {
      formData.append(fileField.name, fileField.file)
    }

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as T)
      } else if (xhr.status === 401) {
        triggerUnauthorized()
        reject(new Error('未认证'))
      } else {
        try {
          const detail = JSON.parse(xhr.responseText)?.detail
          reject(new Error(detail || `请求失败: ${xhr.status}`))
        } catch {
          reject(new Error(`请求失败: ${xhr.status}`))
        }
      }
    })
    xhr.addEventListener('error', () => reject(new Error('网络错误')))
    xhr.open('POST', url)
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    }
    xhr.send(formData)
  })
}

export const toolHubApi = {
  list: (params?: { tool_kind?: ToolKind; tool_type?: string }) =>
    apiClient.get<ToolCard[]>('/tool-hub/tools', { params }),

  get: (toolId: string) => apiClient.get<ToolDetail>(`/tool-hub/tools/${toolId}`),

  create: (payload: ToolCreatePayload) => {
    const fields: Record<string, string> = {
      slug: payload.slug,
      display_name: payload.display_name,
      tool_kind: payload.tool_kind,
      tool_type: payload.tool_type ?? 'default',
      version_label: payload.version_label ?? '1.0.0',
      manual_md: payload.manual_md,
    }
    if (payload.link_url) {
      fields.link_url = payload.link_url
    }
    return multipartPost<ToolDetail>(
      '/api/tool-hub/tools',
      fields,
      payload.artifact ? { name: 'artifact', file: payload.artifact } : undefined,
    )
  },

  addVersion: (toolId: string, payload: ToolVersionPayload) => {
    const fields: Record<string, string> = {
      version_label: payload.version_label,
      changelog_md: payload.changelog_md,
    }
    if (payload.manual_md) {
      fields.manual_md = payload.manual_md
    }
    return multipartPost<ToolDetail>(
      `/api/tool-hub/tools/${toolId}/versions`,
      fields,
      payload.artifact ? { name: 'artifact', file: payload.artifact } : undefined,
    )
  },

  update: (toolId: string, data: Partial<{ display_name: string; link_url: string; tool_type: string; enabled: boolean }>) =>
    apiClient.put<ToolDetail>(`/tool-hub/tools/${toolId}`, data),

  delete: (toolId: string) => apiClient.delete(`/tool-hub/tools/${toolId}`),

  downloadUrl: (toolId: string) => `/api/tool-hub/tools/${toolId}/download`,
}

export async function downloadToolArtifact(toolId: string, filename?: string) {
  const token = localStorage.getItem('token')
  const res = await fetch(`/api/tool-hub/tools/${toolId}/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (res.status === 401) {
    triggerUnauthorized()
    throw new Error('未认证')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || '下载失败')
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename || 'tool-download'
  a.click()
  URL.revokeObjectURL(url)
}
