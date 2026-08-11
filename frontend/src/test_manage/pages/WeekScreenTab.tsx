/**
 * 本周作战大屏：给领导看的周 × Task 汇总视图。
 * 明细默认「需关注」折叠已完成，表格定高滚动，避免整页狂滑。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Button, Empty, Progress, Select, Space, Tag, Typography } from 'antd'
import {
  ExpandOutlined,
  CompressOutlined,
  WarningOutlined,
  ThunderboltOutlined,
  DownOutlined,
  RightOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import type { BoardOut, BoardTask, WeekHistoryOption } from '../../shared/api/test-manage'
import { toScreenBoardTasks } from '../utils/boardUi'
import WeekViewSwitcher, { type WeekViewMode } from './WeekViewSwitcher'
import './WeekScreenTab.css'

const { Text } = Typography

const STATUS_LABEL: Record<string, { color: string; text: string }> = {
  draft: { color: 'default', text: '草稿' },
  published: { color: 'processing', text: '进行中' },
  done: { color: 'success', text: '完成' },
  cancelled: { color: 'error', text: '取消' },
}

type FocusMode = 'focus' | 'all' | 'done'

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

/** 均进度旁侧文案：只反映进度，不把「有风险」绑在进度环上（避免 83% 却写风险偏高）。 */
function progressHealthLabel(progress: number) {
  if (progress >= 80) return { text: '推进良好', tone: 'good' as const }
  if (progress >= 40) return { text: '稳步推进', tone: 'ok' as const }
  if (progress > 0) return { text: '启动阶段', tone: 'ok' as const }
  return { text: '尚未填报', tone: 'ok' as const }
}

/** 开放风险：仅「进行中」Action 的最新日更仍带风险文案 */
function isOpenRiskAction(a: { status: string; latest_risk?: string }) {
  return a.status === 'published' && !!(a.latest_risk || '').trim()
}

function taskNeedsAttention(bt: BoardTask): boolean {
  // 需关注：有开放风险，或仍有进行中 Action；纯草稿不算
  if (bt.actions.some(isOpenRiskAction)) return true
  return bt.actions.some((a) => a.status === 'published')
}

function taskIsDoneLike(bt: BoardTask): boolean {
  // 「已完成」Tab：仅 Task 自身完成/取消（Task 维度，不因 Action 全做完而归入）
  return bt.task.status === 'done' || bt.task.status === 'cancelled'
}

function summarizeFiltered(tasks: BoardTask[]) {
  const actions = tasks.flatMap((bt) => bt.actions)
  const riskActions = actions.filter(isOpenRiskAction)
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
      with_risk: tasks.filter((bt) => bt.actions.some(isOpenRiskAction)).length,
    },
    action: {
      total: actions.length,
      published: actions.filter((a) => a.status === 'published').length,
      done: actions.filter((a) => a.status === 'done').length,
      draft: actions.filter((a) => a.status === 'draft').length,
      cancelled: actions.filter((a) => a.status === 'cancelled').length,
      with_risk: riskActions.length,
      progress_avg: progressAvg,
    },
  }
}

/**
 * 大 Task 行「负责人」：始终 Task 测试负责人在前；
 * 本周另有 Action 负责人时 →「袁小君 等4人」（人数含负责人本人）。
 */
function actionOwnersLabel(bt: BoardTask, userName: (id: number) => string) {
  const leadId = Number(bt.task.lead_id)
  const ownerIds = [...new Set(bt.actions.map((a) => Number(a.owner_id)))]
  if (ownerIds.length === 0) return userName(leadId)
  const others = ownerIds.filter((id) => id !== leadId)
  const total = 1 + others.length
  if (total === 1) return userName(leadId)
  return `${userName(leadId)} 等${total}人`
}

