# Test info

- Name: TM req-stage rmtb3i7nn >> 01 建项目/领域/Task，默认待开发无 +Action
- Location: D:\代码\testai_community\frontend\e2e\tm-req-stage.spec.ts:29:3

# Error details

```
Error: Timed out 20000ms waiting for expect(locator).toBeVisible()

Locator: locator('.ant-message-notice, .ant-notification-notice').filter({ hasText: /项目已创建/ }).first()
Expected: visible
Received: <element(s) not found>
Call log:
  - expect.toBeVisible with timeout 20000ms
  - waiting for locator('.ant-message-notice, .ant-notification-notice').filter({ hasText: /项目已创建/ }).first()

    at expectToast (D:\代码\testai_community\frontend\e2e\helpers.ts:167:32)
    at D:\代码\testai_community\frontend\e2e\tm-req-stage.spec.ts:37:11
```

# Page snapshot

```yaml
- banner:
  - img "thunderbolt"
  - strong: TestAI Community
  - button "project 项目管理":
    - img "project"
    - text: 项目管理
  - button "appstore Skill 管理":
    - img "appstore"
    - text: Skill 管理
  - button "tool 工具集":
    - img "tool"
    - text: 工具集
  - button "book 知识库":
    - img "book"
    - text: 知识库
  - button "history 更新日志":
    - img "history"
    - text: 更新日志
  - button "moon":
    - img "moon"
  - button "user manager":
    - img "user"
    - text: manager
- main:
  - heading "项目管理" [level=3]
  - button "question-circle 使用说明":
    - img "question-circle"
    - text: 使用说明
  - tablist:
    - tab "今日大屏"
    - tab "工作台" [selected]
    - tab "我的 Action"
  - tabpanel "工作台":
    - strong: 本周
    - button "本 周"
    - button "历 史"
    - text: 0 Task 0 阻塞 0% Task 均进度
    - combobox
    - text: 我的 Task（0）
    - combobox
    - text: 按项目筛选
    - button "plus 新建 down":
      - img "plus"
      - text: 新建
      - img "down"
    - img "No data"
    - text: 暂无你负责的 Task。可切到「其他 / 全部」，或新建 Task。
- dialog "新建项目":
  - button "Close":
    - img "close"
  - text: 新建项目 * 名称
  - textbox "* 名称": 【E2E阶段】P-rmtb3i7nn
  - button "创 建"
```

# Test source

