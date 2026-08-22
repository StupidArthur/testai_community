/**
 * 大屏筛选项单行排布：空间不够时从末尾收进「更多」弹出层。
 * 测量与展示共用同一批 DOM（隐藏项 display:none），避免双份控件与重复 testid。
 */
import { useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Button, Popover } from 'antd'

const FILTER_ROW_GAP_PX = 6
/** 「更多」按钮预估宽度（含角标） */
const MORE_BTN_RESERVE_PX = 72

export type ScreenFilterOverflowItem = {
  key: string
  /** 相对默认是否已改，用于「更多」角标 */
  active: boolean
  node: ReactNode
}

export default function ScreenFilterOverflowRow(props: {
  items: ScreenFilterOverflowItem[]
  trailing?: ReactNode
  'data-testid'?: string
}) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const rowRef = useRef<HTMLDivElement>(null)
  const trailingRef = useRef<HTMLDivElement>(null)
  const [visibleCount, setVisibleCount] = useState(props.items.length)
  /** 测量阶段短暂展示全部，避免 display:none 量不到宽 */
  const [measuring, setMeasuring] = useState(true)

  const recalc = () => {
    const wrap = wrapRef.current
    const row = rowRef.current
    if (!wrap || !row) return

    const itemEls = Array.from(row.querySelectorAll<HTMLElement>('[data-filter-item]'))
    if (itemEls.length === 0) {
      setVisibleCount(0)
      setMeasuring(false)
      return
    }

    // 测量前确保全部可见
    itemEls.forEach((el) => {
      el.style.display = 'inline-flex'
    })

    const widths = itemEls.map((el) => el.getBoundingClientRect().width)
    const trailingW = trailingRef.current?.getBoundingClientRect().width ?? 0

    const fitCount = (budget: number) => {
      let used = 0
      let count = 0
      for (let i = 0; i < widths.length; i += 1) {
        const next = used + (count > 0 ? FILTER_ROW_GAP_PX : 0) + widths[i]
        if (next <= budget + 0.5) {
          used = next
          count += 1
        } else {
          break
        }
      }
      return count
    }

    const fullBudget = Math.max(0, wrap.clientWidth - trailingW - (trailingW > 0 ? FILTER_ROW_GAP_PX : 0))
    let count = fitCount(fullBudget)
    if (count < widths.length) {
      const withMoreBudget = Math.max(
        0,
        wrap.clientWidth -
          trailingW -
          MORE_BTN_RESERVE_PX -
          (trailingW > 0 ? FILTER_ROW_GAP_PX : 0) -
          FILTER_ROW_GAP_PX,
      )
      count = fitCount(withMoreBudget)
      if (widths.length > 0) count = Math.max(1, count)
      if (count >= widths.length) count = widths.length - 1
    }

    setVisibleCount(count)
    setMeasuring(false)
  }

  useLayoutEffect(() => {
    setMeasuring(true)
    const id = requestAnimationFrame(() => recalc())
    const wrap = wrapRef.current
    if (!wrap || typeof ResizeObserver === 'undefined') {
      return () => cancelAnimationFrame(id)
    }
    const ro = new ResizeObserver(() => {
      setMeasuring(true)
      requestAnimationFrame(() => recalc())
    })
    ro.observe(wrap)
    return () => {
      cancelAnimationFrame(id)
      ro.disconnect()
    }
  }, [props.items])

  const hidden = measuring ? [] : props.items.slice(visibleCount)
  const hiddenActive = useMemo(() => hidden.filter((i) => i.active).length, [hidden])

  return (
    <div className="tm-screen__filters" data-testid={props['data-testid']} ref={wrapRef}>
      <div className="tm-screen__filters-visible" ref={rowRef}>
        {props.items.map((item, index) => {
          const show = measuring || index < visibleCount
          return (
            <div
              key={item.key}
              className="tm-screen__filter-item"
              data-filter-item={item.key}
              style={{ display: show ? 'inline-flex' : 'none' }}
            >
              {item.node}
            </div>
          )
        })}
        {!measuring && hidden.length > 0 ? (
          <Popover
            trigger="click"
            placement="bottomLeft"
            content={
              <div className="tm-screen__filters-overflow" data-testid="tm-screen-more-filters">
                {hidden.map((item) => (
                  <div key={item.key} className="tm-screen__filter-item">
                    {item.node}
                  </div>
                ))}
              </div>
            }
          >
            <Button
              type="link"
              size="small"
              className="tm-screen__filters-more-btn"
              data-testid="tm-screen-more-toggle"
            >
              更多{hiddenActive > 0 ? ` (${hiddenActive})` : ''}
            </Button>
          </Popover>
        ) : null}
        {props.trailing ? (
          <div className="tm-screen__filters-trailing" ref={trailingRef}>
            {props.trailing}
          </div>
        ) : null}
      </div>
    </div>
  )
}
