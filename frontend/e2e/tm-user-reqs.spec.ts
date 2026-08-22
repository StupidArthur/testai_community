/**
 * 用户三点需求前端自测（打现网：后端 48010 + 前端 3003）
 * 1) Task 未手填进度 → 推荐提示
 * 2) Manager 可改周结束；创建 Action 跟当前周；预计发送可见
 * 3) Action 延续历史（克隆后抽屉可见「延续历史」）
 */
import { test, expect } from '@playwright/test'
import {
  PASS,
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
  action: `${TAG} Action`,
  actionClone: `${TAG} Action续`,
}

test.describe(`TM 三点需求 UI ${RUN}`, () => {
  test('01 Manager：周结束控件 + 周报预计文案', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)

    const picker = page.getByTestId('tm-week-end-picker')
    await expect(picker).toBeVisible({ timeout: 20_000 })
    await expect(page.getByText(/周报预计.*发送（周结束后 15min）/)).toBeVisible()

    const pushHint = page.getByTestId('tm-weekly-push-at')
    await expect(pushHint).toBeVisible()
    await expect(pushHint).toContainText(/周报预计/)
  })

  test('02 Engineer：看不到改周结束', async ({ page }) => {
    const engUser = `e2e_eng_${RUN}`
    await login(page, 'admin', 'admin')
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
    await setTaskReqStage(page, card, '测试中')
    const cardReady = await boardTaskByTitle(page, names.task)
    await cardReady.getByTestId('tm-btn-add-action').click()
    await expect(page.getByTestId('tm-modal-new-action')).toBeVisible()
    await page.getByTestId('tm-action-title').fill(names.action)
    await page.getByTestId('tm-action-content').fill('测试内容')
    await page.getByTestId('tm-action-env').fill('qa')
    await page.getByTestId('tm-submit-action-publish').click()
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

  test('04 Manager：API 克隆 → UI 见延续历史共 2 周', async ({ page, request }) => {
    const loginRes = await request.post('http://127.0.0.1:48010/api/auth/login', {
      data: { username: 'manager', password: PASS },
    })
    expect(loginRes.ok()).toBeTruthy()
    const token = (await loginRes.json()).access_token
    const headers = { Authorization: `Bearer ${token}` }

    const boardRes = await request.get('http://127.0.0.1:48010/api/test-manage/board', {
      headers,
    })
    expect(boardRes.ok()).toBeTruthy()
    const board = await boardRes.json()
    const hit = (board.tasks || []).find((t: { task: { title: string } }) =>
      t.task.title.includes(TAG),
    )
    expect(hit).toBeTruthy()
    const srcId = hit.actions[0].id as string

    const cloneRes = await request.post(
      `http://127.0.0.1:48010/api/test-manage/actions/${srcId}/clone`,
      { headers, data: { title: names.actionClone, publish: false } },
    )
    expect(cloneRes.status()).toBe(201)
    const cloned = await cloneRes.json()
    expect(cloned.source_action_id).toBe(srcId)

    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)
    const card = await boardTaskByTitle(page, names.task)
    const target = card.locator(`[data-testid="tm-action-card-${cloned.id}"]`)
    if (await target.count()) {
      await target.click()
    } else {
      await card.locator('[data-testid^="tm-action-card-"]').filter({ hasText: '续' }).first().click()
    }
    await expect(page.getByTestId('tm-drawer-action')).toBeVisible()
    const lineage = page.getByTestId('tm-action-lineage')
    await expect(lineage).toBeVisible({ timeout: 15_000 })
    await expect(lineage).toContainText(/延续历史/)
    await expect(lineage).toContainText(/2\s*周/)
  })
})
