/**
 * 项目管理看板 / Action 相关纯 UI 判定（便于单测，不依赖 React）。
 *
 * 与后端口径对齐：
 * - 空卡标红：当前周 + 0 Action + Task 仍可加 Action
 * - A1 参与者：lead + testers
 * - done Task 不显示 +Action
 */

export type BoardScope = 'mine' | 'other' | 'all'

export type ScopeUser = { id: number; username: string; real_name?: string }

export type ScopeTask = {
  lead_id: number
  tester_ids?: number[]
  can_add_action?: boolean
  status?: string
}

export type BoardTaskLike = {
  task: ScopeTask & { id?: string }
  actions: unknown[]
}

/** 看板空 Task 是否标红（对应 tm-board-task--empty） */
export function shouldHighlightEmptyTask(opts: {
  viewingHistory: boolean
  actionCount: number
  canAddAction: boolean
}): boolean {
  return !opts.viewingHistory && opts.actionCount === 0 && opts.canAddAction
}

/** 是否展示「+ Action」按钮 */
export function shouldShowAddActionButton(opts: {
  readOnly: boolean
  canEdit: boolean
  canAddAction: boolean
}): boolean {
  return !opts.readOnly && opts.canEdit && opts.canAddAction
}

/** Task 抽屉保存成功提示（与 Toast 文案一致，抽屉内 Alert 兜底） */
export function formatTaskSaveTip(leadDisplayName?: string): string {
  const name = (leadDisplayName || '').trim()
  return name ? `已保存 · 测试负责人：${name}` : 'Task 已更新'
}

/** A1：Action 负责人候选 = Task lead + testers */
export function taskParticipantUsers(
  task: { lead_id: number; tester_ids?: number[] } | null | undefined,
  users: ScopeUser[],
): ScopeUser[] {
  if (!task) return []
  const ids = new Set<number>([Number(task.lead_id), ...(task.tester_ids || []).map(Number)])
  return users.filter((u) => ids.has(Number(u.id)))
}

/** 看板「我的 / 其他 / 全部」过滤（泛型保留 BoardTask 等完整类型） */
export function filterBoardTasksByScope<T extends BoardTaskLike>(
  list: T[],
  scope: BoardScope,
  currentUserId: number | null | undefined,
): T[] {
  if (currentUserId == null || scope === 'all') return list
  if (scope === 'mine') {
    return list.filter((bt) => Number(bt.task.lead_id) === currentUserId)
  }
  return list.filter((bt) => Number(bt.task.lead_id) !== currentUserId)
}

export function countBoardTasksByScope(
  list: BoardTaskLike[],
  currentUserId: number | null | undefined,
): { mine: number; other: number; all: number } {
  if (currentUserId == null) {
    return { mine: 0, other: list.length, all: list.length }
  }
  let mine = 0
  let other = 0
  for (const bt of list) {
    if (Number(bt.task.lead_id) === currentUserId) mine += 1
    else other += 1
  }
  return { mine, other, all: list.length }
}

/** 空卡 Empty 文案 */
export function emptyActionDescription(opts: {
  readOnly: boolean
  canAddAction: boolean
}): string {
  if (opts.readOnly) return '该周无 Action'
  if (opts.canAddAction) return '本周尚无 Action — 点「+ Action」新建或复制上周'
  return '本周无 Action（Task 已完成，不可再添加）'
}

/**
 * 大屏视图：去掉草稿 Action（领导汇报不展示未发布项）。
 * - 仅草稿的 Task 整行隐藏
 * - 本周 0 Action 的空 Task 仍保留（提醒尚未建 Action）
 * - 未手填时：按可见 Action 重算 week_progress_avg / recommended
 * - 已手填：保留 week_progress_avg，仅用可见 Action 更新 recommended_progress
 */
export function toScreenBoardTasks<
  T extends {
    actions: { status: string; progress_percent?: number }[]
    week_progress_avg: number
    progress_is_manual?: boolean
    recommended_progress?: number
  },
>(tasks: T[]): T[] {
  const out: T[] = []
  for (const bt of tasks) {
    const visible = bt.actions.filter((a) => a.status !== 'draft')
    if (bt.actions.length > 0 && visible.length === 0) {
      continue
    }
    const actionAvg = visible.length
      ? Math.round(
          visible.reduce((s, a) => s + (a.progress_percent || 0), 0) / visible.length,
        )
      : 0
    const weekAvg = bt.progress_is_manual ? bt.week_progress_avg : actionAvg
    out.push({
      ...bt,
      actions: visible,
      week_progress_avg: weekAvg,
      recommended_progress: actionAvg,
    })
  }
  return out
}
