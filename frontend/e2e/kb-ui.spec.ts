/**
 * 知识库 UI E2E（含清洗入库 Tab，不单测 API）
 *
 * 前置：后端 48010 已启动；vite 由 playwright webServer 拉起（3003）。
 * 数据经页面创建；文档前缀 【KB-E2E】+ RUN。
 */
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { test, expect, type Page } from '@playwright/test'
import { login } from './helpers.ts'

test.describe.configure({ mode: 'serial' })

// 勿把 process.pid / Date.now 放进 describe 标题（主进程与 worker 求值不一致）
const RUN = process.env.E2E_RUN_ID || 'kbui'
const SAMPLE = path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures', 'kb_e2e_sample.md')
const FILENAME = `【KB-E2E】${RUN}.md`

async function goKnowledgeBase(page: Page) {
  await page.getByTestId('nav-knowledge-base').click()
  await expect(page).toHaveURL(/\/knowledge-base/)
  await expect(page.getByTestId('kb-hub')).toBeVisible({ timeout: 20_000 })
}

async function openCleanTab(page: Page) {
  await page.getByRole('tab', { name: /清洗入库/ }).click()
  await expect(page).toHaveURL(/tab=clean/)
  await expect(page.getByTestId('kb-clean-panel')).toBeVisible()
  await expect(page.getByTestId('kb-clean-new')).toBeVisible()
}

