# Test info

- Name: TM UI E2E rmtb3lbfd >> 10 Manager：再建一条直接「保存并发布」给 Owner
- Location: D:\代码\testai_community\frontend\e2e\tm-ui-full.spec.ts:217:3

# Error details

```
Error: locator.scrollIntoViewIfNeeded: Element is not attached to the DOM
Call log:
  - attempting scroll into view action
    2 × waiting for element to be stable
      - element is not stable
    - retrying scroll into view action
    - waiting 20ms
    - waiting for element to be stable
    - element is not stable
  - retrying scroll into view action
    - waiting 100ms
    - waiting for element to be stable

    at antdSelectByLabel (D:\代码\testai_community\frontend\e2e\helpers.ts:101:16)
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
    - text: 【E2E】rmtb3lbfd 项目
    - button "plus 新建 down":
      - img "plus"
      - text: 新建
      - img "down"
    - text: 【E2E】rmtb3lbfd TaskDone 进行中 【E2E】rmtb3lbfd 项目/【E2E】rmtb3lbfd 领域 0%
    - img "exclamation-circle"
    - button "操作 down":
      - text: 操作
      - img "down"
    - text: 待开发 需求：x · 负责人 测试管理员
    - img "No data"
    - text: 本周无 Action（Task 已完成，不可再添加） 【E2E】rmtb3lbfd Task主 进行中 【E2E】rmtb3lbfd 项目/【E2E】rmtb3lbfd 领域 0%
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
        - row "【E2E】rmtb3lbfd 子需求 【E2E】rmtb3lbfd 草稿Action 测试管理员 0 进行中 —":
          - cell "【E2E】rmtb3lbfd 子需求"
          - cell "【E2E】rmtb3lbfd 草稿Action"
          - cell "测试管理员"
          - cell "0":
            - progressbar: 0%
          - cell "进行中"
          - cell "—"
          - cell
    - text: 【E2E】rmtb3lbfd Task空 进行中 【E2E】rmtb3lbfd 项目/【E2E】rmtb3lbfd 领域 0%
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
```

# Test source

```ts
   1 | /**
   2 |  * E2E 公共操作：登录/注销、Ant Design Select、进入项目管理。
   3 |  * 不调用业务 API 灌数。
   4 |  */
   5 | import { expect, type Page } from '@playwright/test'
   6 |
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
> 101 |     await root.scrollIntoViewIfNeeded()
      |                ^ Error: locator.scrollIntoViewIfNeeded: Element is not attached to the DOM
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
  167 |   await expect(notice.first()).toBeVisible({ timeout: 20_000 })
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
```