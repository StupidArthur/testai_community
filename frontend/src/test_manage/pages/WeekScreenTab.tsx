/**
 * 本周作战大屏：给领导看的周 × Task 汇总视图。
 * 明细默认「需关注」；「已完成 / 归档」用下拉切换。
 */
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Button, Empty, message, Progress, Select, Space, Tag, Tooltip, Typography } from 'antd'
import {
  ExpandOutlined,
  CompressOutlined,
  WarningOutlined,
  DownOutlined,
  RightOutlined,
  LinkOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import type { BoardOut, BoardTask, WeekHistoryOption } from '../../shared/api/test-manage'
import { toScreenBoardTasks } from '../utils/boardUi'
import {
  applyScreenFilters,
  hasRiskText,
  isMissingDailyToday,
  isOpenBlockingAction,
  taskShowsRisk,
  type ScreenFilters,
} from '../utils/screenFilters'
import {
  DISPLAY_STATUS_OPTIONS,
  displayStatusLabel,
  displayStatusTagColor,
} from '../utils/displayStatus'
import {
  REQ_STAGE_OPTIONS,
  REQ_STAGES_SCREEN_FOCUS,
  comparePipelineTasksByReqStage,
} from '../utils/reqStage'
import WeekViewSwitcher, { type WeekViewMode } from './WeekViewSwitcher'
import './WeekScreenTab.css'

const { Text } = Typography

const STATUS_LABEL: Record<string, { color: string; text: string }> = {
  draft: { color: 'default', text: '草稿' },
  published: { color: 'processing', text: '进行中' },
  done: { color: 'success', text: '完成' },
  cancelled: { color: 'default', text: '归档' },
}

type ScreenTabFilters = ScreenFilters

const EXTRA_FILTER_DEFAULTS: Pick<
  ScreenTabFilters,
  | 'ownerId'
  | 'leadId'
  | 'actionProgressBand'
  | 'weekProgressBand'
  | 'weekHasMissingDaily'
> = {
  ownerId: null,
  leadId: null,
  actionProgressBand: 'all',
  weekProgressBand: 'all',
  weekHasMissingDaily: false,
}

const DEFAULT_WEEK_FILTERS: ScreenTabFilters = {
  focus: 'all',
  domain: '全部',
  reqStage: [],
  displayStatus: ['testing_progress'],
  actionStatus: 'all',
  taskBlocking: 'all',
  actionRisk: 'all',
  includeMissingDaily: false,
  tags: [],
  taskId: null,
  ...EXTRA_FILTER_DEFAULTS,
}

/**
 * 今日默认：进行中 + 标记（阻塞/未日更）→ 阻塞或未日更的 Action 均显示。
 */
const DEFAULT_TODAY_FILTERS: ScreenTabFilters = {
  focus: 'all',
  domain: '全部',
  reqStage: [],
  displayStatus: [],
  actionStatus: 'published',
  taskBlocking: 'all',
  actionRisk: 'all',
  includeMissingDaily: false,
  tags: ['blocking', 'missing_daily'],
  taskId: null,
  ...EXTRA_FILTER_DEFAULTS,
}

/** 需求总览默认：六阶段全部展示 */
const DEFAULT_PIPELINE_FILTERS: ScreenTabFilters = {
  focus: 'all',
  domain: '全部',
  reqStage: [],
  displayStatus: [],
  actionStatus: 'all',
  taskBlocking: 'all',
  actionRisk: 'all',
  includeMissingDaily: false,
  tags: [],
  taskId: null,
  ...EXTRA_FILTER_DEFAULTS,
}

/** 清空筛选：所有条件回到「全部」（今日/本周/历史/需求总览通用） */
const EMPTY_SCREEN_FILTERS: ScreenTabFilters = {
  focus: 'all',
  domain: '全部',
  reqStage: [],
  displayStatus: [],
  actionStatus: 'all',
  taskBlocking: 'all',
  actionRisk: 'all',
  includeMissingDaily: false,
  tags: [],
  taskId: null,
  ...EXTRA_FILTER_DEFAULTS,
}

function formatWeekRange(weekStart?: string, weekEnd?: string) {
  if (!weekStart) return '—'
  const s = new Date(weekStart)
  const e = weekEnd ? new Date(weekEnd) : null
  const fmt = (d: Date) =>
    `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(
      d.getMinutes(),
    ).padStart(2, '0')}`
  return e ? `${fmt(s)} → ${fmt(e)}` : fmt(s)
}

/** 均进度旁侧文案：只反映进度，不把「有阻塞」绑在进度环上（避免 83% 却写阻塞偏高）。 */
function progressHealthLabel(progress: number) {
  if (progress >= 80) return { text: '推进良好', tone: 'good' as const }
  if (progress >= 40) return { text: '稳步推进', tone: 'ok' as const }
  if (progress > 0) return { text: '启动阶段', tone: 'ok' as const }
  return { text: '尚未填报', tone: 'ok' as const }
}

function summarizeFiltered(tasks: BoardTask[]) {
  const actions = tasks.flatMap((bt) => bt.actions)
  /** 风险仅在「测试中」阶段的 Task 上统计（旧 Action 残留风险不上屏） */
  const testingActions = tasks.filter(taskShowsRisk).flatMap((bt) => bt.actions)
  const riskActions = testingActions.filter(isOpenBlockingAction)
  const missingDaily = actions.filter((a) => isMissingDailyToday(a))
  const progressAvg = actions.length
    ? Math.round(actions.reduce((s, a) => s + (a.progress_percent || 0), 0) / actions.length)
    : 0

  return {
    task: {
      total: tasks.length,
      published: tasks.filter((bt) => bt.task.status === 'published').length,
      done: tasks.filter((bt) => bt.task.status === 'done').length,
      draft: tasks.filter((bt) => bt.task.status === 'draft').length,
      cancelled: tasks.filter((bt) => bt.task.status === 'cancelled').length,
      with_risk: tasks.filter(
        (bt) => taskShowsRisk(bt) && bt.actions.some(isOpenBlockingAction),
      ).length,
    },
    action: {
      total: actions.length,
      published: actions.filter((a) => a.status === 'published').length,
      done: actions.filter((a) => a.status === 'done').length,
      draft: actions.filter((a) => a.status === 'draft').length,
      cancelled: actions.filter((a) => a.status === 'cancelled').length,
      with_risk: riskActions.length,
      missing_daily: missingDaily.length,
      progress_avg: progressAvg,
    },
  }
}

type FlatActionRow = {
  action: BoardTask['actions'][number]
  taskTitle: string
  domainName: string
  subtaskName: string
  /** 所属 Task 是否「测试中」：非测试中不展示风险/阻塞（旧 Action 残留） */
  showsRisk: boolean
}

type TaskGroupRow = {
  taskId: string
  taskTitle: string
  domainName: string
  statusKey: string
  statusLabel: string
  statusColor: string
  leadName: string
  actionCount: number
  /** Task 周进度（手动填的优先；无则 Action 平均推荐值），周报口径 */
  weekProgressAvg: number
  hasBlocking: boolean
  hasRiskOnly: boolean
  progressIsManual: boolean
  subtasks: string[]
}

/** 本周/历史：按 Task 分组（Subtask 占第二列多行，其余列 Task 级合并一行）；风险从高到低排序 */
function flattenToTaskGroups(tasks: BoardTask[], userName: (id: number) => string): TaskGroupRow[] {
  const rows: TaskGroupRow[] = []
  for (const bt of tasks) {
    const showRisk = taskShowsRisk(bt)
    const subNames = new Set<string>()
    for (const a of bt.actions) {
      subNames.add((a.subtask_name || '').trim() || '未分组子需求')
    }
    // 没有 Action 的 Task，按其定义的 subtasks 生成空行（如待开发/开发中阶段）
    const subtasks =
      subNames.size > 0
        ? [...subNames]
        : (bt.task.subtasks || []).length > 0
          ? (bt.task.subtasks || []).map((s) => s.name)
          : ['未分组子需求']
    rows.push({
      taskId: bt.task.id,
      taskTitle: bt.task.title,
      domainName: bt.task.domain_name || '—',
      statusKey: bt.task.display_status || 'pending_dev',
      statusLabel: displayStatusLabel(bt.task.display_status),
      statusColor: displayStatusTagColor(bt.task.display_status),
      leadName: userName(Number(bt.task.lead_id)),
      actionCount: bt.actions.length,
      weekProgressAvg: Number(bt.week_progress_avg) || 0,
      hasBlocking: showRisk && bt.actions.some(isOpenBlockingAction),
      hasRiskOnly:
        showRisk && bt.actions.some((a) => hasRiskText(a) && !isOpenBlockingAction(a)),
      progressIsManual: bt.progress_is_manual === true,
      subtasks,
    })
  }
  // 风险从高到低：有阻塞 > 仅风险 > 其余；同级周进度低者在前（进度落后风险更高）
  return rows.sort((a, b) => {
    if (a.hasBlocking !== b.hasBlocking) return a.hasBlocking ? -1 : 1
    if (a.hasRiskOnly !== b.hasRiskOnly) return a.hasRiskOnly ? -1 : 1
    if (a.weekProgressAvg !== b.weekProgressAvg) return a.weekProgressAvg - b.weekProgressAvg
    return a.taskTitle.localeCompare(b.taskTitle, 'zh-CN')
  })
}

/** 今日明细：压平为 Action 行；阻塞优先，其次未日更，再按进度升序 */
function flattenActionsForToday(tasks: BoardTask[]): FlatActionRow[] {
  const rows: FlatActionRow[] = []
  for (const bt of tasks) {
    const showsRisk = taskShowsRisk(bt)
    for (const a of bt.actions) {
      rows.push({
        action: a,
        taskTitle: bt.task.title,
        domainName: bt.task.domain_name || '',
        subtaskName: a.subtask_name || '',
        showsRisk,
      })
    }
  }
  return rows.sort((x, y) => {
    const xb = x.showsRisk && isOpenBlockingAction(x.action) ? 0 : 1
    const yb = y.showsRisk && isOpenBlockingAction(y.action) ? 0 : 1
    if (xb !== yb) return xb - yb
    const xm = isMissingDailyToday(x.action) ? 0 : 1
    const ym = isMissingDailyToday(y.action) ? 0 : 1
    if (xm !== ym) return xm - ym
    return (x.action.progress_percent || 0) - (y.action.progress_percent || 0)
  })
}

/**
 * 本周/历史 Task 行「负责人」：Task lead 在前；另有 Action owner 时 →「某某 等N人」。
 * 需求总览仅展示 Task 唯一负责人（lead）。
 */
function actionOwnersLabel(
  bt: BoardTask,
  userName: (id: number) => string,
  opts?: { taskLeadOnly?: boolean },
) {
  const leadId = Number(bt.task.lead_id)
  if (opts?.taskLeadOnly) return userName(leadId)
  const ownerIds = [...new Set(bt.actions.map((a) => Number(a.owner_id)))]
  if (ownerIds.length === 0) return userName(leadId)
  const others = ownerIds.filter((id) => id !== leadId)
  const total = 1 + others.length
  if (total === 1) return userName(leadId)
  return `${userName(leadId)} 等${total}人`
}

export default function WeekScreenTab(props: {
  board?: BoardOut
  loading?: boolean
  projects: { id: string; name: string }[]
  projectId?: string
  onProjectChange: (id: string | undefined) => void
  weekMode: WeekViewMode
  onWeekModeChange: (mode: WeekViewMode) => void
  historyOptions: WeekHistoryOption[]
  historyWeekStart?: string
  onHistoryWeekStartChange: (weekStart: string) => void
  userName: (id: number) => string
  onOpenAction: (id: string) => void
  /** 公开大屏：只读，点击 Action 不打开编辑抽屉 */
  readOnly?: boolean
  /** 是否展示「复制今日深链」；默认非只读时展示 */
  showShare?: boolean
  /** 截图模式：本周/历史默认展开全部 Task 明细 */
  expandAllTasks?: boolean
}) {
  const rootRef = useRef<HTMLDivElement>(null)
  const [fullscreen, setFullscreen] = useState(false)
  /** 各时间 Tab 独立筛选（切走再切回保留） */
  const [filtersByMode, setFiltersByMode] = useState<Record<WeekViewMode, ScreenTabFilters>>({
    today: { ...DEFAULT_TODAY_FILTERS },
    current: { ...DEFAULT_WEEK_FILTERS },
    history: { ...DEFAULT_WEEK_FILTERS },
    pipeline: { ...DEFAULT_PIPELINE_FILTERS },
  })
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set())
  const viewingHistory = props.weekMode === 'history'
  const isToday = props.weekMode === 'today'
  const isPipeline = props.weekMode === 'pipeline'
  const filters = filtersByMode[props.weekMode]

  const patchFilters = (patch: Partial<ScreenTabFilters>) => {
    setFiltersByMode((prev) => ({
      ...prev,
      [props.weekMode]: { ...prev[props.weekMode], ...patch },
    }))
  }

  const clearFilters = () => {
    setFiltersByMode((prev) => ({
      ...prev,
      [props.weekMode]: { ...EMPTY_SCREEN_FILTERS },
    }))
  }

  useEffect(() => {
    const onFs = () => setFullscreen(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', onFs)
    return () => document.removeEventListener('fullscreenchange', onFs)
  }, [])

  const tasks = useMemo(
    () => toScreenBoardTasks(props.board?.tasks ?? []),
    [props.board?.tasks],
  )

  const domains = useMemo(() => {
    const set = new Set<string>()
    for (const bt of tasks) {
      if (bt.task.domain_name) set.add(bt.task.domain_name)
    }
    return ['全部', ...Array.from(set).sort()]
  }, [tasks])

  /** 今日：Action owner 候选 */
  const ownerOptions = useMemo(() => {
    const ids = new Set<number>()
    for (const bt of tasks) {
      for (const a of bt.actions) {
        if (a.owner_id != null) ids.add(Number(a.owner_id))
      }
    }
    return [...ids]
      .sort((a, b) => props.userName(a).localeCompare(props.userName(b), 'zh'))
      .map((id) => ({ value: id, label: props.userName(id) }))
  }, [tasks, props.userName])

  /** 本周：Task lead 候选 */
  const leadOptions = useMemo(() => {
    const ids = new Set<number>()
    for (const bt of tasks) {
      if (bt.task.lead_id != null) ids.add(Number(bt.task.lead_id))
    }
    return [...ids]
      .sort((a, b) => props.userName(a).localeCompare(props.userName(b), 'zh'))
      .map((id) => ({ value: id, label: props.userName(id) }))
  }, [tasks, props.userName])

  /** 今日+周视图：Task 候选（周视图含无 Action 的待开发 Task） */
  const taskOptions = useMemo(() => {
    return tasks
      .map((bt) => ({ value: bt.task.id, label: bt.task.title }))
  }, [tasks])

  /** 单行筛选项（平铺一行，放不下自动换行） */
  const filterItems = useMemo((): { key: string; node: ReactNode }[] => {
    const field = (label: string, control: ReactNode, title?: string) => (
      <>
        <Text type="secondary" className="tm-screen__filter-label" title={title}>
          {label}
        </Text>
        {control}
      </>
    )

    const domainSelect = (
      <Select
        size="small"
        style={{ width: 120 }}
        value={filters.domain}
        onChange={(v) => patchFilters({ domain: v })}
        options={domains.map((d) => ({ value: d, label: d }))}
        data-testid="tm-screen-domain-select"
      />
    )

    const actionStatusSelect = (
      <Select
        size="small"
        style={{ width: 96 }}
        value={filters.actionStatus}
        onChange={(v) => patchFilters({ actionStatus: v })}
        options={[
          { value: 'all', label: '全部' },
          { value: 'published', label: '进行中' },
          { value: 'done', label: '已完成' },
        ]}
        data-testid="tm-screen-action-status"
      />
    )

    if (isToday) {
      // 标记多选
      const tagSelect = (
        <Select
          mode="multiple"
          size="small"
          maxTagCount="responsive"
          style={{ minWidth: 160 }}
          placeholder="全部"
          value={filters.tags}
          onChange={(v) => patchFilters({ tags: v })}
          options={[
            { value: 'normal', label: '正常' },
            { value: 'missing_daily', label: '未日更' },
            { value: 'blocking', label: '阻塞' },
            { value: 'risk', label: '风险' },
          ]}
          data-testid="tm-screen-tag-select"
        />
      )

      // 顺序：常用在前，负责人紧随其后（平铺不收纳）
      return [
        {
          key: 'actionStatus',
          node: field('Action 状态', actionStatusSelect),
        },
        {
          key: 'owner',
          node: field(
            '负责人',
            <Select
              size="small"
              allowClear
              placeholder="全部"
              style={{ width: 110 }}
              value={filters.ownerId ?? undefined}
              onChange={(v) => patchFilters({ ownerId: v ?? null })}
              options={ownerOptions}
              data-testid="tm-screen-owner-select"
            />,
          ),
        },
        {
          key: 'tags',
          node: field('标记', tagSelect),
        },
        {
          key: 'domain',
          node: field('域', domainSelect),
        },
        {
          key: 'task',
          node: field(
            'Task',
            <Select
              size="small"
              allowClear
              placeholder="全部"
              style={{ width: 140 }}
              value={filters.taskId ?? undefined}
              onChange={(v) => patchFilters({ taskId: v ?? null })}
              options={taskOptions}
              data-testid="tm-screen-task-select"
            />,
          ),
        },
        {
          key: 'actionProgress',
          node: field(
            'Action 进度',
            <Select
              size="small"
              style={{ width: 110 }}
              value={filters.actionProgressBand}
              onChange={(v) => patchFilters({ actionProgressBand: v })}
              options={[
                { value: 'all', label: '全部' },
                { value: 'zero', label: '0%' },
                { value: 'low', label: '1–39%' },
                { value: 'mid', label: '40–79%' },
                { value: 'high', label: '≥80%' },
              ]}
              data-testid="tm-screen-action-progress"
            />,
          ),
        },
      ]
    }

    // 合并状态（display_status）多选
    const displayStatusSelect = (
      <Select
        mode="multiple"
        size="small"
        maxTagCount="responsive"
        style={{ minWidth: 160 }}
        placeholder="全部"
        value={filters.displayStatus}
        onChange={(v) => patchFilters({ displayStatus: v })}
        options={DISPLAY_STATUS_OPTIONS}
        data-testid="tm-screen-display-status"
      />
    )

    if (isPipeline) {
      return [
        {
          key: 'displayStatus',
          node: field('状态', displayStatusSelect),
        },
        {
          key: 'domain',
          node: field('域', domainSelect),
        },
        {
          key: 'lead',
          node: field(
            'Task 负责人',
            <Select
              size="small"
              allowClear
              placeholder="全部"
              style={{ width: 120 }}
              value={filters.leadId ?? undefined}
              onChange={(v) => patchFilters({ leadId: v ?? null })}
              options={leadOptions}
              data-testid="tm-screen-lead-select"
            />,
          ),
        },
      ]
    }

    // 周视图标记多选（含阻塞/含风险/本周完成）
    const tagSelect = (
      <Select
        mode="multiple"
        size="small"
        maxTagCount="responsive"
        style={{ minWidth: 160 }}
        placeholder="全部"
        value={filters.tags}
        onChange={(v) => patchFilters({ tags: v })}
        options={[
          { value: 'blocking', label: '含阻塞' },
          { value: 'risk', label: '含风险' },
          { value: 'completed', label: '本周完成' },
        ]}
        data-testid="tm-screen-week-tag-select"
      />
    )

    return [
      {
        key: 'displayStatus',
        node: field('状态', displayStatusSelect),
      },
      {
        key: 'tags',
        node: field('标记', tagSelect),
      },
      {
        key: 'task',
        node: field(
          'Task',
          <Select
            size="small"
            allowClear
            placeholder="全部"
            style={{ width: 140 }}
            value={filters.taskId ?? undefined}
            onChange={(v) => patchFilters({ taskId: v ?? null })}
            options={taskOptions}
            data-testid="tm-screen-week-task-select"
          />,
        ),
      },
      {
        key: 'weekProgress',
        node: field(
          '周进度',
          <Select
            size="small"
            style={{ width: 110 }}
            value={filters.weekProgressBand}
            onChange={(v) => patchFilters({ weekProgressBand: v })}
            options={[
              { value: 'all', label: '全部' },
              { value: 'unfilled', label: '未手填' },
              { value: 'low', label: '0–39%' },
              { value: 'mid', label: '40–79%' },
              { value: 'high', label: '≥80%' },
            ]}
            data-testid="tm-screen-week-progress"
          />,
        ),
      },
      {
        key: 'actionStatus',
        node: field('Action 状态', actionStatusSelect),
      },
    ]
  }, [isToday, isPipeline, filters, domains, ownerOptions, leadOptions, taskOptions])

  const filteredTasks = useMemo(() => {
    const list = applyScreenFilters(tasks, filters, isToday)
    // 需求总览：按进展优先级排序（测试中优先……待开发靠后）
    if (isPipeline) {
      return [...list].sort(comparePipelineTasksByReqStage)
    }
    return list
  }, [tasks, filters, isToday, isPipeline])

  const filteredSummary = useMemo(() => summarizeFiltered(filteredTasks), [filteredTasks])
  const health = progressHealthLabel(filteredSummary.action.progress_avg)
  const todayActionRows = useMemo(
    () => (isToday ? flattenActionsForToday(filteredTasks) : []),
    [isToday, filteredTasks],
  )
  const taskGroupRows = useMemo(
    () => (!isToday && !isPipeline ? flattenToTaskGroups(filteredTasks, props.userName) : []),
    [isToday, isPipeline, filteredTasks, props.userName],
  )
  /** Subtask 行总数（Task 分组内第二列的多行数之和） */
  const subtaskTotal = useMemo(
    () => taskGroupRows.reduce((n, g) => n + g.subtasks.length, 0),
    [taskGroupRows],
  )

  /** 截图模式：展开当前筛选下全部 Task，露出 Action 明细（需求总览不展开） */
  useEffect(() => {
    if (!props.expandAllTasks || isToday || isPipeline) return
    setExpandedIds(new Set(filteredTasks.map((bt) => bt.task.id)))
  }, [props.expandAllTasks, isToday, isPipeline, filteredTasks])

  const toggleExpand = (taskId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(taskId)) next.delete(taskId)
      else next.add(taskId)
      return next
    })
  }

  const toggleFullscreen = async () => {
    const el = rootRef.current
    if (!el) return
    try {
      if (!document.fullscreenElement) {
        await el.requestFullscreen()
        setFullscreen(true)
      } else {
        await document.exitFullscreen()
        setFullscreen(false)
      }
    } catch {
      setFullscreen(false)
    }
  }

  const showShare = props.showShare ?? !props.readOnly

  const viewParamForMode = (mode: WeekViewMode) =>
    mode === 'current'
      ? 'current'
      : mode === 'history'
        ? 'history'
        : mode === 'pipeline'
          ? 'pipeline'
          : 'today'

  const shareLinkLabel = isToday
    ? '复制今日深链'
    : isPipeline
      ? '复制需求总览深链'
      : viewingHistory
        ? '复制历史周深链'
        : '复制本周深链'

  const copyShareLink = async () => {
    const q = new URLSearchParams({ view: viewParamForMode(props.weekMode) })
    if (props.projectId) q.set('project_id', props.projectId)
    if (props.weekMode === 'history' && props.historyWeekStart) {
      q.set('week_start', props.historyWeekStart)
    }
    const url = `${window.location.origin}/tm-screen?${q.toString()}`
    try {
      await navigator.clipboard.writeText(url)
      message.success(`已复制${isToday ? '今日' : isPipeline ? '需求总览' : viewingHistory ? '历史周' : '本周'}公开深链`)
    } catch {
      message.info(url)
    }
  }

  return (
    <div
      ref={rootRef}
      className={`tm-screen${fullscreen ? ' tm-screen--fs' : ''}`}
      data-testid="tm-screen"
    >
      <header className="tm-screen__hero">
        <div className="tm-screen__hero-left">
          <h1 className="tm-screen__title">
            {isToday
              ? '今日进度与风险总览'
              : isPipeline
                ? '需求进展总览'
                : viewingHistory
                  ? '历史周进度与风险总览'
                  : '本周进度与风险总览'}
          </h1>
          <p className="tm-screen__week">
            周窗口 {formatWeekRange(props.board?.week_start, props.board?.week_end)}
            {'　'}
            当前时间：{dayjs().format('YYYY-MM-DD')}
          </p>
          <Space size={4} style={{ marginTop: 10 }} wrap>
            <WeekViewSwitcher
              mode={props.weekMode}
              onModeChange={props.onWeekModeChange}
              historyOptions={props.historyOptions}
              historyWeekStart={props.historyWeekStart}
              onHistoryWeekStartChange={props.onHistoryWeekStartChange}
              testIdPrefix="tm-screen-week"
            />
          </Space>
        </div>
        <div className="tm-screen__hero-right">
          <Select
            allowClear
            placeholder="全部项目"
            className="tm-screen__project"
            value={props.projectId}
            onChange={(v) => props.onProjectChange(v)}
            options={props.projects.map((p) => ({ value: p.id, label: p.name }))}
            data-testid="tm-screen-project"
          />
          {showShare ? (
            <Button
              icon={<LinkOutlined />}
              onClick={() => void copyShareLink()}
              data-testid="tm-screen-share-today"
            >
              {shareLinkLabel}
            </Button>
          ) : null}
          {!props.readOnly ? (
            <Button
              className="tm-screen__fs-btn"
              icon={fullscreen ? <CompressOutlined /> : <ExpandOutlined />}
              onClick={() => void toggleFullscreen()}
              data-testid="tm-screen-fullscreen"
            >
              {fullscreen ? '退出全屏' : '全屏汇报'}
            </Button>
          ) : null}
        </div>
      </header>

      <section className="tm-screen__kpi-block tm-screen__kpi-block--slim">
        <div className={`tm-screen__kpi-row${isPipeline ? ' tm-screen__kpi-row--6' : isToday ? ' tm-screen__kpi-row--4' : ' tm-screen__kpi-row--5'}`}>
          {isPipeline ? (
            REQ_STAGE_OPTIONS.map((o) => {
              const n = tasks.filter((bt) => {
                const ds = bt.task.display_status || ''
                if (o.value === 'testing') return ds === 'testing_progress' || ds === 'testing_done'
                return ds === o.value
              }).length
              const active = filters.displayStatus.includes(o.value === 'testing' ? 'testing_progress' : o.value)
              return (
                <button
                  key={o.value}
                  type="button"
                  className={`tm-screen__kpi tm-screen__kpi--stage-${o.value}${
                    active ? ' tm-screen__kpi--active' : ''
                  }${REQ_STAGES_SCREEN_FOCUS.has(o.value) && n > 0 ? ' tm-screen__kpi--danger' : ''}`}
                  onClick={() => {
                    if (o.value === 'testing') {
                      const both = ['testing_progress', 'testing_done']
                      const allActive = both.every((v) => filters.displayStatus.includes(v))
                      patchFilters({
                        displayStatus: allActive
                          ? filters.displayStatus.filter((v) => !both.includes(v))
                          : [...filters.displayStatus.filter((v) => !both.includes(v)), ...both],
                      })
                    } else {
                      const active = filters.displayStatus.includes(o.value)
                      patchFilters({
                        displayStatus: active
                          ? filters.displayStatus.filter((v) => v !== o.value)
                          : [...filters.displayStatus, o.value],
                      })
                    }
                  }}
                  data-testid={`tm-screen-stage-kpi-${o.value}`}
                >
                  <div className="tm-screen__kpi-label">{o.label}</div>
                  <div className="tm-screen__kpi-value">{n}</div>
                </button>
              )
            })
          ) : isToday ? (
            <>
              <Kpi label="总 Action" value={filteredSummary.action.total} />
              <Kpi
                label="有阻塞"
                value={filteredSummary.action.with_risk}
                danger={filteredSummary.action.with_risk > 0}
              />
              <Kpi
                label="未日更"
                value={filteredSummary.action.missing_daily}
                danger={filteredSummary.action.missing_daily > 0}
              />
              <div
                className="tm-screen__kpi tm-screen__kpi--pulse"
                title="当前筛选下，各 Action 最新日更进度的算术平均（不是 Task 周进度平均）"
              >
                <div className="tm-screen__kpi-label">Action 均进度</div>
                <div className="tm-screen__kpi-progress">
                  <Progress
                    type="circle"
                    percent={filteredSummary.action.progress_avg}
                    size={52}
                    strokeWidth={10}
                    strokeColor="#0070f3"
                    trailColor="rgba(0, 112, 243, 0.12)"
                    format={(p) => <span className="tm-screen__ring-text">{p}%</span>}
                  />
                  <div className={`tm-screen__health tm-screen__health--${health.tone}`}>{health.text}</div>
                </div>
              </div>
            </>
          ) : (
            <>
              <Kpi label="总 Task" value={filteredSummary.task.total} />
              <Kpi
                label="有阻塞 Task"
                value={filteredSummary.task.with_risk}
                danger={filteredSummary.task.with_risk > 0}
              />
              <Kpi label="总 Subtask" value={subtaskTotal} />
              <Kpi label="总 Action" value={filteredSummary.action.total} />
              <div
                className="tm-screen__kpi tm-screen__kpi--pulse"
                title="当前筛选下，各 Action 最新日更进度的算术平均（不是 Task 周进度平均）"
              >
                <div className="tm-screen__kpi-label">Action 均进度</div>
                <div className="tm-screen__kpi-progress">
                  <Progress
                    type="circle"
                    percent={filteredSummary.action.progress_avg}
                    size={52}
                    strokeWidth={10}
                    strokeColor="#0070f3"
                    trailColor="rgba(0, 112, 243, 0.12)"
                    format={(p) => <span className="tm-screen__ring-text">{p}%</span>}
                  />
                  <div className={`tm-screen__health tm-screen__health--${health.tone}`}>{health.text}</div>
                </div>
              </div>
            </>
          )}
        </div>
        {isPipeline ? (
          <Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>
            默认展示全部需求进展；点上方阶段可筛选，再点取消。点「清空筛选」回到全量。
          </Text>
        ) : null}
      </section>

      <div className="tm-screen__filters" data-testid="tm-screen-filters">
        <div className="tm-screen__filters-visible">
          {filterItems.map((item) => (
            <div key={item.key} className="tm-screen__filter-item">
              {item.node}
            </div>
          ))}
          <div className="tm-screen__filters-trailing">
            <Button type="link" size="small" onClick={clearFilters} data-testid="tm-screen-reset-filters">
              清空筛选
            </Button>
          </div>
        </div>
      </div>

      <div className="tm-screen__body tm-screen__body--wide">
        <section className="tm-screen__main" data-testid="tm-screen-detail">
          <div className="tm-screen__section-head">
            <h2>
              {isToday
                ? '今日 × Action 明细'
                : isPipeline
                  ? '需求 × Task 明细'
                  : '周 × Task / Subtask 明细'}
            </h2>
            <span>
              {isToday
                ? `展示 ${todayActionRows.length} 个 Action`
                : isPipeline
                  ? `展示 ${filteredTasks.length} 个 Task`
                  : `展示 ${taskGroupRows.length} 个 Task / ${subtaskTotal} 个 Subtask · ${filteredTasks.reduce(
                      (n, bt) => n + bt.actions.length,
                      0,
                    )} 个 Action`}
            </span>
          </div>

          {props.loading ? (
            <div className="tm-screen__empty">加载中…</div>
          ) : (isToday ? todayActionRows.length === 0 : filteredTasks.length === 0) ? (
            <Empty
              className="tm-screen__empty"
              description={
                !isToday && filters.focus === 'focus'
                  ? '本周暂无需要关注的 Task'
                  : '当前筛选下暂无数据'
              }
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          ) : isToday ? (
            <div className="tm-screen__table-scroll" data-testid="tm-screen-table">
              <table className="tm-screen__table tm-screen__table--dense tm-screen__table--action-flat">
                <thead>
                  <tr>
                    <th className="tm-screen__th-action">Action</th>
                    <th className="tm-screen__th-flags">标记</th>
                    <th className="tm-screen__th-status">状态</th>
                    <th className="tm-screen__th-owner">负责人</th>
                    <th className="tm-screen__th-progress">进度</th>
                    <th className="tm-screen__th-risk">风险 / 说明</th>
                  </tr>
                </thead>
                <tbody>
                  {todayActionRows.map((row) => (
                    <TodayActionRow
                      key={row.action.id}
                      row={row}
                      readOnly={Boolean(props.readOnly)}
                      userName={props.userName}
                      onOpenAction={props.onOpenAction}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          ) : isPipeline ? (
            <div className="tm-screen__table-scroll" data-testid="tm-screen-table">
              <table className="tm-screen__table tm-screen__table--dense">
                <thead>
                  <tr>
                    <th>Task</th>
                    <th>领域</th>
                    <th>需求进展</th>
                    <th>负责人</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTasks.map((bt) => {
                    const st = {
                      color: displayStatusTagColor(bt.task.display_status),
                      text: displayStatusLabel(bt.task.display_status),
                    }
                    return (
                      <TaskGroup
                        key={bt.task.id}
                        bt={bt}
                        open={false}
                        status={st}
                        hasRisk={false}
                        readOnly={Boolean(props.readOnly)}
                        hideActions={true}
                        userName={props.userName}
                        onToggle={() => {}}
                        onOpenAction={props.onOpenAction}
                      />
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="tm-screen__table-scroll" data-testid="tm-screen-table">
              <table className="tm-screen__table tm-screen__table--dense">
                <thead>
                  <tr>
                    <th>Task</th>
                    <th>Subtask</th>
                    <th>状态</th>
                    <th>负责人</th>
                    <th>Action 数</th>
                    <th>均进度</th>
                    <th>风险 / 阻塞</th>
                  </tr>
                </thead>
                <tbody>
                  {taskGroupRows.flatMap((g) =>
                    g.subtasks.map((subName, i) => (
                      <tr
                        key={`${g.taskId}-${subName}`}
                        className={`tm-screen__subtask-row${i === 0 && g.hasBlocking ? ' tm-screen__row--risk' : ''}`}
                      >
                        {i === 0 ? (
                          <td
                            rowSpan={g.subtasks.length}
                            className="tm-screen__td-task-ref"
                            title={g.taskTitle}
                          >
                            {g.taskTitle}
                          </td>
                        ) : null}
                        <td>
                          <span className="tm-screen__subtask-name">{subName}</span>
                        </td>
                        {i === 0 ? (
                          <>
                            <td rowSpan={g.subtasks.length}>
                              <Tag color={g.statusColor}>{g.statusLabel}</Tag>
                            </td>
                            <td rowSpan={g.subtasks.length}>{g.leadName}</td>
                            <td rowSpan={g.subtasks.length}>
                              <span className="tm-screen__action-count">{g.actionCount} 项</span>
                            </td>
                            <td
                              rowSpan={g.subtasks.length}
                              className="tm-screen__td-progress"
                              title={g.progressIsManual ? '本周手动填写' : 'Action 平均（推荐值）'}
                            >
                              <Progress
                                percent={g.weekProgressAvg}
                                size="small"
                                strokeColor="#0070f3"
                              />
                            </td>
                            <td rowSpan={g.subtasks.length}>
                              {g.hasBlocking || g.hasRiskOnly ? (
                                <div className="tm-screen__risk-stack">
                                  {g.hasBlocking ? (
                                    <span className="tm-screen__risk-inline tm-screen__risk-inline--count">
                                      <WarningOutlined /> 阻塞
                                    </span>
                                  ) : null}
                                  {g.hasRiskOnly ? (
                                    <span className="tm-screen__risk-inline tm-screen__risk-inline--risk-only">
                                      有风险
                                    </span>
                                  ) : null}
                                </div>
                              ) : (
                                <span className="tm-screen__ok">无</span>
                              )}
                            </td>
                          </>
                        ) : null}
                      </tr>
                    )),
                  )}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

function Kpi(props: { label: string; value: number; danger?: boolean; muted?: boolean }) {
  return (
    <div
      className={`tm-screen__kpi${props.danger ? ' tm-screen__kpi--danger' : ''}${
        props.muted ? ' tm-screen__kpi--muted' : ''
      }`}
    >
      <div className="tm-screen__kpi-label">{props.label}</div>
      <div className="tm-screen__kpi-value">{props.value}</div>
    </div>
  )
}

/** 今日扁平 Action 行：Action 为主，Subtask/Task 弱化为副信息（hover 显示） */
function TodayActionRow(props: {
  row: FlatActionRow
  readOnly?: boolean
  userName: (id: number) => string
  onOpenAction: (id: string) => void
}) {
  const { action: a, taskTitle, domainName, subtaskName, showsRisk } = props.row
  const blocking = showsRisk && isOpenBlockingAction(a)
  const missingDaily = isMissingDailyToday(a)
  const riskOnly = showsRisk && hasRiskText(a) && !blocking
  const risk = showsRisk ? (a.latest_risk || '').trim() : ''
  const normal = !blocking && !missingDaily && !riskOnly
  const st = STATUS_LABEL[a.status] || { color: 'default', text: a.status }

  return (
    <tr
      className="tm-screen__action-flat-row"
      onClick={() => {
        if (!props.readOnly) props.onOpenAction(a.id)
      }}
      style={props.readOnly ? { cursor: 'default' } : undefined}
      data-testid="tm-screen-action-flat-row"
    >
      <td className="tm-screen__td-action-main">
        <div className="tm-screen__action-name tm-screen__action-name--lg">{a.title}</div>
        <div className="tm-screen__action-meta">
          <span className="tm-screen__action-subtask" title={subtaskName || '未分组'}>
            subtask: {subtaskName || '未分组'}
          </span>
          <Tooltip
            title={
              <span style={{ whiteSpace: 'pre-line' }}>
                task：{taskTitle}<br />
                domain：{domainName}
              </span>
            }
            mouseEnterDelay={0}
            mouseLeaveDelay={0}
          >
            <span
              className="tm-screen__action-task-ellipsis"
              data-testid="tm-screen-action-task-ellipsis"
            >
              …
            </span>
          </Tooltip>
        </div>
      </td>
      <td className="tm-screen__td-flags">
        <div className="tm-screen__flag-list">
          {blocking ? (
            <Tag className="tm-screen__flag-tag tm-screen__flag-tag--blocking">
              阻塞
            </Tag>
          ) : null}
          {missingDaily ? (
            <Tag color="gold" className="tm-screen__flag-tag">
              未日更
            </Tag>
          ) : null}
          {riskOnly ? (
            <Tag color="blue" className="tm-screen__flag-tag">
              有风险
            </Tag>
          ) : null}
          {normal ? (
            <Tag className="tm-screen__flag-tag tm-screen__flag-tag--normal">正常</Tag>
          ) : null}
        </div>
      </td>
      <td>
        <Tag color={st.color}>{st.text}</Tag>
      </td>
      <td>{props.userName(a.owner_id)}</td>
      <td className="tm-screen__td-progress">
        <Progress percent={a.progress_percent} size="small" strokeColor="#0070f3" />
      </td>
      <td>
        {risk ? (
          <span className={`tm-screen__risk-inline tm-screen__risk-inline--detail${blocking ? ' tm-screen__risk-inline--blocking' : ''}`} title={risk}>
            {risk}
          </span>
        ) : (
          <span className="tm-screen__ok">无</span>
        )}
      </td>
    </tr>
  )
}

/** 需求总览 Task 行（hideActions 时仅 Task 行，不展开 Action 明细） */
function TaskGroup(props: {
  bt: BoardTask
  open: boolean
  status: { color: string; text: string }
  hasRisk: boolean
  readOnly?: boolean
  /** 需求总览：只展示 Task 行，不展开 Action 明细 */
  hideActions?: boolean
  userName: (id: number) => string
  onToggle: () => void
  onOpenAction: (id: string) => void
}) {
  const { bt, open, status, hasRisk, hideActions } = props
  const hasActions = !hideActions && bt.actions.length > 0
  /** 风险口径：仅「测试中」阶段统计（非测试中挂着的旧 Action 风险不展示） */
  const showRisk = taskShowsRisk(bt)
  const blockingN =
    !hideActions && showRisk ? bt.actions.filter(isOpenBlockingAction).length : 0
  /** 有风险文案但未勾阻塞（与「阻塞」拆开展示） */
  const riskOnlyN =
    !hideActions && showRisk
      ? bt.actions.filter((a) => hasRiskText(a) && !isOpenBlockingAction(a)).length
      : 0

  return (
    <>
      <tr
        className={`tm-screen__task-row${
          !hideActions && hasRisk ? ' tm-screen__row--risk' : ''
        }`}
        onClick={() => {
          if (hasActions) props.onToggle()
        }}
        style={hasActions ? undefined : { cursor: 'default' }}
      >
        {hideActions ? null : (
          <td className="tm-screen__td-caret">
            {hasActions ? open ? <DownOutlined /> : <RightOutlined /> : null}
          </td>
        )}
        <td className="tm-screen__td-title">
          <div className="tm-screen__task-title-main">{bt.task.title}</div>
          <div className="tm-screen__stage-line">
            {bt.task.stage_summary ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {bt.task.stage_summary}
              </Text>
            ) : (
              <span className="tm-screen__stage-line-placeholder" aria-hidden>
                {'\u00a0'}
              </span>
            )}
          </div>
        </td>
        <td>{bt.task.domain_name || '—'}</td>
        <td>
          <Tag color={displayStatusTagColor(bt.task.display_status)}>{displayStatusLabel(bt.task.display_status)}</Tag>
        </td>
        <td>{actionOwnersLabel(bt, props.userName, { taskLeadOnly: hideActions })}</td>
        {hideActions ? null : (
          <>
            <td className="tm-screen__td-progress">
              <Progress
                percent={bt.week_progress_avg}
                size="small"
                strokeColor={hasRisk ? '#d97706' : '#0070f3'}
                trailColor="rgba(15, 23, 42, 0.08)"
              />
              {!bt.progress_is_manual ? (
                <div
                  className="tm-screen__progress-tip"
                  title={`推荐值（Action 平均）${bt.recommended_progress ?? bt.week_progress_avg}%`}
                >
                  未手填 Task 进度
                </div>
              ) : null}
            </td>
            <td>
              {blockingN > 0 || riskOnlyN > 0 ? (
                <div className="tm-screen__risk-stack">
                  {blockingN > 0 ? (
                    <span className="tm-screen__risk-inline tm-screen__risk-inline--count">
                      <WarningOutlined /> 阻塞 {blockingN} 项
                    </span>
                  ) : null}
                  {riskOnlyN > 0 ? (
                    <span className="tm-screen__risk-inline tm-screen__risk-inline--risk-only">
                      风险 {riskOnlyN} 项
                    </span>
                  ) : null}
                </div>
              ) : (
                <span className="tm-screen__ok">无</span>
              )}
            </td>
          </>
        )}
      </tr>
      {open && hasActions && (() => {
        const groups = new Map<string, typeof bt.actions>()
        for (const a of bt.actions) {
          const key = (a.subtask_name || '').trim() || '未分组子需求'
          if (!groups.has(key)) groups.set(key, [])
          groups.get(key)!.push(a)
        }
        const rows: React.ReactNode[] = []
        for (const [subName, acts] of groups) {
          rows.push(
            <tr key={`st-${bt.task.id}-${subName}`} className="tm-screen__subtask-head-row">
              <td />
              <td colSpan={6} className="tm-screen__subtask-head">
                <span className="tm-screen__subtask-head-badge" />
                <span className="tm-screen__subtask-head-title">周{subName} subtask明细</span>
                <span className="tm-screen__subtask-head-count">{acts.length} 项</span>
              </td>
            </tr>,
          )
          for (const a of acts) {
            const risk = showRisk ? (a.latest_risk || '').trim() : ''
            const blocking = showRisk && isOpenBlockingAction(a)
            const missingDaily = isMissingDailyToday(a)
            rows.push(
              <tr
                key={a.id}
                className={`tm-screen__action-row${blocking ? ' tm-screen__row--risk' : ''}${
                  missingDaily && !blocking ? ' tm-screen__row--missing-daily' : ''
                }`}
                data-testid="tm-screen-action-row"
                onClick={(e) => {
                  e.stopPropagation()
                  if (!props.readOnly) props.onOpenAction(a.id)
                }}
                style={props.readOnly ? { cursor: 'default' } : undefined}
              >
                <td />
                <td colSpan={2} className="tm-screen__action-title">
                  <div className="tm-screen__action-name">{a.title}</div>
                </td>
                <td>
                  <Tag color={STATUS_LABEL[a.status]?.color}>
                    {STATUS_LABEL[a.status]?.text}
                  </Tag>
                  {blocking ? (
                    <Tag color="orange" style={{ marginLeft: 4 }}>
                      阻塞
                    </Tag>
                  ) : null}
                  {missingDaily ? (
                    <Tag color="gold" style={{ marginLeft: 4 }}>
                      未日更
                    </Tag>
                  ) : null}
                </td>
                <td>{props.userName(a.owner_id)}</td>
                <td className="tm-screen__td-progress">
                  <Progress percent={a.progress_percent} size="small" strokeColor="#0070f3" />
                </td>
                <td>
                  {risk ? (
                    <span
                      className="tm-screen__risk-inline tm-screen__risk-inline--detail"
                      title={risk}
                    >
                      {blocking ? <Tag color="orange">阻塞</Tag> : <Tag>风险</Tag>} {risk}
                    </span>
                  ) : (
                    <span className="tm-screen__ok">无</span>
                  )}
                </td>
              </tr>,
            )
          }
        }
        return rows
      })()}
    </>
  )
}
