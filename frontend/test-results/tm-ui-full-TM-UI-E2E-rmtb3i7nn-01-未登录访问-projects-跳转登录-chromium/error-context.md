# Test info

- Name: TM UI E2E rmtb3i7nn >> 01 未登录访问 /projects 跳转登录
- Location: D:\代码\testai_community\frontend\e2e\tm-ui-full.spec.ts:76:3

# Error details

```
Error: page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:3003/projects
Call log:
  - navigating to "http://127.0.0.1:3003/projects", waiting until "load"

    at D:\代码\testai_community\frontend\e2e\tm-ui-full.spec.ts:77:16
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
   2 |  * 项目管理全量 UI E2E（现网开发库）
   3 |  *
   4 |  * 约定：
   5 |  * - 后端已在 48010 运行（vite 代理 /api）
   6 |  * - 全部业务数据通过页面点击创建，不用 API 灌数
   7 |  * - 数据前缀 【E2E】+ 本次 RUN id，避免互相踩
   8 |  */
   9 | import { test, expect, type Page } from '@playwright/test'
   10 | import {
   11 |   PASS,
   12 |   addSubtaskViaTaskDetail,
   13 |   antdMultiSelect,
   14 |   antdSelectByLabel,
   15 |   boardTaskByTitle,
   16 |   expectToast,
   17 |   fillInputNumber,
   18 |   goProjects,
   19 |   login,
   20 |   openBoardTab,
   21 |   openCreateMenu,
   22 |   openMineTab,
   23 |   openScreenTab,
   24 |   openTaskDetail,
   25 |   selectBoardScope,
   26 |   selectProjectFilter,
   27 |   setTaskReqStage,
   28 | } from './helpers.ts'
   29 |
   30 | test.describe.configure({ mode: 'serial' })
   31 |
   32 | /** 固定本文件加载时的 RUN，避免 worker 二次求值 Date.now 导致标题不一致 */
   33 | const RUN = process.env.E2E_RUN_ID || `r${process.pid}`
   34 | const TAG = `【E2E】${RUN}`
   35 |
   36 | const users = {
   37 |   lead: { username: `e2eL_${RUN}`, realName: `E2ELead${RUN}`, password: PASS },
   38 |   owner: { username: `e2eO_${RUN}`, realName: `E2EOwner${RUN}`, password: PASS },
   39 |   tester: { username: `e2eT_${RUN}`, realName: `E2ETester${RUN}`, password: PASS },
   40 |   stranger: { username: `e2eX_${RUN}`, realName: `E2E路人${RUN}`, password: PASS },
   41 | }
   42 |
   43 | const names = {
   44 |   project: `${TAG} 项目`,
   45 |   domain: `${TAG} 领域`,
   46 |   task: `${TAG} Task主`,
   47 |   taskEmpty: `${TAG} Task空`,
   48 |   taskDone: `${TAG} TaskDone`,
   49 |   subtask: `${TAG} 子需求`,
   50 |   actionDraft: `${TAG} 草稿Action`,
   51 |   actionPub: `${TAG} 进行中Action`,
   52 |   actionTester: `${TAG} TesterAction`,
   53 | }
   54 |
   55 | async function addUserViaAdmin(
   56 |   page: Page,
   57 |   u: { username: string; realName: string },
   58 | ) {
   59 |   await page.goto('/admin')
   60 |   await expect(page.getByText('管理员面板')).toBeVisible()
   61 |   // 已存在则跳过（本 RUN 内幂等）
   62 |   if (await page.getByRole('cell', { name: u.username, exact: true }).count()) {
   63 |     return
   64 |   }
   65 |   await page.getByTestId('admin-btn-add-user').click()
   66 |   await page.getByTestId('admin-input-username').fill(u.username)
   67 |   await page.getByTestId('admin-input-realname').fill(u.realName)
   68 |   await page.getByTestId('admin-submit-user').click()
   69 |   // toast 可能很快消失；以列表出现为准
   70 |   await expect(page.getByRole('cell', { name: u.username, exact: true })).toBeVisible({
   71 |     timeout: 20_000,
   72 |   })
   73 | }
   74 |
   75 | test.describe(`TM UI E2E ${RUN}`, () => {
   76 |   test('01 未登录访问 /projects 跳转登录', async ({ page }) => {
>  77 |     await page.goto('/projects')
      |                ^ Error: page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:3003/projects
   78 |     await expect(page).toHaveURL(/\/login/)
   79 |     await expect(page.getByTestId('login-submit')).toBeVisible()
   80 |   })
   81 |
   82 |   test('02 Admin 登录 → Portal → 使用说明/导航', async ({ page }) => {
   83 |     await login(page, 'admin', 'admin')
   84 |     // Portal 大入口
   85 |     await page.getByRole('button', { name: /进入/ }).click()
   86 |     await expect(page).toHaveURL(/\/projects/)
   87 |     await page.getByTestId('tm-help-btn').click()
   88 |     await expect(page.getByTestId('tm-help-drawer')).toBeVisible()
   89 |     await page.keyboard.press('Escape')
   90 |     // 三 Tab
   91 |     await openScreenTab(page)
   92 |     await openBoardTab(page)
   93 |     await openMineTab(page)
   94 |     await openBoardTab(page)
   95 |   })
   96 |
   97 |   test('03 Admin 在用户管理页创建四个 Engineer', async ({ page }) => {
   98 |     await login(page, 'admin', 'admin')
   99 |     for (const u of Object.values(users)) {
  100 |       await addUserViaAdmin(page, u)
  101 |     }
  102 |     // 列表可见
  103 |     await expect(page.getByText(users.lead.username)).toBeVisible()
  104 |     await expect(page.getByText(users.owner.username)).toBeVisible()
  105 |   })
  106 |
  107 |   test('04 Manager：工作台可见新建按钮；创建项目/领域', async ({ page }) => {
  108 |     await login(page, 'manager', PASS)
  109 |     await goProjects(page)
  110 |     await openBoardTab(page)
  111 |     await expect(page.getByTestId('tm-btn-create-menu')).toBeVisible()
  112 |
  113 |     await openCreateMenu(page, '项目')
  114 |     await page.getByTestId('tm-input-project-name').fill(names.project)
  115 |     await page.getByTestId('tm-submit-project').click()
  116 |     await expectToast(page, '项目已创建')
  117 |
  118 |     await selectProjectFilter(page, names.project)
  119 |     await openCreateMenu(page, '领域')
  120 |     await page.getByTestId('tm-input-domain-name').fill(names.domain)
  121 |     await page.getByTestId('tm-submit-domain').click()
  122 |     await expectToast(page, '领域已创建')
  123 |   })
  124 |
  125 |   test('05 Manager：新建 Task 并见空卡', async ({ page }) => {
  126 |     await login(page, 'manager', PASS)
  127 |     await goProjects(page)
  128 |     await openBoardTab(page)
  129 |     await selectProjectFilter(page, names.project)
  130 |     await selectBoardScope(page, '全部')
  131 |
  132 |     await openCreateMenu(page, 'Task')
  133 |     await expect(page.getByTestId('tm-modal-new-task')).toBeVisible()
  134 |     await antdSelectByLabel(page, 'tm-task-project', names.project)
  135 |     await antdSelectByLabel(page, 'tm-task-domain', names.domain)
  136 |     await page.getByTestId('tm-task-title').fill(names.task)
  137 |     await page.getByTestId('tm-task-requirement').fill('E2E 需求说明')
  138 |     // 负责人默认 manager；测试人员后续在 Action 负责人里只用 manager（规避多选 Select 不稳定）
  139 |     await page.getByTestId('tm-submit-task').click({ force: true })
  140 |     await expect(page.getByText(names.task).first()).toBeVisible({ timeout: 20_000 })
  141 |
  142 |     const card = await boardTaskByTitle(page, names.task)
  143 |     await expect(card).toBeVisible()
  144 |     // 默认待开发：不可 +Action，也不再标红「本周无 Action」（仅测试中可建 Action 时高亮）
  145 |     await expect(card.getByTestId('tm-btn-add-action')).toHaveCount(0)
  146 |     await expect(card.getByTestId('tm-empty-action-tag')).toHaveCount(0)
  147 |   })
  148 |
  149 |   test('06 Manager：再建空 Task / 待完成 Task', async ({ page }) => {
  150 |     await login(page, 'manager', PASS)
  151 |     await goProjects(page)
  152 |     await openBoardTab(page)
  153 |     await selectProjectFilter(page, names.project)
  154 |     await selectBoardScope(page, '全部')
  155 |
  156 |     for (const title of [names.taskEmpty, names.taskDone]) {
  157 |       await openCreateMenu(page, 'Task')
  158 |       await antdSelectByLabel(page, 'tm-task-project', names.project)
  159 |       await antdSelectByLabel(page, 'tm-task-domain', names.domain)
  160 |       await page.getByTestId('tm-task-title').fill(title)
  161 |       await page.getByTestId('tm-task-requirement').fill('x')
  162 |       await page.getByTestId('tm-submit-task').click({ force: true })
  163 |       await expect(page.getByText(title).first()).toBeVisible({ timeout: 15_000 })
  164 |     }
  165 |   })
  166 |
  167 |   test('07 Engineer 路人：无新建按钮；看不到无关空 Task', async ({ page }) => {
  168 |     await login(page, users.stranger.username)
  169 |     await goProjects(page)
  170 |     await openBoardTab(page)
  171 |     await expect(page.getByTestId('tm-btn-create-menu')).toHaveCount(0)
  172 |     await selectProjectFilter(page, names.project)
  173 |     await selectBoardScope(page, '全部')
  174 |     await expect(page.getByText(names.taskEmpty)).toHaveCount(0)
  175 |   })
  176 |
  177 |   test('08 Manager：打开 Task 抽屉改需求并见成功 Alert', async ({ page }) => {
```