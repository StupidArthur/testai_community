import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Collapse,
  DatePicker,
  Dropdown,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Pagination,
  Popconfirm,
  Popover,
  Progress,
  Segmented,
  Select,
  Slider,
  Space,
  Table,
  Tabs,
  Tag,
  Timeline,
  Tooltip,
  Typography,
} from 'antd'
import type { MenuProps } from 'antd'
import type { FormInstance } from 'antd'
import {
  DeleteOutlined,
  DownOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  SendOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import {
  testManageApi,
  type BoardTask,
  type TmAction,
  type TmActionDetail,
  type TmTask,
  type TmSubtask,
} from '../../shared/api/test-manage'
import { useCurrentUser, isTmAdmin } from '../../shared/hooks/useAuth'
import WeekScreenTab from './WeekScreenTab'
import WeekViewSwitcher, { type WeekViewMode } from './WeekViewSwitcher'
import TestManageHelpDrawer from './TestManageHelpDrawer'
import {
  countBoardTasksByScope,
  emptyActionDescription,
  filterBoardTasksByScope,
  formatTaskSaveTip,
  pickDefaultProjectId,
  shouldHighlightEmptyTask,
  shouldShowAddActionButton,
  sortActionCardsForList,
} from '../utils/boardUi'
import { isMissingDailyToday, isBlockingFlag, dailyContextWeekKey, isWeekSwitchDay } from '../utils/screenFilters'
import {
  DISPLAY_STATUS_OPTIONS,
  DISPLAY_STATUS_TAG_COLOR,
  displayStatusLabel,
  displayStatusTagColor,
  splitDisplayStatus,
} from '../utils/displayStatus'
import {
  REQ_STAGE_OPTIONS,
  REQ_STAGE_PENDING_DEV,
  REQ_STAGE_TESTING,
} from '../utils/reqStage'
import './ProjectManagePage.css'
import './tmSheet.css'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

const STATUS_LABEL: Record<string, { color: string; text: string }> = {
  draft: { color: 'default', text: '草稿' },
  published: { color: 'processing', text: '进行中' },
  done: { color: 'success', text: '完成' },
  cancelled: { color: 'default', text: '归档' },
}

/** 与后端 TASK_REQUIREMENT_MAX_CHARS 保持一致 */
const TASK_REQUIREMENT_MAX_CHARS = 5000
/** 与后端 TEXT_FIELD_MAX_CHARS / ACTION_ENVIRONMENT_MAX_CHARS 对齐 */
const TEXT_FIELD_MAX_CHARS = 1000
const ACTION_ENVIRONMENT_MAX_CHARS = 300
/** 工作台 Task 列表分页可选每页条数 */
const BOARD_TASK_PAGE_SIZE_OPTIONS = [10, 20, 50] as const
const BOARD_TASK_PAGE_SIZE_DEFAULT = BOARD_TASK_PAGE_SIZE_OPTIONS[0]
/** Action 卡片：每页最多 20（宽屏约 4 列 × 5 行） */
const ACTION_CARD_PAGE_SIZE = 20

function userSelectOptions(users: { id: number; username: string; real_name?: string }[]) {
  return users.map((u) => ({
    value: Number(u.id),
    label: (u.real_name || '').trim()
      ? `${u.real_name}（${u.username}）`
      : u.username?.trim()
        ? u.username
        : `用户#${u.id}`,
  }))
}

function formatWeekShort(weekStart?: string, weekEnd?: string) {
  if (!weekStart) return ''
  const s = new Date(weekStart)
  const e = weekEnd ? new Date(weekEnd) : null
  const a = `${s.getMonth() + 1}.${s.getDate()}`
  if (!e) return a
  return `${a}-${e.getMonth() + 1}.${e.getDate()}`
}

/** 业务「今天」（UTC+8，与后端 today_tm 对齐），YYYY-MM-DD；offsetDays=-1 即昨天 */
function tmTodayYmd(offsetDays = 0) {
  return new Date(Date.now() + 8 * 3600_000 + offsetDays * 86_400_000).toISOString().slice(0, 10)
}

/** 日更记录日期标签：今天/昨天，其余 MM-DD */
function dailyDateLabel(reportDate?: string) {
  const ymd = (reportDate || '').slice(0, 10)
  if (!ymd) return ''
  if (ymd === tmTodayYmd()) return '今天'
  if (ymd === tmTodayYmd(-1)) return '昨天'
  return ymd.slice(5)
}

/**
 * 项目管理：默认看板（周×Task），Task/Action 创建与日更。
 */
export default function ProjectManagePage() {
  const user = useCurrentUser()
  const tmAdmin = isTmAdmin(user)
  const qc = useQueryClient()
  /** 必须用 App.useApp()，静态 message/Modal 在 AntdApp 下经常不弹出 */
  const { message, modal } = App.useApp()

  const [projectId, setProjectId] = useState<string | undefined>()
  /** 仅首次自动选默认项目；用户清空后不再回填 */
  const didAutoPickProjectRef = useRef(false)
  /** 今日 | 本周 | 历史（历史只读，下拉最多 10 周） */
  const [weekMode, setWeekMode] = useState<WeekViewMode>('today')
  const [historyWeekStart, setHistoryWeekStart] = useState<string | undefined>()
  const [taskModal, setTaskModal] = useState(false)
  const [createTaskForm] = Form.useForm()
  const [projectModal, setProjectModal] = useState(false)
  const [domainModal, setDomainModal] = useState(false)
  const [detailActionId, setDetailActionId] = useState<string | null>(null)
  const [editTaskId, setEditTaskId] = useState<string | null>(null)
  /** 从 Task 抽屉触发：关闭抽屉并在对应卡片展开 inline 新建 Action 表单 */
  const [inlineAddTaskId, setInlineAddTaskId] = useState<string | null>(null)
  /** Task 抽屉：默认只读写进度；点小「编辑」才改基本信息 */
  const [taskInfoEditing, setTaskInfoEditing] = useState(false)
  /** Task 抽屉模式：详情（信息）| 进度（只写本周进度） */
  const [taskDrawerFocus, setTaskDrawerFocus] = useState<'progress' | 'detail'>('progress')
  /** 保存后递增，强制 Task 编辑表单用新 initialValues 重挂载 */
  const [taskFormEpoch, setTaskFormEpoch] = useState(0)
  /** Task 抽屉内成功提示（Toast 被挡时仍可见） */
  const [taskSaveTip, setTaskSaveTip] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('screen')
  const [helpOpen, setHelpOpen] = useState(false)
  /** 工作台：我的 Task（负责人）| 全部 */
  const [boardTaskScope, setBoardTaskScope] = useState<'mine' | 'all'>('mine')
  /** 工作台筛选：负责人 */
  const [boardLeadFilter, setBoardLeadFilter] = useState<number | null>(null)
  /** 工作台筛选：领域 */
  const [boardDomainFilter, setBoardDomainFilter] = useState<string | null>(null)
  /** 工作台筛选：状态 */
  const [boardStatusFilter, setBoardStatusFilter] = useState<string | null>(null)
  /** 工作台筛选：Task 名称模糊搜索 */
  const [boardTaskNameKeyword, setBoardTaskNameKeyword] = useState<string>('')
  /** 工作台筛选：子类/模块 */
  const [boardModuleFilter, setBoardModuleFilter] = useState<string | null>(null)
  /** 工作台筛选：需求类型 */
  const [boardReqTypeFilter, setBoardReqTypeFilter] = useState<string | null>(null)
  /** 工作台筛选：优先级 */
  const [boardPriorityFilter, setBoardPriorityFilter] = useState<string | null>(null)
  /** 工作台筛选：变更标识 */
  const [boardChangeFlagFilter, setBoardChangeFlagFilter] = useState<string | null>(null)
  /** 工作台筛选：验证人 */
  const [boardVerifierFilter, setBoardVerifierFilter] = useState<number | null>(null)
  /** 工作台筛选：验证结果 */
  const [boardVerifyResultFilter, setBoardVerifyResultFilter] = useState<string | null>(null)
  /** 工作台筛选：SR 编号模糊搜索 */
  const [boardSrCodeKeyword, setBoardSrCodeKeyword] = useState<string>('')
  /** 工作台筛选：子需求/Action 名称模糊搜索 */
  const [boardActionKeyword, setBoardActionKeyword] = useState<string>('')
  /** 工作台筛选：开发/产品人员模糊搜索（匹配 Task/子需求/Action 三级人员标签） */
  const [boardMemberKeyword, setBoardMemberKeyword] = useState<string>('')
  /** 工作台排序：字段（名称/SR编号/进度）+ 方向（升序/降序） */
  const [boardSortField, setBoardSortField] = useState<'title' | 'sr_code' | 'progress'>('title')
  const [boardSortOrder, setBoardSortOrder] = useState<'asc' | 'desc'>('asc')
  /** 工作台 Task 分页 */
  const [boardTaskPage, setBoardTaskPage] = useState(1)
  const [boardTaskPageSize, setBoardTaskPageSize] = useState<number>(BOARD_TASK_PAGE_SIZE_DEFAULT)
  const [mineActionPage, setMineActionPage] = useState(1)
  /** 子需求移动弹窗（移到同项目下其他 Task） */
  const [moveSubtaskModal, setMoveSubtaskModal] = useState<{
    open: boolean
    sid: string
    name: string
    targetId?: string
  }>({ open: false, sid: '', name: '' })

  const { data: week } = useQuery({
    queryKey: ['tm-week'],
    queryFn: async () => (await testManageApi.week()).data,
  })

  const upsertTaskWeekProgressMut = useMutation({
    mutationFn: async (p: { id: string; progress_percent: number; note?: string }) =>
      (await testManageApi.upsertTaskWeekProgress(p.id, {
        progress_percent: p.progress_percent,
        note: p.note,
      })).data,
    onSuccess: () => {
      message.success('本周 Task 进度已保存')
      void qc.invalidateQueries({ queryKey: ['tm-task-week-progress'] })
      void qc.invalidateQueries({ queryKey: ['tm-board'] })
      // 同步刷新 Task 详情（弹窗内周进度区依赖 taskDetail.req_stage/can_edit）
      void qc.invalidateQueries({ queryKey: ['tm-task'] })
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '保存周进度失败'),
  })

  const {
    data: users = [],
    isLoading: usersLoading,
    isError: usersError,
    refetch: refetchUsers,
  } = useQuery({
    queryKey: ['tm-users'],
    queryFn: async () => {
      const res = await testManageApi.users()
      const list = Array.isArray(res.data) ? res.data : []
      return list.map((u) => ({
        id: Number(u.id),
        username: String(u.username || ''),
        real_name: String(u.real_name || ''),
      }))
    },
  })

  const userOptions = useMemo(() => userSelectOptions(users), [users])

  const userName = useMemo(() => {
    const m = new Map<number, string>()
    for (const u of users) {
      const rn = (u.real_name || '').trim()
      m.set(u.id, rn || u.username)
    }
    return (id: number) => m.get(id) || `#${id}`
  }, [users])

  const { data: projects = [] } = useQuery({
    queryKey: ['tm-projects'],
    queryFn: async () => (await testManageApi.listProjects()).data,
  })

  /** 大屏/工作台默认项目：与公开 /tm-screen 共用 pickDefaultProjectId；用户清空后不再回填 */
  useEffect(() => {
    if (didAutoPickProjectRef.current) return
    if (projectId) {
      didAutoPickProjectRef.current = true
      return
    }
    if (!projects.length) return
    const pick = pickDefaultProjectId(projects)
    if (pick) {
      setProjectId(pick)
      didAutoPickProjectRef.current = true
    }
  }, [projects, projectId])

  const historyOptions = week?.history ?? []

  useEffect(() => {
    if (weekMode !== 'history') return
    if (!historyOptions.length) return
    const stillValid = historyOptions.some((h) => h.week_start === historyWeekStart)
    if (!stillValid) {
      setHistoryWeekStart(historyOptions[0].week_start)
    }
  }, [weekMode, historyOptions, historyWeekStart])

  const boardWeekStart = weekMode === 'history' ? historyWeekStart : undefined
  const viewingHistory = weekMode === 'history'
  const viewingToday = weekMode === 'today'

  const handleWeekModeChange = (mode: WeekViewMode) => {
    setWeekMode(mode)
    if (mode === 'history' && !historyWeekStart && historyOptions[0]) {
      setHistoryWeekStart(historyOptions[0].week_start)
    }
  }

  const { data: board, isLoading: boardLoading } = useQuery({
    queryKey: ['tm-board', projectId, boardWeekStart || 'current'],
    queryFn: async () =>
      (
        await testManageApi.board({
          ...(projectId ? { project_id: projectId } : {}),
          ...(boardWeekStart ? { week_start: boardWeekStart } : {}),
        })
      ).data,
    enabled: weekMode === 'current' || weekMode === 'today' || !!boardWeekStart,
    staleTime: 0,
    refetchOnMount: 'always',
  })

  const { data: mine = [] } = useQuery({
    queryKey: ['tm-mine'],
    queryFn: async () => (await testManageApi.mine()).data,
  })

  const { data: domains = [] } = useQuery({
    queryKey: ['tm-domains', projectId],
    queryFn: async () =>
      projectId ? (await testManageApi.listDomains(projectId)).data : [],
    enabled: !!projectId && (taskModal || domainModal),
  })

  /** 仅一个领域时自动选中，减少新建 Task 漏选 */
  useEffect(() => {
    if (!taskModal) return
    if (domains.length === 1) {
      createTaskForm.setFieldsValue({ domain_id: domains[0].id })
    }
  }, [taskModal, domains, createTaskForm])

  const { data: actionDetail } = useQuery({
    queryKey: ['tm-action', detailActionId],
    queryFn: async () => (await testManageApi.getAction(detailActionId!)).data,
    enabled: !!detailActionId,
  })

  const { data: taskDetail } = useQuery({
    queryKey: ['tm-task', editTaskId],
    queryFn: async () => (await testManageApi.getTask(editTaskId!)).data,
    enabled: !!editTaskId,
  })

  /** 本周 Task 周进度（周报口径；未填则后端返回 Action 平均推荐值） */
  const { data: taskWeekProgress } = useQuery({
    queryKey: ['tm-task-week-progress', editTaskId, week?.week_key || ''],
    queryFn: async () => (await testManageApi.getTaskWeekProgress(editTaskId!)).data,
    enabled: !!editTaskId && !viewingHistory && taskDrawerFocus === 'progress',
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['tm-board'] })
    void qc.invalidateQueries({ queryKey: ['tm-mine'] })
    void qc.invalidateQueries({ queryKey: ['tm-action'] })
    void qc.invalidateQueries({ queryKey: ['tm-task'] })
    void qc.invalidateQueries({ queryKey: ['tm-task-week-progress'] })
    void qc.invalidateQueries({ queryKey: ['tm-projects'] })
  }

  const createProjectMut = useMutation({
    mutationFn: (name: string) => testManageApi.createProject({ name }),
    onSuccess: (r) => {
      message.success('项目已创建')
      setProjectModal(false)
      setProjectId(r.data.id)
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '失败'),
  })

  const archiveTaskMut = useMutation({
    mutationFn: (id: string) => testManageApi.archiveTask(id),
    onSuccess: () => {
      message.success('Task 已归档（看板不再显示）')
      if (editTaskId) {
        setEditTaskId(null)
        setTaskInfoEditing(false)
      }
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '归档 Task 失败'),
  })

  const deleteTaskMut = useMutation({
    mutationFn: (id: string) => testManageApi.deleteTask(id),
    onSuccess: () => {
      message.success('Task 已永久删除')
      if (editTaskId) {
        setEditTaskId(null)
        setTaskInfoEditing(false)
      }
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '删除 Task 失败'),
  })

  const createDomainMut = useMutation({
    mutationFn: (name: string) => testManageApi.createDomain(projectId!, { name }),
    onSuccess: () => {
      message.success('领域已创建')
      setDomainModal(false)
      void qc.invalidateQueries({ queryKey: ['tm-domains'] })
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '失败'),
  })

  const createTaskMut = useMutation({
    mutationFn: testManageApi.createTask,
    onSuccess: () => {
      message.success('Task 已保存')
      setTaskModal(false)
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '失败'),
  })

  const updateTaskMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof testManageApi.updateTask>[1] }) =>
      testManageApi.updateTask(id, data),
    onSuccess: (res) => {
      const t = res.data
      const lead = t?.lead_id != null ? userName(Number(t.lead_id)) : ''
      const tip = formatTaskSaveTip(lead)
      setTaskSaveTip(tip)
      message.success(tip)
      setTaskFormEpoch((n) => n + 1)
      setTaskInfoEditing(false)
      invalidate()
    },
    onError: (e: any) => {
      setTaskSaveTip(null)
      message.error(e?.response?.data?.detail || '更新失败')
    },
  })

  const createActionMut = useMutation({
    mutationFn: testManageApi.createAction,
    onSuccess: () => {
      message.success('Action 已保存')
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '失败'),
  })

  /** 子需求 CRUD（JSON 列存 Task 上；改名同步刷 Action，软删连带取消未完成 Action） */
  const addSubtaskMut = useMutation({
    mutationFn: (p: {
      taskId: string
      name: string
      content?: string
      dev_members?: string[]
      pm_members?: string[]
    }) =>
      testManageApi.addSubtask(p.taskId, {
        name: p.name,
        content: p.content,
        dev_members: p.dev_members,
        pm_members: p.pm_members,
      }),
    onSuccess: () => {
      message.success('子需求已添加')
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '添加失败'),
  })

  /** 子需求人员维护（信息性字段，所有角色当前周均可改） */
  const updateSubtaskMut = useMutation({
    mutationFn: (p: {
      taskId: string
      sid: string
      data: { dev_members?: string[]; pm_members?: string[] }
    }) => testManageApi.updateSubtask(p.taskId, p.sid, p.data),
    onSuccess: () => {
      message.success('子需求人员已更新')
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '更新失败'),
  })

  const deleteSubtaskMut = useMutation({
    mutationFn: (p: { taskId: string; sid: string }) =>
      testManageApi.deleteSubtask(p.taskId, p.sid),
    onSuccess: () => {
      message.success('子需求已删除（关联未完成 Action 已取消）')
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '删除失败'),
  })

  const moveSubtaskMut = useMutation({
    mutationFn: (p: { taskId: string; sid: string; targetTaskId: string }) =>
      testManageApi.moveSubtask(p.taskId, p.sid, p.targetTaskId),
    onSuccess: () => {
      message.success('子需求已移动（关联 Action 一并随迁）')
      setMoveSubtaskModal({ open: false, sid: '', name: '' })
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '移动失败'),
  })

  /** 工作台列表：归档 Task 默认不展示（与归档确认文案一致） */
  const boardTasksScoped = useMemo(() => {
    const list = (board?.tasks || []).filter((bt) => bt.task.status !== 'cancelled')
    const uid = user?.id != null ? Number(user.id) : null
    let scoped = filterBoardTasksByScope(list, boardTaskScope, uid)
    if (boardLeadFilter != null) {
      // 负责人筛选：匹配 Task 负责人 / 子需求人员 / Action 负责人或人员
      const leadName = userName(boardLeadFilter)
      const nameHit = (arr?: string[]) =>
        (arr || []).some((m) => (m || '').trim() === leadName)
      scoped = scoped.filter(
        (bt) =>
          Number(bt.task.lead_id) === boardLeadFilter ||
          (bt.task.subtasks || []).some(
            (s) => nameHit(s.dev_members) || nameHit(s.pm_members),
          ) ||
          (bt.actions || []).some(
            (a) =>
              Number(a.owner_id) === boardLeadFilter ||
              nameHit(a.dev_members) ||
              nameHit(a.pm_members),
          ),
      )
    }
    if (boardDomainFilter) {
      scoped = scoped.filter((bt) => bt.task.domain_id === boardDomainFilter)
    }
    if (boardStatusFilter) {
      scoped = scoped.filter((bt) => bt.task.display_status === boardStatusFilter)
    }
    if (boardModuleFilter) {
      scoped = scoped.filter((bt) => (bt.task.module || '') === boardModuleFilter)
    }
    if (boardReqTypeFilter) {
      scoped = scoped.filter((bt) => (bt.task.req_type || '') === boardReqTypeFilter)
    }
    if (boardPriorityFilter) {
      scoped = scoped.filter((bt) => (bt.task.priority || '') === boardPriorityFilter)
    }
    if (boardChangeFlagFilter) {
      scoped = scoped.filter((bt) => (bt.task.change_flag || '') === boardChangeFlagFilter)
    }
    if (boardVerifierFilter != null) {
      scoped = scoped.filter((bt) => Number(bt.task.verifier_id ?? -1) === boardVerifierFilter)
    }
    if (boardVerifyResultFilter) {
      scoped = scoped.filter((bt) => (bt.task.verify_result || '') === boardVerifyResultFilter)
    }
    const srKw = boardSrCodeKeyword.trim().toLowerCase()
    if (srKw) {
      scoped = scoped.filter((bt) => (bt.task.sr_code || '').toLowerCase().includes(srKw))
    }
    const kw = boardTaskNameKeyword.trim().toLowerCase()
    if (kw) {
      scoped = scoped.filter((bt) => (bt.task.title || '').toLowerCase().includes(kw))
    }
    const actionKw = boardActionKeyword.trim().toLowerCase()
    if (actionKw) {
      // 模糊匹配子需求名或 Action 名称，命中任一即保留该 Task 卡片
      scoped = scoped.filter((bt) =>
        (bt.actions || []).some(
          (a) =>
            (a.title || '').toLowerCase().includes(actionKw) ||
            (a.subtask_name || '').toLowerCase().includes(actionKw),
        ),
      )
    }
    const memberKw = boardMemberKeyword.trim().toLowerCase()
    if (memberKw) {
      // 模糊匹配 Task / 子需求 / Action 任一级的开发或产品人员标签
      const hit = (arr?: string[]) =>
        (arr || []).some((m) => (m || '').toLowerCase().includes(memberKw))
      scoped = scoped.filter(
        (bt) =>
          hit(bt.task.dev_members) ||
          hit(bt.task.pm_members) ||
          (bt.task.subtasks || []).some((s) => hit(s.dev_members) || hit(s.pm_members)) ||
          (bt.actions || []).some((a) => hit(a.dev_members) || hit(a.pm_members)),
      )
    }
    // 排序：名称（默认）/ SR 编号 / 进度；方向升序/降序（无 SR 编号固定排最后，不随方向翻转）
    const dir = boardSortOrder === 'desc' ? -1 : 1
    const sorted = [...scoped].sort((a, b) => {
      if (boardSortField === 'sr_code') {
        const sa = (a.task.sr_code || '').trim()
        const sb = (b.task.sr_code || '').trim()
        if (!sa || !sb) {
          // 无 SR 编号的固定排最后（不随排序方向翻转）
          if (!sa && !sb) return (a.task.title || '').localeCompare(b.task.title || '', 'zh') * dir
          return sa ? -1 : 1
        }
        return sa.localeCompare(sb, 'zh') * dir
      }
      if (boardSortField === 'progress') {
        const diff = (a.week_progress_avg || 0) - (b.week_progress_avg || 0)
        if (diff !== 0) return diff * dir
        return (a.task.title || '').localeCompare(b.task.title || '', 'zh') * dir
      }
      return (a.task.title || '').localeCompare(b.task.title || '', 'zh') * dir
    })
    return sorted
  }, [
    board?.tasks,
    boardTaskScope,
    user?.id,
    boardLeadFilter,
    boardDomainFilter,
    boardStatusFilter,
    boardModuleFilter,
    boardReqTypeFilter,
    boardPriorityFilter,
    boardChangeFlagFilter,
    boardVerifierFilter,
    boardVerifyResultFilter,
    boardSrCodeKeyword,
    boardTaskNameKeyword,
    boardActionKeyword,
    boardMemberKeyword,
    boardSortField,
    boardSortOrder,
  ])

  /** 筛选下拉选项：从当前看板数据去重（只列实际存在的负责人/领域/状态） */
  const boardFilterOptions = useMemo(() => {
    const list = (board?.tasks || []).filter((bt) => bt.task.status !== 'cancelled')
    const leads = new Map<number, string>()
    const domainsMap = new Map<string, string>()
    const statusSet = new Set<string>()
    const moduleSet = new Set<string>()
    const reqTypeSet = new Set<string>()
    const prioritySet = new Set<string>()
    const changeFlagSet = new Set<string>()
    const verifiers = new Map<number, string>()
    const verifyResultSet = new Set<string>()
    for (const bt of list) {
      const lid = Number(bt.task.lead_id)
      if (!leads.has(lid)) leads.set(lid, userName(lid))
      // 负责人筛选项同时聚合 Action 负责人（子需求/Action 人员为自由文本，不进下拉）
      for (const a of bt.actions || []) {
        const oid = Number(a.owner_id)
        if (!leads.has(oid)) leads.set(oid, userName(oid))
      }
      if (!domainsMap.has(bt.task.domain_id)) {
        domainsMap.set(bt.task.domain_id, bt.task.domain_name || '未分领域')
      }
      const ds = (bt.task.display_status || '').trim()
      if (ds) statusSet.add(ds)
      const mod = (bt.task.module || '').trim()
      if (mod) moduleSet.add(mod)
      const rt = (bt.task.req_type || '').trim()
      if (rt) reqTypeSet.add(rt)
      const pr = (bt.task.priority || '').trim()
      if (pr) prioritySet.add(pr)
      const cf = (bt.task.change_flag || '').trim()
      if (cf) changeFlagSet.add(cf)
      if (bt.task.verifier_id != null) {
        const vid = Number(bt.task.verifier_id)
        if (!verifiers.has(vid)) verifiers.set(vid, userName(vid))
      }
      const vr = (bt.task.verify_result || '').trim()
      if (vr) verifyResultSet.add(vr)
    }
    const leadOpts = [...leads.entries()]
      .sort((a, b) => a[1].localeCompare(b[1], 'zh'))
      .map(([value, label]) => ({ value, label }))
    const domainOpts = [...domainsMap.entries()]
      .sort((a, b) => a[1].localeCompare(b[1], 'zh'))
      .map(([value, label]) => ({ value, label }))
    const labelMap = new Map(DISPLAY_STATUS_OPTIONS.map((o) => [o.value, o.label]))
    const statusOpts = [...statusSet]
      .map((v) => ({ value: v, label: labelMap.get(v) || v }))
      .sort((a, b) => a.label.localeCompare(b.label, 'zh'))
    const sortByZh = (arr: string[]) => arr.sort((a, b) => a.localeCompare(b, 'zh'))
    const moduleOpts = sortByZh([...moduleSet]).map((v) => ({ value: v, label: v }))
    const reqTypeOpts = sortByZh([...reqTypeSet]).map((v) => ({ value: v, label: v }))
    const priorityOpts = sortByZh([...prioritySet]).map((v) => ({ value: v, label: v }))
    const changeFlagOpts = sortByZh([...changeFlagSet]).map((v) => ({ value: v, label: v }))
    const verifierOpts = [...verifiers.entries()]
      .sort((a, b) => a[1].localeCompare(b[1], 'zh'))
      .map(([value, label]) => ({ value, label }))
    const verifyResultOpts = sortByZh([...verifyResultSet]).map((v) => ({ value: v, label: v }))
    return {
      leadOpts,
      domainOpts,
      statusOpts,
      moduleOpts,
      reqTypeOpts,
      priorityOpts,
      changeFlagOpts,
      verifierOpts,
      verifyResultOpts,
    }
  }, [board?.tasks, userName])

  /** 工作台筛选是否有生效条件（空态文案用） */
  const boardFiltersActive =
    boardLeadFilter != null ||
    !!boardDomainFilter ||
    !!boardStatusFilter ||
    !!boardTaskNameKeyword.trim() ||
    !!boardModuleFilter ||
    !!boardReqTypeFilter ||
    !!boardPriorityFilter ||
    !!boardChangeFlagFilter ||
    boardVerifierFilter != null ||
    !!boardVerifyResultFilter ||
    !!boardSrCodeKeyword.trim() ||
    !!boardActionKeyword.trim() ||
    !!boardMemberKeyword.trim()

  /** 筛选/周切换后回到第 1 页 */
  useEffect(() => {
    setBoardTaskPage(1)
  }, [
    boardTaskScope,
    projectId,
    boardWeekStart,
    weekMode,
    boardLeadFilter,
    boardDomainFilter,
    boardStatusFilter,
    boardTaskNameKeyword,
    boardModuleFilter,
    boardReqTypeFilter,
    boardPriorityFilter,
    boardChangeFlagFilter,
    boardVerifierFilter,
    boardVerifyResultFilter,
    boardSrCodeKeyword,
    boardActionKeyword,
    boardMemberKeyword,
  ])

  /** 切项目后领域选项变化，清掉已失效的领域筛选 */
  useEffect(() => {
    setBoardDomainFilter(null)
  }, [projectId])

  /** 删减后当前页超出范围时回退 */
  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(boardTasksScoped.length / boardTaskPageSize) || 1)
    if (boardTaskPage > maxPage) setBoardTaskPage(maxPage)
  }, [boardTasksScoped.length, boardTaskPageSize, boardTaskPage])

  const boardTasksPaged = useMemo(() => {
    const start = (boardTaskPage - 1) * boardTaskPageSize
    return boardTasksScoped.slice(start, start + boardTaskPageSize)
  }, [boardTasksScoped, boardTaskPage, boardTaskPageSize])

  useEffect(() => {
    setMineActionPage(1)
  }, [weekMode, boardWeekStart])

  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(mine.length / ACTION_CARD_PAGE_SIZE) || 1)
    if (mineActionPage > maxPage) setMineActionPage(maxPage)
  }, [mine.length, mineActionPage])

  const mineSorted = useMemo(() => sortActionCardsForList(mine), [mine])

  const mineActionsPaged = useMemo(() => {
    const start = (mineActionPage - 1) * ACTION_CARD_PAGE_SIZE
    return mineSorted.slice(start, start + ACTION_CARD_PAGE_SIZE)
  }, [mineSorted, mineActionPage])

  const boardScopeCounts = useMemo(() => {
    const list = (board?.tasks || []).filter((bt) => bt.task.status !== 'cancelled')
    const uid = user?.id != null ? Number(user.id) : null
    return countBoardTasksByScope(list, uid)
  }, [board?.tasks, user?.id])

  const dailyMut = useMutation({
    mutationFn: (p: {
      id: string
      progress_percent: number
      risk_blocker: string
      is_blocking: boolean
      progress_note: string
    }) =>
      testManageApi.upsertDaily(p.id, {
        progress_percent: p.progress_percent,
        risk_blocker: p.risk_blocker,
        is_blocking: p.is_blocking,
        progress_note: p.progress_note,
      }),
    onSuccess: () => {
      message.success('日更已保存')
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '失败'),
  })

  const correctMut = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) =>
      testManageApi.addCorrection(id, note),
    onSuccess: async () => {
      message.success('追加成功')
      await qc.invalidateQueries({ queryKey: ['tm-action'] })
      void qc.invalidateQueries({ queryKey: ['tm-board'] })
      void qc.invalidateQueries({ queryKey: ['tm-mine'] })
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '追加失败'),
  })

  const publishActionMut = useMutation({
    mutationFn: (id: string) => testManageApi.updateAction(id, { status: 'published' }),
    onSuccess: () => {
      message.success('已发布（字段锁定）')
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '失败'),
  })

  const updateActionMut = useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string
      data: Parameters<typeof testManageApi.updateAction>[1]
    }) => testManageApi.updateAction(id, data),
    onSuccess: (res) => {
      const a = res.data
      const owner = a?.owner_id != null ? userName(Number(a.owner_id)) : ''
      message.success(owner ? `Action 已保存 · 负责人：${owner}` : 'Action 已保存')
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '保存失败'),
  })

  const deleteActionMut = useMutation({
    mutationFn: (id: string) => testManageApi.deleteAction(id),
    onSuccess: () => {
      message.success('Action 已删除（含其日报与更正记录）')
      setDetailActionId(null)
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '删除失败'),
  })

  const deleteDailyMut = useMutation({
    mutationFn: ({ id, reportDate }: { id: string; reportDate: string }) =>
      testManageApi.deleteDaily(id, reportDate),
    onSuccess: () => {
      message.success('日报已删除（已自动记入更正记录）')
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '删除失败'),
  })

  const screenTab = {
    key: 'screen',
    label: viewingToday ? '今日大屏' : viewingHistory ? '历史周大屏' : '本周大屏',
    children: (
      <WeekScreenTab
        board={board}
        loading={boardLoading}
        projects={projects}
        projectId={projectId}
        onProjectChange={setProjectId}
        weekMode={weekMode}
        onWeekModeChange={handleWeekModeChange}
        historyOptions={historyOptions}
        historyWeekStart={historyWeekStart}
        onHistoryWeekStartChange={setHistoryWeekStart}
        userName={userName}
        onOpenAction={(id) => setDetailActionId(id)}
      />
    ),
  }

  const boardTab = {
    key: 'board',
    label: '工作台',
    children: (
      <div>
        <div className="tm-week-summary tm-week-summary--slim">
          <div className="tm-week-summary__meta">
            <Space wrap size={12} align="center">
              <Text strong>{viewingHistory ? '历史周' : '本周'}</Text>
              <Text type="secondary">
                {formatWeekShort(board?.week_start || week?.week_start, board?.week_end || week?.week_end)}
              </Text>
              <WeekViewSwitcher
                mode={weekMode === 'today' ? 'current' : weekMode}
                onModeChange={handleWeekModeChange}
                historyOptions={historyOptions}
                historyWeekStart={historyWeekStart}
                onHistoryWeekStartChange={setHistoryWeekStart}
                testIdPrefix="tm-board-week"
                showToday={false}
                showPipeline={false}
              />
            </Space>
            {!viewingHistory && (board?.week_end || week?.week_end) ? (
              <Space wrap size={8} style={{ marginTop: 8 }} align="center">
                <Text type="warning" data-testid="tm-week-end-hint">
                  每周三 17:00 将发送周报，请大家在 16:55 完成周 Task 的更新，Action 请于每天 19:50
                  前更新
                </Text>
              </Space>
            ) : null}
          </div>
          <div className="tm-week-summary__stats tm-week-summary__stats--slim">
            <div className="tm-week-summary__stat">
              <span className="tm-week-summary__value">{board?.summary?.task_count ?? 0}</span>
              <span className="tm-week-summary__label">Task</span>
            </div>
            <div
              className={`tm-week-summary__stat${(board?.summary?.risk_action_count ?? 0) > 0 ? ' tm-week-summary__stat--risk' : ''}`}
            >
              <span className="tm-week-summary__value">{board?.summary?.risk_action_count ?? 0}</span>
              <span className="tm-week-summary__label">阻塞</span>
            </div>
            <div
              className="tm-week-summary__stat tm-week-summary__stat--progress"
              title="各 Task 周进度的算术平均：已手填用 Task 周进度，未手填用该 Task 下 Action 平均"
            >
              <span className="tm-week-summary__value">{board?.summary?.progress_avg ?? 0}%</span>
              <span className="tm-week-summary__label">Task 均进度</span>
            </div>
          </div>
        </div>

        {viewingHistory ? (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message="历史周只读，编辑请切回本周"
          />
        ) : null}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 8, marginBottom: 16 }}>
          <Select
            style={{ width: '100%' }}
            value={boardTaskScope}
            onChange={setBoardTaskScope}
            options={[
              { value: 'mine', label: `我的Task（${boardScopeCounts.mine}）` },
              { value: 'all', label: `全部（${boardScopeCounts.all}）` },
            ]}
            data-testid="tm-scope-select"
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="项目"
            style={{ width: '100%' }}
            value={projectId}
            onChange={setProjectId}
            options={projects.map((p) => ({ value: p.id, label: p.name }))}
            data-testid="tm-project-filter"
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="负责人"
            style={{ width: '100%' }}
            value={boardLeadFilter ?? undefined}
            onChange={(v) => setBoardLeadFilter(v ?? null)}
            options={boardFilterOptions.leadOpts}
            data-testid="tm-lead-filter"
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="领域"
            style={{ width: '100%' }}
            value={boardDomainFilter ?? undefined}
            onChange={(v) => setBoardDomainFilter(v ?? null)}
            options={boardFilterOptions.domainOpts}
            data-testid="tm-domain-filter"
          />
          <Select
            allowClear
            placeholder="状态"
            style={{ width: '100%' }}
            value={boardStatusFilter ?? undefined}
            onChange={(v) => setBoardStatusFilter(v ?? null)}
            options={boardFilterOptions.statusOpts}
            data-testid="tm-status-filter"
          />
          <BoardSearchInput
            placeholder="搜索Task名称"
            value={boardTaskNameKeyword}
            onChange={setBoardTaskNameKeyword}
            testId="tm-task-name-search"
          />
          <BoardSearchInput
            placeholder="SR编号"
            value={boardSrCodeKeyword}
            onChange={setBoardSrCodeKeyword}
            testId="tm-sr-code-search"
          />
          <BoardSearchInput
            placeholder="搜索子需求/Action名称"
            value={boardActionKeyword}
            onChange={setBoardActionKeyword}
            testId="tm-action-name-search"
          />
          <BoardSearchInput
            placeholder="搜索开发/产品人员"
            value={boardMemberKeyword}
            onChange={setBoardMemberKeyword}
            testId="tm-member-search"
          />
          <Select
            style={{ width: '100%' }}
            value={boardSortField}
            onChange={setBoardSortField}
            options={[
              { value: 'title', label: '按名称排序' },
              { value: 'sr_code', label: '按SR编号排序' },
              { value: 'progress', label: '按进度排序' },
            ]}
            data-testid="tm-sort-field"
          />
          <Segmented
            block
            value={boardSortOrder}
            onChange={(v) => setBoardSortOrder(v as 'asc' | 'desc')}
            options={[
              { value: 'asc', label: '升序' },
              { value: 'desc', label: '降序' },
            ]}
            data-testid="tm-sort-order"
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="子类/模块"
            style={{ width: '100%' }}
            value={boardModuleFilter ?? undefined}
            onChange={(v) => setBoardModuleFilter(v ?? null)}
            options={boardFilterOptions.moduleOpts}
            data-testid="tm-module-filter"
          />
          <Select
            allowClear
            placeholder="需求类型"
            style={{ width: '100%' }}
            value={boardReqTypeFilter ?? undefined}
            onChange={(v) => setBoardReqTypeFilter(v ?? null)}
            options={boardFilterOptions.reqTypeOpts}
            data-testid="tm-req-type-filter"
          />
          <Select
            allowClear
            placeholder="优先级"
            style={{ width: '100%' }}
            value={boardPriorityFilter ?? undefined}
            onChange={(v) => setBoardPriorityFilter(v ?? null)}
            options={boardFilterOptions.priorityOpts}
            data-testid="tm-priority-filter"
          />
          <Select
            allowClear
            placeholder="变更标识"
            style={{ width: '100%' }}
            value={boardChangeFlagFilter ?? undefined}
            onChange={(v) => setBoardChangeFlagFilter(v ?? null)}
            options={boardFilterOptions.changeFlagOpts}
            data-testid="tm-change-flag-filter"
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="验证人"
            style={{ width: '100%' }}
            value={boardVerifierFilter ?? undefined}
            onChange={(v) => setBoardVerifierFilter(v ?? null)}
            options={boardFilterOptions.verifierOpts}
            data-testid="tm-verifier-filter"
          />
          <Select
            allowClear
            placeholder="验证结果"
            style={{ width: '100%' }}
            value={boardVerifyResultFilter ?? undefined}
            onChange={(v) => setBoardVerifyResultFilter(v ?? null)}
            options={boardFilterOptions.verifyResultOpts}
            data-testid="tm-verify-result-filter"
          />
          {tmAdmin && !viewingHistory ? (
            <Dropdown
              menu={{
                items: [
                  { key: 'project', label: '项目' },
                  { key: 'domain', label: '领域', disabled: !projectId },
                  { key: 'task', label: 'Task' },
                ],
                onClick: ({ key }) => {
                  if (key === 'project') setProjectModal(true)
                  if (key === 'domain') setDomainModal(true)
                  if (key === 'task') {
                    if (!projectId && projects[0]) setProjectId(projects[0].id)
                    setTaskModal(true)
                  }
                },
              }}
            >
              <Button type="primary" icon={<PlusOutlined />} style={{ width: '100%' }} data-testid="tm-btn-create-menu">
                新建 <DownOutlined />
              </Button>
            </Dropdown>
          ) : (
            <span />
          )}
        </div>

        {boardLoading ? (
          <Text type="secondary">加载中…</Text>
        ) : !boardTasksScoped.length ? (
          <Empty
            description={
              boardFiltersActive
                ? '没有符合筛选条件的 Task，可清空筛选条件后重试。'
                : viewingHistory
                  ? '该历史周暂无 Action 记录。'
                  : boardTaskScope === 'mine'
                    ? '暂无你负责的 Task。可切到「全部」查看，或新建 Task。'
                    : '本周暂无 Task。可新建 Task，或在已有 Task 上添加 Action。'
            }
          />
        ) : (
          <div className="tm-board-list">
            {boardTasksPaged.map((bt) => (
              <BoardTaskCard
                key={bt.task.id}
                bt={bt}
                readOnly={viewingHistory}
                leadFilter={boardLeadFilter}
                highlightEmpty={shouldHighlightEmptyTask({
                  viewingHistory,
                  actionCount: bt.actions.length,
                  canAddAction: !!bt.task.can_add_action,
                })}
                userName={userName}
                onOpenAction={(id) => setDetailActionId(id)}
                onEditTask={(focus) => {
                  setTaskSaveTip(null)
                  setTaskDrawerFocus(focus)
                  setTaskInfoEditing(false)
                  setEditTaskId(bt.task.id)
                }}
                forceInlineAdd={inlineAddTaskId === bt.task.id}
                onInlineAddDone={() => setInlineAddTaskId(null)}
                onCreateAction={(values, publish) =>
                  createActionMut.mutate({ task_id: bt.task.id, ...values, publish })
                }
                onCreateSubtask={(name, content, devMembers, pmMembers) =>
                  addSubtaskMut.mutate({
                    taskId: bt.task.id,
                    name,
                    content,
                    dev_members: devMembers,
                    pm_members: pmMembers,
                  })
                }
                createActionLoading={createActionMut.isPending}
                createSubtaskLoading={addSubtaskMut.isPending}
                users={users}
                onPublishAction={(id) => publishActionMut.mutate(id)}
                canQuickDaily={(a) => tmAdmin || Number(a.owner_id) === Number(user?.id)}
                onDaily={(p) => dailyMut.mutate(p)}
                dailyLoading={dailyMut.isPending}
                onArchiveTask={() => {
                  modal.confirm({
                    title: `归档 Task「${bt.task.title}」？`,
                    content: '归档后看板默认不再显示；下属 Action 仍保留在库中。',
                    okText: '归档',
                    onOk: () => archiveTaskMut.mutateAsync(bt.task.id),
                  })
                }}
                onDeleteTask={() => {
                  modal.confirm({
                    title: `永久删除 Task「${bt.task.title}」？`,
                    content: '将删除该 Task 下全部 Action、日更等数据，且不可恢复。',
                    okText: '永久删除',
                    okType: 'danger',
                    onOk: () => deleteTaskMut.mutateAsync(bt.task.id),
                  })
                }}
                archiveLoading={archiveTaskMut.isPending}
                deleteLoading={deleteTaskMut.isPending}
              />
            ))}
            <div className="tm-board-pagination" data-testid="tm-board-pagination">
              <Pagination
                current={boardTaskPage}
                pageSize={boardTaskPageSize}
                total={boardTasksScoped.length}
                showSizeChanger
                pageSizeOptions={[...BOARD_TASK_PAGE_SIZE_OPTIONS].map(String)}
                showTotal={(t) => `共 ${t} 个 Task`}
                onChange={(page, size) => {
                  setBoardTaskPage(page)
                  if (size !== boardTaskPageSize) {
                    setBoardTaskPageSize(size)
                    setBoardTaskPage(1)
                  }
                }}
              />
            </div>
          </div>
        )}
      </div>
    ),
  }

  const mineTab = {
    key: 'mine',
    label: '我的 Action',
    children: mine.length === 0 ? (
        <Empty description="暂无你负责的 Action（仅显示本周负责人为你的）" />
    ) : (
      <div>
        <div className="tm-action-grid" data-testid="tm-mine-action-grid">
          {mineActionsPaged.map((a) => {
            const missingDaily = isMissingDailyToday(a)
            const canQuickDaily =
              a.status === 'published' &&
              !viewingHistory &&
              (tmAdmin || Number(a.owner_id) === Number(user?.id))
            return (
            <Card
              key={a.id}
              size="small"
              className="tm-action-card"
              onClick={() => setDetailActionId(a.id)}
              title={a.title}
              extra={
                <Space size={4} wrap onClick={(e) => e.stopPropagation()}>
                  {missingDaily ? (
                    <Tag color="gold" data-testid="tm-mine-missing-daily-tag">
                      今日未日更
                    </Tag>
                  ) : null}
                  <Tag color={STATUS_LABEL[a.status]?.color}>{STATUS_LABEL[a.status]?.text}</Tag>
                </Space>
              }
              data-testid={`tm-action-card-${a.id}`}
              data-action-title={a.title}
            >
              <Progress percent={a.progress_percent} size="small" />
              <Text type="secondary" className="tm-action-card__owner">
                {a.task_title}
              </Text>
              {a.latest_risk && (
                <Paragraph
                  type="danger"
                  className="tm-action-card__risk"
                  ellipsis={{ rows: 3, tooltip: a.latest_risk }}
                  style={{ marginBottom: 0 }}
                >
                  <WarningOutlined /> {a.latest_risk}
                </Paragraph>
              )}
            </Card>
            )
          })}
        </div>
        {mine.length > ACTION_CARD_PAGE_SIZE ? (
          <div className="tm-board-pagination" data-testid="tm-mine-action-pagination">
            <Pagination
              current={mineActionPage}
              pageSize={ACTION_CARD_PAGE_SIZE}
              total={mine.length}
              showSizeChanger={false}
              showTotal={(t) => `共 ${t} 个 Action`}
              onChange={(page) => setMineActionPage(page)}
            />
          </div>
        ) : null}
      </div>
    ),
  }

  return (
    <div className={`project-manage-page${activeTab === 'screen' ? ' project-manage-page--screen' : ''}`}>
      <div className="project-manage-page__header">
        <div className="project-manage-page__header-main">
          <Title level={3} style={{ margin: 0 }}>
            项目管理
          </Title>
        </div>
        <Button
          type="link"
          icon={<QuestionCircleOutlined />}
          onClick={() => setHelpOpen(true)}
          data-testid="tm-help-btn"
        >
          使用说明
        </Button>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[screenTab, boardTab, mineTab]}
        data-testid="tm-main-tabs"
      />

      <TestManageHelpDrawer open={helpOpen} onClose={() => setHelpOpen(false)} />

      {/* 新建 Task */}
      <Modal
        title="新建 Task"
        open={taskModal}
        onCancel={() => setTaskModal(false)}
        footer={null}
        destroyOnClose
        width={560}
        centered
        styles={{ body: { maxHeight: 'calc(100vh - 140px)', overflowY: 'auto' } }}
        afterOpenChange={(open) => {
          if (open) void refetchUsers()
        }}
      >
        <div className="tm-sheet tm-sheet--modal">
          {usersError ? (
            <p className="tm-sheet__tip tm-sheet__tip--warn" style={{ marginBottom: 12 }}>
              用户列表加载失败{' '}
              <Button type="link" size="small" onClick={() => void refetchUsers()}>
                重试
              </Button>
            </p>
          ) : null}
          {!usersError && !usersLoading && users.length === 0 ? (
            <p className="tm-sheet__tip tm-sheet__tip--warn" style={{ marginBottom: 12 }}>
              暂无用户，请先在用户管理创建账号
            </p>
          ) : null}
          <Form
            form={createTaskForm}
            layout="vertical"
            className="tm-sheet__form"
            data-testid="tm-modal-new-task"
            initialValues={{
              project_id: projectId,
              lead_id: user?.id != null ? Number(user.id) : undefined,
              publish: true,
              req_stage: REQ_STAGE_PENDING_DEV,
            }}
            onFinish={(v) =>
              createTaskMut.mutate({
                project_id: v.project_id,
                domain_id: v.domain_id,
                title: v.title,
                requirement: v.requirement || '',
                sr_code: v.sr_code || '',
                ir_codes: v.ir_codes || '',
                module: v.module,
                req_type: v.req_type || '',
                priority: v.priority || '',
                change_flag: v.change_flag || '',
                acceptance_criteria: v.acceptance_criteria || '',
                verifier_id: v.verifier_id ?? null,
                verified_at: v.verified_at || null,
                verify_result: v.verify_result || '',
                remark: v.remark || '',
                lead_id: Number(v.lead_id),
                req_stage: v.req_stage,
                dev_members: v.dev_members || [],
                pm_members: v.pm_members || [],
                publish: true,
              })
            }
          >
            <p className="tm-sheet__tip" style={{ marginBottom: 12 }}>
              创建后可在卡片内直接维护子需求（subtask）与 Action
            </p>
            <Form.Item name="project_id" label="项目" rules={[{ required: true, message: '请选择项目' }]}>
              <Select
                showSearch
                optionFilterProp="label"
                options={projects.map((p) => ({ value: p.id, label: p.name }))}
                onChange={(v) => {
                  setProjectId(v)
                  createTaskForm.setFieldsValue({ domain_id: undefined })
                }}
                data-testid="tm-task-project"
              />
            </Form.Item>
            <Form.Item name="domain_id" label="领域" rules={[{ required: true, message: '请选择领域' }]}>
              <Select
                showSearch
                optionFilterProp="label"
                options={domains.map((d) => ({ value: d.id, label: d.name }))}
                placeholder={projectId ? '选择领域' : '请先选择项目'}
                disabled={!projectId}
                data-testid="tm-task-domain"
              />
            </Form.Item>
            <Form.Item name="title" label="标题" rules={[{ required: true }]}>
              <Input
                placeholder="Task 主题"
                maxLength={300}
                showCount
                data-testid="tm-task-title"
              />
            </Form.Item>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 12 }}>
              <Form.Item name="sr_code" label="SR 编号">
                <Input placeholder="如 SR-TPT-00017" maxLength={64} data-testid="tm-task-sr-code" />
              </Form.Item>
              <Form.Item name="ir_codes" label="关联 IR 编号">
                <Input placeholder="多个用逗号分隔" maxLength={256} data-testid="tm-task-ir-codes" />
              </Form.Item>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 12 }}>
              <Form.Item
                name="module"
                label="子类/模块"
                rules={[{ required: true, message: '请填写子类/模块' }]}
              >
                <Input placeholder="如 回路优化" maxLength={100} data-testid="tm-task-module" />
              </Form.Item>
              <Form.Item name="req_type" label="需求类型">
                <Select
                  allowClear
                  options={[
                    { value: '功能', label: '功能' },
                    { value: '性能', label: '性能' },
                    { value: '接口', label: '接口' },
                    { value: '安全', label: '安全' },
                    { value: '可靠性', label: '可靠性' },
                  ]}
                  placeholder="可选"
                  data-testid="tm-task-req-type"
                />
              </Form.Item>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 12 }}>
              <Form.Item name="priority" label="优先级">
                <Select
                  allowClear
                  options={[
                    { value: '高', label: '高' },
                    { value: '中', label: '中' },
                    { value: '低', label: '低' },
                  ]}
                  placeholder="可选"
                  data-testid="tm-task-priority"
                />
              </Form.Item>
              <Form.Item name="change_flag" label="变更标识">
                <Select
                  allowClear
                  options={[
                    { value: '原始', label: '原始' },
                    { value: '变更', label: '变更' },
                  ]}
                  placeholder="可选"
                  data-testid="tm-task-change-flag"
                />
              </Form.Item>
            </div>
            <Form.Item
              name="requirement"
              label="需求内容"
              rules={[
                {
                  max: TASK_REQUIREMENT_MAX_CHARS,
                  message: `最多 ${TASK_REQUIREMENT_MAX_CHARS} 字`,
                },
              ]}
            >
              <TextArea
                rows={3}
                placeholder="可选"
                maxLength={TASK_REQUIREMENT_MAX_CHARS}
                showCount
                data-testid="tm-task-requirement"
              />
            </Form.Item>
            <Form.Item name="acceptance_criteria" label="验收标准">
              <TextArea rows={2} placeholder="可选" maxLength={4000} data-testid="tm-task-acceptance" />
            </Form.Item>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 12 }}>
              <Form.Item
                name="req_stage"
                label="需求状态"
                rules={[{ required: true, message: '请选择需求状态' }]}
              >
                <Select options={REQ_STAGE_OPTIONS} placeholder="选择" data-testid="tm-task-req-stage" />
              </Form.Item>
              <Form.Item name="lead_id" label="测试负责人" rules={[{ required: true, message: '请选择' }]}>
                <Select
                  options={userOptions}
                  showSearch
                  optionFilterProp="label"
                  loading={usersLoading}
                  placeholder={usersLoading ? '加载中…' : '选择负责人'}
                  notFoundContent={usersLoading ? '加载中…' : '无用户'}
                  data-testid="tm-task-lead"
                />
              </Form.Item>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 12 }}>
              <Form.Item name="dev_members" label="开发人员">
                <MemberTagsSelect testId="tm-task-dev-members" />
              </Form.Item>
              <Form.Item name="pm_members" label="产品人员">
                <MemberTagsSelect testId="tm-task-pm-members" />
              </Form.Item>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', columnGap: 12 }}>
              <Form.Item name="verifier_id" label="验证人">
                <Select
                  allowClear
                  options={userOptions}
                  showSearch
                  optionFilterProp="label"
                  loading={usersLoading}
                  placeholder="可选"
                  data-testid="tm-task-verifier"
                />
              </Form.Item>
              <Form.Item name="verify_result" label="验证结果">
                <Select
                  allowClear
                  options={[
                    { value: '通过', label: '通过' },
                    { value: '不通过', label: '不通过' },
                    { value: '未验证', label: '未验证' },
                  ]}
                  placeholder="可选"
                  data-testid="tm-task-verify-result"
                />
              </Form.Item>
              <Form.Item name="verified_at" label="验证时间">
                <DatePicker
                  style={{ width: '100%' }}
                  placeholder="可选"
                  data-testid="tm-task-verified-at"
                />
              </Form.Item>
            </div>
            <Form.Item name="remark" label="备注">
              <TextArea rows={2} placeholder="可选" maxLength={4000} data-testid="tm-task-remark" />
            </Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              block
              loading={createTaskMut.isPending}
              data-testid="tm-submit-task"
            >
              创建并发布
            </Button>
          </Form>
        </div>
      </Modal>

      {/* Task 弹窗：进度/状态 + 详情（合并原抽屉） */}
      <Modal
        title={
          taskDrawerFocus === 'progress'
            ? `进度/状态 · ${taskDetail?.title || 'Task'}`
            : taskDetail?.title || 'Task 详情'
        }
        open={!!editTaskId}
        onCancel={() => {
          setEditTaskId(null)
          setTaskSaveTip(null)
          setTaskInfoEditing(false)
          setTaskDrawerFocus('progress')
        }}
        footer={null}
        width={560}
        destroyOnClose
        styles={{ body: { paddingTop: 12, paddingBottom: 24 } }}
      >
        {taskDetail ? (
          <div
            className="tm-sheet"
            data-testid="tm-drawer-task"
            data-drawer-mode={taskDrawerFocus}
          >
            <div className="tm-sheet__stack">
              {taskSaveTip ? (
                <p className="tm-sheet__tip" data-testid="tm-task-save-tip">
                  {taskSaveTip}
                </p>
              ) : null}

              {taskDrawerFocus === 'progress' ? (
                <>
                  <section className="tm-sheet__section" data-testid="tm-task-flow">
                    <h3 className="tm-sheet__h">状态 / 进度</h3>
                    {!viewingHistory &&
                    (taskDetail.can_edit_req_stage ||
                      (taskDetail.can_edit && taskDetail.req_stage === 'testing')) ? (
                      <Form
                        key={`flow-${taskDetail.id}-${taskFormEpoch}-${taskDetail.updated_at || ''}`}
                        layout="vertical"
                        className="tm-sheet__form"
                        initialValues={{
                          display_status: taskDetail.display_status || 'pending_dev',
                          expected_handover_at: taskDetail.expected_handover_at
                            ? dayjs(taskDetail.expected_handover_at)
                            : null,
                          actual_handover_at: taskDetail.actual_handover_at
                            ? dayjs(taskDetail.actual_handover_at)
                            : null,
                          test_started_at: taskDetail.test_started_at
                            ? dayjs(taskDetail.test_started_at)
                            : null,
                          expected_test_end_at: taskDetail.expected_test_end_at
                            ? dayjs(taskDetail.expected_test_end_at)
                            : null,
                          test_ended_at: taskDetail.test_ended_at
                            ? dayjs(taskDetail.test_ended_at)
                            : null,
                          change_summary: '',
                        }}
                        onFinish={(v) => {
                          const fmt = (d: dayjs.Dayjs | null | undefined) =>
                            d ? d.format('YYYY-MM-DD') : null
                          const { req_stage, status } = splitDisplayStatus(v.display_status)
                          const payload: Parameters<typeof testManageApi.updateTask>[1] = {
                            change_summary: v.change_summary || '更新状态',
                          }
                          if (taskDetail.can_edit_req_stage) {
                            payload.req_stage = req_stage
                            payload.expected_handover_at = fmt(v.expected_handover_at)
                            payload.actual_handover_at = fmt(v.actual_handover_at)
                            payload.test_started_at = fmt(v.test_started_at)
                            payload.expected_test_end_at = fmt(v.expected_test_end_at)
                            payload.test_ended_at = fmt(v.test_ended_at)
                          }
                          payload.status = status
                          updateTaskMut.mutate({ id: taskDetail.id, data: payload })
                        }}
                      >
                        <Form.Item
                          name="display_status"
                          label="状态"
                        >
                          <Select
                            data-testid="tm-task-display-status"
                            options={DISPLAY_STATUS_OPTIONS}
                          />
                        </Form.Item>
                        {taskDetail.can_edit_req_stage ? (
                          <Form.Item
                            noStyle
                            shouldUpdate={(prev, cur) => prev.display_status !== cur.display_status}
                          >
                            {({ getFieldValue }) => {
                              const ds = getFieldValue('display_status') as string
                              const { req_stage } = splitDisplayStatus(ds)
                              return (
                                <>
                                  {req_stage === 'pending_handover' ? (
                                    <Form.Item
                                      name="expected_handover_at"
                                      label="预计提测时间"
                                    >
                                      <DatePicker
                                        allowClear
                                        placeholder="待定"
                                        style={{ width: '100%' }}
                                      />
                                    </Form.Item>
                                  ) : null}
                                  {req_stage === 'pending_test' ? (
                                    <Form.Item
                                      name="actual_handover_at"
                                      label="实际提测时间"
                                    >
                                      <DatePicker
                                        allowClear
                                        placeholder="待定"
                                        style={{ width: '100%' }}
                                      />
                                    </Form.Item>
                                  ) : null}
                                  {req_stage === 'testing' ? (
                                    <>
                                      <Form.Item
                                        name="test_started_at"
                                        label="测试开始时间"
                                      >
                                        <DatePicker
                                          allowClear
                                          placeholder="待定"
                                          style={{ width: '100%' }}
                                        />
                                      </Form.Item>
                                      <Form.Item
                                        name="expected_test_end_at"
                                        label="预计测试结束"
                                      >
                                        <DatePicker
                                          allowClear
                                          placeholder="待定"
                                          style={{ width: '100%' }}
                                        />
                                      </Form.Item>
                                    </>
                                  ) : null}
                                  {req_stage === 'test_done' ? (
                                    <Form.Item
                                      name="test_ended_at"
                                      label="测试结束时间"
                                    >
                                      <DatePicker
                                        allowClear
                                        placeholder="待定"
                                        style={{ width: '100%' }}
                                      />
                                    </Form.Item>
                                  ) : null}
                                </>
                              )
                            }}
                          </Form.Item>
                        ) : null}
                        <Form.Item name="change_summary" label="变更说明">
                          <Input placeholder="写入更新日志" />
                        </Form.Item>
                        <Button
                          type="primary"
                          htmlType="submit"
                          block
                          loading={updateTaskMut.isPending}
                          data-testid="tm-task-save"
                        >
                          保存状态
                        </Button>
                      </Form>
                    ) : (
                      <p className="tm-sheet__tip">
                        <Tag color={displayStatusTagColor(taskDetail.display_status)}>
                          {displayStatusLabel(taskDetail.display_status)}
                        </Tag>
                        {taskDetail.stage_summary ? (
                          <Text type="secondary"> {taskDetail.stage_summary}</Text>
                        ) : null}
                        {viewingHistory ? ' · 历史周只读' : null}
                        {!taskDetail.can_edit_req_stage ? ' · 仅 Admin/Manager 可改状态' : null}
                      </p>
                    )}
                  </section>

                  <section
                    id="tm-task-drawer-progress"
                    className="tm-sheet__section"
                    data-testid="tm-task-week-progress"
                  >
                    <h3 className="tm-sheet__h">本周测试进度</h3>
                    {taskDetail.req_stage !== REQ_STAGE_TESTING ? (
                      <p className="tm-sheet__tip tm-sheet__tip--warn" data-testid="tm-task-progress-locked">
                        仅「测试中」可填写本周进度（当前：{displayStatusLabel(taskDetail.display_status)}）
                      </p>
                    ) : null}
                    {!viewingHistory && taskWeekProgress ? (
                      <>
                        {!taskWeekProgress.progress_is_manual ? (
                          <p className="tm-sheet__tip tm-sheet__tip--warn">
                            未手填 · 按 Action 平均 {taskWeekProgress.recommended_progress}%
                          </p>
                        ) : null}
                        {taskWeekProgress.can_edit ? (
                          <Form
                            key={`week-progress-${taskDetail.id}-${taskWeekProgress.updated_at || 'new'}-${taskWeekProgress.progress_is_manual}`}
                            layout="vertical"
                            className="tm-sheet__form"
                            initialValues={{
                              progress_percent: taskWeekProgress.progress_percent,
                              note: taskWeekProgress.note || '',
                            }}
                            onFinish={(v) =>
                              upsertTaskWeekProgressMut.mutate({
                                id: taskDetail.id,
                                progress_percent: Number(v.progress_percent),
                                note: (v.note || '').trim(),
                              })
                            }
                          >
                            <Form.Item
                              name="progress_percent"
                              label="进度 %"
                              rules={[{ required: true, message: '请填写进度' }]}
                              extra="每周三 16:55 前填写"
                            >
                              <InputNumber
                                min={0}
                                max={100}
                                style={{ width: '100%' }}
                                data-testid="tm-task-week-progress-input"
                              />
                            </Form.Item>
                            <Form.Item name="note" label="备注">
                              <Input placeholder="可选" maxLength={500} />
                            </Form.Item>
                            <Button
                              type="primary"
                              htmlType="submit"
                              block
                              loading={upsertTaskWeekProgressMut.isPending}
                              data-testid="tm-task-week-progress-save"
                            >
                              保存本周进度
                            </Button>
                          </Form>
                        ) : (
                          <div>
                            <Progress percent={taskWeekProgress.progress_percent} size="small" />
                            {taskWeekProgress.note ? (
                              <p className="tm-sheet__body" style={{ marginTop: 8 }}>
                                {taskWeekProgress.note}
                              </p>
                            ) : null}
                          </div>
                        )}
                      </>
                    ) : (
                      <p className="tm-sheet__tip">
                        {viewingHistory ? '历史周只读不可编辑' : '加载进度中…'}
                      </p>
                    )}
                  </section>
                </>
              ) : taskDrawerFocus === 'detail' ? (
                <>
                  <section
                    id="tm-task-drawer-info"
                    className="tm-sheet__section"
                    data-testid="tm-task-info"
                  >
                    <div className="tm-sheet__actions" style={{ justifyContent: 'space-between' }}>
                      <h3 className="tm-sheet__h">基本信息</h3>
                      {taskDetail.can_edit && !viewingHistory && !taskInfoEditing ? (
                        <Button
                          type="link"
                          size="small"
                          icon={<EditOutlined />}
                          onClick={() => setTaskInfoEditing(true)}
                          data-testid="tm-task-info-edit"
                        >
                          编辑
                        </Button>
                      ) : null}
                    </div>

                    {taskDetail.can_edit && taskInfoEditing ? (
                      <Form
                        key={`${taskDetail.id}-${taskFormEpoch}-${taskDetail.updated_at || ''}`}
                        layout="vertical"
                        className="tm-sheet__form"
                        initialValues={{
                          title: taskDetail.title,
                          requirement: taskDetail.requirement,
                          sr_code: taskDetail.sr_code || '',
                          ir_codes: taskDetail.ir_codes || '',
                          module: taskDetail.module || '',
                          req_type: taskDetail.req_type || undefined,
                          priority: taskDetail.priority || undefined,
                          change_flag: taskDetail.change_flag || undefined,
                          acceptance_criteria: taskDetail.acceptance_criteria || '',
                          verifier_id: taskDetail.verifier_id != null ? Number(taskDetail.verifier_id) : undefined,
                          verified_at: taskDetail.verified_at ? dayjs(taskDetail.verified_at) : undefined,
                          verify_result: taskDetail.verify_result || undefined,
                          remark: taskDetail.remark || '',
                          lead_id: Number(taskDetail.lead_id),
                          dev_members: taskDetail.dev_members || [],
                          pm_members: taskDetail.pm_members || [],
                          change_summary: '',
                        }}
                        onFinish={(v) => {
                          const payload: Parameters<typeof testManageApi.updateTask>[1] = {
                            title: v.title,
                            requirement: v.requirement,
                            sr_code: v.sr_code || '',
                            ir_codes: v.ir_codes || '',
                            module: v.module,
                            req_type: v.req_type || '',
                            priority: v.priority || '',
                            change_flag: v.change_flag || '',
                            acceptance_criteria: v.acceptance_criteria || '',
                            verifier_id: v.verifier_id ?? null,
                            verified_at: v.verified_at ? v.verified_at.format('YYYY-MM-DD') : null,
                            verify_result: v.verify_result || '',
                            remark: v.remark || '',
                            lead_id: Number(v.lead_id),
                            dev_members: v.dev_members || [],
                            pm_members: v.pm_members || [],
                            change_summary: v.change_summary,
                          }
                          updateTaskMut.mutate({ id: taskDetail.id, data: payload })
                        }}
                      >
                        <Form.Item name="title" label="标题" rules={[{ required: true }]}>
                          <Input />
                        </Form.Item>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 12 }}>
                          <Form.Item name="sr_code" label="SR 编号">
                            <Input maxLength={64} />
                          </Form.Item>
                          <Form.Item name="ir_codes" label="关联 IR 编号">
                            <Input maxLength={256} />
                          </Form.Item>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 12 }}>
                          <Form.Item
                            name="module"
                            label="子类/模块"
                            rules={[{ required: true, message: '请填写子类/模块' }]}
                          >
                            <Input maxLength={100} />
                          </Form.Item>
                          <Form.Item name="req_type" label="需求类型">
                            <Select
                              allowClear
                              options={[
                                { value: '功能', label: '功能' },
                                { value: '性能', label: '性能' },
                                { value: '接口', label: '接口' },
                                { value: '安全', label: '安全' },
                                { value: '可靠性', label: '可靠性' },
                              ]}
                            />
                          </Form.Item>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 12 }}>
                          <Form.Item name="priority" label="优先级">
                            <Select
                              allowClear
                              options={[
                                { value: '高', label: '高' },
                                { value: '中', label: '中' },
                                { value: '低', label: '低' },
                              ]}
                            />
                          </Form.Item>
                          <Form.Item name="change_flag" label="变更标识">
                            <Select
                              allowClear
                              options={[
                                { value: '原始', label: '原始' },
                                { value: '变更', label: '变更' },
                              ]}
                            />
                          </Form.Item>
                        </div>
                        <Form.Item name="requirement" label="需求内容">
                          <TextArea rows={4} maxLength={TASK_REQUIREMENT_MAX_CHARS} showCount />
                        </Form.Item>
                        <Form.Item name="acceptance_criteria" label="验收标准">
                          <TextArea rows={2} maxLength={4000} />
                        </Form.Item>
                        <Form.Item name="lead_id" label="测试负责人">
                          <Select
                            options={userOptions}
                            showSearch
                            optionFilterProp="label"
                            loading={usersLoading}
                          />
                        </Form.Item>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 12 }}>
                          <Form.Item name="dev_members" label="开发人员">
                            <MemberTagsSelect testId="tm-task-detail-dev-members" />
                          </Form.Item>
                          <Form.Item name="pm_members" label="产品人员">
                            <MemberTagsSelect testId="tm-task-detail-pm-members" />
                          </Form.Item>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', columnGap: 12 }}>
                          <Form.Item name="verifier_id" label="验证人">
                            <Select
                              allowClear
                              options={userOptions}
                              showSearch
                              optionFilterProp="label"
                              loading={usersLoading}
                            />
                          </Form.Item>
                          <Form.Item name="verify_result" label="验证结果">
                            <Select
                              allowClear
                              options={[
                                { value: '通过', label: '通过' },
                                { value: '不通过', label: '不通过' },
                                { value: '未验证', label: '未验证' },
                              ]}
                            />
                          </Form.Item>
                          <Form.Item name="verified_at" label="验证时间">
                            <DatePicker style={{ width: '100%' }} />
                          </Form.Item>
                        </div>
                        <Form.Item name="remark" label="备注">
                          <TextArea rows={2} maxLength={4000} />
                        </Form.Item>
                        <Form.Item name="change_summary" label="变更说明">
                          <Input placeholder="写入更新日志" />
                        </Form.Item>
                        <div className="tm-sheet__actions">
                          <Button
                            type="primary"
                            htmlType="submit"
                            loading={updateTaskMut.isPending}
                            data-testid="tm-task-save"
                          >
                            保存
                          </Button>
                          <Button onClick={() => setTaskInfoEditing(false)} data-testid="tm-task-info-cancel">
                            取消
                          </Button>
                        </div>
                      </Form>
                    ) : (
                      <dl className="tm-sheet__dl">
                        <div>
                          <dt>状态</dt>
                          <dd>
                            <Tag color={displayStatusTagColor(taskDetail.display_status)}>
                              {displayStatusLabel(taskDetail.display_status)}
                            </Tag>
                            {taskDetail.stage_summary ? (
                              <Text type="secondary"> {taskDetail.stage_summary}</Text>
                            ) : null}
                            <div className="tm-sheet__muted" style={{ marginTop: 4 }}>
                              改状态请在「操作 · 进度/状态」入口
                            </div>
                          </dd>
                        </div>
                        <div>
                          <dt>项目 / 领域</dt>
                          <dd>
                            {taskDetail.project_name} / {taskDetail.domain_name}
                          </dd>
                        </div>
                        {taskDetail.sr_code ? (
                          <div>
                            <dt>SR 编号</dt>
                            <dd>{taskDetail.sr_code}</dd>
                          </div>
                        ) : null}
                        {taskDetail.ir_codes ? (
                          <div>
                            <dt>关联 IR 编号</dt>
                            <dd>{taskDetail.ir_codes}</dd>
                          </div>
                        ) : null}
                        {taskDetail.module ? (
                          <div>
                            <dt>子类/模块</dt>
                            <dd>{taskDetail.module}</dd>
                          </div>
                        ) : null}
                        {taskDetail.req_type || taskDetail.priority || taskDetail.change_flag ? (
                          <div>
                            <dt>类型 / 优先级 / 变更</dt>
                            <dd>
                              {[
                                taskDetail.req_type || '—',
                                taskDetail.priority || '—',
                                taskDetail.change_flag || '—',
                              ].join(' / ')}
                            </dd>
                          </div>
                        ) : null}
                        <div>
                          <dt>负责人</dt>
                          <dd>{userName(taskDetail.lead_id)}</dd>
                        </div>
                        {taskDetail.dev_members?.length || taskDetail.pm_members?.length ? (
                          <div>
                            <dt>开发 / 产品人员</dt>
                            <dd>
                              {[
                                taskDetail.dev_members?.length ? `开发 ${taskDetail.dev_members.join('、')}` : '',
                                taskDetail.pm_members?.length ? `产品 ${taskDetail.pm_members.join('、')}` : '',
                              ]
                                .filter(Boolean)
                                .join(' · ') || '—'}
                            </dd>
                          </div>
                        ) : null}
                        {taskDetail.verifier_id != null ||
                        taskDetail.verify_result ||
                        taskDetail.verified_at ? (
                          <div>
                            <dt>验证</dt>
                            <dd>
                              {[
                                taskDetail.verifier_id != null ? userName(taskDetail.verifier_id) : '—',
                                taskDetail.verify_result || '—',
                                taskDetail.verified_at || '—',
                              ].join(' / ')}
                            </dd>
                          </div>
                        ) : null}
                        <div>
                          <dt>需求</dt>
                          <dd>{taskDetail.requirement?.trim() || '—'}</dd>
                        </div>
                        {taskDetail.acceptance_criteria?.trim() ? (
                          <div>
                            <dt>验收标准</dt>
                            <dd>{taskDetail.acceptance_criteria}</dd>
                          </div>
                        ) : null}
                        {taskDetail.remark?.trim() ? (
                          <div>
                            <dt>备注</dt>
                            <dd>{taskDetail.remark}</dd>
                          </div>
                        ) : null}
                      </dl>
                    )}
                  </section>

                  {taskDetail.update_logs?.length > 0 ? (
                    <section className="tm-sheet__section">
                      <h3 className="tm-sheet__h">
                        更新历史
                        <span className="tm-sheet__muted"> · {taskDetail.update_logs.length}</span>
                      </h3>
                      <div className="tm-sheet__log">
                        {taskDetail.update_logs.map((l) => (
                          <div key={l.id} className="tm-sheet__log-item">
                            <span className="tm-sheet__muted">
                              {l.created_at} · {userName(l.user_id)}
                            </span>
                            <div>{l.summary}</div>
                          </div>
                        ))}
                      </div>
                    </section>
                  ) : null}

                  {(taskDetail.subtasks || []).length > 0 ? (
                    <section className="tm-sheet__section">
                      <h3 className="tm-sheet__h">
                        子需求
                        <span className="tm-sheet__muted"> · {taskDetail.subtasks!.length}</span>
                      </h3>
                      <Table
                        size="small"
                        rowKey="sid"
                        pagination={false}
                        tableLayout="fixed"
                        columns={[
                          { title: '名称', dataIndex: 'name', key: 'name', width: 116, ellipsis: true, render: (t: string) => <Text strong>{t}</Text> },
                          { title: '内容', dataIndex: 'content', key: 'content', width: 40, ellipsis: true, render: (t?: string) => t || <Text type="secondary">—</Text> },
                          {
                            title: '开发人员',
                            dataIndex: 'dev_members',
                            key: 'dev_members',
                            width: 130,
                            render: (v: string[] | undefined, r: TmSubtask) =>
                              !viewingHistory && taskDetail.can_manage_children ? (
                                <MemberTagsSelect
                                  size="small"
                                  value={v || []}
                                  onChange={(nv) =>
                                    updateSubtaskMut.mutate({
                                      taskId: taskDetail.id,
                                      sid: r.sid,
                                      data: { dev_members: nv },
                                    })
                                  }
                                  testId="tm-subtask-dev-members"
                                />
                              ) : v?.length ? (
                                <Text>{v.join('、')}</Text>
                              ) : (
                                <Text type="secondary">—</Text>
                              ),
                          },
                          {
                            title: '产品人员',
                            dataIndex: 'pm_members',
                            key: 'pm_members',
                            width: 130,
                            render: (v: string[] | undefined, r: TmSubtask) =>
                              !viewingHistory && taskDetail.can_manage_children ? (
                                <MemberTagsSelect
                                  size="small"
                                  value={v || []}
                                  onChange={(nv) =>
                                    updateSubtaskMut.mutate({
                                      taskId: taskDetail.id,
                                      sid: r.sid,
                                      data: { pm_members: nv },
                                    })
                                  }
                                  testId="tm-subtask-pm-members"
                                />
                              ) : v?.length ? (
                                <Text>{v.join('、')}</Text>
                              ) : (
                                <Text type="secondary">—</Text>
                              ),
                          },
                          {
                            title: '操作',
                            key: 'op',
                            width: 92,
                            render: (_: unknown, r: TmSubtask) =>
                              !viewingHistory && taskDetail.can_manage_children ? (
                                <Space size={2}>
                                  <Button
                                    size="small"
                                    type="link"
                                    style={{ paddingInline: 4 }}
                                    onClick={() =>
                                      setMoveSubtaskModal({ open: true, sid: r.sid, name: r.name })
                                    }
                                  >
                                    移动
                                  </Button>
                                  <Popconfirm
                                    title="删除该子需求？"
                                    description="其下未完成的 Action 将一并取消"
                                    okText="删除"
                                    okButtonProps={{ danger: true }}
                                    onConfirm={() =>
                                      deleteSubtaskMut.mutate({
                                        taskId: taskDetail.id,
                                        sid: r.sid,
                                      })
                                    }
                                  >
                                    <Button size="small" type="link" danger style={{ paddingInline: 4 }}>
                                      删除
                                    </Button>
                                  </Popconfirm>
                                </Space>
                              ) : null,
                          },
                        ]}
                        dataSource={taskDetail.subtasks}
                      />
                    </section>
                  ) : null}

                  {!viewingHistory && taskDetail.can_manage_children && taskDetail.can_add_action ? (
                    <section className="tm-sheet__section">
                      <Button
                        type="dashed"
                        block
                        onClick={() => {
                          setInlineAddTaskId(taskDetail.id)
                          setEditTaskId(null)
                        }}
                        data-testid="tm-btn-new-action-in-drawer"
                      >
                        新建本周 Action（在工作台卡片内填写）
                      </Button>
                    </section>
                  ) : null}

                  {!viewingHistory && taskDetail.status === 'done' ? (
                    <p className="tm-sheet__tip">已完成 · 不可再加本周 Action</p>
                  ) : null}
                </>
              ) : null}
            </div>
          </div>
        ) : null}
      </Modal>

      <Modal
        title={`移动子需求「${moveSubtaskModal.name}」`}
        open={moveSubtaskModal.open}
        onCancel={() => setMoveSubtaskModal({ open: false, sid: '', name: '' })}
        onOk={() => {
          if (!moveSubtaskModal.targetId || !taskDetail) return
          moveSubtaskMut.mutate({
            taskId: taskDetail.id,
            sid: moveSubtaskModal.sid,
            targetTaskId: moveSubtaskModal.targetId,
          })
        }}
        okText="移动"
        okButtonProps={{
          disabled: !moveSubtaskModal.targetId,
          loading: moveSubtaskMut.isPending,
        }}
        destroyOnClose
      >
        <p className="tm-sheet__muted" style={{ marginTop: 0 }}>
          将移动到同项目下的其他 Task，其关联 Action 一并随迁
        </p>
        <Select
          style={{ width: '100%' }}
          placeholder="选择目标 Task"
          showSearch
          optionFilterProp="label"
          value={moveSubtaskModal.targetId}
          onChange={(v) => setMoveSubtaskModal((s) => ({ ...s, targetId: v }))}
          options={(board?.tasks || [])
            .filter((bt) => bt.task.id !== taskDetail?.id && bt.task.status !== 'cancelled')
            .map((bt) => ({ value: bt.task.id, label: bt.task.title }))}
          data-testid="tm-subtask-move-target"
        />
      </Modal>

      <Modal
        title="新建项目"
        open={projectModal}
        onCancel={() => setProjectModal(false)}
        footer={null}
        destroyOnClose
      >
        <div className="tm-sheet tm-sheet--modal">
          <Form
            layout="vertical"
            className="tm-sheet__form"
            data-testid="tm-modal-new-project"
            onFinish={(v) => createProjectMut.mutate(v.name)}
          >
            <Form.Item name="name" label="名称" rules={[{ required: true }]}>
              <Input placeholder="如 TPT V2.1" data-testid="tm-input-project-name" />
            </Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              block
              loading={createProjectMut.isPending}
              data-testid="tm-submit-project"
            >
              创建
            </Button>
          </Form>
        </div>
      </Modal>

      <Modal
        title="新建领域"
        open={domainModal}
        onCancel={() => setDomainModal(false)}
        footer={null}
        destroyOnClose
      >
        <div className="tm-sheet tm-sheet--modal">
          <Form
            layout="vertical"
            className="tm-sheet__form"
            data-testid="tm-modal-new-domain"
            onFinish={(v) => createDomainMut.mutate(v.name)}
          >
            <Form.Item name="name" label="名称" rules={[{ required: true }]}>
              <Input placeholder="如 Agent" data-testid="tm-input-domain-name" />
            </Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              block
              loading={createDomainMut.isPending}
              data-testid="tm-submit-domain"
            >
              创建
            </Button>
          </Form>
        </div>
      </Modal>

      <ActionDetailDrawer
        open={!!detailActionId}
        detail={actionDetail}
        forceReadOnly={viewingHistory}
        users={users}
        userName={userName}
        onClose={() => setDetailActionId(null)}
        onDaily={(p) => dailyMut.mutate(p)}
        onCorrect={async (id, note) => {
          await correctMut.mutateAsync({ id, note })
        }}
        onPublish={(id) => publishActionMut.mutate(id)}
        onSaveDraft={(id, data) => updateActionMut.mutate({ id, data })}
        onSaveMembers={(id, data) => updateActionMut.mutate({ id, data })}
        membersLoading={updateActionMut.isPending}
        onSaveOwner={(id, owner_id) => updateActionMut.mutate({ id, data: { owner_id } })}
        ownerLoading={updateActionMut.isPending}
        onDeleteAction={(id) => deleteActionMut.mutate(id)}
        onDeleteDaily={(id, reportDate) => deleteDailyMut.mutate({ id, reportDate })}
        deleteLoading={deleteActionMut.isPending || deleteDailyMut.isPending}
        dailyLoading={dailyMut.isPending}
        correctLoading={correctMut.isPending}
        saveDraftLoading={updateActionMut.isPending}
        publishLoading={publishActionMut.isPending}
      />
    </div>
  )
}

