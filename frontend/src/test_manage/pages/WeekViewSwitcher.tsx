/**
 * 周视图切换：今日 | 本周 | 历史；历史模式下用下拉选最近最多 10 个业务周。
 */
import { Button, Select, Space } from 'antd'
import type { WeekHistoryOption } from '../../shared/api/test-manage'

export type WeekViewMode = 'today' | 'current' | 'history' | 'pipeline'

type Props = {
  mode: WeekViewMode
  onModeChange: (mode: WeekViewMode) => void
  historyOptions: WeekHistoryOption[]
  historyWeekStart?: string
  onHistoryWeekStartChange: (weekStart: string) => void
  size?: 'small' | 'middle'
  /** 区分工作台 / 大屏等同源控件，避免 E2E 同页双实例 testid 冲突 */
  testIdPrefix?: string
  /** 工作台可不展示「今日」 */
  showToday?: boolean
  /** 大屏展示「需求总览」；工作台默认隐藏 */
  showPipeline?: boolean
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
    showToday = true,
    showPipeline = true,
  } = props

  return (
    <Space size={8} wrap align="center" data-testid={`${testIdPrefix}-switcher`}>
      {showToday ? (
        <Button
          size={size}
          type={mode === 'today' ? 'primary' : 'default'}
          onClick={() => onModeChange('today')}
          data-testid={`${testIdPrefix}-today`}
        >
          今日
        </Button>
      ) : null}
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
      {showPipeline ? (
        <Button
          size={size}
          type={mode === 'pipeline' ? 'primary' : 'default'}
          onClick={() => onModeChange('pipeline')}
          data-testid={`${testIdPrefix}-pipeline`}
        >
          需求总览
        </Button>
      ) : null}
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
