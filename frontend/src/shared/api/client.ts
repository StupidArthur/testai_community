import axios, { AxiosError } from 'axios'
import type { User, Skill, Branch, SkillVersion, EvaluateDraftResponse, ForkResponse } from '../types/models'

export const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let onUnauthorizedCallback: (() => void) | null = null

export function setOnUnauthorized(cb: () => void) {
  onUnauthorizedCallback = cb
}

export function triggerUnauthorized() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  if (onUnauthorizedCallback) {
    onUnauthorizedCallback()
  } else {
    window.location.href = '/login'
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      triggerUnauthorized()
    }
    return Promise.reject(error)
  }
)

export type { User, Skill, Branch, SkillVersion, EvaluateDraftResponse, ForkResponse }

export const authApi = {
  login: (data: { username: string; password: string }) =>
    apiClient.post<{ access_token: string; user: User }>('/auth/login', data),
  register: (data: { username: string; password?: string; role?: string }) =>
    apiClient.post('/auth/register', data),
}

export const usersApi = {
  list: () => apiClient.get<User[]>('/users'),
  resetPassword: (userId: number, data: { new_password: string }) =>
    apiClient.post(`/users/${userId}/reset-password`, data),
  changeOwnPassword: (data: { old_password: string; new_password: string }) =>
    apiClient.post('/users/me/password', data),
  delete: (userId: number) =>
    apiClient.delete(`/users/${userId}`),
}

export const skillsApi = {
  list: () => apiClient.get<Skill[]>('/skills'),
  get: (skillId: string) => apiClient.get<Skill>(`/skills/${skillId}`),
  create: (data: { name: string; display_name: string; definition?: string }) =>
    apiClient.post<Skill>('/skills', data),
  listBranches: (skillId: string) =>
    apiClient.get<Branch[]>(`/skills/${skillId}/branches`),
  createBranch: (skillId: string) =>
    apiClient.post<Branch>(`/skills/${skillId}/branches`, {}),
  getVersions: (skillId: string, branchId: number) =>
    apiClient.get<SkillVersion[]>(`/skills/${skillId}/branches/${branchId}/versions`),
  createVersion: (skillId: string, branchId: number, data: {
    role: string; profile: string; background: string; goals: string;
    constraints: string; core_skills: string; workflows: string;
    output_format: string; initialization: string; commit_message?: string;
  }) =>
    apiClient.post<SkillVersion>(`/skills/${skillId}/branches/${branchId}/versions`, data),
  evaluateDraft: (skillId: string, branchId: number, data: {
    role: string; profile: string; background: string; goals: string;
    constraints: string; core_skills: string; workflows: string;
    output_format: string; initialization: string;
  }) =>
    apiClient.post<EvaluateDraftResponse>(`/skills/${skillId}/branches/${branchId}/evaluate-draft`, data),
  fork: (skillId: string, branchId: number) =>
    apiClient.post<ForkResponse>(`/skills/${skillId}/branches/${branchId}/fork`),
  merge: (skillId: string, data: { source_version_id: string; commit_message?: string }) =>
    apiClient.post(`/skills/${skillId}/merge`, data),
}
