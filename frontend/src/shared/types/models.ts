// API Type Definitions

export interface User {
  id: number
  username: string
  role: 'Admin' | 'Engineer'
}

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: User
}

export interface RegisterRequest {
  username: string
  password: string
  role?: string
}

export interface SkillCategory {
  id: string
  label: string
  sort_order?: number
  enabled?: boolean
}

export interface Skill {
  id: string
  name: string
  display_name: string
  definition: string
  category: string
  category_label: string
  tags: string[]
  created_at: string
}

export interface Branch {
  id: number
  skill_id: string
  user_id: number
  username: string
  branch_type: 'master' | 'standard' | 'personal'
  created_at: string
}

export interface SkillVersion {
  id: string
  skill_id: string
  branch_id: number
  version_num: number
  revision: number
  source_version_id?: string | null
  version_locator?: string
  role: string
  profile: string
  background: string
  goals: string
  constraints: string
  core_skills: string
  workflows: string
  output_format: string
  initialization: string
  commit_message: string
  ai_commit_summary?: string
  created_at: string
}

export interface EvaluateDraftRequest {
  role: string
  profile: string
  background: string
  goals: string
  constraints: string
  core_skills: string
  workflows: string
  output_format: string
  initialization: string
}

export interface EvaluateDraftResponse {
  diff_summary?: string
  evaluation?: string
  suggestions?: string
}

export interface ForkResponse {
  branch: Branch
  version: SkillVersion
}

export type SkillRefResolveMode = 'pinned' | 'branch_head'

export interface SkillRef {
  resolve_mode: SkillRefResolveMode
  skill_name?: string | null
  version_id?: string | null
  branch_id?: number | null
  branch_type?: 'master' | 'standard' | 'personal' | null
  owner_user_id?: number | null
}

export interface ResolvedSkill {
  skill_id: string
  skill_name: string
  version_id: string
  version_num: number
  revision: number
  branch_id: number
  branch_type: string
  owner_user_id: number
  owner_username: string
  version_locator: string
  source_version_id?: string | null
  payload: string
  fields: Record<string, string>
  resolved_at: string
}

export interface MergeRequest {
  source_version_id: string
  commit_message?: string
}

export interface ResetPasswordRequest {
  new_password: string
}
