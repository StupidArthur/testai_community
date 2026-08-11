import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Collapse,
  DatePicker,
  Descriptions,
  Drawer,
  Dropdown,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Progress,
  Select,
  Space,
  Tabs,
  Tag,
  Timeline,
  Typography,
} from 'antd'
import type { MenuProps } from 'antd'
import {
  CopyOutlined,
  DeleteOutlined,
  DownOutlined,
  EditOutlined,
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
  shouldHighlightEmptyTask,
  shouldShowAddActionButton,
  taskParticipantUsers,
} from '../utils/boardUi'
import './ProjectManagePage.css'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

const STATUS_LABEL: Record<string, { color: string; text: string }> = {
  draft: { color: 'default', text: '草稿' },
  published: { color: 'processing', text: '进行中' },
  done: { color: 'success', text: '完成' },
  cancelled: { color: 'error', text: '取消' },
}

/** 与后端 TASK_REQUIREMENT_MAX_CHARS 保持一致 */
const TASK_REQUIREMENT_MAX_CHARS = 5000
/** 与后端 TEXT_FIELD_MAX_CHARS / ACTION_ENVIRONMENT_MAX_CHARS 对齐 */
const TEXT_FIELD_MAX_CHARS = 1000
const ACTION_ENVIRONMENT_MAX_CHARS = 300

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
  /** 本周 | 历史（历史只读，下拉最多 10 周） */
  const [weekMode, setWeekMode] = useState<WeekViewMode>('current')
  const [historyWeekStart, setHistoryWeekStart] = useState<string | undefined>()
  const [taskModal, setTaskModal] = useState(false)
  const [actionModalTask, setActionModalTask] = useState<TmTask | null>(null)
  const [projectModal, setProjectModal] = useState(false)
  const [domainModal, setDomainModal] = useState(false)
  const [detailActionId, setDetailActionId] = useState<string | null>(null)
  const [editTaskId, setEditTaskId] = useState<string | null>(null)
  /** Task 抽屉：默认只读写进度；点小「编辑」才改基本信息 */
  const [taskInfoEditing, setTaskInfoEditing] = useState(false)
  /** 打开抽屉时滚动焦点：进度 | 详情 */
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

  const { data: week } = useQuery({
    queryKey: ['tm-week'],
    queryFn: async () => (await testManageApi.week()).data,
  })

  const setWeekEndMut = useMutation({
    mutationFn: async (weekEndIso: string) => (await testManageApi.setWeekEnd(weekEndIso)).data,
    onSuccess: (data) => {
      const pushHint = data.weekly_push_at
        ? `；周报预计 ${formatDateTimeShort(data.weekly_push_at)} 发送`
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

  /**
   * 大屏/工作台默认项目：优先名称含 TPT 的最新创建；否则取全部里最新创建。
   */
  useEffect(() => {
    if (projectId) return
    if (!projects.length) return
    const tpt = projects.filter((p) => /tpt/i.test(p.name || ''))
    const pool = tpt.length > 0 ? tpt : projects
    const sorted = [...pool].sort((a, b) => {
      const ta = a.created_at ? Date.parse(a.created_at) : 0
      const tb = b.created_at ? Date.parse(b.created_at) : 0
      return tb - ta
    })
    const pick = sorted[0]
    if (pick?.id) setProjectId(pick.id)
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
    enabled: weekMode === 'current' || !!boardWeekStart,
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

  useEffect(() => {
    if (!editTaskId || !taskDetail) return
    const id =
      taskDrawerFocus === 'detail' ? 'tm-task-drawer-info' : 'tm-task-drawer-progress'
    const t = window.setTimeout(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 80)
    return () => window.clearTimeout(t)
  }, [editTaskId, taskDetail, taskDrawerFocus])

  /** 本周 Task 周进度（周报口径；未填则后端返回 Action 平均推荐值） */
  const { data: taskWeekProgress } = useQuery({
    queryKey: ['tm-task-week-progress', editTaskId, week?.week_key || ''],
    queryFn: async () => (await testManageApi.getTaskWeekProgress(editTaskId!)).data,
    enabled: !!editTaskId && !viewingHistory,
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

  /** 工作台按「我是否为 Task 测试负责人」筛选 */
  const boardTasksScoped = useMemo(() => {
    const list = board?.tasks || []
    const uid = user?.id != null ? Number(user.id) : null
    return filterBoardTasksByScope(list, boardTaskScope, uid)
  }, [board?.tasks, boardTaskScope, user?.id])

  const boardScopeCounts = useMemo(() => {
    const list = board?.tasks || []
    const uid = user?.id != null ? Number(user.id) : null
    return countBoardTasksByScope(list, uid)
  }, [board?.tasks, user?.id])

  const dailyMut = useMutation({
    mutationFn: (p: {
      id: string
      progress_percent: number
      risk_blocker: string
      progress_note: string
    }) =>
      testManageApi.upsertDaily(p.id, {
        progress_percent: p.progress_percent,
        risk_blocker: p.risk_blocker,
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
    label: viewingHistory ? '历史周大屏' : '本周大屏',
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
              {!viewingHistory && (board?.weekly_push_at || week?.weekly_push_at) ? (
                <Text type="secondary" data-testid="tm-weekly-push-at">
                  周报预计 {formatDateTimeShort(board?.weekly_push_at || week?.weekly_push_at)} 发送
                </Text>
              ) : null}
              <WeekViewSwitcher
                mode={weekMode}
                onModeChange={handleWeekModeChange}
                historyOptions={historyOptions}
                historyWeekStart={historyWeekStart}
                onHistoryWeekStartChange={setHistoryWeekStart}
                testIdPrefix="tm-board-week"
              />
            </Space>
            {!viewingHistory && week?.can_set_week_end ? (
              <Space wrap size={8} style={{ marginTop: 8 }} align="center">
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
                <Text type="secondary" style={{ fontSize: 12 }}>
                  周报在周结束时间后 15 分钟发送（到点后约 1 分钟内发出）
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
              <span className="tm-week-summary__label">风险</span>
            </div>
            <div className="tm-week-summary__stat tm-week-summary__stat--progress">
              <span className="tm-week-summary__value">{board?.summary?.progress_avg ?? 0}%</span>
              <span className="tm-week-summary__label">均进度</span>
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
            {boardTasksScoped.map((bt) => (
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
      <div className="tm-action-grid">
        {mine.map((a) => (
          <Card
            key={a.id}
            size="small"
            className="tm-action-card"
            onClick={() => setDetailActionId(a.id)}
            title={a.title}
            extra={<Tag>{STATUS_LABEL[a.status]?.text}</Tag>}
            data-testid={`tm-action-card-${a.id}`}
            data-action-title={a.title}
          >
            <Progress percent={a.progress_percent} size="small" />
            <Text type="secondary">{a.task_title}</Text>
            {a.latest_risk && (
              <Paragraph
                type="danger"
                className="tm-action-card__risk"
                ellipsis={{ rows: 3, tooltip: a.latest_risk }}
                style={{ marginBottom: 0, fontSize: 12 }}
              >
                <WarningOutlined /> {a.latest_risk}
              </Paragraph>
            )}
          </Card>
        ))}
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
          <Text type="secondary">
            当前周 {formatWeekShort(week?.week_start, week?.week_end)}
          </Text>
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
          <Space
            direction="vertical"
            style={{ width: '100%' }}
            size="middle"
            data-testid="tm-modal-clone-preview"
          >
            <div>
              <Text type="secondary">负责人</Text>
              <div>{userName(previewClone.owner_id)}</div>
            </div>
            <div>
              <Text type="secondary">状态 / 进度</Text>
              <div>
                <Tag color={STATUS_LABEL[previewClone.status]?.color}>
                  {STATUS_LABEL[previewClone.status]?.text || previewClone.status}
                </Tag>
                {previewClone.progress_percent}%
              </div>
            </div>
            {previewClone.latest_risk ? (
              <div>
                <Text type="secondary">风险</Text>
                <Paragraph type="danger" style={{ marginBottom: 0 }}>
                  <WarningOutlined /> {previewClone.latest_risk}
                </Paragraph>
              </div>
            ) : null}
            <div>
              <Text type="secondary">测试内容</Text>
              <Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
                {previewClone.test_content?.trim() || '（无）'}
              </Paragraph>
            </div>
            <div>
              <Text type="secondary">测试环境</Text>
              <Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
                {previewClone.environment?.trim() || '（无）'}
              </Paragraph>
            </div>
          </Space>
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
        {usersError && (
          <Alert
            type="error"
            showIcon
            style={{ marginBottom: 12 }}
            message="用户列表加载失败"
            description="请确认后端已重启且可访问 /api/test-manage/users，然后重试。"
            action={
              <Button size="small" onClick={() => void refetchUsers()}>
                重试
              </Button>
            }
          />
        )}
        {!usersError && !usersLoading && users.length === 0 && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 12 }}
            message="暂无系统用户可选，请先在用户管理中创建账号。"
          />
        )}
        <Form
          layout="vertical"
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
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message="创建 Task 后，在 Task 详情里可用「复制上周 Action」带入上周条目。"
          />
          <Form.Item name="project_id" label="项目" rules={[{ required: true }]}>
            <Select
              options={projects.map((p) => ({ value: p.id, label: p.name }))}
              onChange={(v) => setProjectId(v)}
              data-testid="tm-task-project"
            />
          </Form.Item>
          <Form.Item name="domain_id" label="领域" rules={[{ required: true }]}>
            <Select
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
            label={`需求内容（最多 ${TASK_REQUIREMENT_MAX_CHARS} 字）`}
            rules={[
              {
                max: TASK_REQUIREMENT_MAX_CHARS,
                message: `需求内容不能超过 ${TASK_REQUIREMENT_MAX_CHARS} 字`,
              },
            ]}
          >
            <TextArea
              rows={4}
              placeholder="Task 级需求说明"
              maxLength={TASK_REQUIREMENT_MAX_CHARS}
              showCount
              data-testid="tm-task-requirement"
            />
          </Form.Item>
          <Form.Item name="lead_id" label="测试负责人" rules={[{ required: true, message: '请选择测试负责人' }]}>
            <Select
              options={userOptions}
              showSearch
              optionFilterProp="label"
              loading={usersLoading}
              placeholder={usersLoading ? '加载用户中…' : '选择负责人（显示用户名）'}
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
              placeholder={usersLoading ? '加载用户中…' : '可选多人'}
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
      </Modal>

      {/* Task 抽屉：主操作写本周进度；基本信息默认只读，小按钮进入编辑 */}
      <Drawer
        title={taskDetail?.title || 'Task'}
        open={!!editTaskId}
        onClose={() => {
          setEditTaskId(null)
          setTaskSaveTip(null)
          setTaskInfoEditing(false)
          setTaskDrawerFocus('progress')
        }}
        width={480}
        destroyOnClose
      >
        {taskDetail && (
          <Space
            direction="vertical"
            style={{ width: '100%' }}
            size="middle"
            data-testid="tm-drawer-task"
          >
            {taskSaveTip ? (
              <Alert
                type="success"
                showIcon
                closable
                message={taskSaveTip}
                onClose={() => setTaskSaveTip(null)}
                data-testid="tm-task-save-tip"
              />
            ) : null}

            {!viewingHistory && taskWeekProgress ? (
              <Card
                id="tm-task-drawer-progress"
                size="small"
                title="本周 Task 进度（周报）"
                data-testid="tm-task-week-progress"
                style={
                  taskDrawerFocus === 'progress'
                    ? { outline: '2px solid #1677ff', outlineOffset: 2 }
                    : undefined
                }
              >
                {!taskWeekProgress.progress_is_manual ? (
                  <Alert
                    type="warning"
                    showIcon
                    style={{ marginBottom: 12 }}
                    message="尚未手填 Task 进度，当前按本周 Action 进度平均值展示"
                    description={`推荐值 ${taskWeekProgress.recommended_progress}%`}
                  />
                ) : null}
                {taskWeekProgress.can_edit ? (
                  <Form
                    key={`week-progress-${taskDetail.id}-${taskWeekProgress.updated_at || 'new'}-${taskWeekProgress.progress_is_manual}`}
                    layout="vertical"
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
                      label="本周进度 %"
                      rules={[{ required: true, message: '请填写进度' }]}
                      extra={`推荐填 Action 平均 ${taskWeekProgress.recommended_progress}%；请在周结束前填写`}
                    >
                      <InputNumber
                        min={0}
                        max={100}
                        style={{ width: '100%' }}
                        data-testid="tm-task-week-progress-input"
                      />
                    </Form.Item>
                    <Form.Item name="note" label="备注（可选）">
                      <Input placeholder="周进度说明" maxLength={500} />
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
                    <Progress percent={taskWeekProgress.progress_percent} />
                    {taskWeekProgress.note ? (
                      <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                        {taskWeekProgress.note}
                      </Paragraph>
                    ) : null}
                  </div>
                )}
              </Card>
            ) : null}

            <Card
              id="tm-task-drawer-info"
              size="small"
              title="Task 信息"
              data-testid="tm-task-info"
              style={
                taskDrawerFocus === 'detail'
                  ? { outline: '2px solid #1677ff', outlineOffset: 2 }
                  : undefined
              }
              extra={
                taskDetail.can_edit && !viewingHistory && !taskInfoEditing ? (
                  <Button
                    type="link"
                    size="small"
                    icon={<EditOutlined />}
                    onClick={() => setTaskInfoEditing(true)}
                    data-testid="tm-task-info-edit"
                  >
                    编辑
                  </Button>
                ) : null
              }
            >
              {taskDetail.can_edit && taskInfoEditing ? (
                <Form
                  key={`${taskDetail.id}-${taskFormEpoch}`}
                  layout="vertical"
                  initialValues={{
                    title: taskDetail.title,
                    requirement: taskDetail.requirement,
                    lead_id: Number(taskDetail.lead_id),
                    tester_ids: (taskDetail.tester_ids || []).map(Number),
                    status: taskDetail.status,
                    change_summary: '',
                  }}
                  onFinish={(v) =>
                    updateTaskMut.mutate({
                      id: taskDetail.id,
                      data: {
                        title: v.title,
                        requirement: v.requirement,
                        lead_id: Number(v.lead_id),
                        tester_ids: (v.tester_ids || []).map((x: number | string) => Number(x)),
                        status: v.status,
                        change_summary: v.change_summary,
                      },
                    })
                  }
                >
                  <Form.Item name="title" label="标题" rules={[{ required: true }]}>
                    <Input />
                  </Form.Item>
                  <Form.Item
                    name="requirement"
                    label={`需求内容（最多 ${TASK_REQUIREMENT_MAX_CHARS} 字）`}
                  >
                    <TextArea rows={4} maxLength={TASK_REQUIREMENT_MAX_CHARS} showCount />
                  </Form.Item>
                  <Form.Item
                    name="status"
                    label="Task 状态"
                    extra="进行中可加本周 Action；已完成不可再加"
                  >
                    <Select
                      data-testid="tm-task-status"
                      options={[
                        { value: 'published', label: '进行中' },
                        { value: 'done', label: '已完成' },
                      ]}
                    />
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
                  <Form.Item name="change_summary" label="变更说明（写入更新日志）">
                    <Input placeholder="本次改了什么" />
                  </Form.Item>
                  <Space style={{ width: '100%' }} direction="vertical">
                    <Button
                      type="primary"
                      htmlType="submit"
                      block
                      loading={updateTaskMut.isPending}
                      data-testid="tm-task-save"
                    >
                      保存
                    </Button>
                    <Button
                      block
                      onClick={() => setTaskInfoEditing(false)}
                      data-testid="tm-task-info-cancel"
                    >
                      取消编辑
                    </Button>
                  </Space>
                </Form>
              ) : (
                <Descriptions
                  size="small"
                  column={1}
                  labelStyle={{ width: 88, color: 'rgba(0,0,0,0.45)' }}
                >
                  <Descriptions.Item label="状态">
                    <Tag color={STATUS_LABEL[taskDetail.status]?.color}>
                      {STATUS_LABEL[taskDetail.status]?.text}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="项目/领域">
                    {taskDetail.project_name} / {taskDetail.domain_name}
                  </Descriptions.Item>
                  <Descriptions.Item label="负责人">
                    {userName(taskDetail.lead_id)}
                  </Descriptions.Item>
                  <Descriptions.Item label="测试人员">
                    {(taskDetail.tester_ids || []).length
                      ? (taskDetail.tester_ids || []).map((id) => userName(Number(id))).join('、')
                      : '—'}
                  </Descriptions.Item>
                  <Descriptions.Item label="需求">
                    <Paragraph
                      style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}
                      type={taskDetail.requirement ? undefined : 'secondary'}
                    >
                      {taskDetail.requirement?.trim() || '（无）'}
                    </Paragraph>
                  </Descriptions.Item>
                </Descriptions>
              )}
            </Card>

            {taskDetail.update_logs?.length > 0 && (
              <div>
                <Text strong>更新历史</Text>
                {taskDetail.update_logs.map((l) => (
                  <Card key={l.id} size="small" style={{ marginTop: 8 }}>
                    <Text type="secondary">
                      {l.created_at} · {userName(l.user_id)}
                    </Text>
                    <div>{l.summary}</div>
                  </Card>
                ))}
              </div>
            )}
            {taskDetail.can_edit && !viewingHistory && taskDetail.can_add_action && (
              <Card size="small" title="复制上周 Action">
                {cloneCandidates.length === 0 ? (
                  <Text type="secondary">上周无可复制条目</Text>
                ) : (
                  <Space direction="vertical" style={{ width: '100%' }} size={8}>
                    <Button
                      type="primary"
                      icon={<CopyOutlined />}
                      loading={cloneLastWeekMut.isPending}
                      onClick={() => cloneLastWeekMut.mutate(taskDetail.id)}
                      block
                      data-testid="tm-clone-all"
                    >
                      一键复制上周全部（{cloneCandidates.length}）
                    </Button>
                    {cloneCandidates.map((c) => (
                      <div key={c.id} className="tm-clone-row">
                        <Button
                          type="link"
                          size="small"
                          onClick={() => setPreviewClone(c)}
                          title="点击查看详情"
                        >
                          {c.title}
                        </Button>
                        <Button
                          size="small"
                          type="primary"
                          icon={<CopyOutlined />}
                          loading={cloneMut.isPending}
                          onClick={() => cloneMut.mutate(c.id)}
                        >
                          复制
                        </Button>
                      </div>
                    ))}
                  </Space>
                )}
              </Card>
            )}
            {taskDetail.can_edit && taskDetail.can_add_action && (
              <Button
                type="dashed"
                block
                onClick={() => setActionModalTask(taskDetail)}
                data-testid="tm-btn-new-action-in-drawer"
              >
                新建本周 Action
              </Button>
            )}
            {taskDetail.status === 'done' && (
              <Alert type="info" showIcon message="Task 已完成，不可再添加本周 Action" />
            )}
          </Space>
        )}
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
        <div data-testid="tm-modal-new-action">
        {cloneCandidates.length > 0 && (
          <Card size="small" title="复制上周" style={{ marginBottom: 12 }}>
            <Button
              type="primary"
              size="small"
              icon={<CopyOutlined />}
              loading={cloneLastWeekMut.isPending}
              onClick={() => actionModalTask && cloneLastWeekMut.mutate(actionModalTask.id)}
              style={{ marginBottom: 8 }}
            >
              全部复制（{cloneCandidates.length}）
            </Button>
            <div className="tm-clone-list">
              {cloneCandidates.map((c) => (
                <div key={c.id} className="tm-clone-row">
                  <Button
                    type="link"
                    size="small"
                    onClick={() => setPreviewClone(c)}
                    title="点击查看详情"
                  >
                    {c.title}
                  </Button>
                  <Button
                    size="small"
                    type="primary"
                    icon={<CopyOutlined />}
                    loading={cloneMut.isPending}
                    onClick={() => cloneMut.mutate(c.id)}
                  >
                    复制
                  </Button>
                </div>
              ))}
            </div>
          </Card>
        )}
        {cloneCandidates.length === 0 && actionModalTask && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message="上周无可复制 Action，请直接新建"
          />
        )}
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
        <Form
          layout="vertical"
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
      </Modal>

      <Modal
        title="新建领域"
        open={domainModal}
        onCancel={() => setDomainModal(false)}
        footer={null}
        destroyOnClose
      >
        <Form
          layout="vertical"
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
  const st = STATUS_LABEL[bt.task.status] || { color: 'default', text: bt.task.status }
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
          <span data-testid="tm-board-task-title">{bt.task.title}</span>
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
        <Space direction="vertical" size={0} style={{ alignItems: 'flex-end' }}>
          <Space wrap>
            <Text type="secondary">{bt.week_progress_avg}%</Text>
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
          {bt.progress_is_manual === false ? (
            <Text type="warning" style={{ fontSize: 12 }} data-testid="tm-task-progress-tip">
              未手填 Task 进度
            </Text>
          ) : null}
        </Space>
      }
    >
      <Paragraph type="secondary" ellipsis={{ rows: 2 }}>
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
        <div className="tm-action-grid">
          {bt.actions.map((a) => (
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
              <Text type="secondary" style={{ fontSize: 12 }}>
                本周负责人 {userName(a.owner_id)}
              </Text>
              {a.status === 'published' && a.latest_risk && (
                <Paragraph
                  type="danger"
                  className="tm-action-card__risk"
                  ellipsis={{ rows: 3, tooltip: a.latest_risk }}
                  style={{ marginBottom: 0, fontSize: 12 }}
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
        rules={[{ required: true, message: '请从 Task 参与者中选择' }]}
        extra="仅可选该 Task 的测试负责人与测试人员"
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
      <Form.Item name="test_content" label={`测试内容（最多 ${TEXT_FIELD_MAX_CHARS} 字）`}>
        <TextArea
          rows={3}
          placeholder="可选"
          maxLength={TEXT_FIELD_MAX_CHARS}
          showCount
          data-testid="tm-action-content"
        />
      </Form.Item>
      <Form.Item name="environment" label={`测试环境（最多 ${ACTION_ENVIRONMENT_MAX_CHARS} 字）`}>
        <Input
          placeholder="可选"
          maxLength={ACTION_ENVIRONMENT_MAX_CHARS}
          showCount
          data-testid="tm-action-env"
        />
      </Form.Item>
      <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
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
          icon={<SendOutlined />}
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
      </Space>
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

  return (
    <Drawer
      title={d?.title || 'Action'}
      open={props.open}
      onClose={props.onClose}
      width={560}
      destroyOnClose
    >
      <div data-testid="tm-drawer-action">
      {!d ? (
        <Text type="secondary">加载中…</Text>
      ) : (
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <Tag color={STATUS_LABEL[d.status]?.color}>{STATUS_LABEL[d.status]?.text}</Tag>
            <Text type="secondary">
              {' '}
              {d.task_title} · 本周负责人 {props.userName(d.owner_id)} · {d.week_key}
            </Text>
          </div>
          <Progress percent={d.progress_percent} />
          {lineage && lineage.weeks_count > 0 ? (
            <Collapse
              size="small"
              data-testid="tm-action-lineage"
              items={[
                {
                  key: 'lineage',
                  label: `延续历史（共 ${lineage.weeks_count} 周）`,
                  children: (
                    <Timeline
                      items={lineage.segments.map((seg) => ({
                        color: seg.is_current ? 'green' : 'blue',
                        children: (
                          <div>
                            <Space wrap size={4}>
                              <Text strong>{seg.week_key}</Text>
                              {seg.is_current ? <Tag color="success">当前</Tag> : null}
                              <Tag>{STATUS_LABEL[seg.status]?.text || seg.status}</Tag>
                              <Text type="secondary">{seg.progress_percent}%</Text>
                            </Space>
                            <div>{seg.title}</div>
                            {seg.risks.length > 0 ? (
                              <Paragraph type="danger" style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                                风险/问题：{seg.risks.join('；')}
                              </Paragraph>
                            ) : (
                              <Text type="secondary">本周无风险记录</Text>
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
          {forceReadOnly ? (
            <Alert type="info" showIcon message="历史周只读：不可编辑、日更或变更状态，请切回「本周」。" />
          ) : null}
          {!canDaily && !forceReadOnly && d.status === 'published' && (
            <Alert
              type="info"
              showIcon
              message="仅本 Action 的本周负责人或管理员可提交日更"
              description={`当前本周负责人为 ${props.userName(d.owner_id)}`}
            />
          )}

          {d.status === 'draft' && canEditFields ? (
            <Card size="small" title="编辑草稿（发布后字段锁定）">
              <Form
                form={draftForm}
                layout="vertical"
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
                <Form.Item
                  name="owner_id"
                  label="本周负责人"
                  rules={[{ required: true }]}
                  extra="仅可选该 Task 的测试负责人与测试人员"
                >
                  <Select
                    options={userSelectOptions(ownerCandidates)}
                    showSearch
                    optionFilterProp="label"
                  />
                </Form.Item>
                <Form.Item name="test_content" label="测试内容">
                  <TextArea rows={3} maxLength={TEXT_FIELD_MAX_CHARS} showCount />
                </Form.Item>
                <Form.Item name="environment" label={`测试环境（最多 ${ACTION_ENVIRONMENT_MAX_CHARS} 字）`}>
                  <Input maxLength={ACTION_ENVIRONMENT_MAX_CHARS} showCount />
                </Form.Item>
                <Space style={{ width: '100%' }} direction="vertical">
                  <Button
                    block
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
                    保存草稿
                  </Button>
                  <Button
                    type="primary"
                    block
                    icon={<SendOutlined />}
                    loading={props.publishLoading}
                    data-testid="tm-btn-publish-action"
                    onClick={() => props.onPublish(d.id)}
                  >
                    发布（之后字段锁定）
                  </Button>
                </Space>
              </Form>
            </Card>
          ) : (
            <>
              <div>
                <Text strong>测试内容</Text>
                <Paragraph style={{ whiteSpace: 'pre-wrap' }}>{d.test_content || '（空）'}</Paragraph>
              </div>
              <div>
                <Text strong>环境</Text>
                <Paragraph>{d.environment || '（空）'}</Paragraph>
              </div>
            </>
          )}

          {canChangeStatus &&
            d.status !== 'cancelled' &&
            d.status !== 'done' &&
            !(d.status === 'draft' && canEditFields) && (
            <Card
              size="small"
              title="变更状态"
              extra={
                <Text type="secondary" style={{ fontSize: 12 }}>
                  本人 / Task 负责人 / 管理员
                </Text>
              }
            >
              <Space wrap>
                {d.status === 'draft' && (
                  <Button
                    type="primary"
                    loading={props.publishLoading || props.statusLoading}
                    data-testid="tm-btn-publish-action"
                    onClick={() => props.onPublish(d.id)}
                  >
                    发布（进行中）
                  </Button>
                )}
                {d.status === 'published' && (
                  <>
                    <Button
                      type="primary"
                      loading={props.statusLoading}
                      disabled={!canMarkDone}
                      title={
                        canMarkDone
                          ? undefined
                          : '请先将日更进度更新为 100% 后再标记完成'
                      }
                      data-testid="tm-btn-mark-done"
                      onClick={() => props.onChangeStatus(d.id, 'done')}
                    >
                      标记完成
                    </Button>
                    {!canMarkDone && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        当前进度 {d.progress_percent}%：需日更到 100% 才能标记完成
                      </Text>
                    )}
                  </>
                )}
              </Space>
            </Card>
          )}

          {canDaily && (
            <Card
              size="small"
              title="日更"
              extra={
                <Text type="secondary" style={{ fontSize: 12 }}>
                  仅当天 · 19:50 截止
                </Text>
              }
            >
              <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 12 }}>
                仅本 Action 负责人或管理员可填写；说明必填；进度不可倒退
              </Paragraph>
              <Form
                layout="vertical"
                initialValues={{
                  progress_percent: d.progress_percent,
                  risk_blocker: d.latest_risk,
                  progress_note: '',
                }}
                onFinish={(v) =>
                  props.onDaily({
                    id: d.id,
                    progress_percent: v.progress_percent,
                    risk_blocker: v.risk_blocker || '',
                    progress_note: (v.progress_note || '').trim(),
                  })
                }
              >
                <Form.Item
                  name="progress_percent"
                  label="进度 %"
                  extra={`不可低于当前 ${d.progress_percent}%；下调请用「更正说明」`}
                  rules={[{ required: true, message: '进度为必填' }]}
                >
                  <InputNumber
                    min={d.progress_percent ?? 0}
                    max={100}
                    style={{ width: '100%' }}
                    data-testid="tm-daily-progress"
                  />
                </Form.Item>
                <Form.Item name="risk_blocker" label="风险与阻塞（可选，清空=已解除）">
                  <TextArea
                    rows={2}
                    maxLength={TEXT_FIELD_MAX_CHARS}
                    showCount
                    data-testid="tm-daily-risk"
                  />
                </Form.Item>
                <Form.Item
                  name="progress_note"
                  label="进度说明"
                  rules={[
                    {
                      required: true,
                      whitespace: true,
                      message: '进度说明必填',
                    },
                  ]}
                >
                  <TextArea
                    rows={3}
                    maxLength={TEXT_FIELD_MAX_CHARS}
                    showCount
                    placeholder="今天做了什么、结果如何"
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
            </Card>
          )}
          {!canDaily && !forceReadOnly && d.status === 'published' && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              今日日更窗口已关闭（默认 19:50 后锁定），或你无权写本条日更；纠错请用「更正说明」。
            </Text>
          )}

          {canCorrect && (
            <Card size="small" title="追加更正说明">
              <Form
                form={correctForm}
                layout="vertical"
                onFinish={async (v) => {
                  try {
                    pendingScrollToCorrection.current = true
                    await props.onCorrect(d.id, v.note)
                    correctForm.resetFields()
                    // toast 由父级 mutation onSuccess 统一弹出「追加成功」
                  } catch {
                    pendingScrollToCorrection.current = false
                  }
                }}
              >
                <Form.Item
                  name="note"
                  rules={[
                    { required: true, message: '请填写更正' },
                    { max: TEXT_FIELD_MAX_CHARS, message: `最多 ${TEXT_FIELD_MAX_CHARS} 字` },
                  ]}
                >
                  <TextArea
                    rows={3}
                    placeholder="例如：原测试内容写错 xxx，更正为 yyy"
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
            </Card>
          )}

          <Card size="small" title={`更正时间线（${correctionsAsc.length}）`}>
            {correctionsAsc.length === 0 ? (
              <Text type="secondary">暂无更正记录</Text>
            ) : (
              <Timeline
                items={correctionsAsc.map((c, idx) => ({
                  color: idx === correctionsAsc.length - 1 ? 'green' : 'blue',
                  children: (
                    <div>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {c.created_at || ''} · {props.userName(c.user_id)}
                        {idx === correctionsAsc.length - 1 ? ' · 最新' : ''}
                      </Text>
                      <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>{c.note}</Paragraph>
                    </div>
                  ),
                }))}
              />
            )}
            <div ref={correctionEndRef} />
          </Card>
        </Space>
      )}
      </div>
    </Drawer>
  )
}
