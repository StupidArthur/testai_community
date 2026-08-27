# Test info

- Name: TM UI 补充 rmtauryl8 >> B Manager 建项目领域 Task
- Location: D:\代码\testai_community\frontend\e2e\tm-ui-extra.spec.ts:54:3

# Error details

```
Error: locator.click: Test timeout of 120000ms exceeded.
Call log:
  - waiting for getByRole('button', { name: '添加', exact: true })

    at addSubtaskViaTaskDetail (D:\代码\testai_community\frontend\e2e\helpers.ts:187:63)
    at D:\代码\testai_community\frontend\e2e\tm-ui-extra.spec.ts:80:5
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
    - text: 8.25-9.2
    - button "本 周"
    - button "历 史"
    - text: 每周三 17:00 将发送周报，请大家在 16:55 完成周 Task 的更新，Action 请于每天 19:50 前更新 1 Task 0 阻塞 0% Task 均进度
    - combobox
    - text: 全部（1）
    - combobox
    - text: 【E2E】rmtauryl8 P2
    - button "plus 新建 down":
      - img "plus"
      - text: 新建
      - img "down"
    - text: 【E2E】rmtauryl8 T2 进行中 【E2E】rmtauryl8 P2/【E2E】rmtauryl8 D2 0%
    - img "exclamation-circle"
    - button "操作 down":
      - text: 操作
      - img "down"
    - text: 待开发 需求：补测 · 负责人 LeadBrmtauryl8
    - img "No data"
    - text: 本周无 Action（Task 已完成，不可再添加）
    - list:
      - listitem: 共 1 个 Task
      - listitem "Previous Page":
        - button "left" [disabled]:
          - img "left"
      - listitem "1"
      - listitem "Next Page":
        - button "right" [disabled]:
          - img "right"
      - listitem:
        - combobox "Page Size"
        - text: 10 / page
- dialog "【E2E】rmtauryl8 T2":
  - button "Close":
    - img "close"
  - text: 【E2E】rmtauryl8 T2
  - heading "基本信息" [level=3]
  - button "edit 编辑":
    - img "edit"
    - text: 编辑
  - term: 需求进展
  - definition: 待开发 改流程请用「操作 → 进度」
  - term: 项目 / 领域
  - definition: 【E2E】rmtauryl8 P2 / 【E2E】rmtauryl8 D2
  - term: 负责人
  - definition: LeadBrmtauryl8
  - term: 测试人员
  - definition: —
  - term: 需求
  - definition: 补测
  - heading "子需求 · 0" [level=3]
  - button "plus 新增子需求":
    - img "plus"
    - text: 新增子需求
  - text: 暂无子需求
- dialog "新增子需求":
  - button "Close":
    - img "close"
  - text: 新增子需求 * 名称
  - textbox "* 名称": 【E2E】rmtauryl8 S2
  - text: 内容
  - textbox "内容": E2E 子需求内容
  - text: 9 / 5000
  - button "取 消"
  - button "添 加"
```

# Test source

