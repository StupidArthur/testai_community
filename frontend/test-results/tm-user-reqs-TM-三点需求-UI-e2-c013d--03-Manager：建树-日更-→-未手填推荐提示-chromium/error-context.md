# Test info

- Name: TM 三点需求 UI e2e1787793423 >> 03 Manager：建树+日更 → 未手填推荐提示
- Location: D:\代码\testai_community\frontend\e2e\tm-user-reqs.spec.ts:74:3

# Error details

```
Error: locator.click: Test timeout of 120000ms exceeded.
Call log:
  - waiting for getByTestId('tm-project-filter')
    - locator resolved to <div data-testid="tm-project-filter" class="ant-select ant-select-outlined css-dev-only-do-not-override-ynljz7 ant-select-single ant-select-allow-clear ant-select-show-arrow ant-select-show-search">…</div>
  - attempting click action
    2 × waiting for element to be visible, enabled and stable
      - element is visible, enabled and stable
      - scrolling into view if needed
      - done scrolling
      - <div tabindex="-1" class="ant-modal-wrap">…</div> from <div>…</div> subtree intercepts pointer events
    - retrying click action
    - waiting 20ms
    - waiting for element to be visible, enabled and stable
    - element is visible, enabled and stable
    - scrolling into view if needed
    - done scrolling
    - <div class="ant-modal-content">…</div> from <div>…</div> subtree intercepts pointer events
  2 × retrying click action
      - waiting 100ms
      - waiting for element to be visible, enabled and stable
      - element is visible, enabled and stable
      - scrolling into view if needed
      - done scrolling
      - <label title="标题" for="title" class="ant-form-item-required">标题</label> from <div>…</div> subtree intercepts pointer events
  53 × retrying click action
       - waiting 500ms
       - waiting for element to be visible, enabled and stable
       - element is visible, enabled and stable
       - scrolling into view if needed
       - done scrolling
       - <label title="本周负责人" for="owner_id" class="ant-form-item-required">本周负责人</label> from <div>…</div> subtree intercepts pointer events
     - retrying click action
       - waiting 500ms
       - waiting for element to be visible, enabled and stable
       - element is visible, enabled and stable
       - scrolling into view if needed
       - done scrolling
       - <label title="本周负责人" for="owner_id" class="ant-form-item-required">本周负责人</label> from <div>…</div> subtree intercepts pointer events
     - retrying click action
       - waiting 500ms
       - waiting for element to be visible, enabled and stable
       - element is visible, enabled and stable
       - scrolling into view if needed
       - done scrolling
       - <label title="标题" for="title" class="ant-form-item-required">标题</label> from <div>…</div> subtree intercepts pointer events
     - retrying click action
       - waiting 500ms
       - waiting for element to be visible, enabled and stable
       - element is visible, enabled and stable
       - scrolling into view if needed
       - done scrolling
       - <label title="标题" for="title" class="ant-form-item-required">标题</label> from <div>…</div> subtree intercepts pointer events
  2 × retrying click action
      - waiting 500ms
      - waiting for element to be visible, enabled and stable
      - element is visible, enabled and stable
      - scrolling into view if needed
      - done scrolling
      - <label title="本周负责人" for="owner_id" class="ant-form-item-required">本周负责人</label> from <div>…</div> subtree intercepts pointer events
  - retrying click action
    - waiting 500ms

    at selectProjectFilter (D:\代码\testai_community\frontend\e2e\helpers.ts:224:18)
    at D:\代码\testai_community\frontend\e2e\tm-user-reqs.spec.ts:110:5
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
    - text: 我的 Task（1）
    - combobox
    - text: 【UI自测】e2e1787793423 项目
    - button "plus 新建 down":
      - img "plus"
      - text: 新建
      - img "down"
    - text: 【UI自测】e2e1787793423 Task 进行中 【UI自测】e2e1787793423 项目/【UI自测】e2e1787793423 领域 本周无 Action 0%
    - img "exclamation-circle"
    - button "操作 down":
      - text: 操作
      - img "down"
    - button "+ Action"
    - text: 测试中 测试开始 08-01 ~ 预计结束 08-01 · 需求：UI 自测需求：未手填推荐 · 负责人 测试管理员
    - img "No data"
    - text: 本周尚无 Action — 点「+ Action」新建（须选子需求）
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
- dialog "新建 Action · 【UI自测】e2e1787793423 Task":
  - button "Close":
    - img "close"
  - text: 新建 Action · 【UI自测】e2e1787793423 Task
  - paragraph: 该 Task 暂无子需求，请先在 Task 详情维护子需求后再创建 Action
  - text: "* 关联子需求"
  - combobox "* 关联子需求"
  - text: 请先在 Task 详情维护子需求 请选择子需求 * 标题
  - textbox "* 标题": 【UI自测】e2e1787793423 Action
  - text: 26 / 300 * 本周负责人
  - combobox "* 本周负责人"
  - text: 测试管理员（manager） 测试内容
  - textbox "测试内容"
  - text: 4 / 1000 环境
  - textbox "环境": qa
  - text: 2 / 300
  - button "仅存草稿"
  - button "保存并发布"
```

