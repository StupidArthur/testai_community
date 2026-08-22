/**
 * 大屏筛选单测：阻塞 / 风险 / 查看未日更 / 人对齐 / 进度带。
 */
import { describe, expect, it } from 'vitest'
import {
  applyScreenFilters,
  countActiveMoreFilters,
  hasRiskText,
  isOpenBlockingAction,
  matchesActionProgressBand,
  matchesWeekProgressBand,
  type ScreenFilters,
  type ScreenTaskLike,
} from './screenFilters'

const baseFilters: ScreenFilters = {
  focus: 'all',
  domain: '全部',
  taskStatus: 'all',
  reqStage: 'all',
  actionStatus: 'published',
  taskBlocking: 'all',
  actionRisk: 'all',
  includeMissingDaily: false,
  ownerId: null,
  leadId: null,
  actionProgressBand: 'all',
  weekProgressBand: 'all',
  weekHasMissingDaily: false,
}

function task(partial: Partial<ScreenTaskLike> & { actions: ScreenTaskLike['actions'] }): ScreenTaskLike {
  const { task: taskPartial, actions, risks, ...rest } = partial
  return {
    task: {
      id: 't1',
      status: 'published',
      domain_name: 'Agent',
      lead_id: 1,
      ...(taskPartial || {}),
    },
    week_progress_avg: 50,
    progress_is_manual: true,
    risks: risks || [],
    actions,
    ...rest,
  }
}