```ts
   67 |   await dropdown.locator('.ant-select-item-option-content').filter({ hasText: re }).first().click()
   68 | }
   69 |
   70 | /** 新建菜单：项目 / 领域 / Task */
   71 | export async function openCreateMenu(page: Page, item: '项目' | '领域' | 'Task') {
   72 |   await page.getByTestId('tm-btn-create-menu').click()
   73 |   await page.getByRole('menuitem', { name: item, exact: true }).click()
   74 | }
   75 |
   76 | /** Ant Design Select：点开 →（可搜时）过滤 → 等选项出现再选中（带重试，防下拉竞态） */
   77 | export async function antdSelectByLabel(page: Page, testId: string, optionText: string | RegExp) {
   78 |   const root = page.getByTestId(testId)
   79 |   await expect(root).toBeVisible({ timeout: 15_000 })
   80 |   // 已选中则跳过，避免重复点开串到其它 Select
   81 |   const already =
   82 |     typeof optionText === 'string'
   83 |       ? (await root.textContent())?.includes(optionText)
   84 |       : optionText.test((await root.textContent()) || '')
   85 |   if (already) return
   86 |
   87 |   const q =
   88 |     typeof optionText === 'string' ? optionText : optionText.source.replace(/^\^|\$$/g, '').replace(/\\/g, '')
   89 |
   90 |   for (let attempt = 0; attempt < 3; attempt++) {
   91 |     // 若有其它下拉展开：点一下标题区关闭（勿 Escape，会关掉 Modal）
   92 |     const openDd = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)')
   93 |     if (await openDd.count()) {
   94 |       await page
   95 |         .locator('.ant-modal-open .ant-modal-title, .tm-sheet__h, h3')
   96 |         .first()
   97 |         .click({ force: true })
   98 |         .catch(() => undefined)
   99 |     }
  100 |
  101 |     await root.scrollIntoViewIfNeeded()
  102 |     await root.locator('.ant-select-selector').click({ force: true })
  103 |
  104 |     // 优先用 antd 的 id 关联精确定位本 Select 的下拉（{id}_list 挂在下拉内层），避免串到其它下拉
  105 |     const inputId = await root
  106 |       .locator('input.ant-select-selection-search-input')
  107 |       .first()
  108 |       .getAttribute('id')
  109 |     let dropdown = inputId
  110 |       ? page.locator(
  111 |           `.ant-select-dropdown:not(.ant-select-dropdown-hidden):has(#${inputId}_list)`,
  112 |         )
  113 |       : page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
  114 |     try {
  115 |       await expect(dropdown.first()).toBeVisible({ timeout: 4_000 })
  116 |     } catch {
  117 |       // 精确定位失败（antd 版本差异）：退回最后一个可见下拉
  118 |       dropdown = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
  119 |       try {
  120 |         await expect(dropdown).toBeVisible({ timeout: 3_000 })
  121 |       } catch {
  122 |         continue
  123 |       }
  124 |     }
  125 |     const dropdownRoot = dropdown.first()
  126 |
  127 |     const option = dropdownRoot.locator('.ant-select-item-option-content').filter({ hasText: optionText })
  128 |     const search = root.locator('input.ant-select-selection-search-input:not([readonly])')
  129 |     if ((await search.count()) > 0) {
  130 |       await search.first().fill('')
  131 |       await search.first().type(q, { delay: 15 })
  132 |     }
  133 |     try {
  134 |       await expect(option.first()).toBeVisible({ timeout: 6_000 })
  135 |     } catch {
  136 |       continue
  137 |     }
  138 |     await option.first().click()
  139 |     await expect(root).toContainText(optionText, { timeout: 8_000 })
  140 |     return
  141 |   }
  142 |   throw new Error(`antdSelectByLabel: 3 次尝试后仍未选中 "${q}"（${testId}）`)
  143 | }
  144 |
  145 | /** 多选 Select */
  146 | export async function antdMultiSelect(page: Page, testId: string, optionTexts: (string | RegExp)[]) {
  147 |   const root = page.getByTestId(testId)
  148 |   await root.click()
  149 |   for (const t of optionTexts) {
  150 |     const q = typeof t === 'string' ? t : t.source.replace(/^\^|\$$/g, '').replace(/\\/g, '')
  151 |     const search = page.locator('.ant-select-focused input.ant-select-selection-search-input:not([readonly])')
  152 |     const dropdown = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
  153 |     if ((await search.count()) > 0) {
  154 |       await search.first().fill('')
  155 |       await search.first().type(q, { delay: 15 })
  156 |       await page.keyboard.press('ArrowDown')
  157 |       await page.keyboard.press('Enter')
  158 |     } else {
  159 |       await dropdown.locator('.ant-select-item-option-content').filter({ hasText: t }).first().click()
  160 |     }
  161 |   }
  162 |   await page.getByText('新建 Task', { exact: true }).click({ force: true }).catch(() => undefined)
  163 | }
  164 |
  165 | export async function expectToast(page: Page, text: string | RegExp) {
  166 |   const notice = page.locator('.ant-message-notice, .ant-notification-notice').filter({ hasText: text })
> 167 |   await expect(notice.first()).toBeVisible({ timeout: 20_000 })
      |                                ^ Error: Timed out 20000ms waiting for expect(locator).toBeVisible()
  168 | }
  169 |
  170 | /** Ant Design InputNumber：testid 可能在根上或直接在 input 上 */
  171 | export async function fillInputNumber(page: Page, testId: string, value: string) {
  172 |   const root = page.getByTestId(testId)
  173 |   await expect(root).toBeVisible({ timeout: 15_000 })
  174 |   await root.scrollIntoViewIfNeeded().catch(() => undefined)
  175 |   await page.locator('.ant-drawer-open .ant-drawer-body, .ant-modal-open .ant-modal-body').last()
  176 |     .evaluate((el) => {
  177 |       el.scrollTop = el.scrollHeight
  178 |     })
  179 |     .catch(() => undefined)
  180 |   const nested = root.locator('input').first()
  181 |   const input = (await nested.count()) > 0 ? nested : root
  182 |   await input.fill(value, { force: true })
  183 |   await input.blur()
  184 | }
  185 |
  186 | export async function boardTaskByTitle(page: Page, title: string) {
  187 |   return page.locator('.tm-board-task').filter({ hasText: title }).first()
  188 | }
  189 |
  190 |
  191 | /** 打开 Task 卡片「操作 → 详情/进度」抽屉 */
  192 | export async function openTaskDetail(
  193 |   page: Page,
  194 |   card: import('@playwright/test').Locator,
  195 |   menu: '详情' | '进度' = '详情',
  196 | ) {
  197 |   await card.getByTestId('tm-btn-task-menu').click()
  198 |   await page.getByRole('menuitem', { name: menu }).click()
  199 |   await expect(page.getByTestId('tm-drawer-task')).toBeVisible()
  200 | }
  201 |
  202 | export async function closeTaskDrawer(page: Page) {
  203 |   await page.locator('.ant-drawer-open .ant-drawer-close').click()
  204 |   await expect(page.getByTestId('tm-drawer-task')).toHaveCount(0)
  205 | }
  206 |
  207 | /**
  208 |  * 在 Task 详情抽屉新增一个子需求（Action 必填 subtask_name，建 Action 前先调用）。
  209 |  */
  210 | export async function addSubtaskViaTaskDetail(
  211 |   page: Page,
  212 |   card: import('@playwright/test').Locator,
  213 |   name: string,
  214 |   content = 'E2E 子需求内容',
  215 | ) {
  216 |   await openTaskDetail(page, card)
  217 |   await page.getByTestId('tm-btn-add-subtask').click()
  218 |   await page.getByTestId('tm-subtask-name').fill(name)
  219 |   await page.getByTestId('tm-subtask-content').fill(content)
  220 |   // antd 两字中文按钮会在字符间自动插空格（可访问名为「添 加」），用正则兼容
  221 |   await page.getByRole('button', { name: /^添\s*加$/ }).click()
  222 |   await expectToast(page, '子需求已添加')
  223 |   await expect(page.getByTestId('tm-subtask-table').getByText(name)).toBeVisible({
  224 |     timeout: 15_000,
  225 |   })
  226 |   await closeTaskDrawer(page)
  227 | }
  228 |
  229 | /**
  230 |  * 将 Task 需求进展改到指定阶段（含必填日期）。
  231 |  * stageLabel 例：测试中 / 测试完成
  232 |  * dateFieldLabels 例：['测试开始时间','预计测试结束'] 或 '测试结束时间'
  233 |  */
  234 | export async function setTaskReqStage(
  235 |   page: Page,
  236 |   card: import('@playwright/test').Locator,
  237 |   stageLabel: string,
  238 |   dateFieldLabels?: string | string[],
  239 | ) {
  240 |   await openTaskDetail(page, card, '进度')
  241 |   await antdSelectByLabel(page, 'tm-task-req-stage', stageLabel)
  242 |   const labels = !dateFieldLabels
  243 |     ? []
  244 |     : Array.isArray(dateFieldLabels)
  245 |       ? dateFieldLabels
  246 |       : [dateFieldLabels]
  247 |   const fields =
  248 |     labels.length > 0
  249 |       ? labels
  250 |       : stageLabel === '测试中'
  251 |         ? ['测试开始时间', '预计测试结束']
  252 |         : stageLabel === '测试完成'
  253 |           ? ['测试结束时间']
  254 |           : []
  255 |   for (const label of fields) {
  256 |     const field = page.getByLabel(label)
  257 |     await expect(field).toBeVisible()
  258 |     await field.click()
  259 |     const panel = page.locator('.ant-picker-dropdown:not(.ant-picker-dropdown-hidden)').last()
  260 |     await panel
  261 |       .locator('.ant-picker-cell-in-view')
  262 |       .filter({ hasNot: page.locator('.ant-picker-cell-disabled') })
  263 |       .first()
  264 |       .click()
  265 |   }
  266 |   const change = page.getByLabel(/变更说明/)
  267 |   if (await change.count()) {
```