/**
 * 快捷日更：卡片/表格行内轻量弹层，免开详情抽屉。
 * 三步完成：拖进度 → 写今日完成 → 选风险状态（无/风险/阻塞）。
 */
function DailyQuickPopover(props: {
  action: Pick<TmAction, 'id' | 'progress_percent' | 'latest_risk' | 'latest_is_blocking'>
  loading?: boolean
  onSubmit: (p: {
    id: string
    progress_percent: number
    risk_blocker: string
    is_blocking: boolean
    progress_note: string
  }) => void
  children: ReactNode
}) {
  const { message } = App.useApp()
  const [open, setOpen] = useState(false)
  const [progress, setProgress] = useState(props.action.progress_percent ?? 0)
  const [note, setNote] = useState('')
  const [riskLevel, setRiskLevel] = useState<'none' | 'risk' | 'blocking'>(
    isBlockingFlag(props.action.latest_is_blocking)
      ? 'blocking'
      : (props.action.latest_risk || '').trim()
        ? 'risk'
        : 'none',
  )
  const [riskText, setRiskText] = useState(props.action.latest_risk || '')

  /** 进度只增不减：下限为当前进度 */
  const min = Math.min(props.action.progress_percent ?? 0, 100)

  const reset = () => {
    setProgress(props.action.progress_percent ?? 0)
    setNote('')
    setRiskLevel(
      isBlockingFlag(props.action.latest_is_blocking)
        ? 'blocking'
        : (props.action.latest_risk || '').trim()
          ? 'risk'
          : 'none',
    )
    setRiskText(props.action.latest_risk || '')
  }

  const submit = () => {
    if (!note.trim()) {
      message.warning('请填写今日完成内容')
      return
    }
    if (riskLevel !== 'none' && !riskText.trim()) {
      message.warning('请填写风险/阻塞说明')
      return
    }
    props.onSubmit({
      id: props.action.id,
      progress_percent: progress,
      risk_blocker: riskLevel === 'none' ? '' : riskText.trim(),
      is_blocking: riskLevel === 'blocking',
      progress_note: note.trim(),
    })
    setOpen(false)
    reset()
  }

  return (
    <Popover
      trigger="click"
      placement="left"
      open={open}
      onOpenChange={(v) => {
        setOpen(v)
        if (v) reset()
      }}
      title={
        <span style={{ fontSize: 13 }}>
          快捷日更 <Text type="secondary" style={{ fontSize: 12 }}>19:50 截止</Text>
        </span>
      }
      content={
        <div className="tm-daily-pop" data-testid="tm-daily-pop">
          <div className="tm-daily-pop__progress-row">
            <span className="tm-daily-pop__value" data-testid="tm-daily-pop-progress">
              {progress}%
            </span>
            <Space size={4}>
              <Button
                size="small"
                disabled={progress >= 100}
                onClick={() => setProgress(Math.min(100, progress + 10))}
                data-testid="tm-daily-pop-plus10"
              >
                +10
              </Button>
              <Button
                size="small"
                disabled={progress >= 100}
                onClick={() => setProgress(100)}
              >
                100%
              </Button>
            </Space>
          </div>
          <Slider
            min={min}
            max={100}
            value={progress}
            onChange={setProgress}
            tooltip={{ formatter: (v) => `${v}%` }}
          />
          <Input
            placeholder="今日完成（必填）"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            onPressEnter={submit}
            maxLength={TEXT_FIELD_MAX_CHARS}
            data-testid="tm-daily-pop-note"
          />
          <Segmented
            block
            value={riskLevel}
            onChange={(v) => setRiskLevel(v as 'none' | 'risk' | 'blocking')}
            options={[
              { value: 'none', label: '无风险' },
              { value: 'risk', label: '有风险' },
              { value: 'blocking', label: '阻塞' },
            ]}
            data-testid="tm-daily-pop-risk"
          />
          {riskLevel !== 'none' ? (
            <Input
              placeholder={riskLevel === 'blocking' ? '阻塞说明（必填）' : '风险说明（必填）'}
              value={riskText}
              onChange={(e) => setRiskText(e.target.value)}
              status={!riskText.trim() ? 'error' : undefined}
              maxLength={TEXT_FIELD_MAX_CHARS}
              data-testid="tm-daily-pop-risk-text"
            />
          ) : null}
          <div className="tm-sheet__actions">
            <Button
              color="primary"
              variant="outlined"
              size="small"
              loading={props.loading}
              onClick={submit}
              data-testid="tm-daily-pop-submit"
            >
              提交日更
            </Button>
          </div>
        </div>
      }
    >
      {props.children}
    </Popover>
  )
}

