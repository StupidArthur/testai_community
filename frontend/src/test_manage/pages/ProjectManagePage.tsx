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
  Drawer,
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
  taskParticipantUsers,
} from '../utils/boardUi'
import { isMissingDailyToday, isBlockingFlag } from '../utils/screenFilters'
import {
  DISPLAY_STATUS_OPTIONS,
  DISPLAY_STATUS_TAG_COLOR,
  displayStatusLabel,
  displayStatusTagColor,
  splitDisplayStatus,
} from '../utils/displayStatus'
import {
  REQ_STAGE_OPTIONS,
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
  /** 工作台 Task 分页 */
  const [boardTaskPage, setBoardTaskPage] = useState(1)
  const [boardTaskPageSize, setBoardTaskPageSize] = useState<number>(BOARD_TASK_PAGE_SIZE_DEFAULT)
  const [mineActionPage, setMineActionPage] = useState(1)

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
    mutationFn: (p: { taskId: string; name: string; content?: string }) =>
      testManageApi.addSubtask(p.taskId, { name: p.name, content: p.content }),
    onSuccess: () => {
      message.success('子需求已添加')
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '添加失败'),
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

  /** 工作台列表：归档 Task 默认不展示（与归档确认文案一致） */
  const boardTasksScoped = useMemo(() => {
    const list = (board?.tasks || []).filter((bt) => bt.task.status !== 'cancelled')
    const uid = user?.id != null ? Number(user.id) : null
    let scoped = filterBoardTasksByScope(list, boardTaskScope, uid)
    if (boardLeadFilter != null) {
      scoped = scoped.filter((bt) => Number(bt.task.lead_id) === boardLeadFilter)
    }
    if (boardDomainFilter) {
      scoped = scoped.filter((bt) => bt.task.domain_id === boardDomainFilter)
    }
    if (boardStatusFilter) {
      scoped = scoped.filter((bt) => bt.task.display_status === boardStatusFilter)
    }
    return scoped
  }, [
    board?.tasks,
    boardTaskScope,
    user?.id,
    boardLeadFilter,
    boardDomainFilter,
    boardStatusFilter,
  ])

  /** 筛选下拉选项：从当前看板数据去重（只列实际存在的负责人/领域/状态） */
  const boardFilterOptions = useMemo(() => {
    const list = (board?.tasks || []).filter((bt) => bt.task.status !== 'cancelled')
    const leads = new Map<number, string>()
    const domainsMap = new Map<string, string>()
    const statusSet = new Set<string>()
    for (const bt of list) {
      const lid = Number(bt.task.lead_id)
      if (!leads.has(lid)) leads.set(lid, userName(lid))
      if (!domainsMap.has(bt.task.domain_id)) {
        domainsMap.set(bt.task.domain_id, bt.task.domain_name || '未分领域')
      }
      const ds = (bt.task.display_status || '').trim()
      if (ds) statusSet.add(ds)
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
    return { leadOpts, domainOpts, statusOpts }
  }, [board?.tasks, userName])

  /** 工作台筛选是否有生效条件（空态文案用） */
  const boardFiltersActive =
    boardLeadFilter != null || !!boardDomainFilter || !!boardStatusFilter

  /** 筛选/周切换后回到第 1 页 */
  useEffect(() => {
    setBoardTaskPage(1)
  }, [boardTaskScope, projectId, boardWeekStart, weekMode, boardLeadFilter, boardDomainFilter, boardStatusFilter])

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

  const changeActionStatusMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      testManageApi.updateAction(id, { status }),
    onSuccess: (_data, vars) => {
      message.success(`状态已更新为「${STATUS_LABEL[vars.status]?.text || vars.status}」`)
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '状态更新失败'),
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

        <Space wrap style={{ marginBottom: 16 }}>
          <Select
            style={{ minWidth: 160 }}
            value={boardTaskScope}
            onChange={setBoardTaskScope}
            options={[
              { value: 'mine', label: `我的 Task（${boardScopeCounts.mine}）` },
              { value: 'all', label: `全部（${boardScopeCounts.all}）` },
            ]}
            data-testid="tm-scope-select"
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="按项目筛选"
            style={{ minWidth: 200 }}
            value={projectId}
            onChange={setProjectId}
            options={projects.map((p) => ({ value: p.id, label: p.name }))}
            data-testid="tm-project-filter"
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="按负责人筛选"
            style={{ minWidth: 150 }}
            value={boardLeadFilter ?? undefined}
            onChange={(v) => setBoardLeadFilter(v ?? null)}
            options={boardFilterOptions.leadOpts}
            data-testid="tm-lead-filter"
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="按领域筛选"
            style={{ minWidth: 150 }}
            value={boardDomainFilter ?? undefined}
            onChange={(v) => setBoardDomainFilter(v ?? null)}
            options={boardFilterOptions.domainOpts}
            data-testid="tm-domain-filter"
          />
          <Select
            allowClear
            placeholder="按状态筛选"
            style={{ minWidth: 130 }}
            value={boardStatusFilter ?? undefined}
            onChange={(v) => setBoardStatusFilter(v ?? null)}
            options={boardFilterOptions.statusOpts}
            data-testid="tm-status-filter"
          />
          {tmAdmin && !viewingHistory && (
            <Dropdown
              menu={{
                items: [
                  {
                    key: 'project',
                    label: '项目',
                  },
                  {
                    key: 'domain',
                    label: '领域',
                    disabled: !projectId,
                  },
                  {
                    key: 'task',
                    label: 'Task',
                  },
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
              <Button type="primary" icon={<PlusOutlined />} data-testid="tm-btn-create-menu">
                新建 <DownOutlined />
              </Button>
            </Dropdown>
          )}
        </Space>

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
                onCreateSubtask={(name, content) =>
                  addSubtaskMut.mutate({ taskId: bt.task.id, name, content })
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
                  {canQuickDaily ? (
                    <DailyQuickPopover
                      action={a}
                      loading={dailyMut.isPending}
                      onSubmit={(p) => dailyMut.mutate(p)}
                    >
                      <Button size="small" data-testid={`tm-mine-quick-daily-${a.id}`}>
                        日更
                      </Button>
                    </DailyQuickPopover>
                  ) : null}
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
            }}
            onFinish={(v) =>
              createTaskMut.mutate({
                project_id: v.project_id,
                domain_id: v.domain_id,
                title: v.title,
                requirement: v.requirement || '',
                lead_id: Number(v.lead_id),
                tester_ids: (v.tester_ids || []).map((x: number | string) => Number(x)),
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
            <Form.Item name="tester_ids" label="测试人员">
              <Select
                mode="multiple"
                options={userOptions}
                showSearch
                optionFilterProp="label"
                loading={usersLoading}
                placeholder={usersLoading ? '加载中…' : '可选多人'}
                notFoundContent={usersLoading ? '加载中…' : '无用户'}
                data-testid="tm-task-testers"
              />
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

      {/* Task 抽屉：详情 | 进展（需求流程 + 本周进度） */}
      <Drawer
        title={
          taskDrawerFocus === 'progress'
            ? `进展 · ${taskDetail?.title || 'Task'}`
            : taskDetail?.title || 'Task 详情'
        }
        open={!!editTaskId}
        onClose={() => {
          setEditTaskId(null)
          setTaskSaveTip(null)
          setTaskInfoEditing(false)
          setTaskDrawerFocus('progress')
        }}
        width={480}
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
                    <h3 className="tm-sheet__h">状态</h3>
                    {!viewingHistory &&
                    (taskDetail.can_edit_req_stage ||
                      (taskDetail.can_edit && taskDetail.req_stage === 'testing')) ? (
                      <Form
                        key={`flow-${taskDetail.id}-${taskFormEpoch}`}
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
                          extra="阶段决定能否建 Action、能否填本周进度"
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
                                      extra="可清空表示待定"
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
                                      extra="可清空表示待定"
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
                                        extra="可清空表示待定"
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
                                        extra="可清空表示待定"
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
                                      extra="可清空表示待定"
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
              ) : (
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
                        key={`${taskDetail.id}-${taskFormEpoch}`}
                        layout="vertical"
                        className="tm-sheet__form"
                        initialValues={{
                          title: taskDetail.title,
                          requirement: taskDetail.requirement,
                          lead_id: Number(taskDetail.lead_id),
                          tester_ids: (taskDetail.tester_ids || []).map(Number),
                          change_summary: '',
                        }}
                        onFinish={(v) => {
                          const payload: Parameters<typeof testManageApi.updateTask>[1] = {
                            title: v.title,
                            requirement: v.requirement,
                            lead_id: Number(v.lead_id),
                            tester_ids: (v.tester_ids || []).map((x: number | string) => Number(x)),
                            change_summary: v.change_summary,
                          }
                          updateTaskMut.mutate({ id: taskDetail.id, data: payload })
                        }}
                      >
                        <Form.Item name="title" label="标题" rules={[{ required: true }]}>
                          <Input />
                        </Form.Item>
                        <Form.Item name="requirement" label="需求内容">
                          <TextArea rows={4} maxLength={TASK_REQUIREMENT_MAX_CHARS} showCount />
                        </Form.Item>
                        <Form.Item name="lead_id" label="测试负责人">
                          <Select
                            options={userOptions}
                            showSearch
                            optionFilterProp="label"
                            loading={usersLoading}
                          />
                        </Form.Item>
                        <Form.Item name="tester_ids" label="测试人员">
                          <Select
                            mode="multiple"
                            options={userOptions}
                            showSearch
                            optionFilterProp="label"
                            loading={usersLoading}
                          />
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
                              改状态请用「操作 → 进度」
                            </div>
                          </dd>
                        </div>
                        <div>
                          <dt>项目 / 领域</dt>
                          <dd>
                            {taskDetail.project_name} / {taskDetail.domain_name}
                          </dd>
                        </div>
                        <div>
                          <dt>负责人</dt>
                          <dd>{userName(taskDetail.lead_id)}</dd>
                        </div>
                        <div>
                          <dt>测试人员</dt>
                          <dd>
                            {(taskDetail.tester_ids || []).length
                              ? (taskDetail.tester_ids || []).map((id) => userName(Number(id))).join('、')
                              : '—'}
                          </dd>
                        </div>
                        <div>
                          <dt>需求</dt>
                          <dd>{taskDetail.requirement?.trim() || '—'}</dd>
                        </div>
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
                        columns={[
                          { title: '名称', dataIndex: 'name', key: 'name', width: 180, render: (t: string) => <Text strong>{t}</Text> },
                          { title: '内容', dataIndex: 'content', key: 'content', ellipsis: true, render: (t?: string) => t || <Text type="secondary">—</Text> },
                          {
                            title: '操作',
                            key: 'op',
                            width: 60,
                            render: (_: unknown, r: TmSubtask) =>
                              !viewingHistory && taskDetail.can_edit ? (
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
                                  <Button size="small" type="link" danger>
                                    删除
                                  </Button>
                                </Popconfirm>
                              ) : null,
                          },
                        ]}
                        dataSource={taskDetail.subtasks}
                      />
                    </section>
                  ) : null}

                  {taskDetail.can_edit && !viewingHistory && taskDetail.can_add_action ? (
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
              )}
            </div>
          </div>
        ) : null}
      </Drawer>

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
        onChangeStatus={(id, status) => changeActionStatusMut.mutate({ id, status })}
        onSaveDraft={(id, data) => updateActionMut.mutate({ id, data })}
        dailyLoading={dailyMut.isPending}
        correctLoading={correctMut.isPending}
        saveDraftLoading={updateActionMut.isPending}
        publishLoading={publishActionMut.isPending}
        statusLoading={changeActionStatusMut.isPending}
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
          <Button
            type="primary"
            block
            loading={props.loading}
            onClick={submit}
            data-testid="tm-daily-pop-submit"
          >
            提交日更
          </Button>
        </div>
      }
    >
      {props.children}
    </Popover>
  )
}

function BoardTaskCard(props: {
  bt: BoardTask
  readOnly?: boolean
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
    },
    publish: boolean,
  ) => void
  onCreateSubtask: (name: string, content?: string) => void
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

  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(bt.actions.length / ACTION_CARD_PAGE_SIZE) || 1)
    if (actionPage > maxPage) setActionPage(maxPage)
  }, [bt.actions.length, actionPage])

  const actionsSorted = useMemo(() => sortActionCardsForList(bt.actions), [bt.actions])

  const actionsPaged = useMemo(() => {
    const start = (actionPage - 1) * ACTION_CARD_PAGE_SIZE
    return actionsSorted.slice(start, start + ACTION_CARD_PAGE_SIZE)
  }, [actionsSorted, actionPage])

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
    ...(!readOnly && bt.task.can_edit
      ? [
          { key: 'progress', label: '进度' },
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
          <Tag color={stColor}>{stLabel}</Tag>
          <Tag>
            {bt.task.project_name}/{bt.task.domain_name}
          </Tag>
          {highlightEmpty ? (
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
          bt.task.can_edit &&
          shouldShowAddActionButton({
            readOnly: !!readOnly,
            canEdit: !!bt.task.can_edit,
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
              + Action
            </Button>
          ) : null}
        </Space>
      }
    >
      <Paragraph type="secondary" className="tm-board-task-req" ellipsis={{ rows: 2 }}>
        需求：{bt.task.requirement || '（无）'} · 负责人 {userName(bt.task.lead_id)}
      </Paragraph>
      {bt.actions.length === 0 ? (
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
            onRow={(a): any => ({
              onClick: () => props.onOpenAction(a.id),
              className: 'tm-action-card tm-action-table__row',
              'data-testid': `tm-action-card-${a.id}`,
              'data-action-title': a.title,
            })}
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
                    <Text type="secondary">—</Text>
                  )
                },
              },
              {
                title: 'Action',
                dataIndex: 'title',
                ellipsis: true,
                render: (v: string) => <span className="tm-action-table__title">{v}</span>,
              },
              {
                title: '负责人',
                dataIndex: 'owner_id',
                width: 90,
                ellipsis: true,
                render: (v: number) => userName(v),
              },
              {
                title: '进度',
                dataIndex: 'progress_percent',
                width: 150,
                render: (v: number) => (
                  <Progress percent={v} size="small" className="tm-action-table__progress" />
                ),
              },
              {
                title: '状态',
                dataIndex: 'status',
                width: 96,
                render: (v: string, a: TmAction) => (
                  <Space size={4} wrap={false}>
                    <Tag color={STATUS_LABEL[v]?.color}>{STATUS_LABEL[v]?.text}</Tag>
                    {!readOnly && v === 'draft' && a.can_edit_fields ? (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        点开可编辑
                      </Text>
                    ) : null}
                  </Space>
                ),
              },
              {
                title: '风险',
                dataIndex: 'latest_risk',
                ellipsis: true,
                render: (v: string | undefined, a: TmAction) =>
                  a.status === 'published' && v ? (
                    <Tooltip title={v}>
                      <Text type="danger" className="tm-action-table__risk">
                        <WarningOutlined /> {v}
                      </Text>
                    </Tooltip>
                  ) : (
                    <Text type="secondary">—</Text>
                  ),
              },
              {
                title: '操作',
                key: 'op',
                width: 108,
                render: (_: unknown, a: TmAction) =>
                  !readOnly ? (
                    <Space size={0} wrap={false} onClick={(e) => e.stopPropagation()}>
                      {a.status === 'published' && (props.canQuickDaily?.(a) ?? true) ? (
                        <DailyQuickPopover
                          action={a}
                          loading={props.dailyLoading}
                          onSubmit={props.onDaily}
                        >
                          <Button size="small" type="link" data-testid={`tm-quick-daily-${a.id}`}>
                            日更
                          </Button>
                        </DailyQuickPopover>
                      ) : null}
                      {a.status === 'draft' && a.can_edit_fields ? (
                        <Button
                          size="small"
                          type="link"
                          icon={<SendOutlined />}
                          onClick={() => props.onPublishAction(a.id)}
                        >
                          发布
                        </Button>
                      ) : null}
                    </Space>
                  ) : null,
              },
            ]}
          />
          {bt.actions.length > ACTION_CARD_PAGE_SIZE ? (
            <div
              className="tm-board-pagination"
              data-testid={`tm-task-action-pagination-${bt.task.id}`}
            >
              <Pagination
                current={actionPage}
                pageSize={ACTION_CARD_PAGE_SIZE}
                total={bt.actions.length}
                showSizeChanger={false}
                showTotal={(t) => `共 ${t} 个 Action`}
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
            props.onCreateSubtask(name, newSubtaskContent.trim())
            setNewSubtaskName('')
            setNewSubtaskContent('')
            setNewSubtaskMode(false)
            addForm.setFieldsValue({ subtask_name: name })
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
              if (!subName) {
                message.warning('请选择或新建子需求')
                return
              }
              props.onCreateAction(
                {
                  title: v.title.trim(),
                  subtask_name: subName,
                  owner_id: Number(v.owner_id),
                  test_content: v.test_content || '',
                  environment: v.environment || '',
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
    () =>
      (task.subtasks || []).map((s) => ({
        value: s.name,
        label: s.name,
      })),
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
          <Form.Item
            name="subtask_name"
            label="子需求"
            style={{ width: 140, marginBottom: 0 }}
            rules={props.newSubtaskMode ? [] : [{ required: true, message: '必填' }]}
          >
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
            rules={[{ required: true, message: '必填' }]}
          >
            <Input placeholder="本周 Action" maxLength={300} data-testid="tm-inline-title" />
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
          <Form.Item name="test_content" label="测试内容" style={{ marginBottom: 0, marginTop: 8 }}>
            <Input placeholder="可选" maxLength={TEXT_FIELD_MAX_CHARS} data-testid="tm-inline-content" />
          </Form.Item>
        ) : null}
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
  onChangeStatus: (id: string, status: string) => void
  onSaveDraft: (
    id: string,
    data: {
      title?: string
      subtask_name?: string
      owner_id?: number
      test_content?: string
      environment?: string
    },
  ) => void
  dailyLoading: boolean
  correctLoading: boolean
  saveDraftLoading: boolean
  publishLoading: boolean
  statusLoading: boolean
}) {
  const d = props.detail
  const forceReadOnly = !!props.forceReadOnly
  const canEditFields = !forceReadOnly && !!d?.can_edit_fields
  const canDaily = !forceReadOnly && !!d?.can_daily
  const canCorrect = !forceReadOnly && !!d?.can_correct
  const canChangeStatus = !forceReadOnly && !!d?.can_change_status
  const canMarkDone = !forceReadOnly && !!d?.can_mark_done
  const [correctForm] = Form.useForm()
  const [draftForm] = Form.useForm()
  const [dailyForm] = Form.useForm()
  const correctionEndRef = useRef<HTMLDivElement>(null)
  const pendingScrollToCorrection = useRef(false)

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

  const ownerCandidates = taskParticipantUsers(draftTask, props.users)

  /** 时间线按时间正序：最旧在上、最新在下，滚到底即可看到刚追加的 */
  const correctionsAsc = useMemo(() => {
    const list = d?.corrections ? [...d.corrections] : []
    return list.sort((a, b) => {
      const ta = a.created_at ? new Date(a.created_at).getTime() : 0
      const tb = b.created_at ? new Date(b.created_at).getTime() : 0
      return ta - tb
    })
  }, [d?.corrections])

  useEffect(() => {
    if (!pendingScrollToCorrection.current) return
    if (!props.open) return
    const t = window.setTimeout(() => {
      correctionEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
      pendingScrollToCorrection.current = false
    }, 80)
    return () => window.clearTimeout(t)
  }, [correctionsAsc.length, props.open, d?.id])

  /** 详情异步加载后同步日更表单，避免 initialValues 只生效一次导致「是否阻塞」被旧值覆盖写丢 */
  useEffect(() => {
    if (!props.open || !d || !canDaily) return
    dailyForm.setFieldsValue({
      progress_percent: d.progress_percent,
      risk_blocker: d.latest_risk || '',
      is_blocking: Boolean(d.latest_is_blocking),
      progress_note: '',
    })
  }, [
    props.open,
    canDaily,
    d?.id,
    d?.progress_percent,
    d?.latest_risk,
    d?.latest_is_blocking,
    dailyForm,
  ])

  return (
    <Drawer
      title={d?.title || 'Action'}
      open={props.open}
      onClose={props.onClose}
      width={520}
      destroyOnClose
      styles={{ body: { paddingTop: 12, paddingBottom: 24 } }}
    >
      <div className="tm-sheet" data-testid="tm-drawer-action">
        {!d ? (
          <Text type="secondary">加载中…</Text>
        ) : (
          <div className="tm-sheet__stack">
            {/* 1. 摘要 */}
            <header className="tm-sheet__summary">
              <div className="tm-sheet__summary-top">
                <Tag color={STATUS_LABEL[d.status]?.color}>{STATUS_LABEL[d.status]?.text}</Tag>
                <span className="tm-sheet__task">{d.task_title}</span>
              </div>
              <div className="tm-sheet__meta-row">
                子需求 {d.subtask_name || '—'} · 负责人 {props.userName(d.owner_id)}
              </div>
              <Progress
                percent={d.progress_percent}
                size="small"
                strokeColor="#1677ff"
                className="tm-sheet__progress"
              />
            </header>

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
                {canCorrect
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
                  }}
                >
                  <Form.Item
                    name="subtask_name"
                    label="关联子需求"
                    rules={[{ required: true, message: '请选择子需求' }]}
                  >
                    <Select
                      options={(draftTask?.subtasks || []).map((s) => ({
                        value: s.name,
                        label: s.name,
                      }))}
                      showSearch
                      optionFilterProp="label"
                      placeholder="选择子需求"
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
            ) : (
              <section className="tm-sheet__section">
                <h3 className="tm-sheet__h">基本信息</h3>
                <dl className="tm-sheet__dl">
                  <div>
                    <dt>子需求</dt>
                    <dd>{d.subtask_name || '—'}</dd>
                  </div>
                  <div>
                    <dt>测试内容</dt>
                    <dd>{d.test_content || '—'}</dd>
                  </div>
                  <div>
                    <dt>环境</dt>
                    <dd>{d.environment || '—'}</dd>
                  </div>
                </dl>
              </section>
            )}

            {/* 5. 变更状态 */}
            {canChangeStatus &&
            d.status !== 'cancelled' &&
            d.status !== 'done' &&
            !(d.status === 'draft' && canEditFields) ? (
              <section className="tm-sheet__section">
                <h3 className="tm-sheet__h">状态</h3>
                <div className="tm-sheet__actions">
                  {d.status === 'draft' ? (
                    <Button
                      type="primary"
                      loading={props.publishLoading || props.statusLoading}
                      data-testid="tm-btn-publish-action"
                      onClick={() => props.onPublish(d.id)}
                    >
                      发布
                    </Button>
                  ) : null}
                  {d.status === 'published' ? (
                    <>
                      <Button
                        type="primary"
                        loading={props.statusLoading}
                        disabled={!canMarkDone}
                        title={canMarkDone ? undefined : '需日更到 100% 才能完成'}
                        data-testid="tm-btn-mark-done"
                        onClick={() => props.onChangeStatus(d.id, 'done')}
                      >
                        标记完成
                      </Button>
                      {!canMarkDone ? (
                        <span className="tm-sheet__muted">需日更到 100%（当前 {d.progress_percent}%）</span>
                      ) : null}
                    </>
                  ) : null}
                </div>
              </section>
            ) : null}

            {/* 6. 日更 */}
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
                    label="当前进度"
                    rules={[{ required: true, message: '必填' }]}
                    style={{ marginBottom: 12 }}
                  >
                    <InputNumber
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
                    style={{ marginBottom: 12 }}
                  >
                    <TextArea
                      rows={2}
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
                      marginBottom: 12,
                    }}
                  >
                    <Form.Item
                      name="risk_blocker"
                      label="风险"
                      style={{ flex: 1, marginBottom: 0 }}
                    >
                      <TextArea
                        rows={2}
                        maxLength={TEXT_FIELD_MAX_CHARS}
                        placeholder="如有风险，简要说明"
                        data-testid="tm-daily-risk"
                      />
                    </Form.Item>
                    <Form.Item
                      name="is_blocking"
                      label="阻塞"
                      valuePropName="checked"
                      style={{ marginBottom: 0, paddingTop: 22 }}
                    >
                      <Checkbox data-testid="tm-daily-is-blocking">是否阻塞</Checkbox>
                    </Form.Item>
                  </div>
                  <Button
                    type="primary"
                    htmlType="submit"
                    block
                    loading={props.dailyLoading}
                    data-testid="tm-submit-daily"
                  >
                    提交日更
                  </Button>
                </Form>
              </section>
            ) : null}

            {/* 7. 更正 */}
            {canCorrect ? (
              <section className="tm-sheet__section">
                <h3 className="tm-sheet__h">更正说明</h3>
                <Form
                  form={correctForm}
                  layout="vertical"
                  size="middle"
                  className="tm-sheet__form"
                  onFinish={async (v) => {
                    try {
                      pendingScrollToCorrection.current = true
                      await props.onCorrect(d.id, v.note)
                      correctForm.resetFields()
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
                      rows={2}
                      placeholder="更正内容…"
                      maxLength={TEXT_FIELD_MAX_CHARS}
                      showCount
                      data-testid="tm-correction-note"
                    />
                  </Form.Item>
                  <Button
                    type="primary"
                    htmlType="submit"
                    block
                    loading={props.correctLoading}
                    data-testid="tm-submit-correction"
                  >
                    追加更正
                  </Button>
                </Form>
              </section>
            ) : null}

            {/* 8. 时间线 */}
            <section className="tm-sheet__section">
              <h3 className="tm-sheet__h">
                更正记录
                {correctionsAsc.length > 0 ? (
                  <span className="tm-sheet__muted"> · {correctionsAsc.length}</span>
                ) : null}
              </h3>
              {correctionsAsc.length === 0 ? (
                <p className="tm-sheet__muted">暂无</p>
              ) : (
                <Timeline
                  items={correctionsAsc.map((c, idx) => ({
                    color: idx === correctionsAsc.length - 1 ? 'green' : 'gray',
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
            </section>
          </div>
        )}
      </div>
    </Drawer>
  )
}
