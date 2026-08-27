# Test info

- Name: TM 三点需求 UI rmtb3lbfd >> 04 Manager：Action 抽屉显示延续历史（当前周）
- Location: D:\代码\testai_community\frontend\e2e\tm-user-reqs.spec.ts:140:3

# Error details

```
Error: Timed out 15000ms waiting for expect(locator).toContainText(expected)

Locator: getByTestId('tm-action-lineage')
Expected string: "当前"
Received string: "延续历史 · 1 周"
Call log:
  - expect.toContainText with timeout 15000ms
  - waiting for getByTestId('tm-action-lineage')
    18 × locator resolved to <div data-testid="tm-action-lineage" class="ant-collapse ant-collapse-icon-position-start ant-collapse-ghost ant-collapse-small tm-sheet__lineage css-dev-only-do-not-override-ynljz7">…</div>
       - unexpected value "延续历史 · 1 周"

    at D:\代码\testai_community\frontend\e2e\tm-user-reqs.spec.ts:157:27
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
    - text: 每周三 17:00 将发送周报，请大家在 16:55 完成周 Task 的更新，Action 请于每天 19:50 前更新 1 Task 0 阻塞 55% Task 均进度
    - combobox
    - text: 我的 Task（1）
    - combobox
    - text: 【UI自测】rmtb3lbfd 项目
    - button "plus 新建 down":
      - img "plus"
      - text: 新建
      - img "down"
    - text: 【UI自测】rmtb3lbfd Task 进行中 【UI自测】rmtb3lbfd 项目/【UI自测】rmtb3lbfd 领域 55%
    - img "exclamation-circle"
    - button "操作 down":
      - text: 操作
      - img "down"
    - button "+ Action"
    - text: 测试中 测试开始 08-01 ~ 预计结束 08-01 · 需求：UI 自测需求：未手填推荐 · 负责人 测试管理员
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
        - row "【UI自测】rmtb3lbfd 子需求 【UI自测】rmtb3lbfd Action 测试管理员 55 进行中 —":
          - cell "【UI自测】rmtb3lbfd 子需求"
          - cell "【UI自测】rmtb3lbfd Action"
          - cell "测试管理员"
          - cell "55":
            - progressbar: 55%
          - cell "进行中"
          - cell "—"
          - cell
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
- dialog "【UI自测】rmtb3lbfd Action":
  - button "Close":
    - img "close"
  - text: 【UI自测】rmtb3lbfd Action
  - banner:
    - text: 进行中 【UI自测】rmtb3lbfd Task 子需求 【UI自测】rmtb3lbfd 子需求 · 负责人 测试管理员
    - progressbar: 55%
  - button "collapsed 延续历史 · 1 周":
    - img "collapsed"
    - text: 延续历史 · 1 周
  - heading "基本信息" [level=3]
  - term: 子需求
  - definition: 【UI自测】rmtb3lbfd 子需求
  - term: 测试内容
  - definition: 测试内容
  - term: 环境
  - definition: qa
  - heading "状态" [level=3]
  - button "标记完成" [disabled]
  - text: 需日更到 100%（当前 55%）
  - heading "日更 19:50 截止" [level=3]
  - text: "* 进度 %"
  - button "Increase Value":
    - img "up"
  - button "Decrease Value" [disabled]:
    - img "down"
  - spinbutton "* 进度 %": "55"
  - text: ≥ 当前 55% 风险
  - textbox "风险"
  - text: 0 / 1000 是否阻塞
  - checkbox "是否阻塞 此风险构成阻塞"
  - text: 此风险构成阻塞 必须勾选后，大屏「阻塞」筛选 / 日报才会计入 * 说明
  - textbox "* 说明"
  - text: 0 / 1000
  - button "提交日更"
  - heading "更正说明" [level=3]
  - textbox "更正内容…"
  - text: 0 / 1000
  - button "追加更正"
  - heading "更正记录" [level=3]
  - paragraph: 暂无
```

# Test source

