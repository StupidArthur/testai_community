# 项目管理全场景回归报告（2026-07-31，扩充版 v2）

## 环境

- 自动化：pytest 独立库 `database_test.sqlite`
- 前端：vitest 纯逻辑（空卡 / Toast 文案 / A1 / 看板过滤）
- 现场：开发库 **TPT v2.1**，临时数据前缀 `【回归】` / `【回归+】` / `【切周】`
- 企微：仅 `dry_run`

## 结果总览

| 套件 | 结果 |
|------|------|
| `tests/test_tm_full_regression.py` | 8 passed |
| `tests/test_tm_full_regression_extra.py` | 24 passed |
| `tests/test_tm_wednesday_cutover.py` | **9 passed**（新增） |
| 上述 + `test_test_manage*` + `test_wecom_push` | **116 passed**（含切周 W9） |
| `frontend` `npm test`（boardUi） | **11 passed** |
| `scripts/tm_live_regression_tpt.py` | FAIL count 0（约 45 项） |
| Playwright `e2e/tm-ui-full.spec.ts` | **21 passed**（现网开发库，纯 UI 建数） |

## 本轮新增：周三切周

| # | 场景 | 期望 | 结果 |
|---|------|------|------|
| W1 | 周三全天 `daily_context` = 刚结束周；≥18:00 `current` = 新周 | 纯函数 | PASS |
| W2 | 非周三 `daily_context` == `current` | 纯函数 | PASS |
| W3 | 切周后：新周 Action 不可日更；旧周 Action 可日更 | 400 / 200 | PASS |
| W4 | 切周前（17:59）本周 Action 可日更 | 200 | PASS |
| W5 | 切周后默认看板 = 新周；旧 Action 仅历史周可见 | PASS | PASS |
| W6 | 切周后空 Task 仍出现在新周看板 | 空卡 + can_add | PASS |
| W7 | clone-candidates = 刚结束周；clone 进新周且不带风险 | PASS | PASS |
| W8 | 日报 dry_run / open_risks 用 daily_context，含旧周风险词 | PASS | PASS |
| W9 | 切周后周三 19:51：旧周 Action 仍受日更锁定 | 400「截止」 | PASS |

## 本轮新增：前端 UI 契约（vitest）

| # | 场景 | 结果 |
|---|------|------|
| U1 | 空卡标红：当前周 + 0 Action + can_add | PASS |
| U2 | 历史周 / 有 Action / done → 不标红 | PASS |
| U3 | +Action 按钮显隐 | PASS |
| U4 | Task 保存 Toast/Alert 文案 `已保存 · 测试负责人：…` | PASS |
| U5 | A1 参与者过滤 | PASS |
| U6 | 看板 mine/other/all | PASS |
| U7 | 空卡 Empty 三种文案 | PASS |

实现：`frontend/src/test_manage/utils/boardUi.ts`（页面已改用该模块）。

## 本轮新增：Playwright UI E2E（现网开发库）

约定：**不调用业务 API 灌数**；Admin 在用户管理页建 Engineer；Manager 在工作台逐个新建项目/领域/Task/Action；数据前缀 `【E2E】` + `E2E_RUN_ID`。

| # | 场景 | 结果 |
|---|------|------|
| E01 | 未登录访问 `/projects` → 登录页 | PASS |
| E02 | Admin 登录 → Portal / 导航 | PASS |
| E03 | Admin 用户管理创建 4 个 Engineer | PASS |
| E04 | Manager：新建项目 / 领域 | PASS |
| E05–E06 | 新建 Task（含空卡 / 待完成） | PASS |
| E07 | 路人 Engineer：无新建；看不到无关空 Task | PASS |
| E08 | Task 抽屉改需求 + 成功提示 | PASS |
| E09–E11 | +Action 保存并发布（多条） | PASS |
| E12 | 日更 + 风险；UI 禁止倒退（min / 减号禁用）；清空风险 | PASS |
| E13 | 更正说明；未满 100% 完成按钮禁用 | PASS |
| E14 | Tester 不可日更他人 Action | PASS |
| E15 | 「我的 Action」可见本人负责项 | PASS |
| E16 | 看板 scope：我的 / 其他 / 全部 | PASS |
| E17 | 大屏 chip / 风险面板 / 周切换 | PASS |
| E18 | Task 标完成 → 无 +Action | PASS |
| E19 | 日更到 100% 并标记完成 | PASS |
| E20 | 历史周只读 Alert；无新建 | PASS |
| E21 | 本轮实体仍在看板 | PASS |

说明：后端「进度不可倒退」仍由 pytest 覆盖；E2E 断言 InputNumber `aria-valuemin` 与减号禁用（真实 UI 层防护）。

## 仍未覆盖（可选下一轮）

- 多角色 Select 精选 lead/tester（Ant Select 搜索偶发不稳，本轮负责人默认 Manager）
- `tm-ui-extra.spec.ts`（clone / 使用说明等补充用例，待打磨）
- 企微真发、19:50 锁定的浏览器时钟模拟

## 如何复跑

```powershell
cd backend
python -m pytest tests/test_tm_full_regression.py tests/test_tm_full_regression_extra.py tests/test_tm_wednesday_cutover.py tests/test_test_manage.py tests/test_test_manage_edge.py tests/test_test_manage_audit.py tests/test_wecom_push.py -q
python scripts/tm_live_regression_tpt.py

cd ..\frontend
npm test

# UI E2E（后端 48010 + 前端已起；Windows 必设 PW_DISABLE_TS_ESM）
$env:PW_DISABLE_TS_ESM='1'
$env:E2E_RUN_ID=("e2e" + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
npm run test:e2e -- e2e/tm-ui-full.spec.ts
```
