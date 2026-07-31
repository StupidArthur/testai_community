/**
 * 周视图切换：本周 | 历史；历史模式下用下拉选最近最多 10 个业务周。
 */
import { Button, Select, Space } from 'antd'
import type { WeekHistoryOption } from '../../shared/api/test-manage'

export type WeekViewMode = 'current' | 'history'

type Props = {
  mode: WeekViewMode
  onModeChange: (mode: WeekViewMode) => void
  historyOptions: WeekHistoryOption[]
  historyWeekStart?: string
  onHistoryWeekStartChange: (weekStart: string) => void
  size?: 'small' | 'middle'
  /** 区分工作台 / 大屏等同源控件，避免 E2E 同页双实例 testid 冲突 */
  testIdPrefix?: string
}

export default function WeekViewSwitcher(props: Props) {
  const {
    mode,
    onModeChange,
    historyOptions,
    historyWeekStart,
    onHistoryWeekStartChange,
    size = 'small',
    testIdPrefix = 'tm-week',
  } = props

  return (
    <Space size={8} wrap align="center" data-testid={`${testIdPrefix}-switcher`}>
      <Button
        size={size}
        type={mode === 'current' ? 'primary' : 'default'}
        onClick={() => onModeChange('current')}
        data-testid={`${testIdPrefix}-current`}
      >
        本周
      </Button>
      <Button
        size={size}
        type={mode === 'history' ? 'primary' : 'default'}
        onClick={() => onModeChange('history')}
        data-testid={`${testIdPrefix}-history`}
      >
        历史
      </Button>
      {mode === 'history' ? (
        <Select
          size={size}
          style={{ minWidth: 280 }}
          placeholder="选择历史周"
          value={historyWeekStart}
          options={historyOptions.map((h) => ({
            value: h.week_start,
            label: h.label,
          }))}
          onChange={(v) => onHistoryWeekStartChange(v)}
          data-testid={`${testIdPrefix}-history-select`}
        />
      ) : null}
    </Space>
  )
}
