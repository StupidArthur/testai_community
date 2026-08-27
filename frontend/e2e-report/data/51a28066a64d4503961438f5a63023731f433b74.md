# Test info

- Name: TM UI E2E rmtb3uh63 >> 19 Manager：日更到 100% 并标记完成
- Location: D:\代码\testai_community\frontend\e2e\tm-ui-full.spec.ts:381:3

# Error details

```
Error: locator.click: Test timeout of 120000ms exceeded.
Call log:
  - waiting for getByTestId('tm-btn-mark-done')

    at D:\代码\testai_community\frontend\e2e\tm-ui-full.spec.ts:394:48
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
    - text: 每周三 17:00 将发送周报，请大家在 16:55 完成周 Task 的更新，Action 请于每天 19:50 前更新 3 Task 0 阻塞 11% Task 均进度
    - combobox
    - text: 全部（3）
    - combobox
    - text: 【E2E】rmtb3uh63 项目
    - button "plus 新建 down":
      - img "plus"
      - text: 新建
      - img "down"
    - text: 【E2E】rmtb3uh63 TaskDone 完成 【E2E】rmtb3uh63 项目/【E2E】rmtb3uh63 领域 0%
    - img "exclamation-circle"
    - button "操作 down":
      - text: 操作
      - img "down"
    - text: 测试完成 测试结束 08-01 · 需求：x · 负责人 测试管理员
    - img "No data"
    - text: 本周无 Action（Task 已完成，不可再添加） 【E2E】rmtb3uh63 Task主 进行中 【E2E】rmtb3uh63 项目/【E2E】rmtb3uh63 领域 33%
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
        - row "【E2E】rmtb3uh63 子需求 【E2E】rmtb3uh63 草稿Action 测试管理员 0 进行中 —":
          - cell "【E2E】rmtb3uh63 子需求"
          - cell "【E2E】rmtb3uh63 草稿Action"
          - cell "测试管理员"
          - cell "0":
            - progressbar: 0%
          - cell "进行中"
          - cell "—"
          - cell
        - row "【E2E】rmtb3uh63 子需求 【E2E】rmtb3uh63 TesterAction 测试管理员 0 进行中 —":
          - cell "【E2E】rmtb3uh63 子需求"
          - cell "【E2E】rmtb3uh63 TesterAction"
          - cell "测试管理员"
          - cell "0":
            - progressbar: 0%
          - cell "进行中"
          - cell "—"
          - cell
        - row "【E2E】rmtb3uh63 子需求 【E2E】rmtb3uh63 进行中Action 测试管理员 100 完成 —":
          - cell "【E2E】rmtb3uh63 子需求"
          - cell "【E2E】rmtb3uh63 进行中Action"
          - cell "测试管理员"
          - cell "100":
            - progressbar:
              - img "check-circle"
          - cell "完成"
          - cell "—"
          - cell
    - text: 【E2E】rmtb3uh63 Task空 进行中 【E2E】rmtb3uh63 项目/【E2E】rmtb3uh63 领域 0%
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
- dialog "【E2E】rmtb3uh63 进行中Action":
  - button "Close":
    - img "close"
  - text: 【E2E】rmtb3uh63 进行中Action
  - banner:
    - text: 完成 【E2E】rmtb3uh63 Task主 子需求 【E2E】rmtb3uh63 子需求 · 负责人 测试管理员
    - progressbar:
      - img "check-circle"
  - button "collapsed 延续历史 · 1 周":
    - img "collapsed"
    - text: 延续历史 · 1 周
  - heading "基本信息" [level=3]
  - term: 子需求
  - definition: 【E2E】rmtb3uh63 子需求
  - term: 测试内容
  - definition: —
  - term: 环境
  - definition: —
  - heading "更正说明" [level=3]
  - textbox "更正内容…"
  - text: 0 / 1000
  - button "追加更正"
  - heading "更正记录 · 1" [level=3]
  - list:
    - listitem: 2026-08-27T05:52:41 · 测试管理员 · 最新 Manager 更正一条
```

# Test source