/** 共享 canvas 上下文（placeholder 溢出检测用） */
const measureCtx = (() => {
  let ctx: CanvasRenderingContext2D | null | undefined
  return () => {
    if (ctx === undefined) ctx = document.createElement('canvas').getContext('2d')
    return ctx
  }
})()

/** 工作台搜索框：placeholder 过长被截断时，鼠标悬停可查看完整提示 */
function BoardSearchInput(props: {
  placeholder: string
  value?: string
  onChange?: (v: string) => void
  testId?: string
}) {
  const [tip, setTip] = useState('')
  const measure = (e: {
    currentTarget: EventTarget & HTMLInputElement
  }) => {
    const el = e.currentTarget
    // 有值时 placeholder 不展示，无需提示
    if (props.value) {
      setTip('')
      return
    }
    const ctx = measureCtx()
    if (!ctx) return
    const style = getComputedStyle(el)
    ctx.font = style.font
    const padding =
      parseFloat(style.paddingLeft || '0') + parseFloat(style.paddingRight || '0')
    // 留 1px 容差，避免临界情况抖动
    setTip(
      ctx.measureText(props.placeholder).width > el.clientWidth - padding + 1
        ? props.placeholder
        : '',
    )
  }
  return (
    <Tooltip title={tip} mouseEnterDelay={0.2}>
      <Input
        allowClear
        placeholder={props.placeholder}
        style={{ width: '100%' }}
        value={props.value}
        onChange={(e) => props.onChange?.(e.target.value)}
        onMouseEnter={measure}
        onFocus={measure}
        data-testid={props.testId}
      />
    </Tooltip>
  )
}

