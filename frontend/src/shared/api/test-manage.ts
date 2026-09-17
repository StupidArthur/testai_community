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

export interface TmSubtask {
  sid: string
  name: string
  content: string
  /** 开发人员（自由文本标签） */
  dev_members?: string[]
  /** 产品人员（自由文本标签） */
  pm_members?: string[]
}

export interface TmTask {
  id: string
  project_id: string
  domain_id: string
  title: string
  requirement: string
  /** 系统需求编号（如 SR-TPT-00017） */
  sr_code?: string
  /** 关联初始需求编号（多个逗号分隔） */
  ir_codes?: string
  /** 子类/模块 */
  module?: string
  /** 需求类型：功能 / 性能… */
  req_type?: string
  /** 优先级：高 / 中 / 低 */
  priority?: string
  /** 变更标识：原始 / 变更… */
  change_flag?: string
  /** 验收标准 */
  acceptance_criteria?: string
  /** 验证人 */
  verifier_id?: number | null
  /** 验证时间 */
  verified_at?: string | null
  /** 验证结果：通过 / 不通过 / 未验证 */
  verify_result?: string
  /** 备注 */
  remark?: string
  /** 子需求明细（JSON 列存储；未删除项） */
  subtasks?: TmSubtask[]
  /** 开发人员（自由文本标签） */
  dev_members?: string[]
  /** 产品人员（自由文本标签） */
  pm_members?: string[]
  lead_id: number
  tester_ids: number[]
  /** 测试状态：published / done / cancelled */
  status: string
  /** 需求进展 */
  req_stage?: string
  expected_handover_at?: string | null
  actual_handover_at?: string | null
  test_started_at?: string | null
  expected_test_end_at?: string | null
  test_ended_at?: string | null
  stage_summary?: string
  created_by: number
  published_at: string | null
  project_name?: string | null
  domain_name?: string | null
  can_edit: boolean
  can_edit_req_stage?: boolean
  /** 测试中时可加本周 Action */
  can_add_action?: boolean
  /** 子需求/Action 管理入口（宽松模式全员；严格模式管理员/Task 负责人） */
  can_manage_children?: boolean
  /** 前端合并计算的状态（req_stage + status） */
  display_status?: string
  display_status_label?: string
}

export interface TmTaskDetail extends TmTask {
  updated_at?: string | null
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
  /** 关联子需求名称（必填） */
  subtask_name: string
  owner_id: number
  /** 开发人员（自由文本标签） */
  dev_members?: string[]
  /** 产品人员（自由文本标签） */
  pm_members?: string[]
  test_content: string
  environment: string
  status: string
  /** 完成时间（仅 done 状态有值） */
  completed_at?: string | null
  source_action_id: string | null
  /** 周继承带入的起始进度（无日更时的当前进度；周报增量 = 当前 - 起始） */
  initial_progress?: number
  created_by: number
  published_at: string | null
  due_at: string | null
  /** 创建时间；卡片列表「先创建的在前」排序用 */
  created_at?: string | null
  /** 用于草稿表单重挂载；后端若未返回可缺省 */
  updated_at?: string | null
  progress_percent: number
  latest_risk: string
  /** 最新日更是否勾选「构成阻塞」 */
  latest_is_blocking?: boolean
  /** 今日是否已日更 */
  has_daily_today?: boolean
  /** 历史总览：跨周聚合的延续周数（>1 表示延续多周） */
  span_count?: number
  /** 历史总览：跨周聚合的首次开始时间 */
  first_created_at?: string | null
  task_title?: string | null
  project_name?: string | null
  domain_name?: string | null
  can_edit_fields: boolean
  can_change_status?: boolean
  /** 进行中且日更进度已达 100% 时可标记完成 */
  can_mark_done?: boolean
  can_daily: boolean
  can_correct: boolean
  /** 发布后可由管理员/Task 负责人更改负责人（强制留痕） */
  can_change_owner?: boolean
  /** 开发/产品人员编辑入口（宽松模式全员；严格模式管理员/Task 负责人） */
  can_edit_members?: boolean
  /** 发布后可由管理员/Task 负责人修正子需求关联（可清空为未关联，强制留痕） */
  can_relink?: boolean
  /** 数据删除入口（宽松模式）：可删除该 Action */
  can_delete?: boolean
  /** 数据删除入口（宽松模式）：可删除该 Action 的指定日期日报 */
  can_delete_daily?: boolean
}