type RiskItem = {
  key: string
  actionId: string
  actionTitle: string
  taskTitle: string
  ownerName: string
  risk: string
  progress: number
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
}) {
  const rootRef = useRef<HTMLDivElement>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const [focus, setFocus] = useState<FocusMode>('focus')
  const [domain, setDomain] = useState<string>('全部')
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set())
  const viewingHistory = props.weekMode === 'history'

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

  const filteredTasks = useMemo(() => {
    let list = tasks
    if (domain !== '全部') {
      list = list.filter((bt) => bt.task.domain_name === domain)
    }
    if (focus === 'focus') {
      list = list.filter(taskNeedsAttention)
    } else if (focus === 'done') {
      list = list.filter(taskIsDoneLike)
    }
    // 有风险优先，再按进度升序（落后在前）
    return [...list].sort((a, b) => {
      const ar = a.risks.length > 0 ? 0 : 1
      const br = b.risks.length > 0 ? 0 : 1
      if (ar !== br) return ar - br
      return a.week_progress_avg - b.week_progress_avg
    })
  }, [tasks, domain, focus])

  const filteredSummary = useMemo(() => summarizeFiltered(filteredTasks), [filteredTasks])
  const health = progressHealthLabel(filteredSummary.action.progress_avg)

  const hiddenDoneCount = useMemo(() => {
    if (focus !== 'focus') return 0
    let list = tasks
    if (domain !== '全部') list = list.filter((bt) => bt.task.domain_name === domain)
    return list.filter(taskIsDoneLike).length
  }, [tasks, domain, focus])

  const riskItems: RiskItem[] = useMemo(() => {
    const rows: RiskItem[] = []
    for (const bt of filteredTasks) {
      for (const a of bt.actions) {
        if (!isOpenRiskAction(a)) continue
        rows.push({
          key: a.id,
          actionId: a.id,
          actionTitle: a.title,
          taskTitle: bt.task.title,
          ownerName: props.userName(a.owner_id),
          risk: (a.latest_risk || '').trim(),
          progress: a.progress_percent,
        })
      }
    }
    return rows
  }, [filteredTasks, props.userName])

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

  return (
    <div
      ref={rootRef}
      className={`tm-screen${fullscreen ? ' tm-screen--fs' : ''}`}
      data-testid="tm-screen"
    >
      <header className="tm-screen__hero">
        <div className="tm-screen__hero-left">
          <div className="tm-screen__eyebrow">
            <ThunderboltOutlined /> TestAI · 测试作战大屏
          </div>
          <h1 className="tm-screen__title">
            {viewingHistory ? '历史周进度与风险总览' : '本周进度与风险总览'}
          </h1>
          <p className="tm-screen__week">
            周窗口 {formatWeekRange(props.board?.week_start, props.board?.week_end)}
            {props.board?.weekly_push_at ? (
              <> · 周报预计 {dayjs(props.board.weekly_push_at).format('MM-DD HH:mm')} 发送</>
            ) : null}
            {props.board?.week_key ? ` · ${props.board.week_key}` : ''}
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
          {viewingHistory ? (
            <Alert
              type="info"
              showIcon
              style={{ marginTop: 12, maxWidth: 560 }}
              message="历史周为只读快照：仅展示该周窗口内已有 Action 的 Task；新建 / 编辑请切回「本周」。"
            />
          ) : null}
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
          <Button
            className="tm-screen__fs-btn"
            icon={fullscreen ? <CompressOutlined /> : <ExpandOutlined />}
            onClick={() => void toggleFullscreen()}
            data-testid="tm-screen-fullscreen"
          >
            {fullscreen ? '退出全屏' : '全屏汇报'}
          </Button>
        </div>
      </header>

      <section className="tm-screen__kpi-block tm-screen__kpi-block--slim">
        <div className="tm-screen__kpi-row tm-screen__kpi-row--4">
          <Kpi label="Task" value={filteredSummary.task.total} />
          <Kpi
            label="有风险"
            value={filteredSummary.task.with_risk}
            danger={filteredSummary.task.with_risk > 0}
          />
          <Kpi label="Action" value={filteredSummary.action.total} />
          <div
            className="tm-screen__kpi tm-screen__kpi--pulse"
            title="均进度 = 当前筛选下各 Action 最新日更进度的算术平均"
          >
            <div className="tm-screen__kpi-label">均进度</div>
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
        </div>
      </section>

      <div className="tm-screen__filters">
        <Space size={8} wrap>
          <Select
            style={{ minWidth: 120 }}
            value={focus}
            onChange={setFocus}
            options={[
              { value: 'focus', label: '需关注' },
              { value: 'all', label: '全部' },
              { value: 'done', label: '已完成' },
            ]}
            data-testid="tm-screen-focus-select"
          />
          <Select
            style={{ minWidth: 140 }}
            value={domain}
            onChange={setDomain}
            options={domains.map((d) => ({ value: d, label: d }))}
            data-testid="tm-screen-domain-select"
          />
          {focus === 'focus' && hiddenDoneCount > 0 ? (
            <Button type="link" size="small" onClick={() => setFocus('done')}>
              另有 {hiddenDoneCount} 个已完成/挂起 · 查看
            </Button>
          ) : null}
        </Space>
      </div>

      <div className="tm-screen__body">
        <section className="tm-screen__main">
          <div className="tm-screen__section-head">
            <h2>周 × Task 明细</h2>
            <span>
              展示 {filteredTasks.length} 个 Task ·{' '}
              {filteredTasks.reduce((n, bt) => n + bt.actions.length, 0)} 个 Action
              {hiddenDoneCount > 0 && focus === 'focus' ? ` · 已折叠完成 ${hiddenDoneCount}` : ''}
            </span>
          </div>

          {props.loading ? (
            <div className="tm-screen__empty">加载中…</div>
          ) : filteredTasks.length === 0 ? (
            <Empty
              className="tm-screen__empty"
              description={focus === 'focus' ? '本周暂无需要关注的 Task' : '本周暂无数据'}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          ) : (
            <div className="tm-screen__table-scroll">
              <table className="tm-screen__table tm-screen__table--dense">
                <thead>
                  <tr>
                    <th style={{ width: 28 }} />
                    <th>Task</th>
                    <th>领域</th>
                    <th>状态</th>
                    <th title="Task 测试负责人优先；多人时「负责人 等N人」">负责人</th>
                    <th>进度</th>
                    <th>风险</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTasks.map((bt) => {
                    const open = expandedIds.has(bt.task.id) || bt.actions.length <= 1
                    const st = STATUS_LABEL[bt.task.status] || {
                      color: 'default',
                      text: bt.task.status,
                    }
                    const hasRisk = bt.actions.some(
                      (a) => a.status === 'published' && !!(a.latest_risk || '').trim(),
                    )
                    return (
                      <TaskGroup
                        key={bt.task.id}
                        bt={bt}
                        open={open}
                        status={st}
                        hasRisk={hasRisk}
                        userName={props.userName}
                        onToggle={() => toggleExpand(bt.task.id)}
                        onOpenAction={props.onOpenAction}
                        onOpenTaskAction={() => {
                          const first = bt.actions[0]
                          if (first) props.onOpenAction(first.id)
                        }}
                      />
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <aside className="tm-screen__side" data-testid="tm-screen-risk-panel">
          <div className="tm-screen__section-head">
            <h2>
              <WarningOutlined /> 风险聚焦
            </h2>
            <span>{riskItems.length} 项</span>
          </div>
          {riskItems.length === 0 ? (
            <div className="tm-screen__side-ok">本周暂无风险与阻塞上报</div>
          ) : (
            <ul className="tm-screen__risk-list">
              {riskItems.map((r) => (
                <li key={r.key}>
                  <button
                    type="button"
                    className="tm-screen__risk-card"
                    onClick={() => props.onOpenAction(r.actionId)}
                  >
                    <div className="tm-screen__risk-top">
                      <strong>{r.taskTitle}</strong>
                      <em>{r.progress}%</em>
                    </div>
                    <div className="tm-screen__risk-meta">
                      {r.actionTitle} · {r.ownerName}
                    </div>
                    <p className="tm-screen__risk-text">{r.risk}</p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
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

function TaskGroup(props: {
  bt: BoardTask
  open: boolean
  status: { color: string; text: string }
  hasRisk: boolean
  userName: (id: number) => string
  onToggle: () => void
  onOpenAction: (id: string) => void
  onOpenTaskAction: () => void
}) {
  const { bt, open, status, hasRisk } = props
  const actionCount = bt.actions.length
  const multi = actionCount > 1
  const hasActions = actionCount > 0

  return (
    <>
      <tr
        className={`tm-screen__task-row${hasRisk ? ' tm-screen__row--risk' : ''}`}
        onClick={() => {
          if (multi) props.onToggle()
          else if (hasActions) props.onOpenTaskAction()
        }}
      >
        <td className="tm-screen__td-caret">
          {multi ? open ? <DownOutlined /> : <RightOutlined /> : null}
        </td>
        <td className="tm-screen__td-title">{bt.task.title}</td>
        <td>{bt.task.domain_name || '—'}</td>
        <td>
          <Tag color={status.color}>{status.text}</Tag>
        </td>
        <td>{actionOwnersLabel(bt, props.userName)}</td>
        <td className="tm-screen__td-progress">
          <Progress
            percent={bt.week_progress_avg}
            size="small"
            strokeColor={hasRisk ? '#d97706' : '#0070f3'}
            trailColor="rgba(15, 23, 42, 0.08)"
          />
          {!bt.progress_is_manual ? (
            <div className="tm-screen__progress-tip" title={`推荐值（Action 平均）${bt.recommended_progress ?? bt.week_progress_avg}%`}>
              未手填 Task 进度
            </div>
          ) : null}
        </td>
        <td>
          {hasRisk ? (
            <span className="tm-screen__risk-inline" title={bt.risks.join('；')}>
              <WarningOutlined /> {bt.risks[0]}
              {bt.risks.length > 1 ? ` +${bt.risks.length - 1}` : ''}
            </span>
          ) : (
            <span className="tm-screen__ok">无</span>
          )}
        </td>
      </tr>
      {/* 有 Action 即展示子行（含仅 1 条），避免 KPI 与明细条数对不上 */}
      {open &&
        hasActions &&
        bt.actions.map((a) => (
          <tr
            key={a.id}
            className={`tm-screen__action-row${(a.latest_risk || '').trim() ? ' tm-screen__row--risk' : ''}`}
            onClick={(e) => {
              e.stopPropagation()
              props.onOpenAction(a.id)
            }}
          >
            <td />
            <td colSpan={2} className="tm-screen__action-title">
              └ {a.title}
            </td>
            <td>
              <Tag color={STATUS_LABEL[a.status]?.color}>{STATUS_LABEL[a.status]?.text}</Tag>
            </td>
            <td>{props.userName(a.owner_id)}</td>
            <td className="tm-screen__td-progress">
              <Progress percent={a.progress_percent} size="small" strokeColor="#0070f3" />
            </td>
            <td>
              {(a.latest_risk || '').trim() ? (
                <span className="tm-screen__risk-inline" title={a.latest_risk}>
                  <WarningOutlined /> {a.latest_risk}
                </span>
              ) : (
                <span className="tm-screen__ok">无</span>
              )}
            </td>
          </tr>
        ))}
    </>
  )
}
