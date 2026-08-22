/**
 * 项目管理全量 UI E2E（现网开发库）
 *
 * 约定：
 * - 后端已在 48010 运行（vite 代理 /api）
 * - 全部业务数据通过页面点击创建，不用 API 灌数
 * - 数据前缀 【E2E】+ 本次 RUN id，避免互相踩
 */
import { test, expect, type Page } from '@playwright/test'
import {
  PASS,
  antdMultiSelect,
  antdSelectByLabel,
  boardTaskByTitle,
  expectToast,
  fillInputNumber,
  goProjects,
  login,
  openBoardTab,
  openCreateMenu,
  openMineTab,
  openScreenTab,
  openTaskDetail,
  selectBoardScope,
  selectProjectFilter,
  setTaskReqStage,
} from './helpers.ts'

test.describe.configure({ mode: 'serial' })

/** 固定本文件加载时的 RUN，避免 worker 二次求值 Date.now 导致标题不一致 */
const RUN = process.env.E2E_RUN_ID || `r${process.pid}`
const TAG = `【E2E】${RUN}`

const users = {
  lead: { username: `e2eL_${RUN}`, realName: `E2ELead${RUN}`, password: PASS },
  owner: { username: `e2eO_${RUN}`, realName: `E2EOwner${RUN}`, password: PASS },
  tester: { username: `e2eT_${RUN}`, realName: `E2ETester${RUN}`, password: PASS },
  stranger: { username: `e2eX_${RUN}`, realName: `E2E路人${RUN}`, password: PASS },
}

const names = {
  project: `${TAG} 项目`,
  domain: `${TAG} 领域`,
  task: `${TAG} Task主`,
  taskEmpty: `${TAG} Task空`,
  taskDone: `${TAG} TaskDone`,
  actionDraft: `${TAG} 草稿Action`,
  actionPub: `${TAG} 进行中Action`,
  actionTester: `${TAG} TesterAction`,
}

async function addUserViaAdmin(
  page: Page,
  u: { username: string; realName: string },
) {
  await page.goto('/admin')
  await expect(page.getByText('管理员面板')).toBeVisible()
  // 已存在则跳过（本 RUN 内幂等）
  if (await page.getByRole('cell', { name: u.username, exact: true }).count()) {
    return
  }
  await page.getByTestId('admin-btn-add-user').click()
  await page.getByTestId('admin-input-username').fill(u.username)
  await page.getByTestId('admin-input-realname').fill(u.realName)
  await page.getByTestId('admin-submit-user').click()
  // toast 可能很快消失；以列表出现为准
  await expect(page.getByRole('cell', { name: u.username, exact: true })).toBeVisible({
    timeout: 20_000,
  })
}