# Test source

```ts
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
  175 |  * 将 Task 需求进展改到指定阶段（含必填日期）。
  176 |  * stageLabel 例：测试中 / 测试完成
  177 |  * dateFieldLabels 例：['测试开始时间','预计测试结束'] 或 '测试结束时间'
  178 |  */
  179 | export async function setTaskReqStage(
  180 |   page: Page,
  181 |   card: import('@playwright/test').Locator,
  182 |   stageLabel: string,
  183 |   dateFieldLabels?: string | string[],
  184 | ) {
  185 |   await openTaskDetail(page, card, '进度')
  186 |   await antdSelectByLabel(page, 'tm-task-req-stage', stageLabel)
  187 |   const labels = !dateFieldLabels
  188 |     ? []
  189 |     : Array.isArray(dateFieldLabels)
  190 |       ? dateFieldLabels
  191 |       : [dateFieldLabels]
  192 |   const fields =
  193 |     labels.length > 0
  194 |       ? labels
  195 |       : stageLabel === '测试中'
  196 |         ? ['测试开始时间', '预计测试结束']
  197 |         : stageLabel === '测试完成'
  198 |           ? ['测试结束时间']
  199 |           : []
  200 |   for (const label of fields) {
  201 |     const field = page.getByLabel(label)
  202 |     await expect(field).toBeVisible()
  203 |     await field.click()
  204 |     const panel = page.locator('.ant-picker-dropdown:not(.ant-picker-dropdown-hidden)').last()
  205 |     await panel
  206 |       .locator('.ant-picker-cell-in-view')
  207 |       .filter({ hasNot: page.locator('.ant-picker-cell-disabled') })
  208 |       .first()
  209 |       .click()
  210 |   }
  211 |   const change = page.getByLabel(/变更说明/)
  212 |   if (await change.count()) {
  213 |     await change.fill('E2E 改阶段')
  214 |   }
  215 |   await page.getByTestId('tm-task-save').click()
  216 |   await expectToast(page, /已保存|更新/)
  217 |   await closeTaskDrawer(page)
  218 | }
  219 |
  220 | export async function selectProjectFilter(page: Page, projectName: string) {
  221 |   // 工作台项目筛选：支持搜索，避免项目多时虚拟列表点不到
  222 |   const filter = page.getByTestId('tm-project-filter')
  223 |   if (await filter.count()) {
> 224 |     await filter.click()
      |                  ^ Error: locator.click: Test timeout of 120000ms exceeded.
  225 |   } else {
  226 |     await page.getByPlaceholder('按项目筛选').click()
  227 |   }
  228 |   const search = page.locator('.ant-select-focused input.ant-select-selection-search-input:not([readonly])')
  229 |   const dropdown = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
  230 |   await expect(dropdown).toBeVisible({ timeout: 10_000 })
  231 |   if ((await search.count()) > 0) {
  232 |     await search.first().fill('')
  233 |     await search.first().type(projectName, { delay: 10 })
  234 |   }
  235 |   await dropdown
  236 |     .locator('.ant-select-item-option', { hasText: projectName })
  237 |     .first()
  238 |     .click()
  239 |   await expect(filter).toContainText(projectName, { timeout: 8_000 })
  240 | }
  241 |
```