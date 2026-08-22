/**
 * 大屏今日/本周筛选纯函数（便于单测）。
 *
 * 各下拉之间：交集（AND）。
 * 今日勾选「查看未日更」：未日更 与「全部下拉结果」取并集（OR）——
 *   （满足全部下拉）∨（进行中且未日更）；人对齐（owner）对两支都生效。
 */

/** Action 进度带 */
export type ActionProgressBand = 'all' | 'zero' | 'low' | 'mid' | 'high'

/** Task 周进度带（含未手填） */
export type WeekProgressBand = 'all' | 'unfilled' | 'low' | 'mid' | 'high'

export type ScreenActionLike = {
  status: string
  owner_id?: number
  progress_percent?: number
  latest_risk?: string
  latest_is_blocking?: boolean | number | string | null
  has_daily_today?: boolean
}

export type ScreenTaskLike = {
  task: {
    id: string
    status: string
    domain_name?: string | null
    lead_id?: number
    req_stage?: string | null
  }
  actions: ScreenActionLike[]
  risks?: string[]
  week_progress_avg: number
  progress_is_manual?: boolean
}

export type ScreenFilters = {
  focus: 'focus' | 'all' | 'done' | 'archived'
  domain: string
  /** 按 Task 状态收窄（今日/本周均可用） */
  taskStatus: 'all' | 'published' | 'done' | 'cancelled'
  /** 需求进展；all=不限 */
  reqStage: 'all' | string
  actionStatus: 'all' | 'published' | 'done'
  taskBlocking: 'all' | 'yes' | 'no'
  actionRisk: 'all' | 'has_risk' | 'none'
  /** 今日：勾选后，未日更与全部下拉条件取并（OR） */
  includeMissingDaily: boolean
  /** 今日主栏：Action 负责人；null=全部 */
  ownerId: number | null
  /** 本周主栏：Task lead；null=全部 */
  leadId: number | null
  /** 今日「更多」：Action 进度带 */
  actionProgressBand: ActionProgressBand
  /** 本周「更多」：Task 周进度带 */
  weekProgressBand: WeekProgressBand
  /** 本周「更多」：仅保留含未日更 Action 的 Task */
  weekHasMissingDaily: boolean
}

export function isBlockingFlag(v: unknown): boolean {
  return v === true || v === 1 || v === '1' || v === 'true'
}

/** 开放阻塞：进行中 + 有风险文案 + 勾选是否阻塞 */
export function isOpenBlockingAction(a: ScreenActionLike): boolean {
  return (
    a.status === 'published' &&
    isBlockingFlag(a.latest_is_blocking) &&
    !!(a.latest_risk || '').trim()
  )
}

export function hasRiskText(a: ScreenActionLike): boolean {
  return a.status === 'published' && !!(a.latest_risk || '').trim()
}

/** 进行中且今日尚未日更 */
export function isMissingDailyToday(a: ScreenActionLike): boolean {
  return a.status === 'published' && !a.has_daily_today
}

/** Action 进度落入指定带 */
export function matchesActionProgressBand(
  percent: number | undefined,
  band: ActionProgressBand,
): boolean {
  if (band === 'all') return true
  const p = Number(percent) || 0
  if (band === 'zero') return p === 0
  if (band === 'low') return p >= 1 && p <= 39
  if (band === 'mid') return p >= 40 && p <= 79
  return p >= 80
}

/** Task 周进度落入指定带 */
export function matchesWeekProgressBand(
  bt: Pick<ScreenTaskLike, 'week_progress_avg' | 'progress_is_manual'>,
  band: WeekProgressBand,
): boolean {
  if (band === 'all') return true
  if (band === 'unfilled') return bt.progress_is_manual !== true
  const p = Number(bt.week_progress_avg) || 0
  if (band === 'low') return p >= 0 && p <= 39
  if (band === 'mid') return p >= 40 && p <= 79
  return p >= 80
}

function matchesBlockingFilter(a: ScreenActionLike, filters: ScreenFilters): boolean {
  if (filters.taskBlocking === 'yes') return isOpenBlockingAction(a)
  if (filters.taskBlocking === 'no') return !isOpenBlockingAction(a)
  return true
}

/** 是否满足全部下拉条件（不含「查看未日更」勾选；不含 owner，owner 对 OR 两支都生效） */
export function matchesDropdownFilters(a: ScreenActionLike, filters: ScreenFilters): boolean {
  if (filters.actionStatus !== 'all' && a.status !== filters.actionStatus) {
    return false
  }
  if (filters.actionRisk === 'has_risk' && !hasRiskText(a)) {
    return false
  }
  if (filters.actionRisk === 'none' && hasRiskText(a)) {
    return false
  }
  if (!matchesActionProgressBand(a.progress_percent, filters.actionProgressBand)) {
    return false
  }
  return matchesBlockingFilter(a, filters)
}