/** 人员自由文本 → 数组（逗号/中文逗号分隔） */
const parseMembers = (s: string) =>
  s
    .split(/[,，]/)
    .map((v) => v.trim())
    .filter(Boolean)

/** 开发/产品人员输入：自由文本（逗号分隔，可多个；人员名为手填，无联想候选） */
function MemberTagsSelect(props: {
  value?: string[]
  onChange?: (v: string[]) => void
  placeholder?: string
  size?: 'small' | 'middle'
  testId?: string
}) {
  // 本地文本镜像：保留输入中的尾随逗号等中间态，避免解析回写把分隔符吃掉
  const [text, setText] = useState(() => (props.value || []).join(','))
  useEffect(() => {
    const external = (props.value || []).join(',')
    if (parseMembers(text).join(',') !== external) setText(external)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.value])
  return (
    <Input
      size={props.size}
      value={text}
      placeholder={props.placeholder || '多人用逗号分隔'}
      maxLength={TEXT_FIELD_MAX_CHARS}
      onChange={(e) => {
        setText(e.target.value)
        props.onChange?.(parseMembers(e.target.value))
      }}
      style={{ width: '100%' }}
      data-testid={props.testId}
    />
  )
}

function BoardTaskCard(props: {
  bt: BoardTask
  readOnly?: boolean
  /** 负责人筛选（工作台）：非空时卡片内仅显示该负责人相关的子需求/Action 行 */
  leadFilter?: number | null
  highlightEmpty?: boolean
  userName: (id: number) => string
  users: { id: number; username: string; real_name: string }[]
  onOpenAction: (id: string) => void
  onEditTask: (focus: 'progress' | 'detail') => void
  /** 外部（Task 抽屉）请求展开 inline 新建表单 */
  forceInlineAdd?: boolean
  onInlineAddDone?: () => void
  onCreateAction: (
    values: {
      title: string
      subtask_name: string
      owner_id: number
      test_content: string
      environment: string
      dev_members?: string[]
      pm_members?: string[]
    },
    publish: boolean,
  ) => void
  onCreateSubtask: (
    name: string,
    content?: string,
    devMembers?: string[],
    pmMembers?: string[],
  ) => void
  createActionLoading?: boolean
  createSubtaskLoading?: boolean
  onPublishAction: (id: string) => void
  /** 快捷日更可见性（默认 true；页面按负责人/管理员判定后传入） */
  canQuickDaily?: (a: TmAction) => boolean
  onDaily: (p: {
    id: string
    progress_percent: number
    risk_blocker: string
    is_blocking: boolean
    progress_note: string
  }) => void
  dailyLoading?: boolean
  onArchiveTask: () => void
  onDeleteTask: () => void
  archiveLoading?: boolean
  deleteLoading?: boolean
}) {
  const { bt, userName, readOnly, highlightEmpty } = props
  const { message } = App.useApp()
  const [actionPage, setActionPage] = useState(1)
  const [inlineAddOpen, setInlineAddOpen] = useState(false)
  const [newSubtaskMode, setNewSubtaskMode] = useState(false)
  const [newSubtaskName, setNewSubtaskName] = useState('')
  const [newSubtaskContent, setNewSubtaskContent] = useState('')
  const [addForm] = Form.useForm()
  const st = bt.task.display_status || 'pending_dev'
  const stLabel = displayStatusLabel(st)
  const stColor = displayStatusTagColor(st)

  useEffect(() => {
    setActionPage(1)
  }, [bt.task.id])

  /** 抽屉触发展开 inline 新建 */
  useEffect(() => {
    if (props.forceInlineAdd) {
      setInlineAddOpen(true)
      setNewSubtaskMode((bt.task.subtasks || []).length === 0)
      props.onInlineAddDone?.()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.forceInlineAdd])

  const actionsSorted = useMemo(() => sortActionCardsForList(bt.actions), [bt.actions])

  /** 负责人筛选（工作台）：选中负责人时，卡片内仅保留其相关的子需求/Action 行 */
  const leadName = props.leadFilter != null ? userName(props.leadFilter) : ''
  const nameHit = (arr?: string[]) => (arr || []).some((m) => (m || '').trim() === leadName)
  const actionLeadHit = (a: TmAction) =>
    props.leadFilter == null ||
    Number(a.owner_id) === props.leadFilter ||
    nameHit(a.dev_members) ||
    nameHit(a.pm_members)
  const subtaskLeadHit = (s: { dev_members?: string[]; pm_members?: string[] }) =>
    props.leadFilter == null || nameHit(s.dev_members) || nameHit(s.pm_members)

  /** 将未被任何 Action 引用的子需求补成占位行（无 Action 的子需求也在表格中展示一行） */
  type ActionRow =
    | TmAction
    | { id: string; __empty_subtask__: true; subtask_name: string; task_id: string }
  const rowsWithSubtasks: ActionRow[] = useMemo(() => {
    const filteredActions = actionsSorted.filter(actionLeadHit)
    const used = new Set(filteredActions.map((a) => (a.subtask_name || '').trim()).filter(Boolean))
    const emptySubtasks = (bt.task.subtasks || [])
      .filter((s) => s.name && !used.has(s.name.trim()) && subtaskLeadHit(s))
      .map(
        (s) =>
          ({
            id: `__empty_subtask__${bt.task.id}__${s.sid}`,
            __empty_subtask__: true,
            subtask_name: s.name,
            task_id: bt.task.id,
          }) as ActionRow,
      )
    return [...emptySubtasks, ...filteredActions]
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actionsSorted, bt.task.subtasks, bt.task.id, props.leadFilter, leadName])

  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(rowsWithSubtasks.length / ACTION_CARD_PAGE_SIZE) || 1)
    if (actionPage > maxPage) setActionPage(maxPage)
  }, [rowsWithSubtasks.length, actionPage])

  const actionsPaged = useMemo(() => {
    const start = (actionPage - 1) * ACTION_CARD_PAGE_SIZE
    return rowsWithSubtasks.slice(start, start + ACTION_CARD_PAGE_SIZE)
  }, [rowsWithSubtasks, actionPage])

  const subtaskRowSpans = useMemo(() => {
    const spans: number[] = new Array(actionsPaged.length).fill(1)
    for (let i = actionsPaged.length - 1; i > 0; i--) {
      const prev = (actionsPaged[i - 1].subtask_name || '').trim()
      const curr = (actionsPaged[i].subtask_name || '').trim()
      if (prev && prev === curr) {
        spans[i - 1] += spans[i]
        spans[i] = 0
      }
    }
    return spans
  }, [actionsPaged])

  const taskMenuItems: MenuProps['items'] = [
    { key: 'detail', label: '详情' },
    { key: 'progress', label: '进度/状态' },
    ...(!readOnly && bt.task.can_edit
      ? [
          {
            key: 'archive-delete',
            label: '归档/删除',
            icon: <DeleteOutlined />,
            disabled: !!props.archiveLoading || !!props.deleteLoading,
            type: 'submenu' as const,
            children: [
              {
                key: 'archive',
                label: '归档',
                disabled: !!props.archiveLoading,
              },
              {
                key: 'delete',
                label: '删除',
                danger: true,
                disabled: !!props.deleteLoading,
              },
            ],
          },
        ]
      : []),
  ]
  return (
    <Card
      className={`tm-board-task${highlightEmpty ? ' tm-board-task--empty' : ''}`}
      data-testid={`tm-board-task-${bt.task.id}`}
      data-task-title={bt.task.title}
      title={
        <Space wrap>
          <span className="tm-board-task-title" data-testid="tm-board-task-title">
            {bt.task.title}
          </span>
          {bt.task.sr_code ? (
            <Tag data-testid="tm-board-task-sr">{bt.task.sr_code}</Tag>
          ) : null}
          <Tag color={stColor}>{stLabel}</Tag>
          <Tag>
            {bt.task.project_name}/{bt.task.domain_name}
          </Tag>
          {highlightEmpty && rowsWithSubtasks.length === 0 ? (
            <Tag color="error" data-testid="tm-empty-action-tag">
              本周无 Action
            </Tag>
          ) : null}
        </Space>
      }
      extra={
        <Space wrap className="tm-board-task-extra" align="center">
          <Text type="secondary">{bt.week_progress_avg}%</Text>
          {bt.progress_is_manual === false && !readOnly ? (
            <Tooltip title="未手填 Task 进度，当前按本周 Action 平均展示">
              <ExclamationCircleOutlined
                className="tm-board-task-extra__tip"
                data-testid="tm-task-progress-tip"
              />
            </Tooltip>
          ) : null}
          <Dropdown
            menu={{
              items: taskMenuItems,
              onClick: ({ key }) => {
                if (key === 'detail') props.onEditTask('detail')
                if (key === 'progress') props.onEditTask('progress')
                if (key === 'archive') props.onArchiveTask()
                if (key === 'delete') props.onDeleteTask()
              },
            }}
          >
            <Button size="small" data-testid="tm-btn-task-menu">
              操作 <DownOutlined />
            </Button>
          </Dropdown>
          {!readOnly &&
          shouldShowAddActionButton({
            readOnly: !!readOnly,
            canEdit: !!bt.task.can_manage_children,
            canAddAction: !!bt.task.can_add_action,
          }) ? (
            <Button
              size="small"
              type="primary"
              onClick={() => {
                setInlineAddOpen(true)
                setNewSubtaskMode((bt.task.subtasks || []).length === 0)
              }}
              data-testid="tm-btn-add-action"
            >
              增加一行
            </Button>
          ) : null}
        </Space>
      }
    >
      <Paragraph type="secondary" className="tm-board-task-req" ellipsis={{ rows: 2 }}>
        {[
          `需求：${bt.task.requirement || '（无）'}`,
          `负责人 ${userName(bt.task.lead_id)}`,
          ...(bt.task.dev_members?.length ? [`开发 ${bt.task.dev_members.join('、')}`] : []),
          ...(bt.task.pm_members?.length ? [`产品 ${bt.task.pm_members.join('、')}`] : []),
        ].join(' · ')}
      </Paragraph>
      {rowsWithSubtasks.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={emptyActionDescription({
            readOnly: !!readOnly,
            canAddAction: !!bt.task.can_add_action,
          })}
        />
      ) : (
        <>
          <Table
            size="small"
            className="tm-action-table"
            data-testid={`tm-task-action-table-${bt.task.id}`}
            rowKey="id"
            dataSource={actionsPaged}
            pagination={false}
            onRow={(a: ActionRow): any => {
              const isEmpty = !!(a as any).__empty_subtask__
              return {
                onClick: isEmpty ? undefined : () => props.onOpenAction(a.id),
                className: `tm-action-card tm-action-table__row${isEmpty ? ' tm-action-table__row--empty' : ''}`,
                'data-testid': `tm-action-card-${a.id}`,
                'data-action-title': isEmpty ? '' : (a as TmAction).title,
                style: isEmpty ? { cursor: 'default' } : undefined,
              }
            }}
            columns={[
              {
                title: '子需求',
                dataIndex: 'subtask_name',
                width: 150,
                ellipsis: true,
                onCell: (_: unknown, index?: number) => ({
                  rowSpan: index != null ? subtaskRowSpans[index] : 1,
                }),
                render: (v: string, _: unknown, index?: number) => {
                  if (index != null && subtaskRowSpans[index] === 0) return null
                  return v ? (
                    <Tooltip title={`子需求：${v}`}>
                      <span className="tm-action-table__subtask">{v}</span>
                    </Tooltip>
                  ) : (
                    <Text type="secondary">未关联</Text>
                  )
                },
              },
              {
                title: 'Action',
                dataIndex: 'title',
                ellipsis: true,
                render: (v: string, a: any) =>
                  a.__empty_subtask__ ? (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      （暂无 Action，可点 +Action 添加）
                    </Text>
                  ) : (
                    <span className="tm-action-table__title">{v}</span>
                  ),
              },
              {
                title: '负责人',
                dataIndex: 'owner_id',
                width: 90,
                ellipsis: true,
                render: (v: number, a: any) => (a.__empty_subtask__ ? <Text type="secondary">—</Text> : userName(v)),
              },
              {
                title: '进度',
                dataIndex: 'progress_percent',
                width: 150,
                render: (v: number, a: any) =>
                  a.__empty_subtask__ ? <Text type="secondary">—</Text> : (
                    <Progress percent={v} size="small" className="tm-action-table__progress" />
                  ),
              },
              {
                title: '状态',
                dataIndex: 'status',
                width: 110,
                render: (v: string, a: any) => {
                  if (a.__empty_subtask__) return <Text type="secondary">—</Text>
                  const act = a as TmAction
                  return (
                    <Space size={4} wrap={false}>
                      <Tag color={STATUS_LABEL[v]?.color}>{STATUS_LABEL[v]?.text}</Tag>
                      {!readOnly && v === 'draft' && act.can_edit_fields ? (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          点开可编辑
                        </Text>
                      ) : null}
                      {v === 'done' && act.completed_at ? (
                        <Tooltip title={`完成时间：${dayjs(act.completed_at).format('YYYY-MM-DD HH:mm')}`}>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {dayjs(act.completed_at).format('MM-DD HH:mm')}
                          </Text>
                        </Tooltip>
                      ) : null}
                    </Space>
                  )
                },
              },
              {
                title: '风险',
                dataIndex: 'latest_risk',
                ellipsis: true,
                render: (v: string | undefined, a: any) => {
                  if (a.__empty_subtask__) return <Text type="secondary">—</Text>
                  return a.status === 'published' && v ? (
                    <Tooltip title={v}>
                      <Text type="danger" className="tm-action-table__risk">
                        <WarningOutlined /> {v}
                      </Text>
                    </Tooltip>
                  ) : (
                    <Text type="secondary">—</Text>
                  )
                },
              },
              {
                title: '操作',
                key: 'op',
                width: 80,
                render: (_: unknown, a: any) =>
                  !readOnly && !a.__empty_subtask__ && a.status === 'draft' && a.can_edit_fields ? (
                    <Space size={0} wrap={false} onClick={(e) => e.stopPropagation()}>
                      <Button
                        size="small"
                        type="link"
                        icon={<SendOutlined />}
                        onClick={() => props.onPublishAction(a.id)}
                      >
                        发布
                      </Button>
                    </Space>
                  ) : null,
              },
            ]}
          />
          {rowsWithSubtasks.length > ACTION_CARD_PAGE_SIZE ? (
            <div
              className="tm-board-pagination"
              data-testid={`tm-task-action-pagination-${bt.task.id}`}
            >
              <Pagination
                current={actionPage}
                pageSize={ACTION_CARD_PAGE_SIZE}
                total={rowsWithSubtasks.length}
                showSizeChanger={false}
                showTotal={(t) => `共 ${t} 项`}
                onChange={(page) => setActionPage(page)}
              />
            </div>
          ) : null}
        </>
      )}
      {inlineAddOpen && !readOnly ? (
        <InlineAddAction
          task={bt.task}
          users={props.users}
          form={addForm}
          loading={!!props.createActionLoading}
          subtaskCreating={!!props.createSubtaskLoading}
          newSubtaskMode={newSubtaskMode}
          newSubtaskName={newSubtaskName}
          newSubtaskContent={newSubtaskContent}
          onToggleNewSubtask={() => {
            setNewSubtaskMode(!newSubtaskMode)
            setNewSubtaskName('')
            setNewSubtaskContent('')
          }}
          onNewSubtaskNameChange={setNewSubtaskName}
          onNewSubtaskContentChange={setNewSubtaskContent}
          onCreateSubtask={() => {
            const name = newSubtaskName.trim()
            if (!name) return
            const fv = addForm.getFieldsValue()
            props.onCreateSubtask(
              name,
              newSubtaskContent.trim(),
              fv.subtask_dev_members || [],
              fv.subtask_pm_members || [],
            )
            setNewSubtaskName('')
            setNewSubtaskContent('')
            setNewSubtaskMode(false)
            setInlineAddOpen(false)
            addForm.resetFields()
          }}
          onCancel={() => {
            setInlineAddOpen(false)
            setNewSubtaskMode(false)
            setNewSubtaskName('')
            setNewSubtaskContent('')
            addForm.resetFields()
          }}
          onSubmit={(publish) => {
            void addForm.validateFields().then((v) => {
              const subName = newSubtaskMode
                ? newSubtaskName.trim()
                : (v.subtask_name || '').trim()
              if (newSubtaskMode && !subName) {
                message.warning('请填写新子需求名称')
                return
              }
              const title = (v.title || '').trim()
              if (!title) {
                // Action 标题留空：只新建子需求（若为新建模式），不创建 Action
                if (newSubtaskMode) {
                  props.onCreateSubtask(
                    subName,
                    newSubtaskContent.trim(),
                    v.subtask_dev_members || [],
                    v.subtask_pm_members || [],
                  )
                } else {
                  message.info('Action 标题为空，无需保存')
                }
                setInlineAddOpen(false)
                setNewSubtaskMode(false)
                setNewSubtaskName('')
                addForm.resetFields()
                return
              }
              props.onCreateAction(
                {
                  title,
                  subtask_name: subName,
                  owner_id: Number(v.owner_id),
                  test_content: v.test_content || '',
                  environment: v.environment || '',
                  dev_members: v.dev_members || [],
                  pm_members: v.pm_members || [],
                },
                publish,
              )
              setInlineAddOpen(false)
              setNewSubtaskMode(false)
              setNewSubtaskName('')
              addForm.resetFields()
            })
          }}
        />
      ) : null}
    </Card>
  )
}

