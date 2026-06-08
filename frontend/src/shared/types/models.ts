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

export interface Skill {
  id: string
  name: string
  display_name: string
  definition: string
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
  branch: {
    id: number
    skill_id: string
    user_id: number
    username: string
    branch_type: 'personal'
    created_at: string
  }
}

export interface MergeRequest {
  source_version_id: string
  commit_message?: string
}

export interface ResetPasswordRequest {
  new_password: string
}
