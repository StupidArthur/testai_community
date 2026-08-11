/**
 * 项目管理 API：Project → Domain → Task → Action
 */
import { apiClient } from './client'

export interface TmProject {
  id: string
  name: string
  description: string | null
  status: string
  created_by: number
  /** 用于「默认选最新创建的 TPT」 */
  created_at?: string
}

export interface TmDomain {
  id: string
  project_id: string
  name: string
  sort_order: number
}

export interface TmUserBrief {
  id: number
  username: string
  real_name?: string
}

export interface TmTask {
  id: string
  project_id: string
  domain_id: string
  title: string
  requirement: string
  lead_id: number
  tester_ids: number[]
  status: string
  created_by: number
  published_at: string | null
  project_name?: string | null
  domain_name?: string | null
  can_edit: boolean
  /** 进行中时可加本周 Action */
  can_add_action?: boolean
}

export interface TmTaskDetail extends TmTask {
  update_logs: {
    id: string
    user_id: number
    summary: string
    detail: string
    created_at?: string
  }[]
}

export interface TmAction {
  id: string
  task_id: string
  project_id: string
  domain_id: string
  week_start: string
  week_key: string
  title: string
  owner_id: number
  test_content: string
  environment: string
  status: string
  source_action_id: string | null
  created_by: number
  published_at: string | null
  due_at: string | null
  /** 用于草稿表单重挂载；后端若未返回可缺省 */
  updated_at?: string | null
  progress_percent: number
  latest_risk: string
  task_title?: string | null
  project_name?: string | null
  domain_name?: string | null
  can_edit_fields: boolean
  can_change_status?: boolean
  /** 进行中且日更进度已达 100% 时可标记完成 */
  can_mark_done?: boolean
  can_daily: boolean
  can_correct: boolean
}

export interface TmActionDetail extends TmAction {
  daily_updates: {
    id: string
    user_id: number
    report_date: string
    progress_percent: number
    risk_blocker: string
    progress_note: string
  }[]
  corrections: {
    id: string
    user_id: number
    note: string
    created_at?: string
  }[]
}

export interface BoardTask {
  task: TmTask
  actions: TmAction[]
  week_progress_avg: number
  /** false=未手填，展示的是 Action 平均推荐值 */
  progress_is_manual?: boolean
  recommended_progress?: number
  risks: string[]
}

export interface BoardSummary {
  task_count: number
  action_count: number
  risk_action_count: number
  progress_avg: number
  draft_count: number
  published_count: number
  done_count?: number
}

export interface WeekHistoryOption {
  week_start: string
  week_end: string
  week_key: string
  label: string
}

export interface WeekInfo {
  week_start: string
  week_end: string
  week_key: string
  weekly_push_at?: string | null
  can_set_week_end?: boolean
  history: WeekHistoryOption[]
}

export interface BoardOut {
  week_start: string
  week_end: string
  week_key: string
  weekly_push_at?: string | null
  summary: BoardSummary
  tasks: BoardTask[]
}

export interface TaskWeekProgress {
  task_id: string
  week_key: string
  progress_percent: number
  recommended_progress: number
  progress_is_manual: boolean
  note: string
  updated_by?: number | null
  updated_at?: string | null
  can_edit: boolean
}

export interface ActionLineageSegment {
  action_id: string
  week_key: string
  week_start: string
  title: string
  status: string
  progress_percent: number
  risks: string[]
  is_current: boolean
}

export interface ActionLineage {
  action_id: string
  weeks_count: number
  segments: ActionLineageSegment[]
}

