import { useEffect, useMemo, useRef, useState } from 'react'
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
  Progress,
  Select,
  Space,
  Tabs,
  Tag,
  Timeline,
  Tooltip,
  Typography,
} from 'antd'
import type { MenuProps } from 'antd'
import {
  CopyOutlined,
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
import { isMissingDailyToday } from '../utils/screenFilters'
import {
  REQ_STAGE_OPTIONS,
  REQ_STAGE_TESTING,
  reqStageLabel,
  reqStageTagColor,
  showTestStatus,
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

function formatDateTimeShort(iso?: string | null) {
  if (!iso) return '—'
  const d = dayjs(iso)
  return d.isValid() ? d.format('MM-DD HH:mm') : iso
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
  const [actionModalTask, setActionModalTask] = useState<TmTask | null>(null)
  const [projectModal, setProjectModal] = useState(false)
  const [domainModal, setDomainModal] = useState(false)
  const [detailActionId, setDetailActionId] = useState<string | null>(null)
  const [editTaskId, setEditTaskId] = useState<string | null>(null)
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
  /** 复制上周前预览候选 Action */
  const [previewClone, setPreviewClone] = useState<TmAction | null>(null)
  /** 工作台：我的 Task（负责人）| 其他 | 全部 */
  const [boardTaskScope, setBoardTaskScope] = useState<'mine' | 'other' | 'all'>('mine')
  /** 工作台 Task 分页 */
  const [boardTaskPage, setBoardTaskPage] = useState(1)
  const [boardTaskPageSize, setBoardTaskPageSize] = useState<number>(BOARD_TASK_PAGE_SIZE_DEFAULT)
  const [mineActionPage, setMineActionPage] = useState(1)

  const { data: week } = useQuery({
    queryKey: ['tm-week'],
    queryFn: async () => (await testManageApi.week()).data,
  })

  const setWeekEndMut = useMutation({
    mutationFn: async (weekEndIso: string) => (await testManageApi.setWeekEnd(weekEndIso)).data,
    onSuccess: (data) => {
      const pushHint = data.weekly_push_at
        ? `；周报预计 ${formatDateTimeShort(data.weekly_push_at)} 发送（周结束后 15min）`
        : ''
      message.success(`本周结束时间已更新；本周 Action 截止时间已同步${pushHint}`)
      void qc.invalidateQueries({ queryKey: ['tm-week'] })
      void qc.invalidateQueries({ queryKey: ['tm-board'] })
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '设置失败'),
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

  const { data: cloneCandidates = [] } = useQuery({
    queryKey: ['tm-clone', actionModalTask?.id || editTaskId || ''],
    queryFn: async () => {
      const tid = actionModalTask?.id || editTaskId
      if (!tid) return []
      return (await testManageApi.cloneCandidates(tid)).data
    },
    enabled: !!(actionModalTask?.id || editTaskId) && !viewingHistory,
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
      setActionModalTask(null)
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '失败'),
  })

  const cloneMut = useMutation({
    mutationFn: (id: string) => testManageApi.cloneAction(id),
    onSuccess: () => {
      message.success('已引用为当前周草稿')
      setActionModalTask(null)
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '失败'),
  })

  /** 切周：一键复制该 Task 上周全部候选 Action */
  const cloneLastWeekMut = useMutation({
    mutationFn: async (taskId: string) => {
      const list = (await testManageApi.cloneCandidates(taskId)).data || []
      for (const c of list) {
        await testManageApi.cloneAction(c.id)
      }
      return list.length
    },
    onSuccess: (n) => {
      if (n === 0) message.info('上周无可复制 Action，请点「+ Action」新建')
      else message.success(`已复制 ${n} 条为草稿`)
      invalidate()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '复制失败'),
  })

  /** 工作台列表：归档 Task 默认不展示（与归档确认文案一致） */
  const boardTasksScoped = useMemo(() => {
    const list = (board?.tasks || []).filter((bt) => bt.task.status !== 'cancelled')
    const uid = user?.id != null ? Number(user.id) : null
    return filterBoardTasksByScope(list, boardTaskScope, uid)
  }, [board?.tasks, boardTaskScope, user?.id])

  /** 筛选/周切换后回到第 1 页 */
  useEffect(() => {
    setBoardTaskPage(1)
  }, [boardTaskScope, projectId, boardWeekStart, weekMode])

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
            {!viewingHistory &&
            (week?.can_set_week_end || board?.weekly_push_at || week?.weekly_push_at) ? (
              <Space wrap size={8} style={{ marginTop: 8 }} align="center">
                {week?.can_set_week_end ? (
                  <>
                    <Text type="secondary">周结束</Text>
                    <DatePicker
                      showTime={{ format: 'HH:mm' }}
                      format="YYYY-MM-DD HH:mm"
                      value={week?.week_end ? dayjs(week.week_end) : null}
                      disabled={setWeekEndMut.isPending}
                      onChange={(v) => {
                        if (!v) return
                        setWeekEndMut.mutate(v.toISOString())
                      }}
                      data-testid="tm-week-end-picker"
                    />
                  </>
                ) : null}
                {board?.weekly_push_at || week?.weekly_push_at ? (
                  <Text type="secondary" data-testid="tm-weekly-push-at">
                    周报预计 {formatDateTimeShort(board?.weekly_push_at || week?.weekly_push_at)}{' '}
                    发送（周结束后 15min）
                  </Text>
                ) : null}
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
              { value: 'other', label: `其他 Task（${boardScopeCounts.other}）` },
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
              viewingHistory
                ? '该历史周暂无 Action 记录。'
                : boardTaskScope === 'mine'
                  ? '暂无你负责的 Task。可切到「其他 / 全部」，或新建 Task。'
                  : boardTaskScope === 'other'
                    ? '暂无其他人负责的 Task。'
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
                onAddAction={() => setActionModalTask(bt.task)}
                onPublishAction={(id) => publishActionMut.mutate(id)}
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
            return (
            <Card
              key={a.id}
              size="small"
              className="tm-action-card"
              onClick={() => setDetailActionId(a.id)}
              title={a.title}
              extra={
                <Space size={4} wrap>
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

      <Modal
        title={previewClone ? `上周 Action · ${previewClone.title}` : '上周 Action'}
        open={!!previewClone}
        onCancel={() => setPreviewClone(null)}
        destroyOnClose
        width={520}
        footer={[
          <Button key="close" onClick={() => setPreviewClone(null)}>
            关闭
          </Button>,
          <Button
            key="copy"
            type="primary"
            icon={<CopyOutlined />}
            loading={cloneMut.isPending}
            data-testid="tm-clone-to-week"
            onClick={() => {
              if (!previewClone) return
              cloneMut.mutate(previewClone.id, {
                onSuccess: () => setPreviewClone(null),
              })
            }}
          >
            复制到本周
          </Button>,
        ]}
      >
        {previewClone && (
          <div className="tm-sheet tm-sheet--modal" data-testid="tm-modal-clone-preview">
            <dl className="tm-sheet__dl">
              <div>
                <dt>负责人</dt>
                <dd>{userName(previewClone.owner_id)}</dd>
              </div>
              <div>
                <dt>状态 / 进度</dt>
                <dd>
                  <Tag color={STATUS_LABEL[previewClone.status]?.color}>
                    {STATUS_LABEL[previewClone.status]?.text || previewClone.status}
                  </Tag>{' '}
                  {previewClone.progress_percent}%
                </dd>
              </div>
              {previewClone.latest_risk ? (
                <div>
                  <dt>阻塞</dt>
                  <dd>
                    <WarningOutlined /> {previewClone.latest_risk}
                  </dd>
                </div>
              ) : null}
              <div>
                <dt>测试内容</dt>
                <dd>{previewClone.test_content?.trim() || '—'}</dd>
              </div>
              <div>
                <dt>环境</dt>
                <dd>{previewClone.environment?.trim() || '—'}</dd>
              </div>
            </dl>
          </div>
        )}
      </Modal>

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
              创建后可在详情里复制上周 Action
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
                    <h3 className="tm-sheet__h">需求进展</h3>
                    {!viewingHistory &&
                    (taskDetail.can_edit_req_stage ||
                      (taskDetail.can_edit && showTestStatus(taskDetail.req_stage))) ? (
                      <Form
                        key={`flow-${taskDetail.id}-${taskFormEpoch}`}
                        layout="vertical"
                        className="tm-sheet__form"
                        initialValues={{
                          status: taskDetail.status,
                          req_stage: taskDetail.req_stage || 'pending_dev',
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
                          const payload: Parameters<typeof testManageApi.updateTask>[1] = {
                            change_summary: v.change_summary || '更新需求进展',
                          }
                          if (taskDetail.can_edit_req_stage) {
                            payload.req_stage = v.req_stage
                            payload.expected_handover_at = fmt(v.expected_handover_at)
                            payload.actual_handover_at = fmt(v.actual_handover_at)
                            payload.test_started_at = fmt(v.test_started_at)
                            payload.expected_test_end_at = fmt(v.expected_test_end_at)
                            payload.test_ended_at = fmt(v.test_ended_at)
                          }
                          if (showTestStatus(v.req_stage || taskDetail.req_stage) && v.status) {
                            payload.status = v.status
                          }
                          updateTaskMut.mutate({ id: taskDetail.id, data: payload })
                        }}
                      >
                        {taskDetail.can_edit_req_stage ? (
                          <>
                            <Form.Item
                              name="req_stage"
                              label="需求进展"
                              extra="阶段决定能否建 Action、能否填本周进度"
                            >
                              <Select data-testid="tm-task-req-stage" options={REQ_STAGE_OPTIONS} />
                            </Form.Item>
                            <Form.Item
                              noStyle
                              shouldUpdate={(prev, cur) => prev.req_stage !== cur.req_stage}
                            >
                              {({ getFieldValue }) => {
                                const stage = getFieldValue('req_stage') as string
                                return (
                                  <>
                                    {stage === 'pending_handover' ? (
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
                                    {stage === 'pending_test' ? (
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
                                    {stage === 'testing' ? (
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
                                    {stage === 'test_done' ? (
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
                          </>
                        ) : (
                          <p className="tm-sheet__tip" style={{ marginBottom: 12 }}>
                            <Tag color={reqStageTagColor(taskDetail.req_stage)}>{reqStageLabel(taskDetail.req_stage)}</Tag>
                            {taskDetail.stage_summary ? (
                              <Text type="secondary"> {taskDetail.stage_summary}</Text>
                            ) : null}
                            <span className="tm-sheet__muted"> · 仅 Admin/Manager 可改需求进展</span>
                          </p>
                        )}
                        {showTestStatus(taskDetail.req_stage) || taskDetail.can_edit_req_stage ? (
                          <Form.Item noStyle shouldUpdate>
                            {({ getFieldValue }) => {
                              const stage = (getFieldValue('req_stage') ||
                                taskDetail.req_stage) as string
                              if (!showTestStatus(stage)) return null
                              return (
                                <Form.Item name="status" label="测试状态">
                                  <Select
                                    data-testid="tm-task-status"
                                    options={[
                                      { value: 'published', label: '进行中' },
                                      { value: 'done', label: '已完成' },
                                    ]}
                                  />
                                </Form.Item>
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
                          保存需求进展
                        </Button>
                      </Form>
                    ) : (
                      <p className="tm-sheet__tip">
                        <Tag color={reqStageTagColor(taskDetail.req_stage)}>{reqStageLabel(taskDetail.req_stage)}</Tag>
                        {taskDetail.stage_summary ? (
                          <Text type="secondary"> {taskDetail.stage_summary}</Text>
                        ) : null}
                        {viewingHistory ? ' · 历史周只读' : null}
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
                        仅「测试中」可填写本周进度（当前：{reqStageLabel(taskDetail.req_stage)}）
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
                              extra="周结束前填写"
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
                          <dt>需求进展</dt>
                          <dd>
                            <Tag color={reqStageTagColor(taskDetail.req_stage)}>{reqStageLabel(taskDetail.req_stage)}</Tag>
                            {taskDetail.stage_summary ? (
                              <Text type="secondary"> {taskDetail.stage_summary}</Text>
                            ) : null}
                            <div className="tm-sheet__muted" style={{ marginTop: 4 }}>
                              改流程请用「操作 → 进度」
                            </div>
                          </dd>
                        </div>
                        {showTestStatus(taskDetail.req_stage) ? (
                          <div>
                            <dt>测试状态</dt>
                            <dd>
                              <Tag color={STATUS_LABEL[taskDetail.status]?.color}>
                                {STATUS_LABEL[taskDetail.status]?.text}
                              </Tag>
                            </dd>
                          </div>
                        ) : null}
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

                  {taskDetail.can_edit && !viewingHistory && taskDetail.can_add_action ? (
                    <section className="tm-sheet__section">
                      <CloneLastWeekPanel
                        candidates={cloneCandidates}
                        cloneAllLoading={cloneLastWeekMut.isPending}
                        cloneOneLoading={cloneMut.isPending}
                        onCloneAll={() => cloneLastWeekMut.mutate(taskDetail.id)}
                        onCloneOne={(id) => cloneMut.mutate(id)}
                        onPreview={(c) => setPreviewClone(c)}
                      />
                      <Button
                        type="dashed"
                        block
                        onClick={() => setActionModalTask(taskDetail)}
                        data-testid="tm-btn-new-action-in-drawer"
                      >
                        新建本周 Action
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

      {/* 新建 Action */}
      <Modal
        title={actionModalTask ? `新建 Action · ${actionModalTask.title}` : '新建 Action'}
        open={!!actionModalTask}
        onCancel={() => setActionModalTask(null)}
        footer={null}
        destroyOnClose
        width={560}
      >
        <div className="tm-sheet tm-sheet--modal" data-testid="tm-modal-new-action">
          {cloneCandidates.length > 0 ? (
            <div style={{ marginBottom: 12 }}>
              <CloneLastWeekPanel
                candidates={cloneCandidates}
                cloneAllLoading={cloneLastWeekMut.isPending}
                cloneOneLoading={cloneMut.isPending}
                onCloneAll={() => actionModalTask && cloneLastWeekMut.mutate(actionModalTask.id)}
                onCloneOne={(id) => cloneMut.mutate(id)}
                onPreview={(c) => setPreviewClone(c)}
              />
            </div>
          ) : actionModalTask ? (
            <p className="tm-sheet__tip" style={{ marginBottom: 12 }}>
              上周无可复制条目，请直接新建
            </p>
          ) : null}
          <ActionCreateButtons
            loading={createActionMut.isPending}
            onDraft={(values) =>
              createActionMut.mutate({
                task_id: actionModalTask!.id,
                ...values,
                publish: false,
              })
            }
            onPublish={(values) =>
              createActionMut.mutate({
                task_id: actionModalTask!.id,
                ...values,
                publish: true,
              })
            }
            defaultOwnerId={actionModalTask?.lead_id || user?.id}
            users={taskParticipantUsers(actionModalTask, users)}
          />
        </div>
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

function CloneLastWeekPanel(props: {
  candidates: TmAction[]
  cloneAllLoading?: boolean
  cloneOneLoading?: boolean
  onCloneAll: () => void
  onCloneOne: (id: string) => void
  onPreview: (c: TmAction) => void
}) {
  const { candidates } = props
  return (
    <Card
      size="small"
      className="tm-clone-panel"
      title="复制上周"
      data-testid="tm-clone-panel"
      extra={
        candidates.length > 0 ? (
          <Button
            type="link"
            size="small"
            loading={props.cloneAllLoading}
            onClick={props.onCloneAll}
            data-testid="tm-clone-all"
          >
            全部 · {candidates.length}
          </Button>
        ) : null
      }
    >
      {candidates.length === 0 ? (
        <Text type="secondary">上周无可复制条目</Text>
      ) : (
        <div className="tm-clone-list">
          {candidates.map((c) => (
            <div key={c.id} className="tm-clone-row">
              <Button
                type="link"
                size="small"
                className="tm-clone-row__title"
                onClick={() => props.onPreview(c)}
                title={c.title}
              >
                {c.title}
              </Button>
              <Button
                type="text"
                size="small"
                className="tm-clone-row__copy"
                icon={<CopyOutlined />}
                loading={props.cloneOneLoading}
                onClick={() => props.onCloneOne(c.id)}
                aria-label={`复制 ${c.title}`}
                title="复制到本周"
              />
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function BoardTaskCard(props: {
  bt: BoardTask
  /** 历史周只读：隐藏新建 / 发布等写操作 */
  readOnly?: boolean
  /** 本周无 Action 时标红提示 */
  highlightEmpty?: boolean
  userName: (id: number) => string
  onOpenAction: (id: string) => void
  onEditTask: (focus: 'progress' | 'detail') => void
  onAddAction: () => void
  onPublishAction: (id: string) => void
  onArchiveTask: () => void
  onDeleteTask: () => void
  archiveLoading?: boolean
  deleteLoading?: boolean
}) {
  const { bt, userName, readOnly, highlightEmpty } = props
  const [actionPage, setActionPage] = useState(1)
  const st = STATUS_LABEL[bt.task.status] || { color: 'default', text: bt.task.status }

  useEffect(() => {
    setActionPage(1)
  }, [bt.task.id])

  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(bt.actions.length / ACTION_CARD_PAGE_SIZE) || 1)
    if (actionPage > maxPage) setActionPage(maxPage)
  }, [bt.actions.length, actionPage])

  const actionsSorted = useMemo(() => sortActionCardsForList(bt.actions), [bt.actions])

  const actionsPaged = useMemo(() => {
    const start = (actionPage - 1) * ACTION_CARD_PAGE_SIZE
    return actionsSorted.slice(start, start + ACTION_CARD_PAGE_SIZE)
  }, [actionsSorted, actionPage])

  const taskMenuItems: MenuProps['items'] = [
    { key: 'detail', label: '详情' },
    ...(!readOnly && bt.task.can_edit
      ? [
          { key: 'progress', label: '进度' },
          {
            key: 'archive',
            label: '归档',
            disabled: !!props.archiveLoading,
          },
          {
            key: 'delete',
            label: '删除',
            danger: true,
            icon: <DeleteOutlined />,
            disabled: !!props.deleteLoading,
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
          <Tag color={st.color}>{st.text}</Tag>
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
              onClick={props.onAddAction}
              data-testid="tm-btn-add-action"
            >
              + Action
            </Button>
          ) : null}
        </Space>
      }
    >
      <Paragraph type="secondary" className="tm-board-task-req" ellipsis={{ rows: 2 }}>
        <Tag color={reqStageTagColor(bt.task.req_stage)}>{reqStageLabel(bt.task.req_stage)}</Tag>
        {bt.task.stage_summary ? `${bt.task.stage_summary} · ` : null}
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
          <div className="tm-action-grid" data-testid={`tm-task-action-grid-${bt.task.id}`}>
            {actionsPaged.map((a) => (
              <Card
                key={a.id}
                size="small"
                className="tm-action-card"
                onClick={() => props.onOpenAction(a.id)}
                title={a.title}
                data-testid={`tm-action-card-${a.id}`}
                data-action-title={a.title}
                extra={
                  <Space size={4}>
                    <Tag color={STATUS_LABEL[a.status]?.color}>{STATUS_LABEL[a.status]?.text}</Tag>
                    {!readOnly && a.status === 'draft' && a.can_edit_fields && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        点开可编辑
                      </Text>
                    )}
                  </Space>
                }
              >
                <Progress percent={a.progress_percent} size="small" />
                <Text type="secondary" className="tm-action-card__owner">
                  本周负责人 {userName(a.owner_id)}
                </Text>
                {a.status === 'published' && a.latest_risk && (
                  <Paragraph
                    type="danger"
                    className="tm-action-card__risk"
                    ellipsis={{ rows: 3, tooltip: a.latest_risk }}
                    style={{ marginBottom: 0 }}
                  >
                    <WarningOutlined /> {a.latest_risk}
                  </Paragraph>
                )}
                {!readOnly && a.status === 'draft' && a.can_edit_fields && (
                  <Button
                    size="small"
                    type="link"
                    icon={<SendOutlined />}
                    onClick={(e) => {
                      e.stopPropagation()
                      props.onPublishAction(a.id)
                    }}
                  >
                    发布
                  </Button>
                )}
              </Card>
            ))}
          </div>
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
    </Card>
  )
}

function ActionCreateButtons(props: {
  loading: boolean
  defaultOwnerId?: number
  users: { id: number; username: string }[]
  onDraft: (v: {
    title: string
    owner_id: number
    test_content: string
    environment: string
  }) => void
  onPublish: (v: {
    title: string
    owner_id: number
    test_content: string
    environment: string
  }) => void
}) {
  const [form] = Form.useForm()
  const ownerOptions = userSelectOptions(props.users)
  const defaultOwner =
    props.defaultOwnerId != null &&
    props.users.some((u) => Number(u.id) === Number(props.defaultOwnerId))
      ? Number(props.defaultOwnerId)
      : props.users[0]?.id
  return (
    <Form
      form={form}
      layout="vertical"
      className="tm-sheet__form"
      initialValues={{ owner_id: defaultOwner }}
    >
      <Form.Item name="title" label="标题" rules={[{ required: true }]}>
        <Input
          placeholder="本周 Action"
          maxLength={300}
          showCount
          data-testid="tm-action-title"
        />
      </Form.Item>
      <Form.Item
        name="owner_id"
        label="本周负责人"
        rules={[{ required: true, message: '请选择' }]}
      >
        <Select
          options={ownerOptions}
          showSearch
          optionFilterProp="label"
          placeholder={ownerOptions.length ? '选择负责人' : '无参与者可选'}
          notFoundContent="无参与者"
          data-testid="tm-action-owner"
        />
      </Form.Item>
      <Form.Item name="test_content" label="测试内容">
        <TextArea
          rows={3}
          placeholder="可选"
          maxLength={TEXT_FIELD_MAX_CHARS}
          showCount
          data-testid="tm-action-content"
        />
      </Form.Item>
      <Form.Item name="environment" label="环境">
        <Input
          placeholder="可选"
          maxLength={ACTION_ENVIRONMENT_MAX_CHARS}
          showCount
          data-testid="tm-action-env"
        />
      </Form.Item>
      <div className="tm-sheet__actions" style={{ justifyContent: 'flex-end' }}>
        <Button
          loading={props.loading}
          data-testid="tm-submit-action-draft"
          onClick={() =>
            void form.validateFields().then((v) =>
              props.onDraft({
                title: v.title,
                owner_id: Number(v.owner_id),
                test_content: v.test_content || '',
                environment: v.environment || '',
              }),
            )
          }
        >
          仅存草稿
        </Button>
        <Button
          type="primary"
          loading={props.loading}
          data-testid="tm-submit-action-publish"
          onClick={() =>
            void form.validateFields().then((v) =>
              props.onPublish({
                title: v.title,
                owner_id: Number(v.owner_id),
                test_content: v.test_content || '',
                environment: v.environment || '',
              }),
            )
          }
        >
          保存并发布
        </Button>
      </div>
    </Form>
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
                负责人 {props.userName(d.owner_id)}
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
                    owner_id: d.owner_id,
                    test_content: d.test_content,
                    environment: d.environment,
                  }}
                >
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
                  size="middle"
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
                    label="进度 %"
                    extra={`≥ 当前 ${d.progress_percent}%`}
                    rules={[{ required: true, message: '必填' }]}
                  >
                    <InputNumber
                      min={d.progress_percent ?? 0}
                      max={100}
                      style={{ width: '100%' }}
                      data-testid="tm-daily-progress"
                    />
                  </Form.Item>
                  <Form.Item name="risk_blocker" label="风险">
                    <TextArea
                      rows={2}
                      maxLength={TEXT_FIELD_MAX_CHARS}
                      showCount
                      placeholder="可选：当前风险说明"
                      data-testid="tm-daily-risk"
                    />
                  </Form.Item>
                  <Form.Item
                    name="is_blocking"
                    label="是否阻塞"
                    valuePropName="checked"
                    extra="必须勾选后，大屏「阻塞」筛选 / 日报才会计入"
                  >
                    <Checkbox data-testid="tm-daily-is-blocking">此风险构成阻塞</Checkbox>
                  </Form.Item>
                  <Form.Item
                    name="progress_note"
                    label="说明"
                    rules={[{ required: true, whitespace: true, message: '必填' }]}
                  >
                    <TextArea
                      rows={2}
                      maxLength={TEXT_FIELD_MAX_CHARS}
                      showCount
                      placeholder="今天做了什么"
                      data-testid="tm-daily-note"
                    />
                  </Form.Item>
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