function InlineAddAction(props: {
  task: TmTask
  users: { id: number; username: string; real_name: string }[]
  form: FormInstance
  loading: boolean
  subtaskCreating: boolean
  newSubtaskMode: boolean
  newSubtaskName: string
  onToggleNewSubtask: () => void
  onNewSubtaskNameChange: (v: string) => void
  onNewSubtaskContentChange: (v: string) => void
  newSubtaskContent: string
  onCreateSubtask: () => void
  onCancel: () => void
  onSubmit: (publish: boolean) => void
}) {
  const { task, users, form } = props
  const ownerOptions = userSelectOptions(users.map((u) => ({ ...u, real_name: u.real_name || u.username })))
  const subtaskOptions = useMemo(
    () => [
      { value: '', label: '暂不关联（未关联）' },
      ...(task.subtasks || []).map((s) => ({
        value: s.name,
        label: s.name,
      })),
    ],
    [task.subtasks],
  )
  const defaultOwner = task.lead_id && users.some((u) => Number(u.id) === Number(task.lead_id))
    ? Number(task.lead_id)
    : users[0]?.id
  useEffect(() => {
    form.setFieldsValue({ owner_id: defaultOwner })
  }, [defaultOwner, form])
  return (
    <div className="tm-inline-add" data-testid="tm-inline-add-action">
      <Form form={form} layout="vertical" size="small" className="tm-inline-add__form" initialValues={{ owner_id: defaultOwner }}>
        <div className="tm-inline-add__row">
          <Form.Item name="subtask_name" label="子需求" style={{ width: 140, marginBottom: 0 }}>
            {props.newSubtaskMode ? (
              <Input
                placeholder="新子需求名称"
                value={props.newSubtaskName}
                onChange={(e) => props.onNewSubtaskNameChange(e.target.value)}
                onPressEnter={props.onCreateSubtask}
                data-testid="tm-inline-new-subtask"
              />
            ) : (
              <Select
                options={subtaskOptions}
                showSearch
                optionFilterProp="label"
                placeholder="选择子需求"
                data-testid="tm-inline-subtask"
                dropdownRender={(menu) => (
                  <>
                    {menu}
                    <div className="tm-inline-add__dropdown-new">
                      <Button
                        type="link"
                        size="small"
                        block
                        icon={<PlusOutlined />}
                        onClick={props.onToggleNewSubtask}
                      >
                        新建子需求
                      </Button>
                    </div>
                  </>
                )}
              />
            )}
          </Form.Item>
          {props.newSubtaskMode ? (
            <Form.Item label="子需求内容" style={{ flex: 1, marginBottom: 0, minWidth: 180 }}>
              <Input
                placeholder="子需求内容（可选）"
                value={props.newSubtaskContent}
                onChange={(e) => props.onNewSubtaskContentChange(e.target.value)}
                onPressEnter={props.onCreateSubtask}
                maxLength={TEXT_FIELD_MAX_CHARS}
                data-testid="tm-inline-new-subtask-content"
              />
            </Form.Item>
          ) : null}
          <Form.Item
            name="title"
            label="Action 标题"
            style={{ flex: 1, marginBottom: 0, minWidth: 160 }}
            tooltip="可留空：留空时仅新建/关联子需求，不创建 Action"
          >
            <Input placeholder="本周 Action（可留空）" maxLength={300} data-testid="tm-inline-title" />
          </Form.Item>
          <Form.Item
            name="owner_id"
            label="负责人"
            style={{ width: 100, marginBottom: 0 }}
            rules={[{ required: true, message: '必填' }]}
          >
            <Select options={ownerOptions} showSearch optionFilterProp="label" placeholder="选择" data-testid="tm-inline-owner" />
          </Form.Item>
          <Form.Item name="environment" label="环境" style={{ width: 110, marginBottom: 0 }}>
            <Input placeholder="test/prod" maxLength={ACTION_ENVIRONMENT_MAX_CHARS} data-testid="tm-inline-env" />
          </Form.Item>
          <div className="tm-inline-add__btns">
            {props.newSubtaskMode ? (
              <Button
                size="small"
                type="primary"
                loading={props.subtaskCreating}
                disabled={!props.newSubtaskName.trim()}
                onClick={props.onCreateSubtask}
              >
                创建子需求
              </Button>
            ) : null}
            <Button size="small" onClick={props.onCancel}>取消</Button>
            {!props.newSubtaskMode ? (
              <>
                <Button
                  size="small"
                  loading={props.loading}
                  onClick={() => props.onSubmit(false)}
                  data-testid="tm-inline-draft"
                >
                  存草稿
                </Button>
                <Button
                  size="small"
                  type="primary"
                  loading={props.loading}
                  onClick={() => props.onSubmit(true)}
                  data-testid="tm-inline-publish"
                >
                  发布
                </Button>
              </>
            ) : null}
          </div>
        </div>
        {!props.newSubtaskMode ? (
          <div className="tm-inline-add__row" style={{ marginTop: 8 }}>
            <Form.Item name="test_content" label="测试内容" style={{ flex: 1, marginBottom: 0, minWidth: 160 }}>
              <Input placeholder="可选" maxLength={TEXT_FIELD_MAX_CHARS} data-testid="tm-inline-content" />
            </Form.Item>
            <Form.Item name="dev_members" label="开发人员" style={{ width: 200, marginBottom: 0 }}>
              <MemberTagsSelect size="small" testId="tm-inline-dev-members" />
            </Form.Item>
            <Form.Item name="pm_members" label="产品人员" style={{ width: 200, marginBottom: 0 }}>
              <MemberTagsSelect size="small" testId="tm-inline-pm-members" />
            </Form.Item>
          </div>
        ) : (
          <div className="tm-inline-add__row" style={{ marginTop: 8 }}>
            <Form.Item name="subtask_dev_members" label="开发人员" style={{ width: 200, marginBottom: 0 }}>
              <MemberTagsSelect size="small" testId="tm-inline-subtask-dev-members" />
            </Form.Item>
            <Form.Item name="subtask_pm_members" label="产品人员" style={{ width: 200, marginBottom: 0 }}>
              <MemberTagsSelect size="small" testId="tm-inline-subtask-pm-members" />
            </Form.Item>
          </div>
        )}
      </Form>
    </div>
  )
}

