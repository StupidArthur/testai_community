# Test info

- Name: TM UI E2E rmtauw2id >> 10 Manager：再建一条直接「保存并发布」给 Owner
- Location: D:\代码\testai_community\frontend\e2e\tm-ui-full.spec.ts:217:3

# Error details

```
Error: Timed out 20000ms waiting for expect(locator).toBeVisible()

Locator: locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last().locator('.ant-select-item-option-content').filter({ hasText: '【E2E】rmtauw2id 子需求' }).first()
Expected: visible
Received: <element(s) not found>
Call log:
  - expect.toBeVisible with timeout 20000ms
  - waiting for locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last().locator('.ant-select-item-option-content').filter({ hasText: '【E2E】rmtauw2id 子需求' }).first()

    at antdSelectByLabel (D:\代码\testai_community\frontend\e2e\helpers.ts:107:32)
    at D:\代码\testai_community\frontend\e2e\tm-ui-full.spec.ts:226:5
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
    - text: 每周三 17:00 将发送周报，请大家在 16:55 完成周 Task 的更新，Action 请于每天 19:50 前更新 3 Task 0 阻塞 0% Task 均进度
    - combobox
    - text: 全部（3）
    - combobox
    - text: 【E2E】rmtauw2id 项目
    - button "plus 新建 down":
      - img "plus"
      - text: 新建
      - img "down"
    - text: 【E2E】rmtauw2id TaskDone 进行中 【E2E】rmtauw2id 项目/【E2E】rmtauw2id 领域 0%
    - img "exclamation-circle"
    - button "操作 down":
      - text: 操作
      - img "down"
    - text: 待开发 需求：x · 负责人 测试管理员
    - img "No data"
    - text: 本周无 Action（Task 已完成，不可再添加） 【E2E】rmtauw2id Task主 进行中 【E2E】rmtauw2id 项目/【E2E】rmtauw2id 领域 0%
    - img "exclamation-circle"
    - button "操作 down":
      - text: 操作
      - img "down"
    - button "+ Action"
    - text: 测试中 测试开始 08-01 ~ 预计结束 08-01 · 需求：Manager 更新后的需求 · 负责人 测试管理员
    - table:
      - rowgroup:
        - row "子需求 Action 负责人 进度 状态 风险 操作":
          - columnheader "子需求"
          - columnheader "Action"
          - columnheader "负责人"
          - columnheader "进度"
          - columnheader "状态"
          - columnheader "风险"
          - columnheader "操作"
      - rowgroup:
        - row "【E2E】rmtauw2id 子需求 【E2E】rmtauw2id 草稿Action 测试管理员 0 进行中 —":
          - cell "【E2E】rmtauw2id 子需求"
          - cell "【E2E】rmtauw2id 草稿Action"
          - cell "测试管理员"
          - cell "0":
            - progressbar: 0%
          - cell "进行中"
          - cell "—"
          - cell
    - text: 【E2E】rmtauw2id Task空 进行中 【E2E】rmtauw2id 项目/【E2E】rmtauw2id 领域 0%
    - img "exclamation-circle"
    - button "操作 down":
      - text: 操作
      - img "down"
    - text: 待开发 需求：x · 负责人 测试管理员
    - img "No data"
    - text: 本周无 Action（Task 已完成，不可再添加）
    - list:
      - listitem: 共 3 个 Task
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
- dialog "新建 Action · 【E2E】rmtauw2id Task主":
  - button "Close":
    - img "close"
  - text: 新建 Action · 【E2E】rmtauw2id Task主 * 关联子需求
  - combobox "* 关联子需求"
  - text: 选择子需求 * 标题
  - textbox "* 标题"
  - text: 0 / 300 * 本周负责人
  - combobox "* 本周负责人"
  - text: 测试管理员（manager） 测试内容
  - textbox "测试内容"
  - text: 0 / 1000 环境
  - textbox "环境"
  - text: 0 / 300
  - button "仅存草稿"
  - button "保存并发布"
```

# Test source

