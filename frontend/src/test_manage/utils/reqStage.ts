/**
 * 需求进展：与后端 req_stage 对齐的展示/筛选用常量。
 */
export const REQ_STAGE_PENDING_DEV = 'pending_dev'
export const REQ_STAGE_DEVELOPING = 'developing'
export const REQ_STAGE_PENDING_HANDOVER = 'pending_handover'
export const REQ_STAGE_PENDING_TEST = 'pending_test'
export const REQ_STAGE_TESTING = 'testing'
export const REQ_STAGE_TEST_DONE = 'test_done'

export type ReqStage =
  | typeof REQ_STAGE_PENDING_DEV
  | typeof REQ_STAGE_DEVELOPING
  | typeof REQ_STAGE_PENDING_HANDOVER
  | typeof REQ_STAGE_PENDING_TEST
  | typeof REQ_STAGE_TESTING
  | typeof REQ_STAGE_TEST_DONE

export const REQ_STAGE_OPTIONS: { value: ReqStage; label: string }[] = [
  { value: REQ_STAGE_PENDING_DEV, label: '待开发' },
  { value: REQ_STAGE_DEVELOPING, label: '开发中' },
  { value: REQ_STAGE_PENDING_HANDOVER, label: '待提测' },
  { value: REQ_STAGE_PENDING_TEST, label: '待测试' },
  { value: REQ_STAGE_TESTING, label: '测试中' },
  { value: REQ_STAGE_TEST_DONE, label: '测试完成' },
]

export const REQ_STAGE_LABEL: Record<string, string> = Object.fromEntries(
  REQ_STAGE_OPTIONS.map((o) => [o.value, o.label]),
)

/**
 * Ant Design Tag / 大屏阶段卡片配色（六阶段互不相同）。
 * 待开发灰 → 开发青 → 待提测金 → 待测试橙 → 测试中蓝 → 测试完成绿。
 */
export const REQ_STAGE_TAG_COLOR: Record<string, string> = {
  [REQ_STAGE_PENDING_DEV]: 'default',
  [REQ_STAGE_DEVELOPING]: 'cyan',
  [REQ_STAGE_PENDING_HANDOVER]: 'gold',
  [REQ_STAGE_PENDING_TEST]: 'orange',
  [REQ_STAGE_TESTING]: 'processing',
  [REQ_STAGE_TEST_DONE]: 'success',
}

/** 大屏需关注默认：待测试 + 测试中 */
export const REQ_STAGES_SCREEN_FOCUS = new Set<string>([
  REQ_STAGE_PENDING_TEST,
  REQ_STAGE_TESTING,
])

/**
 * 需求总览列表排序（数字越小越靠前）。
 * 测试中 → 待测试 → 待提测 → 测试完成 → 开发中 → 待开发
 */
export const REQ_STAGE_PIPELINE_SORT_RANK: Record<string, number> = {
  [REQ_STAGE_TESTING]: 0,
  [REQ_STAGE_PENDING_TEST]: 1,
  [REQ_STAGE_PENDING_HANDOVER]: 2,
  [REQ_STAGE_TEST_DONE]: 3,
  [REQ_STAGE_DEVELOPING]: 4,
  [REQ_STAGE_PENDING_DEV]: 5,
}

const PIPELINE_SORT_RANK_FALLBACK = 99

/** 需求总览：按进展优先级比较；同阶段按标题 */
export function comparePipelineTasksByReqStage(
  a: { task: { req_stage?: string | null; title?: string } },
  b: { task: { req_stage?: string | null; title?: string } },
): number {
  const ra = REQ_STAGE_PIPELINE_SORT_RANK[a.task.req_stage || ''] ?? PIPELINE_SORT_RANK_FALLBACK
  const rb = REQ_STAGE_PIPELINE_SORT_RANK[b.task.req_stage || ''] ?? PIPELINE_SORT_RANK_FALLBACK
  if (ra !== rb) return ra - rb
  return String(a.task.title || '').localeCompare(String(b.task.title || ''), 'zh')
}

export function reqStageLabel(stage?: string | null): string {
  if (!stage) return REQ_STAGE_LABEL[REQ_STAGE_PENDING_DEV]
  return REQ_STAGE_LABEL[stage] || stage
}

/** 需求进展 Tag / KPI 用色 */
export function reqStageTagColor(stage?: string | null): string {
  if (!stage) return REQ_STAGE_TAG_COLOR[REQ_STAGE_PENDING_DEV]
  return REQ_STAGE_TAG_COLOR[stage] || 'default'
}

/** 是否展示测试状态列 */
export function showTestStatus(stage?: string | null): boolean {
  return stage === REQ_STAGE_TESTING || stage === REQ_STAGE_TEST_DONE
}