test.describe(`TM UI E2E ${RUN}`, () => {
  test('01 未登录访问 /projects 跳转登录', async ({ page }) => {
    await page.goto('/projects')
    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByTestId('login-submit')).toBeVisible()
  })

  test('02 Admin 登录 → Portal → 使用说明/导航', async ({ page }) => {
    await login(page, 'admin', 'admin')
    // Portal 大入口
    await page.getByRole('button', { name: /进入/ }).click()
    await expect(page).toHaveURL(/\/projects/)
    await page.getByTestId('tm-help-btn').click()
    await expect(page.getByTestId('tm-help-drawer')).toBeVisible()
    await page.keyboard.press('Escape')
    // 三 Tab
    await openScreenTab(page)
    await openBoardTab(page)
    await openMineTab(page)
    await openBoardTab(page)
  })

  test('03 Admin 在用户管理页创建四个 Engineer', async ({ page }) => {
    await login(page, 'admin', 'admin')
    for (const u of Object.values(users)) {
      await addUserViaAdmin(page, u)
    }
    // 列表可见
    await expect(page.getByText(users.lead.username)).toBeVisible()
    await expect(page.getByText(users.owner.username)).toBeVisible()
  })

  test('04 Manager：工作台可见新建按钮；创建项目/领域', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await expect(page.getByTestId('tm-btn-create-menu')).toBeVisible()

    await openCreateMenu(page, '项目')
    await page.getByTestId('tm-input-project-name').fill(names.project)
    await page.getByTestId('tm-submit-project').click()
    await expectToast(page, '项目已创建')

    await selectProjectFilter(page, names.project)
    await openCreateMenu(page, '领域')
    await page.getByTestId('tm-input-domain-name').fill(names.domain)
    await page.getByTestId('tm-submit-domain').click()
    await expectToast(page, '领域已创建')
  })

  test('05 Manager：新建 Task 并见空卡', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)
    await selectBoardScope(page, '全部')

    await openCreateMenu(page, 'Task')
    await expect(page.getByTestId('tm-modal-new-task')).toBeVisible()
    await antdSelectByLabel(page, 'tm-task-project', names.project)
    await antdSelectByLabel(page, 'tm-task-domain', names.domain)
    await page.getByTestId('tm-task-title').fill(names.task)
    await page.getByTestId('tm-task-requirement').fill('E2E 需求说明')
    // 负责人默认 manager；测试人员后续在 Action 负责人里只用 manager（规避多选 Select 不稳定）
    await page.getByTestId('tm-submit-task').click({ force: true })
    await expect(page.getByText(names.task).first()).toBeVisible({ timeout: 20_000 })

    const card = await boardTaskByTitle(page, names.task)
    await expect(card).toBeVisible()
    // 默认待开发：不可 +Action，也不再标红「本周无 Action」（仅测试中可建 Action 时高亮）
    await expect(card.getByTestId('tm-btn-add-action')).toHaveCount(0)
    await expect(card.getByTestId('tm-empty-action-tag')).toHaveCount(0)
  })

  test('06 Manager：再建空 Task / 待完成 Task', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)
    await selectBoardScope(page, '全部')

    for (const title of [names.taskEmpty, names.taskDone]) {
      await openCreateMenu(page, 'Task')
      await antdSelectByLabel(page, 'tm-task-project', names.project)
      await antdSelectByLabel(page, 'tm-task-domain', names.domain)
      await page.getByTestId('tm-task-title').fill(title)
      await page.getByTestId('tm-task-requirement').fill('x')
      await page.getByTestId('tm-submit-task').click({ force: true })
      await expect(page.getByText(title).first()).toBeVisible({ timeout: 15_000 })
    }
  })

  test('07 Engineer 路人：无新建按钮；看不到无关空 Task', async ({ page }) => {
    await login(page, users.stranger.username)
    await goProjects(page)
    await openBoardTab(page)
    await expect(page.getByTestId('tm-btn-create-menu')).toHaveCount(0)
    await selectProjectFilter(page, names.project)
    await selectBoardScope(page, '全部')
    await expect(page.getByText(names.taskEmpty)).toHaveCount(0)
  })

  test('08 Manager：打开 Task 抽屉改需求并见成功 Alert', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)
    await selectBoardScope(page, '全部')

    const card = await boardTaskByTitle(page, names.task)
    await openTaskDetail(page, card)
    await page.getByTestId('tm-task-info-edit').click()
    await page.getByLabel(/需求内容/).fill('Manager 更新后的需求')
    await page.getByLabel(/变更说明/).fill('E2E 改需求')
    await page.getByTestId('tm-task-save').click()
    await expect(page.getByTestId('tm-task-save-tip')).toBeVisible()
    await expectToast(page, /已保存|测试负责人/)
  })

  test('09 Manager：切到测试中后 +Action 保存并发布', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)
    await selectBoardScope(page, '全部')

    const card = await boardTaskByTitle(page, names.task)
    await setTaskReqStage(page, card, '测试中')
    const cardReady = await boardTaskByTitle(page, names.task)
    await cardReady.getByTestId('tm-btn-add-action').click()
    await expect(page.getByTestId('tm-modal-new-action')).toBeVisible()
    await page.getByTestId('tm-action-title').fill(names.actionDraft)
    await page.getByTestId('tm-action-content').fill('草稿内容')
    await page.getByTestId('tm-submit-action-publish').click({ force: true })
    await expectToast(page, 'Action 已保存')
    await expect(page.locator('.tm-action-card').filter({ hasText: names.actionDraft })).toBeVisible()
  })

  test('10 Manager：再建一条直接「保存并发布」给 Owner', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)
    await selectBoardScope(page, '全部')

    const card = await boardTaskByTitle(page, names.task)
    await card.getByTestId('tm-btn-add-action').click()
    await page.getByTestId('tm-action-title').fill(names.actionPub)
    await page.getByTestId('tm-submit-action-publish').click({ force: true })
    await expectToast(page, 'Action 已保存')
    await expect(page.locator('.tm-action-card').filter({ hasText: names.actionPub })).toBeVisible()
  })

  test('11 Manager：再建一条 Action（供权限对照）', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)
    await selectBoardScope(page, '全部')

    const card = await boardTaskByTitle(page, names.task)
    await card.getByTestId('tm-btn-add-action').click()
    await page.getByTestId('tm-action-title').fill(names.actionTester)
    await page.getByTestId('tm-submit-action-publish').click({ force: true })
    await expectToast(page, 'Action 已保存')
  })

  test('12 Manager：日更 + 风险；进度倒退被拒；清空风险', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)
    await selectBoardScope(page, '全部')

    await page.locator('.tm-action-card').filter({ hasText: names.actionPub }).first().click()
    await expect(page.getByTestId('tm-drawer-action')).toBeVisible()
    const progress = page.getByRole('spinbutton', { name: /进度/ })
    await expect(progress).toBeVisible({ timeout: 15_000 })
    await progress.click()
    await progress.fill('30')
    await page.getByTestId('tm-daily-risk').fill('E2E阻塞UNIQUE')
    await page.getByTestId('tm-daily-note').fill('推进中说明必填')
    await page.getByTestId('tm-submit-daily').click()
    await expectToast(page, '日更已保存')

    // 真实 UI：减号禁用 + 「≥ 当前 N%」；下调走「更正说明」；后端倒退拦截由 pytest 覆盖
    await expect(page.getByText(/≥\s*当前\s*30%/)).toBeVisible()
    await expect(
      page.getByRole('button', { name: 'Decrease Value' }),
    ).toBeDisabled()
    await expect(progress).toHaveAttribute('aria-valuemin', '30')

    await progress.fill('40')
    await page.getByTestId('tm-daily-risk').fill('')
    await page.getByTestId('tm-daily-note').fill('风险已解除')
    await page.getByTestId('tm-submit-daily').click()
    await expectToast(page, '日更已保存')
  })

  test('13 Manager：更正说明；未满100% 标记完成禁用或失败', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)
    await selectBoardScope(page, '全部')

    await page.locator('.tm-action-card').filter({ hasText: names.actionPub }).first().click()
    await page.getByTestId('tm-correction-note').fill('Manager 更正一条')
    await page.getByTestId('tm-submit-correction').click()
    await expectToast(page, '追加成功')

    const doneBtn = page.getByTestId('tm-btn-mark-done')
    if (await doneBtn.count()) {
      await expect(doneBtn).toBeDisabled()
    }
  })

  test('14 Tester：不可日更 Manager 的 Action；无 +Action', async ({ page }) => {
    await login(page, users.tester.username)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)
    await selectBoardScope(page, '全部')

    // 非参与者可能看不到空关联；若看得到卡片则无 +Action
    const card = page.locator('.tm-board-task').filter({ hasText: names.task })
    if (await card.count()) {
      await expect(card.first().getByTestId('tm-btn-add-action')).toHaveCount(0)
    }

    const actionCard = page.locator('.tm-action-card').filter({ hasText: names.actionPub })
    if (await actionCard.count()) {
      await actionCard.first().click()
      await expect(page.getByTestId('tm-submit-daily')).toHaveCount(0)
    }
  })

  test('15 我的 Action：Manager 能看到自己负责的', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openMineTab(page)
    await expect(page.getByText(names.actionPub)).toBeVisible()
  })

  test('16 看板 scope：我的/其他/全部', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)

    const boardTitle = page.getByTestId('tm-board-task-title').filter({ hasText: names.task })

    await selectBoardScope(page, '我的')
    await expect(boardTitle).toBeVisible()

    await selectBoardScope(page, '其他')
    await expect(boardTitle).toHaveCount(0)

    await selectBoardScope(page, '全部')
    await expect(boardTitle).toBeVisible()
  })

  test('17 大屏：关注范围 / 需求进展 / 全屏 / 周切换', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openScreenTab(page)
    await expect(page.getByTestId('tm-screen')).toBeVisible()
    // 默认「今日」无关注范围；切到本周后再验筛选
    await page.getByTestId('tm-screen-week-current').click()
    const focus = page.getByTestId('tm-screen-focus-select')
    if (!(await focus.isVisible())) {
      await page.getByTestId('tm-screen-more-toggle').click()
      await expect(page.getByTestId('tm-screen-more-filters')).toBeVisible()
    }
    await expect(focus).toBeVisible()
    await expect(page.getByTestId('tm-screen-req-stage')).toBeVisible()
    await expect(page.getByTestId('tm-screen-fullscreen')).toBeVisible()
    await page.getByTestId('tm-screen-week-history').click()
    await expect(page.getByText('历史周进度与风险总览')).toBeVisible()
    await page.getByTestId('tm-screen-week-current').click()
    await page.getByTestId('tm-screen-week-pipeline').click()
    await expect(page.getByText('需求进展总览')).toBeVisible()
    await page.getByTestId('tm-screen-week-current').click()
  })

  test('18 Manager：Task 标测试完成 → 无 +Action', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)
    await selectBoardScope(page, '全部')

    const card = await boardTaskByTitle(page, names.taskDone)
    await setTaskReqStage(page, card, '测试完成', '测试结束时间')

    const card2 = await boardTaskByTitle(page, names.taskDone)
    await expect(card2.getByTestId('tm-btn-add-action')).toHaveCount(0)
  })

  test('19 Manager：日更到 100% 并标记完成', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)
    await selectBoardScope(page, '全部')

    await page.locator('.tm-action-card').filter({ hasText: names.actionPub }).first().click()
    const progress = page.getByRole('spinbutton', { name: /进度/ })
    await progress.fill('100')
    await page.getByTestId('tm-daily-note').fill('收尾完成')
    await page.getByTestId('tm-submit-daily').click()
    await expectToast(page, '日更已保存')
    await page.getByTestId('tm-btn-mark-done').click({ force: true })
    await expectToast(page, /完成/)
  })

  test('20 历史周只读：工作台 Alert；无新建', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await page.getByTestId('tm-board-week-history').click()
    await expect(page.getByText('历史周只读，编辑请切回本周')).toBeVisible()
    await expect(page.getByTestId('tm-btn-create-menu')).toHaveCount(0)
    await page.getByTestId('tm-board-week-current').click()
  })

  test('21 本轮创建的关键实体仍在看板', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await page.getByTestId('tm-board-week-current').click()
    await selectProjectFilter(page, names.project)
    await selectBoardScope(page, '全部')
    await expect(page.getByTestId('tm-board-task-title').filter({ hasText: names.task })).toBeVisible()
    await expect(page.locator('.tm-action-card').filter({ hasText: names.actionPub }).first()).toBeVisible()
  })
})
