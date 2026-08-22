/**
 * E2E 公共操作：登录/注销、Ant Design Select、进入项目管理。
 * 不调用业务 API 灌数。
 */
import { expect, type Page } from '@playwright/test'

export const PASS = '123456'

export async function login(page: Page, username: string, password = PASS) {
  await page.goto('/login')
  await page.getByTestId('login-username').fill(username)
  await page.getByTestId('login-password').fill(password)
  await page.getByTestId('login-submit').click()
  await expect(page).toHaveURL(/\/($|\?)/, { timeout: 20_000 })
  // Portal 首页
  await expect(page.getByText('TestAI Community').first()).toBeVisible()
}

export async function logout(page: Page) {
  // 用户菜单：右上角用户名/头像
  const trigger = page.locator('.ant-layout-header').getByRole('button').last()
  if (await trigger.count()) {
    await trigger.click()
  } else {
    await page.locator('.ant-dropdown-trigger').last().click()
  }
  const logoutItem = page.getByTestId('logout')
  if (await logoutItem.count()) {
    await logoutItem.click()
  } else {
    await page.getByText('注销').click()
  }
  await expect(page).toHaveURL(/\/login/)
}

export async function goProjects(page: Page) {
  await page.getByTestId('nav-projects').click()
  await expect(page).toHaveURL(/\/projects/)
  await expect(page.getByRole('heading', { name: '项目管理' })).toBeVisible()
}

export async function openBoardTab(page: Page) {
  await page.getByRole('tab', { name: '工作台' }).click()
  await expect(page.getByTestId('tm-scope-select')).toBeVisible()
}

export async function openScreenTab(page: Page) {
  await page.getByRole('tab', { name: /大屏/ }).click()
  await expect(page.getByTestId('tm-screen')).toBeVisible()
}

export async function openMineTab(page: Page) {
  await page.getByRole('tab', { name: '我的 Action' }).click()
}

/** 工作台 scope：我的 / 其他 / 全部 */
export async function selectBoardScope(page: Page, label: '我的' | '其他' | '全部') {
  const root = page.getByTestId('tm-scope-select')
  await root.click()
  const dropdown = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
  const re =
    label === '全部'
      ? /^全部/
      : label === '我的'
        ? /^我的 Task/
        : /^其他 Task/
  await dropdown.locator('.ant-select-item-option-content').filter({ hasText: re }).first().click()
}

/** 新建菜单：项目 / 领域 / Task */
export async function openCreateMenu(page: Page, item: '项目' | '领域' | 'Task') {
  await page.getByTestId('tm-btn-create-menu').click()
  await page.getByRole('menuitem', { name: item, exact: true }).click()
}

/** Ant Design Select：点开 →（可搜时）过滤 → 等选项出现再选中 */
export async function antdSelectByLabel(page: Page, testId: string, optionText: string | RegExp) {
  const root = page.getByTestId(testId)
  await expect(root).toBeVisible({ timeout: 15_000 })
  // 已选中则跳过，避免重复点开串到其它 Select
  const already =
    typeof optionText === 'string'
      ? (await root.textContent())?.includes(optionText)
      : optionText.test((await root.textContent()) || '')
  if (already) return

  // 若有其它下拉展开：点一下当前 selector 外区域关闭（勿 Escape，会关掉 Modal）
  const openDd = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)')
  if (await openDd.count()) {
    await page.locator('.ant-modal-open .ant-modal-title, .tm-sheet__h, h3').first().click({ force: true }).catch(() => undefined)
  }

  await root.scrollIntoViewIfNeeded()
  const selector = root.locator('.ant-select-selector')
  await selector.click({ force: true })
  const q =
    typeof optionText === 'string' ? optionText : optionText.source.replace(/^\^|\$$/g, '').replace(/\\/g, '')
  // 搜索框必须挂在当前 Select 上，避免串到上一个仍展开的下拉
  const search = root.locator('input.ant-select-selection-search-input:not([readonly])')
  const dropdown = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
  await expect(dropdown).toBeVisible()
  const option = dropdown.locator('.ant-select-item-option-content').filter({ hasText: optionText })
  if ((await search.count()) > 0) {
    await search.first().fill('')
    await search.first().type(q, { delay: 15 })
  }
  await expect(option.first()).toBeVisible({ timeout: 20_000 })
  await option.first().click()
  await expect(root).toContainText(optionText, { timeout: 8_000 })
}

