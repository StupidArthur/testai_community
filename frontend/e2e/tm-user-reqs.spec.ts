/**
 * 用户三点需求前端自测（打现网：后端 48010 + 前端 3003）
 * 1) Task 未手填进度 → 推荐提示
 * 2) 周结束固定周三 17:00（设置控件已下线，截止提示全员可见）；创建 Action 跟当前周
 * 3) Action 延续历史（克隆后抽屉可见「延续历史」）
 */
import { test, expect } from '@playwright/test'
import {
  PASS,
  addSubtaskViaInline,
  antdSelectByLabel,
  boardTaskByTitle,
  expectToast,
  fillInputNumber,
  goProjects,
  login,
  logout,
  openBoardTab,
  openCreateMenu,
  openTaskDetail,
  selectBoardScope,
  selectProjectFilter,
  setTaskReqStage,
} from './helpers.ts'

test.describe.configure({ mode: 'serial' })

const RUN = process.env.E2E_RUN_ID || `ui${Date.now().toString().slice(-8)}`
const TAG = `【UI自测】${RUN}`
const names = {
  project: `${TAG} 项目`,
  domain: `${TAG} 领域`,
  task: `${TAG} Task`,
  subtask: `${TAG} 子需求`,
  action: `${TAG} Action`,
}

test.describe(`TM 三点需求 UI ${RUN}`, () => {
  test('01 Manager：周截止提示可见（设置控件已下线）', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)

    // 周结束设置控件已下线
    await expect(page.getByTestId('tm-week-end-picker')).toHaveCount(0)
    // 固定截止提示全员可见
    const hint = page.getByTestId('tm-week-end-hint')
    await expect(hint).toBeVisible({ timeout: 20_000 })
    await expect(hint).toContainText('每周三 17:00')
    await expect(hint).toContainText('16:55')
  })

  test('02 Engineer：同样只有截止提示，无设置控件', async ({ page }) => {
    const engUser = `e2e_eng_${RUN}`
    await login(page, 'admin')
    await page.goto('/admin')
    await expect(page.getByText('管理员面板')).toBeVisible()
    if (!(await page.getByRole('cell', { name: engUser, exact: true }).count())) {
      await page.getByTestId('admin-btn-add-user').click()
      await page.getByTestId('admin-input-username').fill(engUser)
      await page.getByTestId('admin-input-realname').fill(`UIEng${RUN}`)
      await page.getByTestId('admin-submit-user').click()
      await expect(page.getByRole('cell', { name: engUser, exact: true })).toBeVisible({
        timeout: 20_000,
      })
    }
    await logout(page)
    await login(page, engUser, PASS)
    await goProjects(page)
    await openBoardTab(page)
    await expect(page.getByTestId('tm-week-end-picker')).toHaveCount(0)
    await expect(page.getByTestId('tm-week-end-hint')).toBeVisible({ timeout: 20_000 })
  })

  test('03 Manager：建树+日更 → 未手填推荐提示', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)

    await openCreateMenu(page, '项目')
    await page.getByTestId('tm-input-project-name').fill(names.project)
    await page.getByTestId('tm-submit-project').click()
    await expectToast(page, '项目已创建')

    await selectProjectFilter(page, names.project)
    await openCreateMenu(page, '领域')
    await page.getByTestId('tm-input-domain-name').fill(names.domain)
    await page.getByTestId('tm-submit-domain').click()
    await expectToast(page, '领域已创建')

    await openCreateMenu(page, 'Task')
    await expect(page.getByTestId('tm-modal-new-task')).toBeVisible()
    await antdSelectByLabel(page, 'tm-task-project', names.project)
    await antdSelectByLabel(page, 'tm-task-domain', names.domain)
    await page.getByTestId('tm-task-title').fill(names.task)
    await page.getByTestId('tm-task-requirement').fill('UI 自测需求：未手填推荐')
    await page.getByTestId('tm-submit-task').click({ force: true })
    await expect(page.getByText(names.task).first()).toBeVisible({ timeout: 20_000 })

    const card = await boardTaskByTitle(page, names.task)
    // Action 必须关联子需求：先在 inline 表单中创建
    await addSubtaskViaInline(page, card, names.subtask)
    await setTaskReqStage(page, card, '测试中-进行中')
    const cardReady = await boardTaskByTitle(page, names.task)
    await cardReady.getByTestId('tm-btn-add-action').click()
    await expect(page.getByTestId('tm-inline-add-action')).toBeVisible()
    await antdSelectByLabel(page, 'tm-inline-subtask', names.subtask)
    await page.getByTestId('tm-inline-title').fill(names.action)
    await page.getByTestId('tm-inline-content').fill('测试内容')
    await page.getByTestId('tm-inline-env').fill('qa')
    await page.getByTestId('tm-inline-publish').click()
    await expectToast(page, /已保存|发布|创建/)

    await selectProjectFilter(page, names.project)
    const card2 = await boardTaskByTitle(page, names.task)
    await expect(card2.getByTestId('tm-task-progress-tip')).toBeVisible()
    await card2.getByTestId('tm-task-progress-tip').hover()
    await expect(page.getByRole('tooltip').filter({ hasText: '未手填' })).toBeVisible()
    await card2.locator('[data-testid^="tm-action-card-"]').first().click()
    await expect(page.getByTestId('tm-drawer-action')).toBeVisible()
    await fillInputNumber(page, 'tm-daily-progress', '55')
    await page.getByTestId('tm-daily-note').fill('本日进展说明：UI自测日更')
    await page.getByTestId('tm-submit-daily').click()
    await expectToast(page, /日更|成功|已保存|提交/)
    await page.keyboard.press('Escape')

    await selectBoardScope(page, '全部')
    const card3 = await boardTaskByTitle(page, names.task)
    await expect(card3.getByTestId('tm-task-progress-tip')).toBeVisible({ timeout: 15_000 })
    await card3.getByTestId('tm-task-progress-tip').hover()
    await expect(page.getByRole('tooltip').filter({ hasText: '未手填' })).toBeVisible()

    await openTaskDetail(page, card3, '进度')
    await expect(page.getByTestId('tm-drawer-task')).toBeVisible()
    await expect(page.getByTestId('tm-task-week-progress')).toBeVisible()
    await expect(page.getByTestId('tm-task-week-progress').getByText(/未手填 · 按 Action 平均\s*55%/)).toBeVisible()
    await page.keyboard.press('Escape')
  })

  test('04 Manager：Action 抽屉显示延续历史（当前周）', async ({ page }) => {
    // 手动「克隆」API 已下线（切周自动继承取代）；单周 Action 抽屉即显示延续历史 1 周
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)
    const card = await boardTaskByTitle(page, names.task)
    await card
      .locator('[data-testid^="tm-action-card-"]')
      .filter({ hasText: names.action })
      .first()
      .click()
    await expect(page.getByTestId('tm-drawer-action')).toBeVisible()
    const lineage = page.getByTestId('tm-action-lineage')
    await expect(lineage).toBeVisible({ timeout: 15_000 })
    // Collapse 默认折叠：仅断言面板标题（周数），不展开断言「当前」标签
    await expect(lineage).toContainText(/延续历史/)
    await expect(lineage).toContainText(/1\s*周/)
  })
})