```ts
   57 |     await expect(page.getByText('管理员面板')).toBeVisible()
   58 |     if (!(await page.getByRole('cell', { name: engUser, exact: true }).count())) {
   59 |       await page.getByTestId('admin-btn-add-user').click()
   60 |       await page.getByTestId('admin-input-username').fill(engUser)
   61 |       await page.getByTestId('admin-input-realname').fill(`UIEng${RUN}`)
   62 |       await page.getByTestId('admin-submit-user').click()
   63 |       await expect(page.getByRole('cell', { name: engUser, exact: true })).toBeVisible({
   64 |         timeout: 20_000,
   65 |       })
   66 |     }
   67 |     await logout(page)
   68 |     await login(page, engUser, PASS)
   69 |     await goProjects(page)
   70 |     await openBoardTab(page)
   71 |     await expect(page.getByTestId('tm-week-end-picker')).toHaveCount(0)
   72 |     await expect(page.getByTestId('tm-week-end-hint')).toBeVisible({ timeout: 20_000 })
   73 |   })
   74 |
   75 |   test('03 Manager：建树+日更 → 未手填推荐提示', async ({ page }) => {
   76 |     await login(page, 'manager', PASS)
   77 |     await goProjects(page)
   78 |     await openBoardTab(page)
   79 |
   80 |     await openCreateMenu(page, '项目')
   81 |     await page.getByTestId('tm-input-project-name').fill(names.project)
   82 |     await page.getByTestId('tm-submit-project').click()
   83 |     await expectToast(page, '项目已创建')
   84 |
   85 |     await selectProjectFilter(page, names.project)
   86 |     await openCreateMenu(page, '领域')
   87 |     await page.getByTestId('tm-input-domain-name').fill(names.domain)
   88 |     await page.getByTestId('tm-submit-domain').click()
   89 |     await expectToast(page, '领域已创建')
   90 |
   91 |     await openCreateMenu(page, 'Task')
   92 |     await expect(page.getByTestId('tm-modal-new-task')).toBeVisible()
   93 |     await antdSelectByLabel(page, 'tm-task-project', names.project)
   94 |     await antdSelectByLabel(page, 'tm-task-domain', names.domain)
   95 |     await page.getByTestId('tm-task-title').fill(names.task)
   96 |     await page.getByTestId('tm-task-requirement').fill('UI 自测需求：未手填推荐')
   97 |     await page.getByTestId('tm-submit-task').click({ force: true })
   98 |     await expect(page.getByText(names.task).first()).toBeVisible({ timeout: 20_000 })
   99 |
  100 |     const card = await boardTaskByTitle(page, names.task)
  101 |     // Action 必须关联子需求：先在 Task 详情维护
  102 |     await addSubtaskViaTaskDetail(page, card, names.subtask)
  103 |     await setTaskReqStage(page, card, '测试中')
  104 |     const cardReady = await boardTaskByTitle(page, names.task)
  105 |     await cardReady.getByTestId('tm-btn-add-action').click()
  106 |     await expect(page.getByTestId('tm-modal-new-action')).toBeVisible()
  107 |     await antdSelectByLabel(page, 'tm-action-subtask', names.subtask)
  108 |     await page.getByTestId('tm-action-title').fill(names.action)
  109 |     await page.getByTestId('tm-action-content').fill('测试内容')
  110 |     await page.getByTestId('tm-action-env').fill('qa')
  111 |     await page.getByTestId('tm-submit-action-publish').click()
  112 |     await expectToast(page, /已保存|发布|创建/)
  113 |
  114 |     await selectProjectFilter(page, names.project)
  115 |     const card2 = await boardTaskByTitle(page, names.task)
  116 |     await expect(card2.getByTestId('tm-task-progress-tip')).toBeVisible()
  117 |     await card2.getByTestId('tm-task-progress-tip').hover()
  118 |     await expect(page.getByRole('tooltip').filter({ hasText: '未手填' })).toBeVisible()
  119 |     await card2.locator('[data-testid^="tm-action-card-"]').first().click()
  120 |     await expect(page.getByTestId('tm-drawer-action')).toBeVisible()
  121 |     await fillInputNumber(page, 'tm-daily-progress', '55')
  122 |     await page.getByTestId('tm-daily-note').fill('本日进展说明：UI自测日更')
  123 |     await page.getByTestId('tm-submit-daily').click()
  124 |     await expectToast(page, /日更|成功|已保存|提交/)
  125 |     await page.keyboard.press('Escape')
  126 |
  127 |     await selectBoardScope(page, '全部')
  128 |     const card3 = await boardTaskByTitle(page, names.task)
  129 |     await expect(card3.getByTestId('tm-task-progress-tip')).toBeVisible({ timeout: 15_000 })
  130 |     await card3.getByTestId('tm-task-progress-tip').hover()
  131 |     await expect(page.getByRole('tooltip').filter({ hasText: '未手填' })).toBeVisible()
  132 |
  133 |     await openTaskDetail(page, card3, '进度')
  134 |     await expect(page.getByTestId('tm-drawer-task')).toBeVisible()
  135 |     await expect(page.getByTestId('tm-task-week-progress')).toBeVisible()
  136 |     await expect(page.getByTestId('tm-task-week-progress').getByText(/未手填 · 按 Action 平均\s*55%/)).toBeVisible()
  137 |     await page.keyboard.press('Escape')
  138 |   })
  139 |
  140 |   test('04 Manager：Action 抽屉显示延续历史（当前周）', async ({ page }) => {
  141 |     // 手动「克隆」API 已下线（切周自动继承取代）；单周 Action 抽屉即显示延续历史 1 周
  142 |     await login(page, 'manager', PASS)
  143 |     await goProjects(page)
  144 |     await openBoardTab(page)
  145 |     await selectProjectFilter(page, names.project)
  146 |     const card = await boardTaskByTitle(page, names.task)
  147 |     await card
  148 |       .locator('[data-testid^="tm-action-card-"]')
  149 |       .filter({ hasText: names.action })
  150 |       .first()
  151 |       .click()
  152 |     await expect(page.getByTestId('tm-drawer-action')).toBeVisible()
  153 |     const lineage = page.getByTestId('tm-action-lineage')
  154 |     await expect(lineage).toBeVisible({ timeout: 15_000 })
  155 |     await expect(lineage).toContainText(/延续历史/)
  156 |     await expect(lineage).toContainText(/1\s*周/)
> 157 |     await expect(lineage).toContainText('当前')
      |                           ^ Error: Timed out 15000ms waiting for expect(locator).toContainText(expected)
  158 |   })
  159 | })
  160 |
```