describe('screenFilters blocking/risk', () => {
  const sample = [
    task({
      task: { id: 't-block', status: 'published', domain_name: 'Agent', lead_id: 1 },
      actions: [
        {
          status: 'published',
          owner_id: 10,
          progress_percent: 20,
          latest_risk: '环境挂了',
          latest_is_blocking: true,
          has_daily_today: true,
        },
        {
          status: 'published',
          owner_id: 11,
          progress_percent: 0,
          latest_risk: '',
          latest_is_blocking: false,
          has_daily_today: false,
        },
      ],
    }),
    task({
      task: { id: 't-risk-only', status: 'published', domain_name: 'UI', lead_id: 2 },
      actions: [
        {
          status: 'published',
          owner_id: 20,
          progress_percent: 80,
          latest_risk: '有风险未勾选阻塞',
          latest_is_blocking: false,
          has_daily_today: true,
        },
      ],
    }),
  ]

  it('isOpenBlockingAction requires is_blocking', () => {
    expect(
      isOpenBlockingAction({
        status: 'published',
        latest_risk: 'x',
        latest_is_blocking: true,
      }),
    ).toBe(true)
    expect(
      isOpenBlockingAction({
        status: 'published',
        latest_risk: 'x',
        latest_is_blocking: false,
      }),
    ).toBe(false)
    expect(hasRiskText({ status: 'published', latest_risk: 'x' })).toBe(true)
  })

  it('阻塞=有阻塞 only keeps blocking actions', () => {
    const out = applyScreenFilters(sample, { ...baseFilters, taskBlocking: 'yes' }, true)
    expect(out).toHaveLength(1)
    expect(out[0].task.id).toBe('t-block')
    expect(out[0].actions).toHaveLength(1)
    expect(out[0].actions[0].latest_is_blocking).toBe(true)
  })

  it('风险=有风险 keeps risk text including non-blocking', () => {
    const out = applyScreenFilters(sample, { ...baseFilters, actionRisk: 'has_risk' }, true)
    expect(out.map((t) => t.task.id).sort()).toEqual(['t-block', 't-risk-only'])
    expect(out.find((t) => t.task.id === 't-risk-only')?.actions).toHaveLength(1)
  })

  it('查看未日更：与全部下拉结果取并（含有风险+有阻塞时仍并入纯未日更）', () => {
    const data = [
      task({
        task: { id: 't-both', status: 'published', domain_name: 'A' },
        actions: [
          {
            status: 'published',
            latest_risk: '阻塞且未日更',
            latest_is_blocking: true,
            has_daily_today: false,
          },
          {
            status: 'published',
            latest_risk: '阻塞但已日更',
            latest_is_blocking: true,
            has_daily_today: true,
          },
        ],
      }),
      task({
        task: { id: 't-blocking-daily', status: 'published', domain_name: 'B' },
        actions: [
          {
            status: 'published',
            latest_risk: '仅阻塞已日更',
            latest_is_blocking: true,
            has_daily_today: true,
          },
        ],
      }),
      task({
        task: { id: 't-missing-only', status: 'published', domain_name: 'C' },
        actions: [
          {
            status: 'published',
            latest_risk: '',
            latest_is_blocking: false,
            has_daily_today: false,
          },
        ],
      }),
      task({
        task: { id: 't-ok', status: 'published', domain_name: 'D' },
        actions: [
          {
            status: 'published',
            latest_risk: '',
            latest_is_blocking: false,
            has_daily_today: true,
          },
        ],
      }),
    ]
    const withOr = applyScreenFilters(
      data,
      { ...baseFilters, taskBlocking: 'yes', includeMissingDaily: true },
      true,
    )
    expect(withOr.map((t) => t.task.id).sort()).toEqual([
      't-blocking-daily',
      't-both',
      't-missing-only',
    ])
    expect(withOr.find((t) => t.task.id === 't-both')?.actions).toHaveLength(2)

    const blockOnly = applyScreenFilters(
      data,
      { ...baseFilters, taskBlocking: 'yes', includeMissingDaily: false },
      true,
    )
    expect(blockOnly.map((t) => t.task.id).sort()).toEqual(['t-blocking-daily', 't-both'])
    expect(blockOnly.find((t) => t.task.id === 't-missing-only')).toBeUndefined()

    const riskAndBlock = applyScreenFilters(
      data,
      {
        ...baseFilters,
        taskBlocking: 'yes',
        actionRisk: 'has_risk',
        includeMissingDaily: true,
      },
      true,
    )
    expect(riskAndBlock.map((t) => t.task.id).sort()).toEqual([
      't-blocking-daily',
      't-both',
      't-missing-only',
    ])
    const missing = riskAndBlock.find((t) => t.task.id === 't-missing-only')?.actions[0]
    expect(missing?.has_daily_today).toBe(false)
    expect(missing?.latest_risk).toBe('')
  })

  it('owner 过滤对未日更并集也生效', () => {
    const data = [
      task({
        task: { id: 't1', status: 'published' },
        actions: [
          {
            status: 'published',
            owner_id: 1,
            latest_risk: '',
            latest_is_blocking: false,
            has_daily_today: false,
          },
          {
            status: 'published',
            owner_id: 2,
            latest_risk: 'x',
            latest_is_blocking: true,
            has_daily_today: true,
          },
        ],
      }),
    ]
    const out = applyScreenFilters(
      data,
      {
        ...baseFilters,
        taskBlocking: 'yes',
        includeMissingDaily: true,
        ownerId: 1,
      },
      true,
    )
    expect(out).toHaveLength(1)
    expect(out[0].actions).toHaveLength(1)
    expect(out[0].actions[0].owner_id).toBe(1)
  })

  it('lead / 周进度 / 含未日更（本周）', () => {
    const data = [
      task({
        task: { id: 't-a', status: 'published', lead_id: 1 },
        week_progress_avg: 20,
        progress_is_manual: true,
        actions: [
          {
            status: 'published',
            has_daily_today: false,
            latest_risk: '',
            latest_is_blocking: false,
          },
        ],
      }),
      task({
        task: { id: 't-b', status: 'published', lead_id: 2 },
        week_progress_avg: 90,
        progress_is_manual: false,
        actions: [
          {
            status: 'published',
            has_daily_today: true,
            latest_risk: '',
            latest_is_blocking: false,
          },
        ],
      }),
    ]
    expect(
      applyScreenFilters(data, { ...baseFilters, actionStatus: 'all', leadId: 1 }, false).map(
        (t) => t.task.id,
      ),
    ).toEqual(['t-a'])
    expect(
      applyScreenFilters(
        data,
        { ...baseFilters, actionStatus: 'all', weekProgressBand: 'unfilled' },
        false,
      ).map((t) => t.task.id),
    ).toEqual(['t-b'])
    expect(
      applyScreenFilters(
        data,
        { ...baseFilters, actionStatus: 'all', weekHasMissingDaily: true },
        false,
      ).map((t) => t.task.id),
    ).toEqual(['t-a'])
  })

  it('本周 Task 状态筛选', () => {
    const data = [
      task({
        task: { id: 't-pub', status: 'published' },
        actions: [{ status: 'published', latest_risk: '', latest_is_blocking: false }],
      }),
      task({
        task: { id: 't-done', status: 'done' },
        actions: [{ status: 'published', latest_risk: '', latest_is_blocking: false }],
      }),
    ]
    expect(
      applyScreenFilters(
        data,
        { ...baseFilters, focus: 'all', actionStatus: 'all', taskStatus: 'done' },
        false,
      ).map((t) => t.task.id),
    ).toEqual(['t-done'])
  })

  it('matchesActionProgressBand / matchesWeekProgressBand / countActiveMoreFilters', () => {
    expect(matchesActionProgressBand(0, 'zero')).toBe(true)
    expect(matchesActionProgressBand(20, 'low')).toBe(true)
    expect(matchesActionProgressBand(50, 'mid')).toBe(true)
    expect(matchesActionProgressBand(80, 'high')).toBe(true)
    expect(matchesWeekProgressBand({ week_progress_avg: 10, progress_is_manual: false }, 'unfilled')).toBe(
      true,
    )
    expect(countActiveMoreFilters(baseFilters, true)).toBe(0)
    expect(
      countActiveMoreFilters(
        { ...baseFilters, actionRisk: 'has_risk', actionProgressBand: 'low' },
        true,
      ),
    ).toBe(2)
    expect(
      countActiveMoreFilters({ ...baseFilters, weekHasMissingDaily: true, actionStatus: 'done' }, false),
    ).toBe(2)
  })

  it('Task 排序：阻塞数降序，同阻塞按风险数降序', () => {
    const data = [
      task({
        task: { id: 't-1block-1risk', status: 'published' },
        week_progress_avg: 10,
        actions: [
          {
            status: 'published',
            latest_risk: '阻塞',
            latest_is_blocking: true,
          },
          {
            status: 'published',
            latest_risk: '仅风险',
            latest_is_blocking: false,
          },
        ],
      }),
      task({
        task: { id: 't-2block', status: 'published' },
        week_progress_avg: 90,
        actions: [
          {
            status: 'published',
            latest_risk: 'a',
            latest_is_blocking: true,
          },
          {
            status: 'published',
            latest_risk: 'b',
            latest_is_blocking: true,
          },
        ],
      }),
      task({
        task: { id: 't-0block-2risk', status: 'published' },
        week_progress_avg: 50,
        actions: [
          {
            status: 'published',
            latest_risk: 'r1',
            latest_is_blocking: false,
          },
          {
            status: 'published',
            latest_risk: 'r2',
            latest_is_blocking: false,
          },
        ],
      }),
      task({
        task: { id: 't-clean', status: 'published' },
        week_progress_avg: 5,
        actions: [
          {
            status: 'published',
            latest_risk: '',
            latest_is_blocking: false,
          },
        ],
      }),
    ]
    const out = applyScreenFilters(data, { ...baseFilters, actionStatus: 'all' }, false)
    expect(out.map((t) => t.task.id)).toEqual([
      't-2block',
      't-1block-1risk',
      't-0block-2risk',
      't-clean',
    ])
  })
})