function ActionDetailDrawer(props: {
  open: boolean
  detail?: TmActionDetail
  /** 查看历史周时强制只读（隐藏写操作） */
  forceReadOnly?: boolean
  users: { id: number; username: string; real_name?: string }[]
  userName: (id: number) => string
  onClose: () => void
  onDaily: (p: {
    id: string
    progress_percent: number
    risk_blocker: string
    is_blocking: boolean
    progress_note: string
  }) => void
  onCorrect: (id: string, note: string) => Promise<void>
  onPublish: (id: string) => void
  onSaveDraft: (
    id: string,
    data: {
      title?: string
      subtask_name?: string
      owner_id?: number
      test_content?: string
      environment?: string
      dev_members?: string[]
      pm_members?: string[]
    },
  ) => void
  /** 发布后维护开发/产品人员（信息性字段，所有角色当前周均可改） */
  onSaveMembers: (id: string, data: { dev_members?: string[]; pm_members?: string[] }) => void
  membersLoading: boolean
  /** 发布后改派负责人（走同一 PATCH，后端强制留痕） */
  onSaveOwner: (id: string, owner_id: number) => void
  ownerLoading: boolean
  /** 删除 Action（宽松模式，二次确认；级联删除其日报与更正记录） */
  onDeleteAction: (id: string) => void
  /** 删除指定日期日报（宽松模式，后端自动留痕更正记录） */
  onDeleteDaily: (id: string, reportDate: string) => void
  deleteLoading: boolean
  dailyLoading: boolean
  correctLoading: boolean
  saveDraftLoading: boolean
  publishLoading: boolean
}) {
  const d = props.detail
  const forceReadOnly = !!props.forceReadOnly
  const canEditFields = !forceReadOnly && !!d?.can_edit_fields
  const canDaily = !forceReadOnly && !!d?.can_daily
  const canCorrect = !forceReadOnly && !!d?.can_correct
  /** 发布后改派负责人入口（草稿态走上方编辑表单，不重复展示） */
  const canChangeOwner =
    !forceReadOnly && !!d?.can_change_owner && d.status !== 'draft'
  /** 数据删除入口（宽松模式） */
  const canDeleteAction = !forceReadOnly && !!d?.can_delete
  const canDeleteDaily = !forceReadOnly && !!d?.can_delete_daily
  const [correctForm] = Form.useForm()
  const [draftForm] = Form.useForm()
  const [dailyForm] = Form.useForm()
  const [ownerForm] = Form.useForm()
  const [membersForm] = Form.useForm()
  /** 负责人编辑态：默认收起，点「更改」展开表单，改派成功后自动收起 */
  const [ownerEditing, setOwnerEditing] = useState(false)
  /** 开发/产品人员编辑态：默认收起，点「更改」展开表单，保存成功后自动收起 */
  const [membersEditing, setMembersEditing] = useState(false)
  const correctionEndRef = useRef<HTMLDivElement>(null)
  const pendingScrollToCorrection = useRef(false)
  /** 记录区 tab：daily=日更记录，corr=更正记录 */
  const [logTab, setLogTab] = useState<'daily' | 'corr'>('daily')

  const { data: draftTask } = useQuery({
    queryKey: ['tm-task', d?.task_id, 'for-draft'],
    queryFn: async () => (await testManageApi.getTask(d!.task_id)).data,
    enabled: !!d && props.open && canEditFields,
  })

  const { data: lineage } = useQuery({
    queryKey: ['tm-action-lineage', d?.id],
    queryFn: async () => (await testManageApi.getActionLineage(d!.id)).data,
    enabled: !!d?.id && props.open,
  })

  const ownerCandidates = props.users

  /** 时间线按时间正序：最旧在上、最新在下，滚到底即可看到刚追加的 */
  const correctionsAsc = useMemo(() => {
    const list = d?.corrections ? [...d.corrections] : []
    return list.sort((a, b) => {
      const ta = a.created_at ? new Date(a.created_at).getTime() : 0
      const tb = b.created_at ? new Date(b.created_at).getTime() : 0
      return ta - tb
    })
  }, [d?.corrections])

  /** 日更记录（按日期倒序，最新在上） */
  const dailyLog = useMemo(() => {
    const list = d?.daily_updates ? [...d.daily_updates] : []
    list.sort((a, b) => (b.report_date || '').localeCompare(a.report_date || ''))
    return list
  }, [d?.daily_updates])

  /** 今天（业务日）已提交的日更：用于表单回显，提交后立即可见 */
  const todayDaily = dailyLog.find(
    (u) => (u.report_date || '').slice(0, 10) === tmTodayYmd(),
  )
  const todayNote = todayDaily?.progress_note || ''
  const todayProgress = todayDaily?.progress_percent ?? null
  const todayRisk = todayDaily?.risk_blocker ?? null
  const todayBlocking = todayDaily?.is_blocking ?? null

  useEffect(() => {
    if (!pendingScrollToCorrection.current) return
    if (!props.open) return
    const t = window.setTimeout(() => {
      correctionEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
      pendingScrollToCorrection.current = false
    }, 80)
    return () => window.clearTimeout(t)
  }, [correctionsAsc.length, props.open, d?.id])

  /** 切换 Action 或重新打开时，记录区回到「日更」tab、负责人/人员编辑态收起；
   *  改派成功（owner_id 变化）后也自动收起编辑态 */
  useEffect(() => {
    setLogTab('daily')
    setOwnerEditing(false)
    setMembersEditing(false)
  }, [props.open, d?.id, d?.owner_id])

  /** 详情异步加载后同步日更表单，避免 initialValues 只生效一次导致「是否阻塞」被旧值覆盖写丢；
   *  今天已提交过日更时回显当日内容（进度/完成/风险/阻塞），提交后无需刷新即可见 */
  useEffect(() => {
    if (!props.open || !d || !canDaily) return
    dailyForm.setFieldsValue({
      progress_percent: todayProgress ?? d.progress_percent,
      risk_blocker: todayRisk ?? (d.latest_risk || ''),
      is_blocking: Boolean(todayBlocking ?? d.latest_is_blocking),
      progress_note: todayNote,
    })
  }, [
    props.open,
    canDaily,
    d?.id,
    d?.progress_percent,
    d?.latest_risk,
    d?.latest_is_blocking,
    todayProgress,
    todayRisk,
    todayBlocking,
    todayNote,
    dailyForm,
  ])

  return (
    <Modal
      title={d?.title || 'Action'}
      open={props.open}
      onCancel={props.onClose}
      footer={null}
      width={560}
      destroyOnClose
      styles={{ body: { paddingTop: 12, paddingBottom: 24 } }}
    >
      <div className="tm-sheet" data-testid="tm-drawer-action">
        {!d ? (
          <Text type="secondary">加载中…</Text>
        ) : (
          <div className="tm-sheet__stack">
            {/* 1. 摘要：纯文字，与下方 section 风格统一 */}
            <header className="tm-sheet__head">
              <div className="tm-sheet__head-line">
                <Tag color={STATUS_LABEL[d.status]?.color}>{STATUS_LABEL[d.status]?.text}</Tag>
                <span className="tm-sheet__head-task">{d.task_title}</span>
                <span className="tm-sheet__muted"> · 进度 {d.progress_percent}%</span>
              </div>
              <div className="tm-sheet__head-meta">
                子需求 {d.subtask_name || '未关联'} · 负责人 {props.userName(d.owner_id)}
                {d.environment ? <> · 环境 {d.environment}</> : null}
                {d.dev_members?.length ? <> · 开发 {d.dev_members.join('、')}</> : null}
                {d.pm_members?.length ? <> · 产品 {d.pm_members.join('、')}</> : null}
                {d.status === 'done' && d.completed_at ? (
                  <> · 完成 {dayjs(d.completed_at).format('MM-DD HH:mm')}</>
                ) : null}
              </div>
            </header>

            {/* 1a. 更改负责人（发布后改派；后端自动写「负责人更正」留痕；点「更改」展开表单） */}
            {canChangeOwner ? (
              <section className="tm-sheet__section">
                <h3
                  className="tm-sheet__h"
                  style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 4 }}
                >
                  更改负责人
                  <span className="tm-sheet__muted">
                    · 当前 {props.userName(d.owner_id)} · 自动记入更正记录
                  </span>
                  {!ownerEditing ? (
                    <Button
                      type="link"
                      size="small"
                      onClick={() => setOwnerEditing(true)}
                      data-testid="tm-owner-edit"
                    >
                      更改
                    </Button>
                  ) : null}
                </h3>
                {ownerEditing ? (
                  <Form
                    form={ownerForm}
                    layout="vertical"
                    size="small"
                    className="tm-sheet__form"
                    key={`tm-owner-${d.id}-${d.owner_id}`}
                    initialValues={{ owner_id: d.owner_id }}
                    onFinish={(v) => props.onSaveOwner(d.id, Number(v.owner_id))}
                  >
                    <div className="tm-sheet__inline">
                      <Form.Item
                        name="owner_id"
                        label="新负责人"
                        rules={[
                          { required: true, message: '请选择新负责人' },
                          {
                            validator: (_rule, value) =>
                              value && Number(value) !== d.owner_id
                                ? Promise.resolve()
                                : Promise.reject(new Error('请选择与当前不同的负责人')),
                          },
                        ]}
                      >
                        <Select
                          options={userSelectOptions(ownerCandidates)}
                          showSearch
                          optionFilterProp="label"
                          autoFocus
                          data-testid="tm-owner-select"
                        />
                      </Form.Item>
                      <Button
                        color="primary"
                        variant="outlined"
                        size="small"
                        htmlType="submit"
                        loading={props.ownerLoading}
                        data-testid="tm-submit-owner"
                      >
                        确认更改
                      </Button>
                      <Button size="small" type="text" onClick={() => setOwnerEditing(false)}>
                        取消
                      </Button>
                    </div>
                  </Form>
                ) : null}
              </section>
            ) : null}

            {/* 1b. 开发/产品人员（信息性字段：宽松模式所有角色当前周均可维护；严格模式管理员/Task 负责人；已完成/已取消不可改） */}
            {!forceReadOnly && d.can_edit_members && d.status === 'published' ? (
              <section className="tm-sheet__section">
                <h3
                  className="tm-sheet__h"
                  style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 4 }}
                >
                  开发/产品人员
                  <span className="tm-sheet__muted">
                    · 开发 {d.dev_members?.length ? d.dev_members.join('、') : '—'} · 产品{' '}
                    {d.pm_members?.length ? d.pm_members.join('、') : '—'}
                  </span>
                  {!membersEditing ? (
                    <Button
                      type="link"
                      size="small"
                      onClick={() => setMembersEditing(true)}
                      data-testid="tm-members-edit"
                    >
                      更改
                    </Button>
                  ) : null}
                </h3>
                {membersEditing ? (
                  <Form
                    form={membersForm}
                    layout="vertical"
                    size="small"
                    className="tm-sheet__form"
                    key={`tm-members-${d.id}`}
                    initialValues={{
                      dev_members: d.dev_members || [],
                      pm_members: d.pm_members || [],
                    }}
                    onFinish={(v) =>
                      props.onSaveMembers(d.id, {
                        dev_members: v.dev_members || [],
                        pm_members: v.pm_members || [],
                      })
                    }
                  >
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 12 }}>
                      <Form.Item name="dev_members" label="开发人员">
                        <MemberTagsSelect size="small" testId="tm-members-dev" />
                      </Form.Item>
                      <Form.Item name="pm_members" label="产品人员">
                        <MemberTagsSelect size="small" testId="tm-members-pm" />
                      </Form.Item>
                    </div>
                    <div className="tm-sheet__actions">
                      <Button
                        color="primary"
                        variant="outlined"
                        size="small"
                        htmlType="submit"
                        loading={props.membersLoading}
                        data-testid="tm-submit-members"
                      >
                        保存
                      </Button>
                      <Button size="small" type="text" onClick={() => setMembersEditing(false)}>
                        取消
                      </Button>
                    </div>
                  </Form>
                ) : null}
              </section>
            ) : null}

            {/* 2. 延续历史 */}
            {lineage && lineage.weeks_count > 0 ? (
              <Collapse
                size="small"
                ghost
                className="tm-sheet__lineage"
                data-testid="tm-action-lineage"
                items={[
                  {
                    key: 'lineage',
                    label: `延续历史 · ${lineage.weeks_count} 周`,
                    children: (
                      <Timeline
                        className="tm-lineage-timeline"
                        items={lineage.segments.map((seg) => ({
                          color: seg.is_current ? 'green' : 'gray',
                          children: (
                            <div className="tm-lineage-item">
                              <div className="tm-lineage-item__head">
                                <span className="tm-lineage-item__week">{seg.week_key}</span>
                                {seg.is_current ? <Tag color="success">当前</Tag> : null}
                                <Tag>{STATUS_LABEL[seg.status]?.text || seg.status}</Tag>
                                <span className="tm-sheet__muted">{seg.progress_percent}%</span>
                              </div>
                              <div className="tm-lineage-item__title">{seg.title}</div>
                              {seg.risks.length > 0 ? (
                                <Paragraph
                                  type="danger"
                                  className="tm-lineage-item__risk"
                                  ellipsis={{ rows: 2, tooltip: seg.risks.join('；') }}
                                >
                                  阻塞：{seg.risks.join('；')}
                                </Paragraph>
                              ) : (
                                <span className="tm-sheet__muted">无阻塞</span>
                              )}
                            </div>
                          ),
                        }))}
                      />
                    ),
                  },
                ]}
              />
            ) : null}

            {/* 3. 提示（一行） */}
            {forceReadOnly ? (
              <p className="tm-sheet__tip">历史周只读不可编辑</p>
            ) : null}
            {!canDaily && !forceReadOnly && d.status === 'published' ? (
              <p className="tm-sheet__tip">
                {isWeekSwitchDay() && d.week_key && d.week_key !== dailyContextWeekKey()
                  ? '今天 17:00 已切周，今日日更归属上一汇报周；请在上方「延续历史」中打开上一周的记录写日更'
                  : canCorrect
                    ? '今日不可日更 · 可用更正说明'
                    : `仅负责人或测试管理员可日更（${props.userName(d.owner_id)}）`}
              </p>
            ) : null}

            {/* 4. 基本信息 / 草稿编辑 */}
            {d.status === 'draft' && canEditFields ? (
              <section className="tm-sheet__section">
                <h3 className="tm-sheet__h">编辑草稿</h3>
                <Form
                  form={draftForm}
                  layout="vertical"
                  size="middle"
                  className="tm-sheet__form"
                  key={`${d.id}-${d.updated_at || ''}`}
                  initialValues={{
                    title: d.title,
                    subtask_name: d.subtask_name,
                    owner_id: d.owner_id,
                    test_content: d.test_content,
                    environment: d.environment,
                    dev_members: d.dev_members || [],
                    pm_members: d.pm_members || [],
                  }}
                >
                  <Form.Item name="subtask_name" label="关联子需求">
                    <Select
                      options={[
                        { value: '', label: '暂不关联（未关联）' },
                        ...(draftTask?.subtasks || []).map((s) => ({
                          value: s.name,
                          label: s.name,
                        })),
                      ]}
                      showSearch
                      optionFilterProp="label"
                      placeholder="选择子需求（可暂不关联）"
                    />
                  </Form.Item>
                  <Form.Item name="title" label="标题" rules={[{ required: true }]}>
                    <Input maxLength={300} showCount />
                  </Form.Item>
                  <Form.Item name="owner_id" label="本周负责人" rules={[{ required: true }]}>
                    <Select
                      options={userSelectOptions(ownerCandidates)}
                      showSearch
                      optionFilterProp="label"
                    />
                  </Form.Item>
                  <Form.Item name="test_content" label="测试内容">
                    <TextArea rows={3} maxLength={TEXT_FIELD_MAX_CHARS} showCount />
                  </Form.Item>
                  <Form.Item name="environment" label="环境">
                    <Input maxLength={ACTION_ENVIRONMENT_MAX_CHARS} showCount />
                  </Form.Item>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 12 }}>
                    <Form.Item name="dev_members" label="开发人员">
                      <MemberTagsSelect testId="tm-draft-dev-members" />
                    </Form.Item>
                    <Form.Item name="pm_members" label="产品人员">
                      <MemberTagsSelect testId="tm-draft-pm-members" />
                    </Form.Item>
                  </div>
                  <div className="tm-sheet__actions">
                    <Button
                      loading={props.saveDraftLoading}
                      data-testid="tm-btn-save-draft"
                      onClick={() =>
                        void draftForm.validateFields().then((v) =>
                          props.onSaveDraft(d.id, {
                            title: v.title,
                            subtask_name: v.subtask_name,
                            owner_id: Number(v.owner_id),
                            test_content: v.test_content || '',
                            environment: v.environment || '',
                            dev_members: v.dev_members || [],
                            pm_members: v.pm_members || [],
                          }),
                        )
                      }
                    >
                      保存
                    </Button>
                    <Button
                      type="primary"
                      icon={<SendOutlined />}
                      loading={props.publishLoading}
                      data-testid="tm-btn-publish-action"
                      onClick={() => props.onPublish(d.id)}
                    >
                      发布
                    </Button>
                  </div>
                </Form>
              </section>
            ) : null}

            {/* 5. 非草稿态：测试内容非空时折叠显示，默认收起 */}
            {d.status !== 'draft' && d.test_content ? (
              <Collapse
                size="small"
                ghost
                className="tm-sheet__details"
                items={[
                  {
                    key: 'info',
                    label: '测试内容',
                    children: <div className="tm-sheet__body">{d.test_content}</div>,
                  },
                ]}
              />
            ) : null}

            {/* 6. 日更（进行中可写；已完成展示最近日更记录，避免突变） */}
            {canDaily ? (
              <section className="tm-sheet__section">
                <h3 className="tm-sheet__h">
                  日更 <span className="tm-sheet__muted">19:50 截止</span>
                </h3>
                <Form
                  form={dailyForm}
                  layout="vertical"
                  size="small"
                  className="tm-sheet__form"
                  key={`tm-daily-${d.id}`}
                  preserve={false}
                  onFinish={(v) =>
                    props.onDaily({
                      id: d.id,
                      progress_percent: v.progress_percent,
                      risk_blocker: v.risk_blocker || '',
                      is_blocking: v.is_blocking === true,
                      progress_note: (v.progress_note || '').trim(),
                    })
                  }
                >
                  <Form.Item
                    name="progress_percent"
                    label={
                      <span>
                        当前进度
                        <span className="tm-sheet__muted">
                          {' '}
                          （进度 100 默认当前 Action 完成）
                        </span>
                      </span>
                    }
                    rules={[{ required: true, message: '必填' }]}
                    extra={
                      (d.progress_percent ?? 0) > 0 ? (
                        <span data-testid="tm-daily-progress-min">
                          ≥ 当前 {d.progress_percent}%，进度只增不减
                        </span>
                      ) : undefined
                    }
                    style={{ marginBottom: 8 }}
                  >
                    <InputNumber
                      size="small"
                      min={d.progress_percent ?? 0}
                      max={100}
                      style={{ width: '100%' }}
                      placeholder={`当前 ${d.progress_percent}%`}
                      data-testid="tm-daily-progress"
                    />
                  </Form.Item>
                  <Form.Item
                    name="progress_note"
                    label="今日完成"
                    rules={[{ required: true, whitespace: true, message: '必填' }]}
                    style={{ marginBottom: 10 }}
                  >
                    <TextArea
                      rows={1}
                      autoSize={{ minRows: 1, maxRows: 4 }}
                      maxLength={TEXT_FIELD_MAX_CHARS}
                      showCount
                      placeholder="今天做了什么"
                      data-testid="tm-daily-note"
                    />
                  </Form.Item>
                  <div
                    style={{
                      display: 'flex',
                      gap: 12,
                      alignItems: 'flex-start',
                      marginBottom: 10,
                    }}
                  >
                    <Form.Item
                      name="risk_blocker"
                      label="风险"
                      style={{ flex: 1, marginBottom: 0 }}
                    >
                      <TextArea
                        rows={1}
                        autoSize={{ minRows: 1, maxRows: 3 }}
                        maxLength={TEXT_FIELD_MAX_CHARS}
                        placeholder="如有风险，简要说明"
                        data-testid="tm-daily-risk"
                      />
                    </Form.Item>
                    <Form.Item
                      name="is_blocking"
                      valuePropName="checked"
                      style={{ marginBottom: 0, paddingTop: 22 }}
                    >
                      <Checkbox data-testid="tm-daily-is-blocking">是否阻塞</Checkbox>
                    </Form.Item>
                  </div>
                  <div className="tm-sheet__actions">
                    <Button
                      color="primary"
                      variant="outlined"
                      size="small"
                      htmlType="submit"
                      loading={props.dailyLoading}
                      data-testid="tm-submit-daily"
                    >
                      提交日更
                    </Button>
                  </div>
                </Form>
              </section>
            ) : null}

            {/* 6b. 记录（tab 切换）：日更=今天/昨天/更早；更正=留痕时间线；进行中/已完成/历史周均可见 */}
            <section className="tm-sheet__section tm-sheet__daily-log">
              <Tabs
                key={d.id}
                size="small"
                style={{ marginBottom: 0 }}
                activeKey={logTab}
                onChange={(k) => setLogTab(k as 'daily' | 'corr')}
                tabBarExtraContent={
                  logTab === 'daily' && !canDaily && !forceReadOnly && canDeleteDaily ? (
                    <Popconfirm
                      title="删除该日日报？"
                      description="删除后自动记入更正记录，进度以剩余日更为准"
                      okText="删除"
                      cancelText="取消"
                      okButtonProps={{ danger: true }}
                      onConfirm={() =>
                        props.onDeleteDaily(d.id, dailyLog[0].report_date.slice(0, 10))
                      }
                    >
                      <Button
                        size="small"
                        type="text"
                        danger
                        loading={props.deleteLoading}
                        data-testid="tm-delete-daily"
                      >
                        删除日报
                      </Button>
                    </Popconfirm>
                  ) : null
                }
                items={[
                  {
                    key: 'daily',
                    label: (
                      <>
                        日更 <span className="tm-sheet__muted">{dailyLog.length}</span>
                      </>
                    ),
                    children:
                      dailyLog.length === 0 ? (
                        <p className="tm-sheet__muted">暂无</p>
                      ) : (
                        dailyLog.map((u, i) => (
                          <div
                            key={u.id}
                            data-testid="tm-daily-log-row"
                            style={{
                              padding: '8px 0',
                              borderTop: i ? '1px dashed #f0f0f0' : undefined,
                            }}
                          >
                            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                              <Text strong>{dailyDateLabel(u.report_date)}</Text>
                              <Text type="secondary">{u.progress_percent}%</Text>
                              {u.is_blocking ? (
                                <Tag color="red" style={{ marginRight: 0 }}>
                                  阻塞
                                </Tag>
                              ) : null}
                            </div>
                            {u.progress_note ? (
                              <div className="tm-sheet__body">{u.progress_note}</div>
                            ) : null}
                            {u.risk_blocker ? (
                              <div className="tm-sheet__risk-note">
                                <Text type="danger">风险：{u.risk_blocker}</Text>
                              </div>
                            ) : null}
                          </div>
                        ))
                      ),
                  },
                  {
                    key: 'corr',
                    label: (
                      <>
                        更正 <span className="tm-sheet__muted">{correctionsAsc.length}</span>
                      </>
                    ),
                    children: (
                      <>
                        {correctionsAsc.length === 0 ? (
                          <p className="tm-sheet__muted">暂无</p>
                        ) : (
                          <Timeline
                            items={correctionsAsc.map((c, idx) => ({
                              color: idx === correctionsAsc.length - 1 ? 'orange' : 'gray',
                              children: (
                                <div className="tm-sheet__corr">
                                  <div className="tm-sheet__muted">
                                    {c.created_at || ''} · {props.userName(c.user_id)}
                                    {idx === correctionsAsc.length - 1 ? ' · 最新' : ''}
                                  </div>
                                  <div className="tm-sheet__corr-note">{c.note}</div>
                                </div>
                              ),
                            }))}
                          />
                        )}
                        <div ref={correctionEndRef} />
                      </>
                    ),
                  },
                ]}
              />
            </section>

            {/* 7. 更正 */}
            {canCorrect ? (
              <section className="tm-sheet__section">
                <h3 className="tm-sheet__h">更正说明</h3>
                <Form
                  form={correctForm}
                  layout="vertical"
                  size="small"
                  className="tm-sheet__form"
                  onFinish={async (v) => {
                    try {
                      pendingScrollToCorrection.current = true
                      await props.onCorrect(d.id, v.note)
                      correctForm.resetFields()
                      setLogTab('corr')
                    } catch {
                      pendingScrollToCorrection.current = false
                    }
                  }}
                >
                  <Form.Item
                    name="note"
                    rules={[
                      { required: true, message: '请填写' },
                      { max: TEXT_FIELD_MAX_CHARS, message: `最多 ${TEXT_FIELD_MAX_CHARS} 字` },
                    ]}
                  >
                    <TextArea
                      rows={1}
                      autoSize={{ minRows: 1, maxRows: 4 }}
                      placeholder="更正内容…"
                      maxLength={TEXT_FIELD_MAX_CHARS}
                      showCount
                      data-testid="tm-correction-note"
                    />
                  </Form.Item>
                  <div className="tm-sheet__actions">
                    <Button
                      color="primary"
                      variant="outlined"
                      size="small"
                      htmlType="submit"
                      loading={props.correctLoading}
                      data-testid="tm-submit-correction"
                    >
                      追加更正
                    </Button>
                  </div>
                </Form>
              </section>
            ) : null}

            {/* 9. 危险操作：删除 Action（宽松模式，需二次确认） */}
            {canDeleteAction ? (
              <section className="tm-sheet__section">
                <Popconfirm
                  title="删除该 Action？"
                  description="将级联删除其全部日报与更正记录，不可恢复"
                  okText="删除"
                  cancelText="取消"
                  okButtonProps={{ danger: true }}
                  onConfirm={() => props.onDeleteAction(d.id)}
                >
                  <Button block danger loading={props.deleteLoading} data-testid="tm-delete-action">
                    删除 Action
                  </Button>
                </Popconfirm>
              </section>
            ) : null}
          </div>
        )}
      </div>
    </Modal>
  )
}
