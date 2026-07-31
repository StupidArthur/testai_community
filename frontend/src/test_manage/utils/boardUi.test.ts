/**
 * boardUi 纯逻辑单测（不启浏览器；无 Playwright 时覆盖空卡/Toast/过滤契约）。
 */
import { describe, expect, it } from 'vitest'
import {
  countBoardTasksByScope,
  emptyActionDescription,
  filterBoardTasksByScope,
  formatTaskSaveTip,
  shouldHighlightEmptyTask,
  shouldShowAddActionButton,
  taskParticipantUsers,
} from './boardUi'

describe('shouldHighlightEmptyTask', () => {
  it('当前周空且可加 Action → 标红', () => {
    expect(
      shouldHighlightEmptyTask({ viewingHistory: false, actionCount: 0, canAddAction: true }),
    ).toBe(true)
  })
  it('历史周 / 已有 Action / 不可加 → 不标红', () => {
    expect(
      shouldHighlightEmptyTask({ viewingHistory: true, actionCount: 0, canAddAction: true }),
    ).toBe(false)
    expect(
      shouldHighlightEmptyTask({ viewingHistory: false, actionCount: 1, canAddAction: true }),
    ).toBe(false)
    expect(
      shouldHighlightEmptyTask({ viewingHistory: false, actionCount: 0, canAddAction: false }),
    ).toBe(false)
  })
})

describe('shouldShowAddActionButton', () => {
  it('可编辑且可加时显示', () => {
    expect(
      shouldShowAddActionButton({ readOnly: false, canEdit: true, canAddAction: true }),
    ).toBe(true)
  })
  it('只读 / 无编辑权 / done 不可加 → 隐藏', () => {
    expect(
      shouldShowAddActionButton({ readOnly: true, canEdit: true, canAddAction: true }),
    ).toBe(false)
    expect(
      shouldShowAddActionButton({ readOnly: false, canEdit: false, canAddAction: true }),
    ).toBe(false)
    expect(
      shouldShowAddActionButton({ readOnly: false, canEdit: true, canAddAction: false }),
    ).toBe(false)
  })
})

describe('formatTaskSaveTip', () => {
  it('有负责人显示名', () => {
    expect(formatTaskSaveTip('现场Lead')).toBe('已保存 · 测试负责人：现场Lead')
  })
  it('无负责人兜底', () => {
    expect(formatTaskSaveTip('')).toBe('Task 已更新')
    expect(formatTaskSaveTip()).toBe('Task 已更新')
  })
})

describe('taskParticipantUsers A1', () => {
  const users = [
    { id: 1, username: 'lead', real_name: 'L' },
    { id: 2, username: 't1', real_name: 'T1' },
    { id: 3, username: 'x', real_name: 'X' },
  ]
  it('仅 lead+testers', () => {
    const got = taskParticipantUsers({ lead_id: 1, tester_ids: [2] }, users)
    expect(got.map((u) => u.id).sort()).toEqual([1, 2])
  })
  it('task 空 → []', () => {
    expect(taskParticipantUsers(null, users)).toEqual([])
  })
})

describe('filterBoardTasksByScope', () => {
  const list = [
    { task: { lead_id: 10, can_add_action: true }, actions: [] },
    { task: { lead_id: 20, can_add_action: true }, actions: [{}] },
  ]
  it('mine / other / all', () => {
    expect(filterBoardTasksByScope(list, 'mine', 10)).toHaveLength(1)
    expect(filterBoardTasksByScope(list, 'other', 10)).toHaveLength(1)
    expect(filterBoardTasksByScope(list, 'all', 10)).toHaveLength(2)
  })
  it('counts', () => {
    expect(countBoardTasksByScope(list, 10)).toEqual({ mine: 1, other: 1, all: 2 })
  })
})

describe('emptyActionDescription', () => {
  it('三种文案', () => {
    expect(emptyActionDescription({ readOnly: true, canAddAction: true })).toContain('该周无')
    expect(emptyActionDescription({ readOnly: false, canAddAction: true })).toContain('+ Action')
    expect(emptyActionDescription({ readOnly: false, canAddAction: false })).toContain('已完成')
  })
})
