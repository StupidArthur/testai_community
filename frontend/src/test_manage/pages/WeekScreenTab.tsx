/**
 * 本周作战大屏：给领导看的周 × Task 汇总视图。
 * 明细默认「需关注」；「已完成 / 归档」用下拉切换。
 */
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Button, Checkbox, Empty, message, Progress, Select, Space, Tag, Typography } from 'antd'
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
  type ScreenFilters,
} from '../utils/screenFilters'
import {
  REQ_STAGE_OPTIONS,
  REQ_STAGES_SCREEN_FOCUS,
  comparePipelineTasksByReqStage,
  reqStageLabel,
  reqStageTagColor,
  showTestStatus,
} from '../utils/reqStage'
import ScreenFilterOverflowRow, { type ScreenFilterOverflowItem } from './ScreenFilterOverflowRow'
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
  focus: 'focus',
  domain: '全部',
  taskStatus: 'all',
  reqStage: 'all',
  actionStatus: 'all',
  taskBlocking: 'all',
  actionRisk: 'all',
  includeMissingDaily: false,
  ...EXTRA_FILTER_DEFAULTS,
}

/**
 * 今日默认：进行中 + 有阻塞；并勾选「查看未日更」→ 有阻塞或未日更均显示。
 */
const DEFAULT_TODAY_FILTERS: ScreenTabFilters = {
  focus: 'all',
  domain: '全部',
  taskStatus: 'all',
  reqStage: 'all',
  actionStatus: 'published',
  taskBlocking: 'yes',
  actionRisk: 'all',
  includeMissingDaily: true,
  ...EXTRA_FILTER_DEFAULTS,
}

/** 需求总览默认：六阶段全部展示 */
const DEFAULT_PIPELINE_FILTERS: ScreenTabFilters = {
  focus: 'all',
  domain: '全部',
  taskStatus: 'all',
  reqStage: 'all',
  actionStatus: 'all',
  taskBlocking: 'all',
  actionRisk: 'all',
  includeMissingDaily: false,
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
  const riskActions = actions.filter(isOpenBlockingAction)
  const missingDaily = actions.filter(isMissingDailyToday)
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
      with_risk: tasks.filter((bt) => bt.actions.some(isOpenBlockingAction)).length,
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
}

