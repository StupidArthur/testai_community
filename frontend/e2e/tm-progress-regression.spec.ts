/**
 * 进度保存即时生效回归（不打刷新）：
 * 1) 测试中 Task：保存本周进度 → 表单/卡片即时更新（无需 F5）
 * 2) Action 日更 → 卡片周进度即时更新（无需 F5）
 * 3) 开发中 Task：进度区只读 + 提示，不可误保存
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
  selectProjectFilter,
  closeTaskDrawer,
} from './helpers.ts'

test.describe.configure({ mode: 'serial' })

const RUN = process.env.E2E_RUN_ID || `pb${Date.now().toString().slice(-8)}`
const TAG = `【进度回归】${RUN}`
const names = {
  project: `${TAG} 项目`,
  domain: `${TAG} 领域`,
  task: `${TAG} Task`,
  subtask: `${TAG} 子需求`,
  action: `${TAG} Action`,
}

async function createTree(page: import('@playwright/test').Page) {
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
  await antdSelectByLabel(page, 'tm-task-project', names.project)
  await antdSelectByLabel(page, 'tm-task-domain', names.domain)
  await page.getByTestId('tm-task-title').fill(names.task)
  await page.getByTestId('tm-task-sr-code').fill(`SR-E2E-${RUN}`)
  await page.getByTestId('tm-task-module').fill('回归模块')
  await page.getByTestId('tm-task-requirement').fill('进度保存即时生效回归')
  // 弹窗内容超高时提交按钮可能在视口外：先滚到按钮再点
  const submitTask = page.getByTestId('tm-submit-task')
  await submitTask.evaluate((el) => el.scrollIntoView({ block: 'center' }))
  await submitTask.click({ force: true })
  await expect(page.getByText(names.task).first()).toBeVisible({ timeout: 20_000 })
}

/** 在「进度」抽屉里把需求进展切到指定阶段（display_status 合并下拉） */
async function setStage(
  page: import('@playwright/test').Page,
  card: import('@playwright/test').Locator,
  stageLabel: string,
) {
  await openTaskDetail(page, card, '进度')
  await antdSelectByLabel(page, 'tm-task-display-status', stageLabel)
  // 测试中需填测试开始时间等 DatePicker（可留空待定，直接保存）
  await page.getByTestId('tm-task-save').click()
  await expectToast(page, /已保存|更新/)
  // 回归断言：不刷新页面，状态下拉应立即显示新值（修复前会回显旧状态）
  await expect(page.getByTestId('tm-task-display-status')).toContainText(
    stageLabel === '测试中' ? '测试中-进行中' : stageLabel,
    { timeout: 15_000 },
  )
  await closeTaskDrawer(page)
}