```ts
   87 |   // 若有其它下拉展开：点一下当前 selector 外区域关闭（勿 Escape，会关掉 Modal）
   88 |   const openDd = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)')
   89 |   if (await openDd.count()) {
   90 |     await page.locator('.ant-modal-open .ant-modal-title, .tm-sheet__h, h3').first().click({ force: true }).catch(() => undefined)
   91 |   }
   92 |
   93 |   await root.scrollIntoViewIfNeeded()
   94 |   const selector = root.locator('.ant-select-selector')
   95 |   await selector.click({ force: true })
   96 |   const q =
   97 |     typeof optionText === 'string' ? optionText : optionText.source.replace(/^\^|\$$/g, '').replace(/\\/g, '')
   98 |   // 搜索框必须挂在当前 Select 上，避免串到上一个仍展开的下拉
   99 |   const search = root.locator('input.ant-select-selection-search-input:not([readonly])')
  100 |   const dropdown = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
  101 |   await expect(dropdown).toBeVisible()
  102 |   const option = dropdown.locator('.ant-select-item-option-content').filter({ hasText: optionText })
  103 |   if ((await search.count()) > 0) {
  104 |     await search.first().fill('')
  105 |     await search.first().type(q, { delay: 15 })
  106 |   }
  107 |   await expect(option.first()).toBeVisible({ timeout: 20_000 })
  108 |   await option.first().click()
  109 |   await expect(root).toContainText(optionText, { timeout: 8_000 })
  110 | }
  111 |
  112 | /** 多选 Select */
  113 | export async function antdMultiSelect(page: Page, testId: string, optionTexts: (string | RegExp)[]) {
  114 |   const root = page.getByTestId(testId)
  115 |   await root.click()
  116 |   for (const t of optionTexts) {
  117 |     const q = typeof t === 'string' ? t : t.source.replace(/^\^|\$$/g, '').replace(/\\/g, '')
  118 |     const search = page.locator('.ant-select-focused input.ant-select-selection-search-input:not([readonly])')
  119 |     const dropdown = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
  120 |     if ((await search.count()) > 0) {
  121 |       await search.first().fill('')
  122 |       await search.first().type(q, { delay: 15 })
  123 |       await page.keyboard.press('ArrowDown')
  124 |       await page.keyboard.press('Enter')
  125 |     } else {
  126 |       await dropdown.locator('.ant-select-item-option-content').filter({ hasText: t }).first().click()
  127 |     }
  128 |   }
  129 |   await page.getByText('新建 Task', { exact: true }).click({ force: true }).catch(() => undefined)
  130 | }
  131 |
  132 | export async function expectToast(page: Page, text: string | RegExp) {
  133 |   const notice = page.locator('.ant-message-notice, .ant-notification-notice').filter({ hasText: text })
  134 |   await expect(notice.first()).toBeVisible({ timeout: 20_000 })
  135 | }
  136 |
  137 | /** Ant Design InputNumber：testid 可能在根上或直接在 input 上 */
  138 | export async function fillInputNumber(page: Page, testId: string, value: string) {
  139 |   const root = page.getByTestId(testId)
  140 |   await expect(root).toBeVisible({ timeout: 15_000 })
  141 |   await root.scrollIntoViewIfNeeded().catch(() => undefined)
  142 |   await page.locator('.ant-drawer-open .ant-drawer-body, .ant-modal-open .ant-modal-body').last()
  143 |     .evaluate((el) => {
  144 |       el.scrollTop = el.scrollHeight
  145 |     })
  146 |     .catch(() => undefined)
  147 |   const nested = root.locator('input').first()
  148 |   const input = (await nested.count()) > 0 ? nested : root
  149 |   await input.fill(value, { force: true })
  150 |   await input.blur()
  151 | }
  152 |
  153 | export async function boardTaskByTitle(page: Page, title: string) {
  154 |   return page.locator('.tm-board-task').filter({ hasText: title }).first()
  155 | }
  156 |
  157 |
  158 | /** 打开 Task 卡片「操作 → 详情/进度」抽屉 */
  159 | export async function openTaskDetail(
  160 |   page: Page,
  161 |   card: import('@playwright/test').Locator,
  162 |   menu: '详情' | '进度' = '详情',
  163 | ) {
  164 |   await card.getByTestId('tm-btn-task-menu').click()
  165 |   await page.getByRole('menuitem', { name: menu }).click()
  166 |   await expect(page.getByTestId('tm-drawer-task')).toBeVisible()
  167 | }
  168 |
  169 | export async function closeTaskDrawer(page: Page) {
  170 |   await page.locator('.ant-drawer-open .ant-drawer-close').click()
  171 |   await expect(page.getByTestId('tm-drawer-task')).toHaveCount(0)
  172 | }
  173 |
  174 | /**
  175 |  * 在 Task 详情抽屉新增一个子需求（Action 必填 subtask_name，建 Action 前先调用）。
  176 |  */
  177 | export async function addSubtaskViaTaskDetail(
  178 |   page: Page,
  179 |   card: import('@playwright/test').Locator,
  180 |   name: string,
  181 |   content = 'E2E 子需求内容',
  182 | ) {
  183 |   await openTaskDetail(page, card)
  184 |   await page.getByTestId('tm-btn-add-subtask').click()
  185 |   await page.getByTestId('tm-subtask-name').fill(name)
  186 |   await page.getByTestId('tm-subtask-content').fill(content)
> 187 |   await page.getByRole('button', { name: '添加', exact: true }).click()
      |                                                               ^ Error: locator.click: Test timeout of 120000ms exceeded.
  188 |   await expectToast(page, '子需求已添加')
  189 |   await expect(page.getByTestId('tm-subtask-table').getByText(name)).toBeVisible({
  190 |     timeout: 15_000,
  191 |   })
  192 |   await closeTaskDrawer(page)
  193 | }
  194 |
  195 | /**
  196 |  * 将 Task 需求进展改到指定阶段（含必填日期）。
  197 |  * stageLabel 例：测试中 / 测试完成
  198 |  * dateFieldLabels 例：['测试开始时间','预计测试结束'] 或 '测试结束时间'
  199 |  */
  200 | export async function setTaskReqStage(
  201 |   page: Page,
  202 |   card: import('@playwright/test').Locator,
  203 |   stageLabel: string,
  204 |   dateFieldLabels?: string | string[],
  205 | ) {
  206 |   await openTaskDetail(page, card, '进度')
  207 |   await antdSelectByLabel(page, 'tm-task-req-stage', stageLabel)
  208 |   const labels = !dateFieldLabels
  209 |     ? []
  210 |     : Array.isArray(dateFieldLabels)
  211 |       ? dateFieldLabels
  212 |       : [dateFieldLabels]
  213 |   const fields =
  214 |     labels.length > 0
  215 |       ? labels
  216 |       : stageLabel === '测试中'
  217 |         ? ['测试开始时间', '预计测试结束']
  218 |         : stageLabel === '测试完成'
  219 |           ? ['测试结束时间']
  220 |           : []
  221 |   for (const label of fields) {
  222 |     const field = page.getByLabel(label)
  223 |     await expect(field).toBeVisible()
  224 |     await field.click()
  225 |     const panel = page.locator('.ant-picker-dropdown:not(.ant-picker-dropdown-hidden)').last()
  226 |     await panel
  227 |       .locator('.ant-picker-cell-in-view')
  228 |       .filter({ hasNot: page.locator('.ant-picker-cell-disabled') })
  229 |       .first()
  230 |       .click()
  231 |   }
  232 |   const change = page.getByLabel(/变更说明/)
  233 |   if (await change.count()) {
  234 |     await change.fill('E2E 改阶段')
  235 |   }
  236 |   await page.getByTestId('tm-task-save').click()
  237 |   await expectToast(page, /已保存|更新/)
  238 |   await closeTaskDrawer(page)
  239 | }
  240 |
  241 | export async function selectProjectFilter(page: Page, projectName: string) {
  242 |   // 工作台项目筛选：支持搜索，避免项目多时虚拟列表点不到
  243 |   const filter = page.getByTestId('tm-project-filter')
  244 |   if (await filter.count()) {
  245 |     await filter.click()
  246 |   } else {
  247 |     await page.getByPlaceholder('按项目筛选').click()
  248 |   }
  249 |   const search = page.locator('.ant-select-focused input.ant-select-selection-search-input:not([readonly])')
  250 |   const dropdown = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
  251 |   await expect(dropdown).toBeVisible({ timeout: 10_000 })
  252 |   if ((await search.count()) > 0) {
  253 |     await search.first().fill('')
  254 |     await search.first().type(projectName, { delay: 10 })
  255 |   }
  256 |   await dropdown
  257 |     .locator('.ant-select-item-option', { hasText: projectName })
  258 |     .first()
  259 |     .click()
  260 |   await expect(filter).toContainText(projectName, { timeout: 8_000 })
  261 | }
  262 |
```