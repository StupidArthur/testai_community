# Test info

- Name: TM UI 补充 rmtb3i7nn >> A Admin 建用户
- Location: D:\代码\testai_community\frontend\e2e\tm-ui-extra.spec.ts:47:3

# Error details

```
Error: page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:3003/login
Call log:
  - navigating to "http://127.0.0.1:3003/login", waiting until "load"

    at login (D:\代码\testai_community\frontend\e2e\helpers.ts:10:14)
    at D:\代码\testai_community\frontend\e2e\tm-ui-extra.spec.ts:48:11
```

# Page snapshot

```yaml
- heading "无法访问此网站" [level=1]
- paragraph:
  - strong: 127.0.0.1
  - text: 拒绝了我们的连接请求。
- paragraph: 请试试以下办法：
- list:
  - listitem: 检查网络连接
  - listitem:
    - link "检查代理服务器和防火墙":
      - /url: "#buttons"
- text: ERR_CONNECTION_REFUSED
- button "重新加载"
- button "详情"
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
>  10 |   await page.goto('/login')
      |              ^ Error: page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:3003/login
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
```