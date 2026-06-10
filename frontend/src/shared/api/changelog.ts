import { apiClient } from './client'

export interface ChangelogView {
  id: number
  version: string
  title: string
  content: string
  published_by: string | null
  created_at: string
  updated_at: string
}

export interface ChangelogCreate {
  version: string
  title: string
  content: string
}

export interface ChangelogUpdate {
  version?: string
  title?: string
  content?: string
}

export async function listChangelog(limit = 50): Promise<ChangelogView[]> {
  const { data } = await apiClient.get<ChangelogView[]>('/changelog', { params: { limit } })
  return data
}

export async function getChangelog(id: number): Promise<ChangelogView> {
  const { data } = await apiClient.get<ChangelogView>(`/changelog/${id}`)
  return data
}

export async function createChangelog(body: ChangelogCreate): Promise<ChangelogView> {
  const { data } = await apiClient.post<ChangelogView>('/changelog', body)
  return data
}

export async function updateChangelog(id: number, body: ChangelogUpdate): Promise<ChangelogView> {
  const { data } = await apiClient.put<ChangelogView>(`/changelog/${id}`, body)
  return data
}

export async function deleteChangelog(id: number): Promise<void> {
  await apiClient.delete(`/changelog/${id}`)
}
