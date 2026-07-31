import type { Citation } from '../../shared/api/knowledge-base'

/**
 * 按文件名合并参考来源标签。
 * 同一文档多 chunk 只显示一次；有页码时合并页码，无页码时用 ×N 表示命中段数。
 */
export function mergeCitationsByFilename(
  citations: Citation[],
): { label: string; key: string }[] {
  const map = new Map<string, { pages: Set<number>; count: number }>()
  for (const c of citations) {
    const name = (c.filename || '文档').trim() || '文档'
    const cur = map.get(name) || { pages: new Set<number>(), count: 0 }
    cur.count += 1
    if (c.page != null && c.page > 0) cur.pages.add(c.page)
    map.set(name, cur)
  }
  return Array.from(map.entries()).map(([name, info]) => {
    const pagePart =
      info.pages.size > 0
        ? ` p${Array.from(info.pages)
            .sort((a, b) => a - b)
            .join(',')}`
        : ''
    const countPart = info.count > 1 && info.pages.size === 0 ? ` ×${info.count}` : ''
    return { key: name, label: `${name}${pagePart}${countPart}` }
  })
}
