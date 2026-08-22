/**
 * 补充按钮/场景：复制上周、空说明拒绝、路人更正、帮助抽屉关闭、Portal 顶栏。
 * 依赖 tm-ui-full 同次 RUN 的数据较难串联，本文件自建一套轻量数据（仍纯 UI）。
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
  openBoardTab,
  openCreateMenu,
  openTaskDetail,
  selectBoardScope,
  selectProjectFilter,
  setTaskReqStage,
} from './helpers.ts'

test.describe.configure({ mode: 'serial' })

const RUN = process.env.E2E_RUN_ID || `b${process.pid}`
const TAG = `【E2E】${RUN}`
const lead = { username: `e2eLb_${RUN}`, realName: `LeadB${RUN}` }
const owner = { username: `e2eOb_${RUN}`, realName: `OwnerB${RUN}` }
const project = `${TAG} P2`
const domain = `${TAG} D2`
const task = `${TAG} T2`
const action = `${TAG} A2`

async function ensureUser(page: import('@playwright/test').Page, u: { username: string; realName: string }) {
  await page.goto('/admin')
  if (await page.getByRole('cell', { name: u.username, exact: true }).count()) return
  await page.getByTestId('admin-btn-add-user').click()
  await page.getByTestId('admin-input-username').fill(u.username)
  await page.getByTestId('admin-input-realname').fill(u.realName)
  await page.getByTestId('admin-submit-user').click()
  await expect(page.getByRole('cell', { name: u.username, exact: true })).toBeVisible({
    timeout: 20_000,
  })
}

test.describe(`TM UI 补充 ${RUN}`, () => {
  test('A Admin 建用户', async ({ page }) => {
    await login(page, 'admin', 'admin')
    await ensureUser(page, lead)
    await ensureUser(page, owner)
  })

  test('B Manager 建项目领域 Task', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await openCreateMenu(page, '项目')
    await page.getByTestId('tm-input-project-name').fill(project)
    await page.getByTestId('tm-submit-project').click()
    await expectToast(page, '项目已创建')
    await selectProjectFilter(page, project)
    await openCreateMenu(page, '领域')
    await page.getByTestId('tm-input-domain-name').fill(domain)
    await page.getByTestId('tm-submit-domain').click()
    await expectToast(page, '领域已创建')
    await openCreateMenu(page, 'Task')
    await expect(page.getByTestId('tm-modal-new-task')).toBeVisible()
    await antdSelectByLabel(page, 'tm-task-project', project)
    await antdSelectByLabel(page, 'tm-task-domain', domain)
    await page.getByTestId('tm-task-title').fill(task)
    await page.getByTestId('tm-task-requirement').fill('补测')
    await antdSelectByLabel(page, 'tm-task-lead', new RegExp(lead.realName))
    await page.getByTestId('tm-submit-task').click()
    await expectToast(page, 'Task 已保存')
    await selectBoardScope(page, '全部')
    const card = await boardTaskByTitle(page, task)
    await expect(card).toBeVisible({ timeout: 20_000 })
    // Lead 不能改需求进展：Manager 先切到测试中，供后续 +Action
    await setTaskReqStage(page, card, '测试中')
  })

  test('C Lead 发布 Action；复制到本周（同周 clone）', async ({ page }) => {
    await login(page, lead.username)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, project)
    await selectBoardScope(page, '全部')

    const cardReady = await boardTaskByTitle(page, task)
    await cardReady.getByTestId('tm-btn-add-action').click()
    await page.getByTestId('tm-action-title').fill(action)
    // 负责人默认当前 Lead；避免用户下拉在 Engineer 会话下不稳定
    await page.getByTestId('tm-submit-action-publish').click()
    await expectToast(page, 'Action 已保存')

    await openTaskDetail(page, cardReady)
    await page.keyboard.press('Escape')
    await cardReady.getByTestId('tm-btn-add-action').click()
    const previewLink = page.getByRole('button', { name: '查看' }).first()
    if (await previewLink.count()) {
      await previewLink.click()
      await expect(page.getByTestId('tm-modal-clone-preview')).toBeVisible()
      await page.getByTestId('tm-clone-to-week').click()
      await expectToast(page, /草稿|引用|复制/)
    } else {
      // 无上周候选：应看到提示
      await expect(page.getByText(/上周无可复制|直接新建/)).toBeVisible()
      await page.keyboard.press('Escape')
    }
  })

  test('D Lead 空进度说明被拒', async ({ page }) => {
    await login(page, lead.username)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, project)
    await selectBoardScope(page, '全部')
    await page.locator('.tm-action-card').filter({ hasText: action }).first().click()
    await fillInputNumber(page, 'tm-daily-progress', '15')
    await page.getByTestId('tm-daily-note').fill('   ')
    await page.getByTestId('tm-submit-daily').click()
    // antd form 校验或后端 toast
    await expect(
      page.getByText(/进度说明必填|不能为空|必填/).or(page.locator('.ant-message-notice').filter({ hasText: /说明/ })),
    ).toBeVisible({ timeout: 10_000 })
  })

  test('E 帮助抽屉开闭；顶栏项目管理', async ({ page }) => {
    await login(page, 'manager', PASS)
    await page.goto('/')
    await page.getByTestId('nav-projects').click()
    await expect(page).toHaveURL(/\/projects/)
    await page.getByTestId('tm-help-btn').click()
    await expect(page.getByTestId('tm-help-drawer')).toBeVisible()
    await expect(page.getByText('项目管理 · 使用说明')).toBeVisible()
    await page.locator('.ant-drawer-close').click()
    await expect(page.getByTestId('tm-help-drawer')).toBeHidden()
  })

  test('F 未选项目时新建菜单「领域」disabled', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    const filter = page.getByTestId('tm-project-filter')
    await filter.hover()
    const clear = filter.locator('.ant-select-clear')
    if ((await clear.count()) > 0) {
      await clear.click({ force: true })
    }
    await page.getByTestId('tm-btn-create-menu').click()
    await expect(page.getByRole('menuitem', { name: '领域' })).toHaveAttribute('aria-disabled', 'true')
  })
})