export const testManageApi = {
  week: () => apiClient.get<WeekInfo>('/test-manage/week'),
  setWeekEnd: (week_end: string) =>
    apiClient.put<WeekInfo>('/test-manage/week/end', { week_end }),
  users: () => apiClient.get<TmUserBrief[]>('/test-manage/users'),
  board: (params?: { project_id?: string; week_start?: string }) =>
    apiClient.get<BoardOut>('/test-manage/board', { params }),

  listProjects: () => apiClient.get<TmProject[]>('/test-manage/projects'),
  createProject: (data: { name: string; description?: string }) =>
    apiClient.post<TmProject>('/test-manage/projects', data),
  updateProject: (id: string, data: { name?: string; description?: string; status?: string }) =>
    apiClient.patch<TmProject>(`/test-manage/projects/${id}`, data),
  archiveProject: (id: string) =>
    apiClient.post<TmProject>(`/test-manage/projects/${id}/archive`),
  deleteProject: (id: string) => apiClient.delete(`/test-manage/projects/${id}`),
  listDomains: (projectId: string) =>
    apiClient.get<TmDomain[]>(`/test-manage/projects/${projectId}/domains`),
  createDomain: (projectId: string, data: { name: string }) =>
    apiClient.post<TmDomain>(`/test-manage/projects/${projectId}/domains`, data),

  listTasks: (params?: { project_id?: string; domain_id?: string }) =>
    apiClient.get<TmTask[]>('/test-manage/tasks', { params }),
  createTask: (data: {
    project_id: string
    domain_id: string
    title: string
    requirement?: string
    lead_id: number
    tester_ids?: number[]
    publish?: boolean
  }) => apiClient.post<TmTask>('/test-manage/tasks', data),
  getTask: (id: string) => apiClient.get<TmTaskDetail>(`/test-manage/tasks/${id}`),
  getTaskWeekProgress: (id: string, week_key?: string) =>
    apiClient.get<TaskWeekProgress>(`/test-manage/tasks/${id}/week-progress`, {
      params: week_key ? { week_key } : undefined,
    }),
  upsertTaskWeekProgress: (
    id: string,
    data: { progress_percent: number; note?: string },
  ) => apiClient.put<TaskWeekProgress>(`/test-manage/tasks/${id}/week-progress`, data),
  updateTask: (
    id: string,
    data: {
      title?: string
      requirement?: string
      lead_id?: number
      tester_ids?: number[]
      status?: string
      change_summary?: string
    },
  ) => apiClient.patch<TmTask>(`/test-manage/tasks/${id}`, data),
  archiveTask: (id: string) =>
    apiClient.post<TmTask>(`/test-manage/tasks/${id}/archive`),
  deleteTask: (id: string) => apiClient.delete(`/test-manage/tasks/${id}`),

  mine: () => apiClient.get<TmAction[]>('/test-manage/actions/mine'),
  cloneCandidates: (taskId: string) =>
    apiClient.get<TmAction[]>(`/test-manage/tasks/${taskId}/clone-candidates`),
  createAction: (data: {
    task_id: string
    title: string
    owner_id?: number
    test_content?: string
    environment?: string
    source_action_id?: string
    publish?: boolean
  }) => apiClient.post<TmAction>('/test-manage/actions', data),
  cloneAction: (id: string, data?: { title?: string; publish?: boolean }) =>
    apiClient.post<TmAction>(`/test-manage/actions/${id}/clone`, data || {}),
  getAction: (id: string) => apiClient.get<TmActionDetail>(`/test-manage/actions/${id}`),
  getActionLineage: (id: string) =>
    apiClient.get<ActionLineage>(`/test-manage/actions/${id}/lineage`),
  updateAction: (
    id: string,
    data: {
      title?: string
      owner_id?: number
      test_content?: string
      environment?: string
      status?: string
    },
  ) => apiClient.patch<TmAction>(`/test-manage/actions/${id}`, data),
  upsertDaily: (
    id: string,
    data: {
      progress_percent: number
      risk_blocker?: string
      progress_note?: string
    },
  ) => apiClient.put(`/test-manage/actions/${id}/daily-updates`, data),
  addCorrection: (id: string, note: string) =>
    apiClient.post(`/test-manage/actions/${id}/corrections`, { note }),
}