```ts
  294 |     if (await doneBtn.count()) {
  295 |       await expect(doneBtn).toBeDisabled()
  296 |     }
  297 |   })
  298 |
  299 |   test('14 Tester：不可日更 Manager 的 Action；无 +Action', async ({ page }) => {
  300 |     await login(page, users.tester.username)
  301 |     await goProjects(page)
  302 |     await openBoardTab(page)
  303 |     await selectProjectFilter(page, names.project)
  304 |     await selectBoardScope(page, '全部')
  305 |
  306 |     // 非参与者可能看不到空关联；若看得到卡片则无 +Action
  307 |     const card = page.locator('.tm-board-task').filter({ hasText: names.task })
  308 |     if (await card.count()) {
  309 |       await expect(card.first().getByTestId('tm-btn-add-action')).toHaveCount(0)
  310 |     }
  311 |
  312 |     const actionCard = page.locator('.tm-action-card').filter({ hasText: names.actionPub })
  313 |     if (await actionCard.count()) {
  314 |       await actionCard.first().click()
  315 |       await expect(page.getByTestId('tm-submit-daily')).toHaveCount(0)
  316 |     }
  317 |   })
  318 |
  319 |   test('15 我的 Action：Manager 能看到自己负责的', async ({ page }) => {
  320 |     await login(page, 'manager', PASS)
  321 |     await goProjects(page)
  322 |     await openMineTab(page)
  323 |     await expect(page.getByText(names.actionPub)).toBeVisible()
  324 |   })
  325 |
  326 |   test('16 看板 scope：我的/其他/全部', async ({ page }) => {
  327 |     await login(page, 'manager', PASS)
  328 |     await goProjects(page)
  329 |     await openBoardTab(page)
  330 |     await selectProjectFilter(page, names.project)
  331 |
  332 |     const boardTitle = page.getByTestId('tm-board-task-title').filter({ hasText: names.task })
  333 |
  334 |     await selectBoardScope(page, '我的')
  335 |     await expect(boardTitle).toBeVisible()
  336 |
  337 |     await selectBoardScope(page, '其他')
  338 |     await expect(boardTitle).toHaveCount(0)
  339 |
  340 |     await selectBoardScope(page, '全部')
  341 |     await expect(boardTitle).toBeVisible()
  342 |   })
  343 |
  344 |   test('17 大屏：关注范围 / 需求进展 / 全屏 / 周切换', async ({ page }) => {
  345 |     await login(page, 'manager', PASS)
  346 |     await goProjects(page)
  347 |     await openScreenTab(page)
  348 |     await expect(page.getByTestId('tm-screen')).toBeVisible()
  349 |     // 默认「今日」无关注范围；切到本周后再验筛选
  350 |     await page.getByTestId('tm-screen-week-current').click()
  351 |     const focus = page.getByTestId('tm-screen-focus-select')
  352 |     if (!(await focus.isVisible())) {
  353 |       await page.getByTestId('tm-screen-more-toggle').click()
  354 |       await expect(page.getByTestId('tm-screen-more-filters')).toBeVisible()
  355 |     }
  356 |     await expect(focus).toBeVisible()
  357 |     await expect(page.getByTestId('tm-screen-req-stage')).toBeVisible()
  358 |     await expect(page.getByTestId('tm-screen-fullscreen')).toBeVisible()
  359 |     await page.getByTestId('tm-screen-week-history').click()
  360 |     await expect(page.getByText('历史周进度与风险总览')).toBeVisible()
  361 |     await page.getByTestId('tm-screen-week-current').click()
  362 |     await page.getByTestId('tm-screen-week-pipeline').click()
  363 |     await expect(page.getByText('需求进展总览')).toBeVisible()
  364 |     await page.getByTestId('tm-screen-week-current').click()
  365 |   })
  366 |
  367 |   test('18 Manager：Task 标测试完成 → 无 +Action', async ({ page }) => {
  368 |     await login(page, 'manager', PASS)
  369 |     await goProjects(page)
  370 |     await openBoardTab(page)
  371 |     await selectProjectFilter(page, names.project)
  372 |     await selectBoardScope(page, '全部')
  373 |
  374 |     const card = await boardTaskByTitle(page, names.taskDone)
  375 |     await setTaskReqStage(page, card, '测试完成', '测试结束时间')
  376 |
  377 |     const card2 = await boardTaskByTitle(page, names.taskDone)
  378 |     await expect(card2.getByTestId('tm-btn-add-action')).toHaveCount(0)
  379 |   })
  380 |
  381 |   test('19 Manager：日更到 100% 并标记完成', async ({ page }) => {
  382 |     await login(page, 'manager', PASS)
  383 |     await goProjects(page)
  384 |     await openBoardTab(page)
  385 |     await selectProjectFilter(page, names.project)
  386 |     await selectBoardScope(page, '全部')
  387 |
  388 |     await page.locator('.tm-action-card').filter({ hasText: names.actionPub }).first().click()
  389 |     const progress = page.getByRole('spinbutton', { name: /进度/ })
  390 |     await progress.fill('100')
  391 |     await page.getByTestId('tm-daily-note').fill('收尾完成')
  392 |     await page.getByTestId('tm-submit-daily').click()
  393 |     await expectToast(page, '日更已保存')
> 394 |     await page.getByTestId('tm-btn-mark-done').click({ force: true })
      |                                                ^ Error: locator.click: Test timeout of 120000ms exceeded.
  395 |     await expectToast(page, /完成/)
  396 |   })
  397 |
  398 |   test('20 历史周只读：工作台 Alert；无新建', async ({ page }) => {
  399 |     await login(page, 'manager', PASS)
  400 |     await goProjects(page)
  401 |     await openBoardTab(page)
  402 |     await page.getByTestId('tm-board-week-history').click()
  403 |     await expect(page.getByText('历史周只读，编辑请切回本周')).toBeVisible()
  404 |     await expect(page.getByTestId('tm-btn-create-menu')).toHaveCount(0)
  405 |     await page.getByTestId('tm-board-week-current').click()
  406 |   })
  407 |
  408 |   test('21 本轮创建的关键实体仍在看板', async ({ page }) => {
  409 |     await login(page, 'manager', PASS)
  410 |     await goProjects(page)
  411 |     await openBoardTab(page)
  412 |     await page.getByTestId('tm-board-week-current').click()
  413 |     await selectProjectFilter(page, names.project)
  414 |     await selectBoardScope(page, '全部')
  415 |     await expect(page.getByTestId('tm-board-task-title').filter({ hasText: names.task })).toBeVisible()
  416 |     await expect(page.locator('.tm-action-card').filter({ hasText: names.actionPub }).first()).toBeVisible()
  417 |   })
  418 | })
  419 |
```