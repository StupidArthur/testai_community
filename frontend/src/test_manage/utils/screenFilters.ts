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
  /** 所属汇报周（如 2026-09-09T17）；切日当天用于抑制「今日未日更」误报 */
  week_key?: string
}

export type ScreenTaskLike = {
  task: {
    id: string
    status: string
    domain_name?: string | null
    lead_id?: number
    req_stage?: string | null
    display_status?: string | null
  }
  actions: ScreenActionLike[]
  risks?: string[]
  week_progress_avg: number
  progress_is_manual?: boolean
}

export type ScreenFilters = {
  focus: 'focus' | 'all' | 'done' | 'archived'
  domain: string
  /** 需求进展多选（仅需求总览用）；空数组=不限 */
  reqStage: string[]
  /** 合并展示状态（display_status）多选；空数组=不限 */
  displayStatus: string[]
  actionStatus: 'all' | 'published' | 'done'
  taskBlocking: 'all' | 'yes' | 'no'
  actionRisk: 'all' | 'has_risk' | 'none'
  /** 今日：勾选后，未日更与全部下拉条件取并（OR） */
  includeMissingDaily: boolean
  /** 今日：标记多选筛选（正常/未日更/阻塞/风险），空数组=不限 */
  tags: string[]
  /** 按 Task 筛选（今日+周视图），null=全部 */
  taskId: string | null
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
export function isMissingDailyToday(a: ScreenActionLike, now: Date = new Date()): boolean {
  if (a.status !== 'published' || a.has_daily_today) return false
  // 切日（周三）当天：日更归属刚结束的周，其他周的 Action 今天收不了日更，
  // 不应标「今日未日更」（如切周自动继承到新周的 Action）
  if (a.week_key && a.week_key !== dailyContextWeekKey(now)) return false
  return true
}

/**
 * 今日日更归属的汇报周 week_key（与后端 get_daily_context_period 口径一致）。
 * 汇报周固定周三 17:00 切换；切日（周三）全天日更归属刚结束的周（week_end 落在
 * 今天的周期），其余日子归属最近一次周三 17:00 开始的汇报周。
 * 统一按北京时间（UTC+8）计算，不依赖本机时区。
 */
export function dailyContextWeekKey(now: Date = new Date()): string {
  // 平移为「北京钟面」后用 UTC 方法读取，避免本机时区影响
  const bjMs = now.getTime() + (480 + now.getTimezoneOffset()) * 60_000
  const dayFloor = Math.floor(bjMs / 86_400_000) * 86_400_000
  const weekday = new Date(bjMs).getUTCDay() // 0=周日 ... 3=周三
  const daysAgo = weekday === 3 ? 7 : (weekday - 3 + 7) % 7
  const anchor = dayFloor - daysAgo * 86_400_000
  return new Date(anchor).toISOString().slice(0, 10) + 'T17'
}

/** 今天是否为切日（北京时间周三）；切日 17:00 后新周 Action 当天收不了日更 */
export function isWeekSwitchDay(now: Date = new Date()): boolean {
  const bjMs = now.getTime() + (480 + now.getTimezoneOffset()) * 60_000
  return new Date(bjMs).getUTCDay() === 3
}

/**
 * 风险展示口径：仅「测试中」阶段的 Task 统计/展示风险。
 * 其他阶段（待开发等）不应有进行中的测试投入；挂着的旧 Action 风险不再上屏。
 */
export function taskShowsRisk(bt: Pick<ScreenTaskLike, 'task'>): boolean {
  return (bt.task.req_stage || '') === 'testing'
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
  // 周视图标记多选（含阻塞/含风险/本周完成），空数组=不限
  // 'completed' 是 Task 级标记，在 applyScreenFilters 的 Task 层处理，此处跳过
  if (!isToday && filters.tags && filters.tags.length > 0) {
    const actionTags = filters.tags.filter((t) => t !== 'completed')
    if (actionTags.length === 0) {
      // 只有 Task 级标记（completed），不按 Action 级标记过滤
      return matchesDropdownFilters(a, filters)
    }
    const matchTag = actionTags.some((tag) => {
      if (tag === 'blocking') return isOpenBlockingAction(a)
      if (tag === 'risk') return hasRiskText(a) && !isOpenBlockingAction(a)
      return false
    })
    if (!matchTag) return false
    return matchesDropdownFilters(a, filters)
  }
  // 今日标记多选（tags）优先于旧字段
  if (isToday && filters.tags && filters.tags.length > 0) {
    const matchTag = filters.tags.some((tag) => {
      if (tag === 'blocking') return isOpenBlockingAction(a)
      if (tag === 'risk') return hasRiskText(a) && !isOpenBlockingAction(a)
      if (tag === 'missing_daily') return isMissingDailyToday(a)
      if (tag === 'normal') {
        return !isOpenBlockingAction(a) && !isMissingDailyToday(a) && !hasRiskText(a)
      }
      return false
    })
    if (!matchTag) return false
    // tags 生效时，传统下拉条件仍叠加（AND）
    return matchesDropdownFilters(a, filters)
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
    if (filters.actionProgressBand !== 'all') n += 1
  } else {
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

  if (filters.taskId) {
    list = list.filter((bt) => bt.task.id === filters.taskId)
  }

  if (!isToday) {
    if (filters.focus === 'focus') {
      list = list.filter((bt) => {
        const ds = bt.task.display_status || ''
        const inFunnel = ds === 'pending_test' || ds === 'testing_progress' || ds === 'testing_done'
        if (!inFunnel) return false
        if (ds === 'pending_test') return true
        return (
          bt.actions.some(isOpenBlockingAction) ||
          bt.actions.some((a) => a.status === 'published')
        )
      })
    } else if (filters.focus === 'all') {
      list = list.filter((bt) => (bt.task.display_status || '') !== 'cancelled')
    } else if (filters.focus === 'done') {
      list = list.filter((bt) => {
        const ds = bt.task.display_status || ''
        return ds === 'test_done' || ds === 'testing_done'
      })
    } else if (filters.focus === 'archived') {
      list = list.filter((bt) => (bt.task.display_status || '') === 'cancelled')
    }
    if (filters.weekProgressBand !== 'all') {
      list = list.filter((bt) => matchesWeekProgressBand(bt, filters.weekProgressBand))
    }
    // displayStatus 筛选；tags 含 completed 时特殊处理
    const tagsHaveCompleted = !!(filters.tags && filters.tags.includes('completed'))
    const hasActionTags = !!(
      filters.tags &&
      filters.tags.some((t) => t === 'blocking' || t === 'risk')
    )
    if (tagsHaveCompleted) {
      if (hasActionTags) {
        // completed + 阻塞/风险 并存：OR 关系，displayStatus 放开到包含 completed
        const dsSet = new Set([
          ...(filters.displayStatus.length > 0 ? filters.displayStatus : []),
          'testing_done',
          'test_done',
        ])
        list = list.filter((bt) => dsSet.has(bt.task.display_status || ''))
      } else {
        // 只选 completed：只看已完成
        list = list.filter((bt) => {
          const ds = bt.task.display_status || ''
          return ds === 'testing_done' || ds === 'test_done'
        })
      }
    } else if (filters.displayStatus.length > 0) {
      list = list.filter((bt) =>
        filters.displayStatus.includes(bt.task.display_status || ''),
      )
    }
  } else {
    // 日视图：tags 含 completed 时，过滤 Task 已完成的 actions
    if (filters.tags && filters.tags.includes('completed')) {
      list = list.filter((bt) => {
        const ds = bt.task.display_status || ''
        return ds === 'testing_done' || ds === 'test_done'
      })
    }
  }

  list = list
    .map((bt) => ({
      ...bt,
      actions: bt.actions.filter((a) => actionMatchesScreenFilters(a, filters, isToday)),
    }))
    .filter((bt) => {
      if (isToday) return bt.actions.length > 0
      if (filters.weekHasMissingDaily) {
        return bt.actions.some((a) => isMissingDailyToday(a))
      }
      if (filters.tags && filters.tags.length > 0) {
        return bt.actions.length > 0
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
  const blockA = taskShowsRisk(a) ? a.actions.filter(isOpenBlockingAction).length : 0
  const blockB = taskShowsRisk(b) ? b.actions.filter(isOpenBlockingAction).length : 0
  if (blockA !== blockB) return blockB - blockA
  const riskA = taskShowsRisk(a) ? a.actions.filter(hasRiskText).length : 0
  const riskB = taskShowsRisk(b) ? b.actions.filter(hasRiskText).length : 0
  if (riskA !== riskB) return riskB - riskA
  return a.week_progress_avg - b.week_progress_avg
}