/**
 * 单条 Action 是否满足当前筛选项。
 * Task 级条件（域 / Task 状态 / focus / lead）在外层处理。
 */
export function actionMatchesScreenFilters(
  a: ScreenActionLike,
  filters: ScreenFilters,
  isToday: boolean,
): boolean {
  if (filters.ownerId != null && Number(a.owner_id) !== Number(filters.ownerId)) {
    return false
  }
  const dropdownOk = matchesDropdownFilters(a, filters)
  if (isToday && filters.includeMissingDaily) {
    return dropdownOk || isMissingDailyToday(a)
  }
  return dropdownOk
}

/**
 * 「更多筛选」里相对默认值的已选项数量（用于角标）。
 * @param isToday 今日与本周「更多」字段不同
 */
export function countActiveMoreFilters(filters: ScreenFilters, isToday: boolean): number {
  let n = 0
  if (isToday) {
    if (filters.actionRisk !== 'all') n += 1
    if (filters.taskStatus !== 'all') n += 1
    if (filters.actionProgressBand !== 'all') n += 1
  } else {
    if (filters.taskStatus !== 'all') n += 1
    if (filters.actionStatus !== 'all') n += 1
    if (filters.actionRisk !== 'all') n += 1
    if (filters.weekProgressBand !== 'all') n += 1
    if (filters.weekHasMissingDaily) n += 1
  }
  return n
}

/**
 * 应用大屏筛选。
 * Task 状态（今日/本周均可用）；本周另用 focus / 周进度等。
 */
export function applyScreenFilters<T extends ScreenTaskLike>(
  tasks: T[],
  filters: ScreenFilters,
  isToday: boolean,
): T[] {
  let list: T[] = tasks

  if (filters.domain !== '全部') {
    list = list.filter((bt) => bt.task.domain_name === filters.domain)
  }

  if (filters.leadId != null) {
    list = list.filter((bt) => Number(bt.task.lead_id) === Number(filters.leadId))
  }

  if (!isToday) {
    if (filters.focus === 'focus') {
      // 交测后：待测试 + 测试中；且有阻塞或进行中 Action，或待测试排队
      list = list.filter((bt) => {
        const stage = bt.task.req_stage || ''
        const inFunnel = stage === 'pending_test' || stage === 'testing'
        if (!inFunnel) return false
        if (stage === 'pending_test') return true
        return (
          bt.actions.some(isOpenBlockingAction) ||
          bt.actions.some((a) => a.status === 'published')
        )
      })
    } else if (filters.focus === 'all') {
      list = list.filter((bt) => bt.task.status !== 'cancelled')
    } else if (filters.focus === 'done') {
      list = list.filter((bt) => bt.task.status === 'done')
    } else if (filters.focus === 'archived') {
      list = list.filter((bt) => bt.task.status === 'cancelled')
    }
    if (filters.weekProgressBand !== 'all') {
      list = list.filter((bt) => matchesWeekProgressBand(bt, filters.weekProgressBand))
    }
    if (filters.reqStage !== 'all') {
      list = list.filter((bt) => (bt.task.req_stage || '') === filters.reqStage)
    }
  }

  if (filters.taskStatus !== 'all') {
    list = list.filter((bt) => bt.task.status === filters.taskStatus)
  }

  list = list
    .map((bt) => ({
      ...bt,
      actions: bt.actions.filter((a) => actionMatchesScreenFilters(a, filters, isToday)),
    }))
    .filter((bt) => {
      if (isToday) return bt.actions.length > 0
      if (filters.weekHasMissingDaily) {
        return bt.actions.some(isMissingDailyToday)
      }
      if (filters.taskBlocking === 'yes' || filters.taskBlocking === 'no') {
        return bt.actions.length > 0
      }
      if (filters.actionRisk === 'has_risk' || filters.actionRisk === 'none') {
        return bt.actions.length > 0
      }
      if (filters.actionStatus !== 'all') {
        return bt.actions.length > 0
      }
      if (filters.ownerId != null) {
        return bt.actions.length > 0
      }
      if (filters.actionProgressBand !== 'all') {
        return bt.actions.length > 0
      }
      return true
    }) as T[]

  return [...list].sort((a, b) => compareScreenTasksByRisk(a, b))
}

/**
 * 大屏 Task 排序：阻塞数降序 → 风险数（有风险文案）降序 → 周进度升序。
 * 「风险」含阻塞与未勾阻塞的有风险 Action。
 */
export function compareScreenTasksByRisk(a: ScreenTaskLike, b: ScreenTaskLike): number {
  const blockA = a.actions.filter(isOpenBlockingAction).length
  const blockB = b.actions.filter(isOpenBlockingAction).length
  if (blockA !== blockB) return blockB - blockA
  const riskA = a.actions.filter(hasRiskText).length
  const riskB = b.actions.filter(hasRiskText).length
  if (riskA !== riskB) return riskB - riskA
  return a.week_progress_avg - b.week_progress_avg
}
