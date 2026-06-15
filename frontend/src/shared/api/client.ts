import axios, { AxiosError } from 'axios'
import type { User, Skill, SkillCategory, Branch, SkillVersion, EvaluateDraftResponse, ForkResponse, SkillRef, ResolvedSkill, SkillDebugRunRequest, SkillDebugRunResponse } from '../types/models'

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

export type { User, Skill, SkillCategory, Branch, SkillVersion, EvaluateDraftResponse, ForkResponse, SkillRef, ResolvedSkill }

export const authApi = {
  login: (data: { username: string; password: string }) =>
    apiClient.post<{ access_token: string; user: User }>('/auth/login', data),
  currentUser: () => apiClient.get<User>('/auth/current-user'),
  addUser: (data: { username: string; password?: string; role?: string }) =>
    apiClient.post('/auth/add-user', data),
  userList: () => apiClient.get<User[]>('/auth/user-list'),
  resetPassword: (userId: number, data: { new_password: string }) =>
    apiClient.post(`/auth/${userId}/reset-password`, data),
  changePassword: (data: { old_password: string; new_password: string }) =>
    apiClient.put('/auth/password', data),
  deleteUser: (userId: number) =>
    apiClient.delete(`/auth/${userId}`),
}

export const skillsApi = {
  listCategories: () => apiClient.get<SkillCategory[]>('/skills/categories'),
  listCategoriesManage: () => apiClient.get<SkillCategory[]>('/skills/categories/manage'),
  createCategory: (data: { id: string; label: string; sort_order?: number }) =>
    apiClient.post<SkillCategory>('/skills/categories', data),
  updateCategory: (
    categoryId: string,
    data: { label?: string; sort_order?: number; enabled?: boolean },
  ) => apiClient.put<SkillCategory>(`/skills/categories/${categoryId}`, data),
  tagSuggestions: (q?: string) =>
    apiClient.get<{ tags: string[] }>('/skills/tags/suggestions', { params: q ? { q } : {} }),
  list: (category?: string) =>
    apiClient.get<Skill[]>('/skills', { params: category ? { category } : {} }),
  get: (skillId: string) => apiClient.get<Skill>(`/skills/${skillId}`),
  patch: (skillId: string, data: { category?: string; tags?: string[] }) =>
    apiClient.patch<Skill>(`/skills/${skillId}`, data),
  create: (data: {
    name: string
    display_name: string
    definition?: string
    category: string
    tags?: string[]
  }) => apiClient.post<Skill>('/skills', data),
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
  resolve: (ref: SkillRef) =>
    apiClient.post<ResolvedSkill>('/skills/resolve', ref),
  debugRun: (skillId: string, data: SkillDebugRunRequest) =>
    apiClient.post<SkillDebugRunResponse>(`/skills/${skillId}/debug/run`, data, { timeout: 120000 }),
}