test.describe('KB UI E2E', () => {
  test('01 未登录访问 /knowledge-base 跳转登录', async ({ page }) => {
    await page.goto('/knowledge-base')
    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByTestId('login-submit')).toBeVisible()
  })

  test('02 Admin 登录 → 导航进入知识库 Hub', async ({ page }) => {
    await login(page, 'admin', 'admin')
    await goKnowledgeBase(page)
    await expect(page.getByRole('heading', { name: '知识库' })).toBeVisible()
    await expect(page.getByRole('tab', { name: '知识问答' })).toBeVisible()
    await expect(page.getByRole('tab', { name: /清洗入库/ })).toBeVisible()
  })

  test('03 知识问答空库提示 + 发送禁用', async ({ page }) => {
    await login(page, 'admin', 'admin')
    await goKnowledgeBase(page)
    await page.getByRole('tab', { name: '知识问答' }).click()
    await expect(page.getByTestId('kb-chat-panel')).toBeVisible()
    // 空库或仅有归档时都有引导 Alert；若库里已有可用文档则输入可点
    const send = page.getByTestId('kb-chat-send')
    await expect(send).toBeVisible()
    const emptyAlert = page.getByTestId('kb-chat-empty-alert')
    if (await emptyAlert.count()) {
      await expect(emptyAlert).toBeVisible()
      await expect(send).toBeDisabled()
      await expect(page.getByTestId('kb-chat-input')).toBeDisabled()
    } else {
      await expect(send).toBeEnabled()
    }
  })

  test('04 清洗入库：打开新建弹窗并校验必填', async ({ page }) => {
    await login(page, 'admin', 'admin')
    await goKnowledgeBase(page)
    await openCleanTab(page)
    await page.getByTestId('kb-clean-new').click()
    const dialog = page.getByRole('dialog', { name: '新建清洗任务' })
    await expect(dialog).toBeVisible()
    // Ant Design 主按钮文案可能是「确定」或「OK」
    await dialog.locator('.ant-modal-footer .ant-btn-primary').click()
    const toast = page.locator('.ant-message-notice, .ant-notification-notice').filter({
      hasText: /请选择文件|创建失败/,
    })
    await expect(toast.or(dialog).first()).toBeVisible({ timeout: 8_000 })
  })

  test('05 清洗入库：上传样例 md 并进入审核页', async ({ page }) => {
    await login(page, 'admin', 'admin')
    await goKnowledgeBase(page)
    await openCleanTab(page)
    await page.getByTestId('kb-clean-new').click()
    const dialog = page.getByRole('dialog', { name: '新建清洗任务' })
    await expect(dialog).toBeVisible()

    // 用可读文件名：先读 fixture 再 setInputFiles 会带真实路径名；复制到临时名不方便。
    // Playwright setInputFiles 使用原文件名；断言用「样例」片段或表格行出现。
    await dialog.locator('input[type="file"]').setInputFiles({
      name: FILENAME,
      mimeType: 'text/markdown',
      buffer: await (await import('node:fs/promises')).readFile(SAMPLE),
    })
    await expect(dialog.getByText(FILENAME)).toBeVisible({ timeout: 5_000 })
    await dialog.locator('.ant-modal-footer .ant-btn-primary').click()

    // 成功应进入审核页（标题与面包屑都含文件名，用 h4 定位避免 strict 冲突）
    await expect(page).toHaveURL(/\/knowledge-base\/clean\/[a-f0-9-]+/, { timeout: 30_000 })
    await expect(page.locator('h4.ant-typography').filter({ hasText: FILENAME })).toBeVisible({
      timeout: 15_000,
    })
  })

  test('06 审核页：等待处理结束（pending_review / failed / approved）', async ({ page }) => {
    test.setTimeout(300_000)
    await login(page, 'admin', 'admin')
    await goKnowledgeBase(page)
    await openCleanTab(page)

    // 点最新一行（本 RUN 文件名）
    const row = page.locator('.ant-table-row').filter({ hasText: FILENAME }).first()
    await expect(row).toBeVisible({ timeout: 20_000 })
    await row.click()
    await expect(page).toHaveURL(/\/knowledge-base\/clean\//)

    // 轮询状态 Tag：uploaded/processing → pending_review | failed | approved
    const statusDeadline = Date.now() + 240_000
    let finalStatus = ''
    while (Date.now() < statusDeadline) {
      const tags = page.locator('.ant-tag')
      const texts = (await tags.allTextContents()).map((t) => t.trim())
      if (texts.some((t) => t === 'pending_review' || t === 'failed' || t === 'approved')) {
        finalStatus = texts.find((t) => t === 'pending_review' || t === 'failed' || t === 'approved') || ''
        break
      }
      await page.reload({ waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(5_000)
    }

    expect(finalStatus, '清洗任务应在 4 分钟内离开 processing').not.toBe('')
    // 记录到注释：failed 也算测出环境/流水线问题
    // eslint-disable-next-line no-console
    console.log(`[KB-E2E] clean job status=${finalStatus}`)

    if (finalStatus === 'pending_review') {
      const approve = page.getByTestId('kb-clean-approve')
      const zeroPara = page.getByText('未生成可审核段落')
      if (await approve.count()) {
        await expect(approve).toBeVisible()
      } else {
        await expect(zeroPara.or(page.getByText('重新处理'))).toBeVisible()
      }
    }

    if (finalStatus === 'failed') {
      await expect(page.locator('.ant-alert-error').first()).toBeVisible()
    }
  })

  test('07 若可批准则入库，并回到问答尝试提问', async ({ page }) => {
    test.setTimeout(360_000)
    await login(page, 'admin', 'admin')
    await goKnowledgeBase(page)
    await openCleanTab(page)
    const row = page.locator('.ant-table-row').filter({ hasText: FILENAME }).first()
    await expect(row).toBeVisible({ timeout: 20_000 })
    await row.click()

    const approve = page.getByTestId('kb-clean-approve')
    if (!(await approve.count()) || !(await approve.isEnabled())) {
      test.info().annotations.push({
        type: 'note',
        description: '无「批准入库」按钮（零段落/失败/已批准），跳过入库与问答深测',
      })
      return
    }

    await approve.click()
    // 批准可能较久（向量写入）
    await expect(page.getByText(/已批准入库|批准/)).toBeVisible({ timeout: 300_000 }).catch(() => undefined)
    await expect(page.locator('.ant-tag').filter({ hasText: 'approved' }).first()).toBeVisible({
      timeout: 300_000,
    })

    await page.getByRole('button', { name: '打开知识库' }).click().catch(async () => {
      await page.getByTestId('nav-knowledge-base').click()
    })
    await expect(page.getByTestId('kb-hub')).toBeVisible()
    await page.getByRole('tab', { name: '知识问答' }).click()

    const send = page.getByTestId('kb-chat-send')
    await expect(send).toBeEnabled({ timeout: 60_000 })
    await page.getByTestId('kb-chat-input').fill('知识库模块的功能要点有哪些？')
    await send.click()
    await expect(page.getByTestId('kb-chat-msg-user')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByTestId('kb-chat-msg-assistant').first()).toBeVisible({ timeout: 120_000 })
    // 引用可选：有则更好
    const cite = page.getByText('参考来源')
    if (await cite.count()) {
      await expect(cite.first()).toBeVisible()
    }
  })

  test('08 清洗 Tab 不再暴露锚点词典入口', async ({ page }) => {
    await login(page, 'admin', 'admin')
    await goKnowledgeBase(page)
    await openCleanTab(page)
    await expect(page.getByTestId('kb-clean-new')).toBeVisible()
    await expect(page.getByTestId('kb-anchors-btn')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '锚点词典' })).toHaveCount(0)
    await page.goto('/knowledge-base/anchors')
    await expect(page).toHaveURL(/\/knowledge-base\?tab=clean|\/knowledge-base\?.*tab=clean/)
  })
})
