# Test info

- Name: TM 三点需求 UI rmtauw2id >> 04 Manager：API 克隆 → UI 见延续历史共 2 周
- Location: D:\代码\testai_community\frontend\e2e\tm-user-reqs.spec.ts:141:3

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: 201
Received: 405
    at D:\代码\testai_community\frontend\e2e\tm-user-reqs.spec.ts:164:31
```

# Test source

```ts
   64 |       await expect(page.getByRole('cell', { name: engUser, exact: true })).toBeVisible({
   65 |         timeout: 20_000,
   66 |       })
   67 |     }
   68 |     await logout(page)
   69 |     await login(page, engUser, PASS)
   70 |     await goProjects(page)
   71 |     await openBoardTab(page)
   72 |     await expect(page.getByTestId('tm-week-end-picker')).toHaveCount(0)
   73 |     await expect(page.getByTestId('tm-week-end-hint')).toBeVisible({ timeout: 20_000 })
   74 |   })
   75 |
   76 |   test('03 Manager：建树+日更 → 未手填推荐提示', async ({ page }) => {
   77 |     await login(page, 'manager', PASS)
   78 |     await goProjects(page)
   79 |     await openBoardTab(page)
   80 |
   81 |     await openCreateMenu(page, '项目')
   82 |     await page.getByTestId('tm-input-project-name').fill(names.project)
   83 |     await page.getByTestId('tm-submit-project').click()
   84 |     await expectToast(page, '项目已创建')
   85 |
   86 |     await selectProjectFilter(page, names.project)
   87 |     await openCreateMenu(page, '领域')
   88 |     await page.getByTestId('tm-input-domain-name').fill(names.domain)
   89 |     await page.getByTestId('tm-submit-domain').click()
   90 |     await expectToast(page, '领域已创建')
   91 |
   92 |     await openCreateMenu(page, 'Task')
   93 |     await expect(page.getByTestId('tm-modal-new-task')).toBeVisible()
   94 |     await antdSelectByLabel(page, 'tm-task-project', names.project)
   95 |     await antdSelectByLabel(page, 'tm-task-domain', names.domain)
   96 |     await page.getByTestId('tm-task-title').fill(names.task)
   97 |     await page.getByTestId('tm-task-requirement').fill('UI 自测需求：未手填推荐')
   98 |     await page.getByTestId('tm-submit-task').click({ force: true })
   99 |     await expect(page.getByText(names.task).first()).toBeVisible({ timeout: 20_000 })
  100 |
  101 |     const card = await boardTaskByTitle(page, names.task)
  102 |     // Action 必须关联子需求：先在 Task 详情维护
  103 |     await addSubtaskViaTaskDetail(page, card, names.subtask)
  104 |     await setTaskReqStage(page, card, '测试中')
  105 |     const cardReady = await boardTaskByTitle(page, names.task)
  106 |     await cardReady.getByTestId('tm-btn-add-action').click()
  107 |     await expect(page.getByTestId('tm-modal-new-action')).toBeVisible()
  108 |     await antdSelectByLabel(page, 'tm-action-subtask', names.subtask)
  109 |     await page.getByTestId('tm-action-title').fill(names.action)
  110 |     await page.getByTestId('tm-action-content').fill('测试内容')
  111 |     await page.getByTestId('tm-action-env').fill('qa')
  112 |     await page.getByTestId('tm-submit-action-publish').click()
  113 |     await expectToast(page, /已保存|发布|创建/)
  114 |
  115 |     await selectProjectFilter(page, names.project)
  116 |     const card2 = await boardTaskByTitle(page, names.task)
  117 |     await expect(card2.getByTestId('tm-task-progress-tip')).toBeVisible()
  118 |     await card2.getByTestId('tm-task-progress-tip').hover()
  119 |     await expect(page.getByRole('tooltip').filter({ hasText: '未手填' })).toBeVisible()
  120 |     await card2.locator('[data-testid^="tm-action-card-"]').first().click()
  121 |     await expect(page.getByTestId('tm-drawer-action')).toBeVisible()
  122 |     await fillInputNumber(page, 'tm-daily-progress', '55')
  123 |     await page.getByTestId('tm-daily-note').fill('本日进展说明：UI自测日更')
  124 |     await page.getByTestId('tm-submit-daily').click()
  125 |     await expectToast(page, /日更|成功|已保存|提交/)
  126 |     await page.keyboard.press('Escape')
  127 |
  128 |     await selectBoardScope(page, '全部')
  129 |     const card3 = await boardTaskByTitle(page, names.task)
  130 |     await expect(card3.getByTestId('tm-task-progress-tip')).toBeVisible({ timeout: 15_000 })
  131 |     await card3.getByTestId('tm-task-progress-tip').hover()
  132 |     await expect(page.getByRole('tooltip').filter({ hasText: '未手填' })).toBeVisible()
  133 |
  134 |     await openTaskDetail(page, card3, '进度')
  135 |     await expect(page.getByTestId('tm-drawer-task')).toBeVisible()
  136 |     await expect(page.getByTestId('tm-task-week-progress')).toBeVisible()
  137 |     await expect(page.getByTestId('tm-task-week-progress').getByText(/未手填 · 按 Action 平均\s*55%/)).toBeVisible()
  138 |     await page.keyboard.press('Escape')
  139 |   })
  140 |
  141 |   test('04 Manager：API 克隆 → UI 见延续历史共 2 周', async ({ page, request }) => {
  142 |     const loginRes = await request.post('http://127.0.0.1:48010/api/auth/login', {
  143 |       data: { username: 'manager', password: PASS },
  144 |     })
  145 |     expect(loginRes.ok()).toBeTruthy()
  146 |     const token = (await loginRes.json()).access_token
  147 |     const headers = { Authorization: `Bearer ${token}` }
  148 |
  149 |     const boardRes = await request.get('http://127.0.0.1:48010/api/test-manage/board', {
  150 |       headers,
  151 |     })
  152 |     expect(boardRes.ok()).toBeTruthy()
  153 |     const board = await boardRes.json()
  154 |     const hit = (board.tasks || []).find((t: { task: { title: string } }) =>
  155 |       t.task.title.includes(TAG),
  156 |     )
  157 |     expect(hit).toBeTruthy()
  158 |     const srcId = hit.actions[0].id as string
  159 |
  160 |     const cloneRes = await request.post(
  161 |       `http://127.0.0.1:48010/api/test-manage/actions/${srcId}/clone`,
  162 |       { headers, data: { title: names.actionClone, publish: false } },
  163 |     )
> 164 |     expect(cloneRes.status()).toBe(201)
      |                               ^ Error: expect(received).toBe(expected) // Object.is equality
  165 |     const cloned = await cloneRes.json()
  166 |     expect(cloned.source_action_id).toBe(srcId)
  167 |
  168 |     await login(page, 'manager', PASS)
  169 |     await goProjects(page)
  170 |     await openBoardTab(page)
  171 |     await selectProjectFilter(page, names.project)
  172 |     const card = await boardTaskByTitle(page, names.task)
  173 |     const target = card.locator(`[data-testid="tm-action-card-${cloned.id}"]`)
  174 |     if (await target.count()) {
  175 |       await target.click()
  176 |     } else {
  177 |       await card.locator('[data-testid^="tm-action-card-"]').filter({ hasText: '续' }).first().click()
  178 |     }
  179 |     await expect(page.getByTestId('tm-drawer-action')).toBeVisible()
  180 |     const lineage = page.getByTestId('tm-action-lineage')
  181 |     await expect(lineage).toBeVisible({ timeout: 15_000 })
  182 |     await expect(lineage).toContainText(/延续历史/)
  183 |     await expect(lineage).toContainText(/2\s*周/)
  184 |   })
  185 | })
  186 |
```