export interface TmActionDetail extends TmAction {
  daily_updates: {
    id: string
    user_id: number
    report_date: string
    progress_percent: number
    risk_blocker: string
    is_blocking?: boolean
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
  history: WeekHistoryOption[]
}

export interface BoardOut {
  week_start: string
  week_end: string
  week_key: string
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
  daily_updates: {
    id: string
    user_id: number
    report_date: string
    progress_percent: number
    risk_blocker: string
    is_blocking?: boolean
    progress_note: string
  }[]
  corrections: {
    id: string
    user_id: number
    note: string
    created_at?: string
  }[]
  is_current: boolean
  owner_id?: number
  /** 该周实例当前是否可写今日日更（切周场景下归属周为 true） */
  can_daily?: boolean
}

export interface ActionLineage {
  action_id: string
  weeks_count: number
  segments: ActionLineageSegment[]
}

export const testManageApi = {
  week: () => apiClient.get<WeekInfo>('/test-manage/week'),
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
    sr_code?: string
    ir_codes?: string
    module: string
    req_type?: string
    priority?: string
    change_flag?: string
    acceptance_criteria?: string
    verifier_id?: number | null
    verified_at?: string | null
    verify_result?: string
    remark?: string
    subtasks?: { name: string; content?: string; dev_members?: string[]; pm_members?: string[] }[]
    dev_members?: string[]
    pm_members?: string[]
    lead_id: number
    tester_ids?: number[]
    publish?: boolean
    req_stage?: string
    expected_handover_at?: string | null
    actual_handover_at?: string | null
    test_started_at?: string | null
    expected_test_end_at?: string | null
    test_ended_at?: string | null
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
      sr_code?: string
      ir_codes?: string
      module?: string
      req_type?: string
      priority?: string
      change_flag?: string
      acceptance_criteria?: string
      verifier_id?: number | null
      verified_at?: string | null
      verify_result?: string
      remark?: string
      lead_id?: number
      tester_ids?: number[]
      status?: string
      change_summary?: string
      dev_members?: string[]
      pm_members?: string[]
      req_stage?: string
      expected_handover_at?: string | null
      actual_handover_at?: string | null
      test_started_at?: string | null
      expected_test_end_at?: string | null
      test_ended_at?: string | null
    },
  ) => apiClient.patch<TmTask>(`/test-manage/tasks/${id}`, data),
  archiveTask: (id: string) =>
    apiClient.post<TmTask>(`/test-manage/tasks/${id}/archive`),
  deleteTask: (id: string) => apiClient.delete(`/test-manage/tasks/${id}`),

  mine: () => apiClient.get<TmAction[]>('/test-manage/actions/mine'),

  /** 历史 Action 总览：已完成（跨全部周）；manager/admin 看全部，其他仅自己 */
  historyActions: (params?: {
    keyword?: string
    task_id?: string
    owner_id?: number
    date_from?: string
    date_to?: string
  }) => apiClient.get<TmAction[]>('/test-manage/actions/history', { params }),

  // ── Subtask（Task 内子需求，JSON 列存储）──────────────────
  addSubtask: (
    taskId: string,
    data: { name: string; content?: string; dev_members?: string[]; pm_members?: string[] },
  ) => apiClient.post<TmTask>(`/test-manage/tasks/${taskId}/subtasks`, data),
  updateSubtask: (
    taskId: string,
    sid: string,
    data: { name?: string; content?: string; dev_members?: string[]; pm_members?: string[] },
  ) => apiClient.patch<TmTask>(`/test-manage/tasks/${taskId}/subtasks/${sid}`, data),
  deleteSubtask: (taskId: string, sid: string) =>
    apiClient.delete<TmTask>(`/test-manage/tasks/${taskId}/subtasks/${sid}`),
  moveSubtask: (taskId: string, sid: string, targetTaskId: string) =>
    apiClient.post<TmTask>(`/test-manage/tasks/${taskId}/subtasks/${sid}/move`, {
      target_task_id: targetTaskId,
    }),

  createAction: (data: {
    task_id: string
    title: string
    subtask_name: string
    owner_id?: number
    dev_members?: string[]
    pm_members?: string[]
    test_content?: string
    environment?: string
    publish?: boolean
  }) => apiClient.post<TmAction>('/test-manage/actions', data),
  getAction: (id: string) => apiClient.get<TmActionDetail>(`/test-manage/actions/${id}`),
  getActionLineage: (id: string) =>
    apiClient.get<ActionLineage>(`/test-manage/actions/${id}/lineage`),
  updateAction: (
    id: string,
    data: {
      title?: string
      subtask_name?: string
      owner_id?: number
      dev_members?: string[]
      pm_members?: string[]
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
      is_blocking?: boolean
      progress_note?: string
    },
  ) => apiClient.put(`/test-manage/actions/${id}/daily-updates`, data),
  deleteAction: (id: string) => apiClient.delete(`/test-manage/actions/${id}`),
  deleteDaily: (id: string, reportDate: string) =>
    apiClient.delete(`/test-manage/actions/${id}/daily-updates/${reportDate}`),
  addCorrection: (id: string, note: string) =>
    apiClient.post(`/test-manage/actions/${id}/corrections`, { note }),
}
