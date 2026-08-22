/**
 * 需求进展 / 需求总览 UI E2E。
 */
import { test, expect } from '@playwright/test'
import {
  PASS,
  antdSelectByLabel,
  boardTaskByTitle,
  expectToast,
  goProjects,
  login,
  openBoardTab,
  openCreateMenu,
  openScreenTab,
  selectBoardScope,
  selectProjectFilter,
} from './helpers.ts'

const RUN = process.env.E2E_RUN_ID || 'reqstage1'
const names = {
  project: `【E2E阶段】P-${RUN}`,
  domain: `域-${RUN}`,
  task: `【E2E阶段】T-${RUN}`,
}

test.describe.configure({ mode: 'serial' })

test.describe(`TM req-stage ${RUN}`, () => {
  test('01 建项目/领域/Task，默认待开发无 +Action', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)

    await openCreateMenu(page, '项目')
    await page.getByTestId('tm-input-project-name').fill(names.project)
    await page.getByTestId('tm-submit-project').click()
    await expectToast(page, /项目已创建/)

    await selectProjectFilter(page, names.project)
    await openCreateMenu(page, '领域')
    await page.getByTestId('tm-input-domain-name').fill(names.domain)
    await page.getByTestId('tm-submit-domain').click()
    await expectToast(page, /领域已创建/)

    await openCreateMenu(page, 'Task')
    await expect(page.getByTestId('tm-modal-new-task')).toBeVisible()
    await antdSelectByLabel(page, 'tm-task-project', names.project)
    await antdSelectByLabel(page, 'tm-task-domain', names.domain)
    await page.getByTestId('tm-task-title').fill(names.task)
    await page.getByTestId('tm-task-requirement').fill('阶段 E2E')
    await page.getByTestId('tm-submit-task').click({ force: true })
    await expect(page.getByText(names.task).first()).toBeVisible({ timeout: 20_000 })

    await selectBoardScope(page, '全部')
    const card = await boardTaskByTitle(page, names.task)
    await expect(card).toBeVisible()
    await expect(card.getByTestId('tm-btn-add-action')).toHaveCount(0)
  })

  test('02 改到测试中后可 +Action；需求总览可见', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)
    await selectBoardScope(page, '全部')

    const card = await boardTaskByTitle(page, names.task)
    await card.getByTestId('tm-btn-task-menu').click()
    await page.getByRole('menuitem', { name: '进度' }).click()
    await expect(page.getByTestId('tm-drawer-task')).toBeVisible()
    await expect(page.getByTestId('tm-task-flow')).toBeVisible()

    await antdSelectByLabel(page, 'tm-task-req-stage', '测试中')
    for (const label of ['测试开始时间', '预计测试结束']) {
      const field = page.getByLabel(label)
      await expect(field).toBeVisible()
      await field.click()
      const panel = page.locator('.ant-picker-dropdown:not(.ant-picker-dropdown-hidden)').last()
      await panel.locator('.ant-picker-cell-in-view').filter({ hasNot: page.locator('.ant-picker-cell-disabled') }).first().click()
    }

    await page.getByTestId('tm-task-save').click()
    await expectToast(page, /已保存|更新/)
    await page.locator('.ant-drawer-open .ant-drawer-close').click()
    await expect(page.getByTestId('tm-drawer-task')).toHaveCount(0)

    const card2 = await boardTaskByTitle(page, names.task)
    await expect(card2.getByTestId('tm-btn-add-action')).toBeVisible({ timeout: 15_000 })

    await openScreenTab(page)
    await page.getByTestId('tm-screen-week-pipeline').click()
    await expect(page.getByText('需求进展总览')).toBeVisible()
    await expect(page.getByTestId('tm-screen-stage-kpi-testing')).toBeVisible()
    await expect(page.getByTestId('tm-screen-req-stage')).toBeVisible()
    await expect(page.getByText('需求 × Task 明细')).toBeVisible()
    await expect(page.getByTestId('tm-screen-action-row')).toHaveCount(0)
    await expect(page.getByText(/^测试：/)).toHaveCount(0)

    await page.getByTestId('tm-screen-week-current').click()
    await expect(page.getByTestId('tm-screen-focus-select')).toBeVisible()
    await expect(page.getByTestId('tm-screen-req-stage')).toBeVisible()
  })

  test('03 公开深链 /tm-screen?view=pipeline', async ({ page }) => {
    await page.goto('/tm-screen?view=pipeline')
    await expect(page.getByTestId('tm-screen')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('需求进展总览')).toBeVisible()
    await expect(page.getByTestId('tm-screen-stage-kpi-pending_dev')).toBeVisible()
  })
})