/** 多选 Select */
export async function antdMultiSelect(page: Page, testId: string, optionTexts: (string | RegExp)[]) {
  const root = page.getByTestId(testId)
  await root.click()
  for (const t of optionTexts) {
    const q = typeof t === 'string' ? t : t.source.replace(/^\^|\$$/g, '').replace(/\\/g, '')
    const search = page.locator('.ant-select-focused input.ant-select-selection-search-input:not([readonly])')
    const dropdown = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
    if ((await search.count()) > 0) {
      await search.first().fill('')
      await search.first().type(q, { delay: 15 })
      await page.keyboard.press('ArrowDown')
      await page.keyboard.press('Enter')
    } else {
      await dropdown.locator('.ant-select-item-option-content').filter({ hasText: t }).first().click()
    }
  }
  await page.getByText('新建 Task', { exact: true }).click({ force: true }).catch(() => undefined)
}

export async function expectToast(page: Page, text: string | RegExp) {
  const notice = page.locator('.ant-message-notice, .ant-notification-notice').filter({ hasText: text })
  await expect(notice.first()).toBeVisible({ timeout: 20_000 })
}

/** Ant Design InputNumber：testid 可能在根上或直接在 input 上 */
export async function fillInputNumber(page: Page, testId: string, value: string) {
  const root = page.getByTestId(testId)
  await expect(root).toBeVisible({ timeout: 15_000 })
  await root.scrollIntoViewIfNeeded().catch(() => undefined)
  await page.locator('.ant-drawer-open .ant-drawer-body, .ant-modal-open .ant-modal-body').last()
    .evaluate((el) => {
      el.scrollTop = el.scrollHeight
    })
    .catch(() => undefined)
  const nested = root.locator('input').first()
  const input = (await nested.count()) > 0 ? nested : root
  await input.fill(value, { force: true })
  await input.blur()
}

export async function boardTaskByTitle(page: Page, title: string) {
  return page.locator('.tm-board-task').filter({ hasText: title }).first()
}


/** 打开 Task 卡片「操作 → 详情/进度」抽屉 */
export async function openTaskDetail(
  page: Page,
  card: import('@playwright/test').Locator,
  menu: '详情' | '进度' = '详情',
) {
  await card.getByTestId('tm-btn-task-menu').click()
  await page.getByRole('menuitem', { name: menu }).click()
  await expect(page.getByTestId('tm-drawer-task')).toBeVisible()
}

export async function closeTaskDrawer(page: Page) {
  await page.locator('.ant-drawer-open .ant-drawer-close').click()
  await expect(page.getByTestId('tm-drawer-task')).toHaveCount(0)
}

/**
 * 将 Task 需求进展改到指定阶段（含必填日期）。
 * stageLabel 例：测试中 / 测试完成
 * dateFieldLabels 例：['测试开始时间','预计测试结束'] 或 '测试结束时间'
 */
export async function setTaskReqStage(
  page: Page,
  card: import('@playwright/test').Locator,
  stageLabel: string,
  dateFieldLabels?: string | string[],
) {
  await openTaskDetail(page, card, '进度')
  await antdSelectByLabel(page, 'tm-task-req-stage', stageLabel)
  const labels = !dateFieldLabels
    ? []
    : Array.isArray(dateFieldLabels)
      ? dateFieldLabels
      : [dateFieldLabels]
  const fields =
    labels.length > 0
      ? labels
      : stageLabel === '测试中'
        ? ['测试开始时间', '预计测试结束']
        : stageLabel === '测试完成'
          ? ['测试结束时间']
          : []
  for (const label of fields) {
    const field = page.getByLabel(label)
    await expect(field).toBeVisible()
    await field.click()
    const panel = page.locator('.ant-picker-dropdown:not(.ant-picker-dropdown-hidden)').last()
    await panel
      .locator('.ant-picker-cell-in-view')
      .filter({ hasNot: page.locator('.ant-picker-cell-disabled') })
      .first()
      .click()
  }
  const change = page.getByLabel(/变更说明/)
  if (await change.count()) {
    await change.fill('E2E 改阶段')
  }
  await page.getByTestId('tm-task-save').click()
  await expectToast(page, /已保存|更新/)
  await closeTaskDrawer(page)
}

export async function selectProjectFilter(page: Page, projectName: string) {
  // 工作台项目筛选：支持搜索，避免项目多时虚拟列表点不到
  const filter = page.getByTestId('tm-project-filter')
  if (await filter.count()) {
    await filter.click()
  } else {
    await page.getByPlaceholder('按项目筛选').click()
  }
  const search = page.locator('.ant-select-focused input.ant-select-selection-search-input:not([readonly])')
  const dropdown = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
  await expect(dropdown).toBeVisible({ timeout: 10_000 })
  if ((await search.count()) > 0) {
    await search.first().fill('')
    await search.first().type(projectName, { delay: 10 })
  }
  await dropdown
    .locator('.ant-select-item-option', { hasText: projectName })
    .first()
    .click()
  await expect(filter).toContainText(projectName, { timeout: 8_000 })
}