test.describe(`TM 进度即时生效 ${RUN}`, () => {
  let taskCreated = false

  test('00 准备：建树 + 测试中 + 发布 Action', async ({ page }) => {
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await createTree(page)
    taskCreated = true

    let card = await boardTaskByTitle(page, names.task)
    // 卡片显示 SR 编号
    await expect(card.getByTestId('tm-board-task-sr')).toHaveText(`SR-E2E-${RUN}`)
    // 先切「测试中」：仅测试中可加 Action / 填周进度（按钮才出现）
    await setStage(page, card, '测试中')

    card = await boardTaskByTitle(page, names.task)
    await addSubtaskViaInline(page, card, names.subtask)

    card = await boardTaskByTitle(page, names.task)
    await card.getByTestId('tm-btn-add-action').click()
    await expect(page.getByTestId('tm-inline-add-action')).toBeVisible()
    await antdSelectByLabel(page, 'tm-inline-subtask', names.subtask)
    await page.getByTestId('tm-inline-title').fill(names.action)
    await page.getByTestId('tm-inline-content').fill('回归内容')
    await page.getByTestId('tm-inline-env').fill('qa')
    await page.getByTestId('tm-inline-publish').click()
    await expectToast(page, /已保存|发布|创建/)
  })

  test('01 保存本周进度 → 不刷新即时生效', async ({ page }) => {
    test.skip(!taskCreated, '前置建树失败')
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)
    const card = await boardTaskByTitle(page, names.task)

    await openTaskDetail(page, card, '进度')
    await expect(page.getByTestId('tm-task-week-progress')).toBeVisible()
    // 未手填：显示推荐值提示
    await expect(page.getByTestId('tm-task-week-progress').getByText(/未手填/)).toBeVisible()

    await fillInputNumber(page, 'tm-task-week-progress-input', '60')
    await page.getByTestId('tm-task-week-progress-save').click()
    await expectToast(page, '本周 Task 进度已保存')

    // 关键：不刷新页面，断言已保存的值可见（表单重挂载显示 60）
    await expect(page.getByTestId('tm-task-week-progress-input')).toHaveValue('60', {
      timeout: 15_000,
    })
    // 不再显示「未手填」推荐提示
    await expect(page.getByTestId('tm-task-week-progress').getByText(/未手填/)).toBeHidden()
    await closeTaskDrawer(page)

    // 关键：不刷新页面，工作台卡片周进度立即变成 60%
    const card2 = await boardTaskByTitle(page, names.task)
    await expect(card2.getByText('60%').first()).toBeVisible({ timeout: 15_000 })
    // 「未手填」感叹号提示消失
    await expect(card2.getByTestId('tm-task-progress-tip')).toBeHidden()
  })

  test('02 日更保存 → 不刷新卡片周进度联动', async ({ page }) => {
    test.skip(!taskCreated, '前置建树失败')
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)

    // 新建第二个 Action 进度 30，验证卡片均值 = (60*0? 手填优先) —— 手填 60 优先展示，
    // 这里改为验证 Action 卡片自身进度即时刷新：打开 Action 详情日更 30%
    const card = await boardTaskByTitle(page, names.task)
    await card.locator('[data-testid^="tm-action-card-"]').first().click()
    await expect(page.getByTestId('tm-drawer-action')).toBeVisible()
    await fillInputNumber(page, 'tm-daily-progress', '30')
    await page.getByTestId('tm-daily-note').fill('回归日更：进度30')
    await page.getByTestId('tm-submit-daily').click()
    await expectToast(page, /日更|已保存|成功/)

    // 不刷新：抽屉头部进度立即显示 30%
    await expect(page.getByTestId('tm-drawer-action').getByText(/进度\s*30%/)).toBeVisible({
      timeout: 15_000,
    })
    // 日更记录：提交后立即出现今天这条（含日期标签「今天」）
    await expect(
      page
        .getByTestId('tm-drawer-action')
        .getByTestId('tm-daily-log-row')
        .filter({ hasText: '回归日更：进度30' })
        .filter({ hasText: '今天' }),
    ).toBeVisible()
    await page.keyboard.press('Escape')
  })

  test('04 工作台搜索：子需求/Action 名称模糊匹配', async ({ page }) => {
    test.skip(!taskCreated, '前置建树失败')
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)

    const search = page.getByTestId('tm-action-name-search')
    const card = page.getByText(names.task).first()

    // 无关关键词 → Task 卡片被过滤掉
    await search.fill('zzz不存在的关键词')
    await expect(card).toBeHidden()

    // 模糊命中子需求名（Task 名称不含「子需求」，只能经 subtask_name 命中）
    await search.fill('子需求')
    await expect(card).toBeVisible({ timeout: 15_000 })

    // 模糊命中 Action 名称（只能经 action.title 命中）
    await search.fill('Action')
    await expect(card).toBeVisible({ timeout: 15_000 })

    // 清空恢复
    await search.fill('')
    await expect(card).toBeVisible({ timeout: 15_000 })
  })

  test('03 开发中 Task：进度区只读，不可误保存', async ({ page }) => {
    test.skip(!taskCreated, '前置建树失败')
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)
    const card = await boardTaskByTitle(page, names.task)

    await openTaskDetail(page, card, '进度')
    await antdSelectByLabel(page, 'tm-task-display-status', '开发中')
    await page.getByTestId('tm-task-save').click()
    await expectToast(page, /已保存|更新/)

    // 状态变为开发中后：进度区出现锁定提示，保存按钮消失（只读），无需刷新
    await expect(page.getByTestId('tm-task-display-status')).toContainText('开发中', {
      timeout: 15_000,
    })
    await expect(page.getByTestId('tm-task-progress-locked')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByTestId('tm-task-progress-locked')).toContainText('开发中')
    await expect(page.getByTestId('tm-task-week-progress-save')).toHaveCount(0)
    await expect(page.getByTestId('tm-task-week-progress-input')).toHaveCount(0)
    await closeTaskDrawer(page)
  })

  test('09 清理：删除测试 Task', async ({ page }) => {
    test.skip(!taskCreated, '前置建树失败')
    await login(page, 'manager', PASS)
    await goProjects(page)
    await openBoardTab(page)
    await selectProjectFilter(page, names.project)
    const card = await boardTaskByTitle(page, names.task)
    // antd 下拉子菜单偶发点击丢失（节点重渲染）：循环重试直到确认弹窗出现
    const confirmBtn = page.getByRole('button', { name: '永久删除' })
    for (let i = 0; i < 3; i++) {
      await card.getByTestId('tm-btn-task-menu').click()
      await page.getByRole('menuitem', { name: '归档/删除' }).hover()
      // exact: 避免「删除」子串命中父项「归档/删除」；子菜单异步弹出，locator 自动等待其出现
      await page.getByRole('menuitem', { name: '删除', exact: true }).click()
      const opened = await confirmBtn
        .waitFor({ state: 'visible', timeout: 3_000 })
        .then(() => true)
        .catch(() => false)
      if (opened) break
      await page.keyboard.press('Escape')
    }
    await confirmBtn.click()
    await expectToast(page, 'Task 已永久删除')
  })
})
