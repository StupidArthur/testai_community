/**
 * 合并展示状态（后端 display_status 前端映射）。
 *
 * 后端 _task_out 中 compute_display_status() 根据 req_stage + status 计算：
 *   pending_dev           → "待开发"
 *   developing            → "开发中"
 *   pending_handover      → "待提测"
 *   pending_test          → "待测试"
 *   testing + published   → "测试中-进行中"
 *   testing + done        → "测试中-已完成"
 *   test_done             → "已完成"
 */

/** 各展示状态对应的 Tag 颜色 */
export const DISPLAY_STATUS_TAG_COLOR: Record<string, string> = {
  pending_dev: 'default',
  developing: 'cyan',
  pending_handover: 'gold',
  pending_test: 'orange',
  testing_progress: 'processing',
  testing_done: 'success',
  test_done: 'success',
}

/** 展示状态 → 中文标签 */
export function displayStatusLabel(key?: string | null): string {
  if (!key) return '待开发'
  const map: Record<string, string> = {
    pending_dev: '待开发',
    developing: '开发中',
    pending_handover: '待提测',
    pending_test: '待测试',
    testing_progress: '测试中-进行中',
    testing_done: '测试中-已完成',
    test_done: '已完成',
  }
  return map[key] || key
}

/** 展示状态 → Tag 颜色 */
export function displayStatusTagColor(key?: string | null): string {
  if (!key) return DISPLAY_STATUS_TAG_COLOR['pending_dev']
  return DISPLAY_STATUS_TAG_COLOR[key] || 'default'
}

/** 展示状态下拉选项（用于编辑） */
export const DISPLAY_STATUS_OPTIONS = [
  { value: 'pending_dev', label: '待开发' },
  { value: 'developing', label: '开发中' },
  { value: 'pending_handover', label: '待提测' },
  { value: 'pending_test', label: '待测试' },
  { value: 'testing_progress', label: '测试中-进行中' },
  { value: 'testing_done', label: '测试中-已完成' },
  { value: 'test_done', label: '已完成' },
]

/**
 * 前端将 display_status 拆回 req_stage + status（用于提交编辑）。
 * 与后端 compute_display_status 互逆。
 */
export function splitDisplayStatus(
  displayStatus: string,
): { req_stage: string; status: string } {
  switch (displayStatus) {
    case 'testing_progress':
      return { req_stage: 'testing', status: 'published' }
    case 'testing_done':
      return { req_stage: 'testing', status: 'done' }
    case 'test_done':
      return { req_stage: 'test_done', status: 'done' }
    case 'pending_dev':
      return { req_stage: 'pending_dev', status: 'published' }
    case 'developing':
      return { req_stage: 'developing', status: 'published' }
    case 'pending_handover':
      return { req_stage: 'pending_handover', status: 'published' }
    case 'pending_test':
      return { req_stage: 'pending_test', status: 'published' }
    default:
      return { req_stage: 'pending_dev', status: 'published' }
  }
}