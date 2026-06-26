import { apiClient } from './client'

export interface KnowledgeBase {
  id: string
  name: string
  description: string
  user_id: number
  username: string
  document_count: number
  ready_document_count: number
  archived_document_count?: number
  vector_chunk_count?: number
  can_manage: boolean
  created_at: string
  updated_at: string
}

export interface KnowledgeDocument {
  id: string
  kb_id: string
  user_id: number
  username: string
  filename: string
  file_size: number
  status: string
  error?: string | null
  chunk_count: number
  asset_count: number
  can_delete: boolean
  created_at: string
  updated_at: string
}

export interface KnowledgeBaseDetail extends KnowledgeBase {
  documents: KnowledgeDocument[]
}

export interface Citation {
  chunk_id?: string | null
  filename: string
  page?: number | null
  snippet: string
  distance?: number | null
}

export interface ChatMessage {
  id: string
  role: string
  content: string
  citations: Citation[]
  created_at: string
}

export interface ChatResponse {
  answer: string
  citations: Citation[]
  message_id: string
}

export const knowledgeBaseApi = {
  listBases: () => apiClient.get<KnowledgeBase[]>('/knowledge-base/bases'),

  getDefaultBase: () => apiClient.get<KnowledgeBase>('/knowledge-base/bases/default'),

  createBase: (data: { name: string; description?: string }) =>
    apiClient.post<KnowledgeBase>('/knowledge-base/bases', data),

  getBase: (kbId: string) =>
    apiClient.get<KnowledgeBaseDetail>(`/knowledge-base/bases/${kbId}`),

  updateBase: (kbId: string, data: { name?: string; description?: string }) =>
    apiClient.patch<KnowledgeBase>(`/knowledge-base/bases/${kbId}`, data),

  deleteBase: (kbId: string) =>
    apiClient.delete(`/knowledge-base/bases/${kbId}`),

  uploadDocument: (kbId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return apiClient.post<KnowledgeDocument>(`/knowledge-base/bases/${kbId}/documents`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
  },

  deleteDocument: (kbId: string, docId: string) =>
    apiClient.delete(`/knowledge-base/bases/${kbId}/documents/${docId}`),

  chat: (kbId: string, question: string) =>
    apiClient.post<ChatResponse>(`/knowledge-base/bases/${kbId}/chat`, { question }, { timeout: 120000 }),

  listMessages: (kbId: string) =>
    apiClient.get<ChatMessage[]>(`/knowledge-base/bases/${kbId}/messages`),
}