```ts
   7 | export const PASS = '123456'
   8 |
   9 | export async function login(page: Page, username: string, password = PASS) {
   10 |   await page.goto('/login')
   11 |   await page.getByTestId('login-username').fill(username)
   12 |   await page.getByTestId('login-password').fill(password)
   13 |   await page.getByTestId('login-submit').click()
   14 |   await expect(page).toHaveURL(/\/($|\?)/, { timeout: 20_000 })
   15 |   // Portal 首页
   16 |   await expect(page.getByText('TestAI Community').first()).toBeVisible()
   17 | }
   18 |
   19 | export async function logout(page: Page) {
   20 |   // 用户菜单：右上角用户名/头像
   21 |   const trigger = page.locator('.ant-layout-header').getByRole('button').last()
   22 |   if (await trigger.count()) {
   23 |     await trigger.click()
   24 |   } else {
   25 |     await page.locator('.ant-dropdown-trigger').last().click()
   26 |   }
   27 |   const logoutItem = page.getByTestId('logout')
   28 |   if (await logoutItem.count()) {
   29 |     await logoutItem.click()
   30 |   } else {
   31 |     await page.getByText('注销').click()
   32 |   }
   33 |   await expect(page).toHaveURL(/\/login/)
   34 | }
   35 |
   36 | export async function goProjects(page: Page) {
   37 |   await page.getByTestId('nav-projects').click()
   38 |   await expect(page).toHaveURL(/\/projects/)
   39 |   await expect(page.getByRole('heading', { name: '项目管理' })).toBeVisible()
   40 | }
   41 |
   42 | export async function openBoardTab(page: Page) {
   43 |   await page.getByRole('tab', { name: '工作台' }).click()
   44 |   await expect(page.getByTestId('tm-scope-select')).toBeVisible()
   45 | }
   46 |
   47 | export async function openScreenTab(page: Page) {
   48 |   await page.getByRole('tab', { name: /大屏/ }).click()
   49 |   await expect(page.getByTestId('tm-screen')).toBeVisible()
   50 | }
   51 |
   52 | export async function openMineTab(page: Page) {
   53 |   await page.getByRole('tab', { name: '我的 Action' }).click()
   54 | }
   55 |
   56 | /** 工作台 scope：我的 / 其他 / 全部 */
   57 | export async function selectBoardScope(page: Page, label: '我的' | '其他' | '全部') {
   58 |   const root = page.getByTestId('tm-scope-select')
   59 |   await root.click()
   60 |   const dropdown = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
   61 |   const re =
   62 |     label === '全部'
   63 |       ? /^全部/
   64 |       : label === '我的'
   65 |         ? /^我的 Task/
   66 |         : /^其他 Task/
   67 |   await dropdown.locator('.ant-select-item-option-content').filter({ hasText: re }).first().click()
   68 | }
   69 |
   70 | /** 新建菜单：项目 / 领域 / Task */
   71 | export async function openCreateMenu(page: Page, item: '项目' | '领域' | 'Task') {
   72 |   await page.getByTestId('tm-btn-create-menu').click()
   73 |   await page.getByRole('menuitem', { name: item, exact: true }).click()
   74 | }
   75 |
   76 | /** Ant Design Select：点开 →（可搜时）过滤 → 等选项出现再选中 */
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
> 107 |   await expect(option.first()).toBeVisible({ timeout: 20_000 })
      |                                ^ Error: Timed out 20000ms waiting for expect(locator).toBeVisible()
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
  187 |   // antd 两字中文按钮会在字符间自动插空格（可访问名为「添 加」），用正则兼容
  188 |   await page.getByRole('button', { name: /^添\s*加$/ }).click()
  189 |   await expectToast(page, '子需求已添加')
  190 |   await expect(page.getByTestId('tm-subtask-table').getByText(name)).toBeVisible({
  191 |     timeout: 15_000,
  192 |   })
  193 |   await closeTaskDrawer(page)
  194 | }
  195 |
  196 | /**
  197 |  * 将 Task 需求进展改到指定阶段（含必填日期）。
  198 |  * stageLabel 例：测试中 / 测试完成
  199 |  * dateFieldLabels 例：['测试开始时间','预计测试结束'] 或 '测试结束时间'
  200 |  */
  201 | export async function setTaskReqStage(
  202 |   page: Page,
  203 |   card: import('@playwright/test').Locator,
  204 |   stageLabel: string,
  205 |   dateFieldLabels?: string | string[],
  206 | ) {
  207 |   await openTaskDetail(page, card, '进度')
```