/** 今日明细：压平为 Action 行；阻塞优先，其次未日更，再按进度升序 */
function flattenActionsForToday(tasks: BoardTask[]): FlatActionRow[] {
  const rows: FlatActionRow[] = []
  for (const bt of tasks) {
    for (const a of bt.actions) {
      rows.push({
        action: a,
        taskTitle: bt.task.title,
      })
    }
  }
  return rows.sort((x, y) => {
    const xb = isOpenBlockingAction(x.action) ? 0 : 1
    const yb = isOpenBlockingAction(y.action) ? 0 : 1
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

  const resetFilters = () => {
    setFiltersByMode((prev) => ({
      ...prev,
      [props.weekMode]: {
        ...(isToday
          ? DEFAULT_TODAY_FILTERS
          : isPipeline
            ? DEFAULT_PIPELINE_FILTERS
            : DEFAULT_WEEK_FILTERS),
      },
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

  /** 单行筛选项（前主后次；空间不足时末尾进「更多」） */
  const filterItems = useMemo((): ScreenFilterOverflowItem[] => {
    const field = (label: string, control: ReactNode, title?: string) => (
      <>
        <Text type="secondary" className="tm-screen__filter-label" title={title}>
          {label}
        </Text>
        {control}
      </>
    )

    const riskSelect = (
      <Select
        size="small"
        style={{ width: 100 }}
        value={filters.actionRisk}
        onChange={(v) => patchFilters({ actionRisk: v })}
        options={[
          { value: 'all', label: '全部' },
          { value: 'has_risk', label: '有风险' },
          { value: 'none', label: '无风险' },
        ]}
        data-testid="tm-screen-action-risk"
      />
    )

    const blockingSelect = (
      <Select
        size="small"
        style={{ width: 96 }}
        value={filters.taskBlocking}
        onChange={(v) => patchFilters({ taskBlocking: v })}
        options={[
          { value: 'all', label: '全部' },
          { value: 'yes', label: '有阻塞' },
          { value: 'no', label: '无阻塞' },
        ]}
        data-testid="tm-screen-task-blocking"
      />
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

    const taskStatusSelect = (
      <Select
        size="small"
        style={{ width: 100 }}
        value={filters.taskStatus}
        onChange={(v) => patchFilters({ taskStatus: v })}
        options={[
          { value: 'all', label: '全部' },
          { value: 'published', label: '进行中' },
          { value: 'done', label: '已完成' },
          { value: 'cancelled', label: '归档' },
        ]}
        data-testid="tm-screen-task-status"
      />
    )

    if (isToday) {
      // 顺序：常用在前；负责人、Task 状态靠后（窄屏优先进「更多」）
      return [
        {
          key: 'actionStatus',
          active: filters.actionStatus !== DEFAULT_TODAY_FILTERS.actionStatus,
          node: field('Action 状态', actionStatusSelect),
        },
        {
          key: 'blocking',
          active: filters.taskBlocking !== DEFAULT_TODAY_FILTERS.taskBlocking,
          node: field('阻塞', blockingSelect, '仅日更勾选了「是否阻塞」的项（橙色「阻塞」标签）'),
        },
        {
          key: 'domain',
          active: filters.domain !== DEFAULT_TODAY_FILTERS.domain,
          node: field('域', domainSelect),
        },
        {
          key: 'missingDaily',
          active: filters.includeMissingDaily !== DEFAULT_TODAY_FILTERS.includeMissingDaily,
          node: (
            <label className="tm-screen__filter-check" data-testid="tm-screen-missing-daily">
              <Checkbox
                checked={filters.includeMissingDaily}
                onChange={(e) => patchFilters({ includeMissingDaily: e.target.checked })}
              />
              <Text type="secondary" className="tm-screen__filter-label">
                查看未日更
              </Text>
            </label>
          ),
        },
        {
          key: 'risk',
          active: filters.actionRisk !== 'all',
          node: field('风险', riskSelect),
        },
        {
          key: 'actionProgress',
          active: filters.actionProgressBand !== 'all',
          node: field(
            'Action 进度',
            <Select
              size="small"
              style={{ width: 120 }}
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
        {
          key: 'owner',
          active: filters.ownerId != null,
          node: field(
            '负责人',
            <Select
              size="small"
              allowClear
              placeholder="全部"
              style={{ width: 120 }}
              value={filters.ownerId ?? undefined}
              onChange={(v) => patchFilters({ ownerId: v ?? null })}
              options={ownerOptions}
              data-testid="tm-screen-owner-select"
            />,
          ),
        },
        {
          key: 'taskStatus',
          active: filters.taskStatus !== 'all',
          node: field('Task 状态', taskStatusSelect),
        },
      ]
    }

    // 本周/历史：需求进展 + 测试状态；需求总览只留需求维度筛选（避免与「测试：进行中」重复）
    const reqStageSelect = (
      <Select
        size="small"
        style={{ width: 110 }}
        value={filters.reqStage}
        onChange={(v) => patchFilters({ reqStage: v })}
        options={[
          { value: 'all', label: '全部' },
          ...REQ_STAGE_OPTIONS.map((o) => ({ value: o.value, label: o.label })),
        ]}
        data-testid="tm-screen-req-stage"
      />
    )

    if (isPipeline) {
      return [
        {
          key: 'reqStage',
          active: filters.reqStage !== 'all',
          node: field('需求进展', reqStageSelect),
        },
        {
          key: 'domain',
          active: filters.domain !== '全部',
          node: field('域', domainSelect),
        },
        {
          key: 'lead',
          active: filters.leadId != null,
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

    return [
      {
        key: 'focus',
        active: filters.focus !== DEFAULT_WEEK_FILTERS.focus,
        node: field(
          '关注范围',
          <Select
            size="small"
            style={{ width: 100 }}
            value={filters.focus}
            onChange={(v) => patchFilters({ focus: v })}
            options={[
              { value: 'focus', label: '需关注' },
              { value: 'all', label: '全部' },
              { value: 'done', label: '已完成' },
              { value: 'archived', label: '归档' },
            ]}
            data-testid="tm-screen-focus-select"
          />,
        ),
      },
      {
        key: 'reqStage',
        active: filters.reqStage !== 'all',
        node: field('需求进展', reqStageSelect),
      },
      {
        key: 'taskStatus',
        active: filters.taskStatus !== 'all',
        node: field('测试状态', taskStatusSelect),
      },
      {
        key: 'blocking',
        active: filters.taskBlocking !== 'all',
        node: field('阻塞', blockingSelect, '仅日更勾选了「是否阻塞」的项（橙色「阻塞」标签）'),
      },
      {
        key: 'domain',
        active: filters.domain !== '全部',
        node: field('域', domainSelect),
      },
      {
        key: 'risk',
        active: filters.actionRisk !== 'all',
        node: field('风险', riskSelect),
      },
      {
        key: 'weekProgress',
        active: filters.weekProgressBand !== 'all',
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
        key: 'weekMissingDaily',
        active: filters.weekHasMissingDaily,
        node: (
          <label className="tm-screen__filter-check" data-testid="tm-screen-week-missing-daily">
            <Checkbox
              checked={filters.weekHasMissingDaily}
              onChange={(e) => patchFilters({ weekHasMissingDaily: e.target.checked })}
            />
            <Text type="secondary" className="tm-screen__filter-label">
              含未日更
            </Text>
          </label>
        ),
      },
      {
        key: 'lead',
        active: filters.leadId != null,
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
      {
        key: 'actionStatus',
        active: filters.actionStatus !== 'all',
        node: field('Action 状态', actionStatusSelect),
      },
    ]
  }, [isToday, isPipeline, filters, domains, ownerOptions, leadOptions])

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

  const copyTodayShareLink = async () => {
    const q = new URLSearchParams({ view: 'today' })
    if (props.projectId) q.set('project_id', props.projectId)
    const url = `${window.location.origin}/tm-screen?${q.toString()}`
    try {
      await navigator.clipboard.writeText(url)
      message.success('已复制今日公开深链')
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
              onClick={() => void copyTodayShareLink()}
              data-testid="tm-screen-share-today"
            >
              复制今日深链
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
        <div className={`tm-screen__kpi-row${isPipeline ? ' tm-screen__kpi-row--6' : ' tm-screen__kpi-row--4'}`}>
          {isPipeline ? (
            REQ_STAGE_OPTIONS.map((o) => {
              const n = tasks.filter((bt) => (bt.task.req_stage || '') === o.value).length
              const active = filters.reqStage === o.value
              return (
                <button
                  key={o.value}
                  type="button"
                  className={`tm-screen__kpi tm-screen__kpi--stage-${o.value}${
                    active ? ' tm-screen__kpi--active' : ''
                  }${REQ_STAGES_SCREEN_FOCUS.has(o.value) && n > 0 ? ' tm-screen__kpi--danger' : ''}`}
                  onClick={() =>
                    patchFilters({ reqStage: filters.reqStage === o.value ? 'all' : o.value })
                  }
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
            默认展示全部需求进展；点上方阶段可筛选，再点取消。点「恢复默认」回到全量。
          </Text>
        ) : null}
      </section>

      <ScreenFilterOverflowRow
        data-testid="tm-screen-filters"
        items={filterItems}
        trailing={
          <Button type="link" size="small" onClick={resetFilters} data-testid="tm-screen-reset-filters">
            恢复默认
          </Button>
        }
      />

      <div className="tm-screen__body tm-screen__body--wide">
        <section className="tm-screen__main" data-testid="tm-screen-detail">
          <div className="tm-screen__section-head">
            <h2>
              {isToday
                ? '今日 × Action 明细'
                : isPipeline
                  ? '需求 × Task 明细'
                  : '周 × Task 明细'}
            </h2>
            <span>
              {isToday
                ? `展示 ${todayActionRows.length} 个 Action`
                : isPipeline
                  ? `展示 ${filteredTasks.length} 个 Task`
                  : `展示 ${filteredTasks.length} 个 Task · ${filteredTasks.reduce(
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
          ) : (
            <div className="tm-screen__table-scroll" data-testid="tm-screen-table">
              <table className="tm-screen__table tm-screen__table--dense">
                <thead>
                  <tr>
                    {isPipeline ? null : <th style={{ width: 28 }} />}
                    <th>Task</th>
                    <th>领域</th>
                    <th>需求进展</th>
                    <th
                      title={
                        isPipeline
                          ? 'Task 测试负责人（每人 Task 仅一名）'
                          : 'Task 测试负责人优先；多人时「负责人 等N人」'
                      }
                    >
                      负责人
                    </th>
                    {isPipeline ? null : (
                      <>
                        <th>进度</th>
                        <th>风险 / 阻塞</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {filteredTasks.map((bt) => {
                    const open =
                      !isPipeline &&
                      (Boolean(props.expandAllTasks) || expandedIds.has(bt.task.id))
                    const st = STATUS_LABEL[bt.task.status] || {
                      color: 'default',
                      text: bt.task.status,
                    }
                    const hasRisk = bt.actions.some(isOpenBlockingAction)
                    return (
                      <TaskGroup
                        key={bt.task.id}
                        bt={bt}
                        open={open}
                        status={st}
                        hasRisk={hasRisk}
                        readOnly={Boolean(props.readOnly)}
                        hideActions={isPipeline}
                        userName={props.userName}
                        onToggle={() => toggleExpand(bt.task.id)}
                        onOpenAction={props.onOpenAction}
                      />
                    )
                  })}
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

/** 今日扁平 Action 行：Action 为主，Task 弱化为副标题 */
function TodayActionRow(props: {
  row: FlatActionRow
  readOnly?: boolean
  userName: (id: number) => string
  onOpenAction: (id: string) => void
}) {
  const { action: a, taskTitle } = props.row
  const risk = (a.latest_risk || '').trim()
  const blocking = isOpenBlockingAction(a)
  const missingDaily = isMissingDailyToday(a)
  const riskOnly = hasRiskText(a) && !blocking
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
        <div className="tm-screen__action-name">{a.title}</div>
        <div className="tm-screen__action-meta" title={taskTitle}>
          Task: {taskTitle}
        </div>
      </td>
      <td className="tm-screen__td-flags">
        <div className="tm-screen__flag-list">
          {blocking ? (
            <Tag color="orange" className="tm-screen__flag-tag">
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
          <span className="tm-screen__risk-inline tm-screen__risk-inline--detail" title={risk}>
            {risk}
          </span>
        ) : (
          <span className="tm-screen__ok">无</span>
        )}
      </td>
    </tr>
  )
}

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
  const blockingN = hideActions ? 0 : bt.actions.filter(isOpenBlockingAction).length
  /** 有风险文案但未勾阻塞（与「阻塞」拆开展示） */
  const riskOnlyN = hideActions
    ? 0
    : bt.actions.filter((a) => hasRiskText(a) && !isOpenBlockingAction(a)).length

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
          <Tag color={reqStageTagColor(bt.task.req_stage)}>{reqStageLabel(bt.task.req_stage)}</Tag>
          {!hideActions && showTestStatus(bt.task.req_stage) ? (
            <div style={{ marginTop: 4 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                测试：{status.text}
              </Text>
            </div>
          ) : null}
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
      {open &&
        hasActions &&
        bt.actions.map((a) => {
          const risk = (a.latest_risk || '').trim()
          const blocking = isOpenBlockingAction(a)
          const missingDaily = isMissingDailyToday(a)
          return (
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
                └ {a.title}
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
            </tr>
          )
        })}
    </>
  )
}
