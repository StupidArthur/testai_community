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
  await expect(page.getByTestId('tm-scope-all')).toBeVisible()
}

export async function openScreenTab(page: Page) {
  await page.getByRole('tab', { name: /大屏/ }).click()
  await expect(page.getByTestId('tm-screen')).toBeVisible()
}

export async function openMineTab(page: Page) {
  await page.getByRole('tab', { name: '我的 Action' }).click()
}

/** Ant Design Select：点开 →（可搜时）过滤 → Enter 选中首项（比点击更稳） */
export async function antdSelectByLabel(page: Page, testId: string, optionText: string | RegExp) {
  const root = page.getByTestId(testId)
  await expect(root).toBeVisible({ timeout: 15_000 })
  await root.scrollIntoViewIfNeeded()
  const selector = root.locator('.ant-select-selector')
  await selector.scrollIntoViewIfNeeded()
  await selector.click({ force: true })
  const q =
    typeof optionText === 'string' ? optionText : optionText.source.replace(/^\^|\$$/g, '').replace(/\\/g, '')
  const search = page.locator('.ant-select-focused input.ant-select-selection-search-input:not([readonly])')
  const dropdown = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
  await expect(dropdown).toBeVisible()
  if ((await search.count()) > 0) {
    await search.first().fill('')
    await search.first().type(q, { delay: 15 })
    await page.keyboard.press('ArrowDown')
    await page.keyboard.press('Enter')
  } else {
    const content = dropdown.locator('.ant-select-item-option-content').filter({ hasText: optionText })
    await expect(content.first()).toBeVisible({ timeout: 20_000 })
    await content.first().click()
  }
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

/** Ant Design InputNumber：testid 在组件根上，填内部 input */
export async function fillInputNumber(page: Page, testId: string, value: string) {
  const root = page.getByTestId(testId)
  await expect(root).toBeVisible({ timeout: 15_000 })
  const input = root.locator('input').first()
  await input.click({ force: true })
  await input.fill(value)
  await input.blur()
}

export async function boardTaskByTitle(page: Page, title: string) {
  return page.locator('.tm-board-task').filter({ hasText: title }).first()
}

export async function selectProjectFilter(page: Page, projectName: string) {
  // 工作台项目筛选：antd Select 可能把 testid 打在外层
  const filter = page.getByTestId('tm-project-filter')
  if (await filter.count()) {
    await filter.click()
  } else {
    await page.getByPlaceholder('按项目筛选').click()
  }
  await page
    .locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option', {
      hasText: projectName,
    })
    .first()
    .click()
}
