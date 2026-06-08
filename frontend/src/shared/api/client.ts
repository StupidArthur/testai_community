import axios, { AxiosError } from 'axios'

export const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截：注入 Token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：401 → 跳转登录
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// ============ Types (local to avoid @ alias issues) ============
export interface User { id: number; username: string; role: 'Admin' | 'Engineer' }
export interface Skill { id: string; name: string; display_name: string; definition: string; created_at: string }
export interface Branch { id: number; skill_id: string; user_id: number; username: string; branch_type: 'master' | 'standard' | 'personal'; created_at: string }
export interface SkillVersion {
  id: string; skill_id: string; branch_id: number; version_num: number;
  role: string; profile: string; background: string; goals: string;
  constraints: string; core_skills: string; workflows: string;
  output_format: string; initialization: string;
  commit_message: string; ai_commit_summary?: string; created_at: string;
}
export interface EvaluateDraftResponse { diff_summary?: string; evaluation?: string; suggestions?: string }
export interface ForkResponse { branch: Branch }

// ============ Auth ============
export const authApi = {
  login: (data: { username: string; password: string }) =>
    apiClient.post<{ access_token: string; user: User }>('/auth/login', data),
  register: (data: { username: string; password: string; role?: string }) =>
    apiClient.post('/auth/register', data),
}

// ============ Users ============
export const usersApi = {
  list: () => apiClient.get<User[]>('/users'),
  resetPassword: (userId: number, data: { new_password: string }) =>
    apiClient.post(`/users/${userId}/reset-password`, data),
}

// ============ Skills ============
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
