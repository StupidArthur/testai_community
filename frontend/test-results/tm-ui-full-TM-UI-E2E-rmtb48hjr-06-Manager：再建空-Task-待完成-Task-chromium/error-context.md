# Test info

- Name: TM UI E2E rmtb48hjr >> 06 Manager：再建空 Task / 待完成 Task
- Location: D:\代码\testai_community\frontend\e2e\tm-ui-full.spec.ts:149:3

# Error details

```
Error: Timed out 15000ms waiting for expect(locator).toBeVisible()

Locator: getByText('【E2E】rmtb48hjr TaskDone').first()
Expected: visible
Received: <element(s) not found>
Call log:
  - expect.toBeVisible with timeout 15000ms
  - waiting for getByText('【E2E】rmtb48hjr TaskDone').first()

    at D:\代码\testai_community\frontend\e2e\tm-ui-full.spec.ts:163:51
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
    - text: 每周三 17:00 将发送周报，请大家在 16:55 完成周 Task 的更新，Action 请于每天 19:50 前更新 2 Task 0 阻塞 0% Task 均进度
    - combobox
    - text: 全部（2）
    - combobox
    - text: 【E2E】rmtb48hjr 项目
    - button "plus 新建 down":
      - img "plus"
      - text: 新建
      - img "down"
    - text: 【E2E】rmtb48hjr Task主 进行中 【E2E】rmtb48hjr 项目/【E2E】rmtb48hjr 领域 0%
    - img "exclamation-circle"
    - button "操作 down":
      - text: 操作
      - img "down"
    - text: 待开发 需求：E2E 需求说明 · 负责人 测试管理员
    - img "No data"
    - text: 本周无 Action（Task 已完成，不可再添加） 【E2E】rmtb48hjr Task空 进行中 【E2E】rmtb48hjr 项目/【E2E】rmtb48hjr 领域 0%
    - img "exclamation-circle"
    - button "操作 down":
      - text: 操作
      - img "down"
    - text: 待开发 需求：x · 负责人 测试管理员
    - img "No data"
    - text: 本周无 Action（Task 已完成，不可再添加）
    - list:
      - listitem: 共 2 个 Task
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
   77 |     await page.goto('/projects')
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
> 163 |       await expect(page.getByText(title).first()).toBeVisible({ timeout: 15_000 })
      |                                                   ^ Error: Timed out 15000ms waiting for expect(locator).toBeVisible()
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
  178 |     await login(page, 'manager', PASS)
  179 |     await goProjects(page)
  180 |     await openBoardTab(page)
  181 |     await selectProjectFilter(page, names.project)
  182 |     await selectBoardScope(page, '全部')
  183 |
  184 |     const card = await boardTaskByTitle(page, names.task)
  185 |     await openTaskDetail(page, card)
  186 |     await page.getByTestId('tm-task-info-edit').click()
  187 |     await page.getByLabel(/需求内容/).fill('Manager 更新后的需求')
  188 |     await page.getByLabel(/变更说明/).fill('E2E 改需求')
  189 |     await page.getByTestId('tm-task-save').click()
  190 |     await expect(page.getByTestId('tm-task-save-tip')).toBeVisible()
  191 |     await expectToast(page, /已保存|测试负责人/)
  192 |   })
  193 |
  194 |   test('09 Manager：切到测试中后 +Action 保存并发布', async ({ page }) => {
  195 |     await login(page, 'manager', PASS)
  196 |     await goProjects(page)
  197 |     await openBoardTab(page)
  198 |     await selectProjectFilter(page, names.project)
  199 |     await selectBoardScope(page, '全部')
  200 |
  201 |     const card = await boardTaskByTitle(page, names.task)
  202 |     await setTaskReqStage(page, card, '测试中')
  203 |     // Action 必须关联子需求：先在 Task 详情维护
  204 |     const cardSub = await boardTaskByTitle(page, names.task)
  205 |     await addSubtaskViaTaskDetail(page, cardSub, names.subtask)
  206 |     const cardReady = await boardTaskByTitle(page, names.task)
  207 |     await cardReady.getByTestId('tm-btn-add-action').click()
  208 |     await expect(page.getByTestId('tm-modal-new-action')).toBeVisible()
  209 |     await antdSelectByLabel(page, 'tm-action-subtask', names.subtask)
  210 |     await page.getByTestId('tm-action-title').fill(names.actionDraft)
  211 |     await page.getByTestId('tm-action-content').fill('草稿内容')
  212 |     await page.getByTestId('tm-submit-action-publish').click({ force: true })
  213 |     await expectToast(page, 'Action 已保存')
  214 |     await expect(page.locator('.tm-action-card').filter({ hasText: names.actionDraft })).toBeVisible()
  215 |   })
  216 |
  217 |   test('10 Manager：再建一条直接「保存并发布」给 Owner', async ({ page }) => {
  218 |     await login(page, 'manager', PASS)
  219 |     await goProjects(page)
  220 |     await openBoardTab(page)
  221 |     await selectProjectFilter(page, names.project)
  222 |     await selectBoardScope(page, '全部')
  223 |
  224 |     const card = await boardTaskByTitle(page, names.task)
  225 |     await card.getByTestId('tm-btn-add-action').click()
  226 |     await expect(page.getByTestId('tm-modal-new-action')).toBeVisible()
  227 |     await antdSelectByLabel(page, 'tm-action-subtask', names.subtask)
  228 |     await page.getByTestId('tm-action-title').fill(names.actionPub)
  229 |     await page.getByTestId('tm-submit-action-publish').click({ force: true })
  230 |     await expectToast(page, 'Action 已保存')
  231 |     await expect(page.locator('.tm-action-card').filter({ hasText: names.actionPub })).toBeVisible()
  232 |   })
  233 |
  234 |   test('11 Manager：再建一条 Action（供权限对照）', async ({ page }) => {
  235 |     await login(page, 'manager', PASS)
  236 |     await goProjects(page)
  237 |     await openBoardTab(page)
  238 |     await selectProjectFilter(page, names.project)
  239 |     await selectBoardScope(page, '全部')
  240 |
  241 |     const card = await boardTaskByTitle(page, names.task)
  242 |     await card.getByTestId('tm-btn-add-action').click()
  243 |     await antdSelectByLabel(page, 'tm-action-subtask', names.subtask)
  244 |     await page.getByTestId('tm-action-title').fill(names.actionTester)
  245 |     await page.getByTestId('tm-submit-action-publish').click({ force: true })
  246 |     await expectToast(page, 'Action 已保存')
  247 |   })
  248 |
  249 |   test('12 Manager：日更 + 风险；进度倒退被拒；清空风险', async ({ page }) => {
  250 |     await login(page, 'manager', PASS)
  251 |     await goProjects(page)
  252 |     await openBoardTab(page)
  253 |     await selectProjectFilter(page, names.project)
  254 |     await selectBoardScope(page, '全部')
  255 |
  256 |     await page.locator('.tm-action-card').filter({ hasText: names.actionPub }).first().click()
  257 |     await expect(page.getByTestId('tm-drawer-action')).toBeVisible()
  258 |     const progress = page.getByRole('spinbutton', { name: /进度/ })
  259 |     await expect(progress).toBeVisible({ timeout: 15_000 })
  260 |     await progress.click()
  261 |     await progress.fill('30')
  262 |     await page.getByTestId('tm-daily-risk').fill('E2E阻塞UNIQUE')
  263 |     await page.getByTestId('tm-daily-note').fill('推进中说明必填')
```