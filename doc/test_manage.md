# 测试任务管理（Test Manage / 项目管理）

> 文档版本：2026-08-10  
> 状态：**一期已实现（Domain → Task → Action）**  
> 模块：`backend/app/test_manage/` · `frontend/src/test_manage/`  
> 入口：顶栏/门户「项目管理」→ `/projects` · API `/api/test-manage`  
> **产品使用说明（谁填什么、日更/周报、界面操作）**：[test_manage_product_guide.md](./test_manage_product_guide.md)  
> 页内为简略版；完整版经 `frontend/public/docs/test_manage_product_guide.md` 提供下载（与上文档同源，改规则时两边一起改）。

---

## 1. 层级

```
Project（组织容器，如 TPT V2.1；创建维度 + 看板可选筛选）
  └── Domain（平台 / Agent / 交付 / 定制…）
        └── Task（需求内容 + 测试负责人 + 测试人员；可更新并记日志）
              └── Action（周实例：测试内容 / 环境；草稿可改，发布后锁定）
```

- **Project**：创建与组织用；看板上可按项目筛选，主汇总仍是 **周 × Task**。Admin/Manager 可**归档**（列表隐藏）或**永久删除**（级联清理下属数据）。  
- **Task**：主题线；负责人写其下 Action。需求内容上限 **5000** 字。**Task 周进度**在周结束前由 Admin/Manager/Task 负责人填写，供周报；未填则展示本周 Action 进度平均并提示「未手填」。  
- **Action**：周轮回（默认周三 17:00 → 下周三 17:00，**周结束可配置**）；本周负责人只能从 Task **测试负责人 + 测试人员** 中选；测试内容上限 **1000** 字，环境上限 **300** 字。可通过 `source_action_id` 查看**延续历史**（跨周次数与每周风险）。

---

## 2. 权限（A1 / B1）

| 操作 | Admin / Manager | Task 测试负责人 | Action 本周负责人（非 lead） | Task 测试人员（非该 Action owner） |
|------|-----------------|-----------------|------------------------------|-------------------------------------|
| **建 / 归档 / 删除 Project**；建 Domain | 是 | 否 | 否 | 否 |
| 编辑 Task / 变更 Task 状态 | 是 | 是 | 否 | 否 |
| **填写本周 Task 进度** | 是 | 是 | 否 | 否 |
| **设置本周结束时刻** | 是 | 否 | 否 | 否 |
| 编辑 Task / 创建草稿 Action | 是 | 是 | 否 | 否 |
| 改草稿 Action 字段 | 是 | 是 | 否 | 否 |
| **变更 Action 状态**（发布/完成；**不可取消**） | 是 | 是 | **是（自己的）** | 否 |
| **写日更** | 是 | **仅自己的 Action** | **仅自己的 Action** | **否** |
| 追加更正 | 是 | 是（本 Task） | 是（自己的 Action） | 否 |

说明：曾存在「Task 下任意测试人员可给任意 Action 写日更」的 bug，已按 B1 收紧为 **仅 owner 或管理员**。

默认账号：**manager / 123456**（角色 `Manager`，启动时 bootstrap 保证存在）。

---

## 3. Action 规则

| 规则 | 说明 |
|------|------|
| 草稿 | 点开 Action 卡片可编辑标题/负责人/测试内容/环境；可保存或发布 |
| 发布后 | 标题/本周负责人/测试内容/环境等**全部锁定**（本周内不改派）；纠错用「更正说明」 |
| 状态机 | `draft→published`；`published→done`；**`done` 终态不可重开**；**不支持取消**。**标记完成要求最新日更进度 = 100%**（常量 `ACTION_DONE_MIN_PROGRESS`）。本人 / Task 负责人 / 管理员可操作（抽屉「变更状态」） |
| 日更 | 仅 **进行中**；owner/管理员；**说明去空白后非空（无最少字数）**；**进度不倒退**；**仅当天**；默认 **19:50** 后锁定（企微日报 **20:00**）；**切周日（周结束当天）日更仍写刚结束周**；已完成不可日更；进度/风险取最新一条 |
| 更正 | 发布后仅**追加**更正说明；时间线正序（最新在底）；提交成功 toast「追加成功」并自动滚到时间线底部 |
| 看板 KPI | 「已发布」仅计 `published`，「完成」另计 `done`（与周报口径一致） |
| 看板风险 | **不**再在 Task 卡片上放大块「风险 N 项」；仅 Action 卡片内最多 **3 行**省略展示 |
| 周截止 | `due_at` = 当前活动周 `week_end`（Admin/Manager 可改；改后同步本周 Action） |
| 延续 | `GET /actions/{id}/lineage`：沿 `source_action_id` 回溯，展示跨越周数与每周风险 |

---

## 3b. 业务周与周报发送时刻

| 项 | 说明 |
|----|------|
| 默认周 | 周三 **17:00** → 下周三 **17:00**（UTC+8）；表 `tm_week_periods` |
| 可配结束 | `PUT /week/end`（Admin/Manager）；须晚于现在与本周起点；同步本周 Action.`due_at` |
| 周报发送 | `compute_weekly_push_at`：**一律周结束 + 15 分钟**（默认周三 17:00 → **17:15**） |
| Windows 计划任务 | 周报触发建议每 **1 分钟** tick，由脚本/进程内判定是否到 `weekly_push_at`（到点后约 1 分钟内发出）；改安装脚本后需**重装计划任务** |

---

## 4. 字数上限

| 字段 | 上限 |
|------|------|
| Task 需求内容 | 5000 |
| Action 测试内容 | 1000 |
| Action 环境 | 300 |
| 日更风险与说明、更正说明等 | 1000 |

---

## 5. 表（`tm_*`，schema 版本重建）

启动时若 `tm_schema_meta.version` ≠ 当前版本，则 **DROP 重建**（开发期丢旧数据）。  
新增周周期 / Task 周进度表采用 **增量 `create_all`**（不 bump schema 版本，避免清空业务数据）。

| 表 | 用途 |
|----|------|
| tm_projects / tm_domains | 项目、领域 |
| tm_tasks | Task |
| tm_task_testers | 测试人员 |
| tm_task_update_logs | Task 更新历史 |
| tm_actions | 周 Action（`test_content` / `environment`） |
| tm_action_corrections | 更正说明追加 |
| tm_daily_updates | 日更 |
| tm_week_periods | 业务周起点/结束（可配） |
| tm_task_week_progress | Task 按周手填进度（周报） |
| tm_push_snapshots | 企微推送风险快照（日报/周报各一份） |
| tm_push_runs | 推送幂等记录（仅成功发送占坑；空跑不写） |

---

## 6. 看板（项目管理首页）

- 默认 Tab「**本周大屏**」：领导汇报视图——KPI、周×Task 明细（**每条非草稿 Action 均展示子行，含仅 1 条**）、风险聚焦侧栏、全屏汇报；支持 **本周 / 历史**（历史下拉最多 10 周，只读）。**草稿 Action 不进入大屏**（KPI/明细均不含；仅草稿的 Task 整行隐藏；工作台仍可见草稿）。Task 进度列：手填优先；未手填时提示「未手填 Task 进度」，数值为 Action 平均。  
- 「工作台」：同一周切换；历史周隐藏新建入口；可看周报预计发送时刻；Admin/Manager 可改周结束。筛选用下拉（scope / 项目）；管理员「新建」下拉；Task 卡「操作」下拉（详情 / 进度 / 归档 / 删除）。**仅支持复制上周 Action**（同 Task、上一业务周 → 本周草稿；单条 / 一键全部；点标题预览）。
- 大屏明细筛选（需关注 / 全部 / 已完成、领域）亦为下拉，减少 chip 占位。  
  - 筛选条在双栏上方；左右面板标题与内容区顶对齐、等高；明细默认「需关注」，多 Action 折叠，表体定高滚动。  
  - **KPI 分两行**：Task / Action 维度各自统计；Action「均进度」= 算术平均（旁侧文案只反映进度，不绑风险）；「有风险」仅计 **进行中** Action。明细「负责人」：**Task 测试负责人在前**，多人「甲 等N人」。  
- Tab「工作台」：创建 Project/Domain/Task/Action、卡片操作与日更入口；Task 抽屉填**本周进度**；Action 抽屉看**延续历史**。  
- Tab「我的 Action」：仅 **当前周** 且 **负责人是当前登录用户** 的 Action。  
- 大屏「**已完成**」Tab：**仅 Task.status = done / cancelled**；不因 Action 全做完而归入。

---

## 6b. 钉钉群推送（日报 / 周报）

基于日更「开放风险」快照对比（R1），推送到钉钉群机器人。

**周归属**：汇总按库表 `tm_week_periods` 的活动周 `week_key`（`get_daily_context_period`），与看板 Action 一致；勿仅用经典「周三 17:00」推算，否则自定义 `week_end` 后会出现「看板有数据、推送汇总为 0」。

| 项 | 说明 |
|----|------|
| 配置 | `.env`：`DINGTALK_WEBHOOK_URL`、`DINGTALK_KEYWORD=msg`、`DINGTALK_PUSH_ENABLED`；可选 `DINGTALK_DAILY_PUSH_*` |
| 定时（推荐） | Windows 计划任务 + keep-awake；单条 ≤4096；用计划任务时 `DINGTALK_PUSH_ENABLED=false`；任务用 `-WindowStyle Hidden` **不弹黑窗**（改后需重装计划任务） |
| 半小时联调（临时） | 生产：`install_halfhour_push_test.cmd`（10:00–21:00 半小时，整点日报/半点周报，`FORCE=1`，禁用原 Daily/Weekly）；测完 `restore_normal_push_schedule.cmd` 并恢复幂等 `true`。入口仍走 `wecom_push_daily/weekly.ps1`，与 20:00 同路径 |
| 幂等开关 | `DINGTALK_PUSH_IDEMPOTENCY_ENABLED`（日报）；`DINGTALK_WEEKLY_IDEMPOTENCY_ENABLED`（周报，默认 **true** 同周只发一次；调试可设 false）；计划任务亦可 `TM_PUSH_FORCE=1` |
| 日报 | Action 视角；每天 1 条 |
| 周报 | Task 视角；标题 **`【TPT测试周报】`**；**优先用手填 Task 周进度**，未填用 Action 平均；风险挂在 Task 下并标注 Action+负责人；Task 仅进行中可加 Action；**本周 0 Action 的 Task 不计入周报/日报 KPI 的 task_count**（看板仍标红空卡片） |
| 需关注 | 开放风险或进行中 Action；**不含纯草稿**；大屏明细亦不展示草稿 Action |
| 切周 | 工作台标红无 Action 的 Task；负责人「复制上周 / 新建」 |
| 已解决 / 不计开放风险 | 最新日更 `risk_blocker` 为空；或 Action 已 **完成/草稿**（及历史取消；完成态遗留风险文案不再进日报与大屏） |
| 过长 | ≤4096：先确定性缩短条数，再硬截断（**不调 AI**，保证定时必发） |
| 备份定时 | 日报 **17:12** 一次 + **20:00～20:04** 共 5 次（幂等，成功一次即可）；周报由 `weekly_push_at`（`week_end+15min`）决定，计划任务建议 **1 分钟**一轮；周报幂等默认开（同周只发一次） |
| 定时 | 进程内轮询（`run.py`）：日报默认每天 **20:00**；周报按周期 `weekly_push_at`。日更当日 **19:50** 后锁定。**生产推荐 Windows 计划任务，见上** |
| 手动 | `POST /api/test-manage/push/daily|weekly`（Admin/Manager）；`dry_run` / `force`；未配置 webhook 且非 dry_run → 400 |
| 调试脚本 | `backend/scripts/trigger_wecom_push.py`（改 `__main__` 参数，勿用 CLI） |

---

## 7. 使用提示

1. 用 **manager / 123456**（或 Admin）登录 → 项目管理。  
2. 新建项目 → 领域 → Task（指定负责人与测试人员）。  
3. 负责人在 Task 下新建本周 Action（负责人下拉仅含参与者）→ 草稿点开可改 → 发布后由 **该 Action 负责人** 写日更。  
4. 字段写错：追加「更正说明」，不要改已发布字段（含本周负责人）。  
5. **周结束前**在 Task 抽屉填写「本周 Task 进度」（推荐填 Action 平均）；未填大屏/周报会用平均值并提示。  
6. Admin/Manager 可在工作台改「周结束」；界面会显示推导出的周报发送时刻。  
7. 开发环境 `python run.py` 默认开启 reload；改路由后若仍 404，请重启后端。  
8. **真实测试计划灌数（本地）**：在 `backend` 目录执行  
   `python scripts/seed_real_test_plan.py`  
   （清空「TPT v2.1」旧 Task/Action **并清空推送快照**；约 **8 个大 Task**，原表小项作为 Action；原表划掉/无人回落到 Task 负责人；占位账号「无」禁止登录；密码 `123456`。）  
9. **企微推送调试**：先 `dry_run=true` 预览，再 `force=true` 真发；**推荐** Windows 计划任务（见 §6b），勿依赖 `run.py` 常驻。改周报触发频率后请重跑 `install_wecom_scheduled_tasks.ps1`。  
10. **schema 重建**：`tm_schema_meta.version` 变更会 DROP 重建 `tm_*` 表并**清空测试任务数据**；重建后执行 `seed_real_test_plan.py`。周周期/进度表为增量建表，一般不必 bump。  
11. 用户真实姓名：Admin 在「用户管理」维护；启动回填**仅补空值**，不覆盖手工修改。见 [user_manual.md](./user_manual.md) §7。

---

## 8. 自测

```powershell
cd backend
# 单元/边界 + 全场景 + 周三切周（推荐）
python -m pytest tests/test_tm_full_regression.py tests/test_tm_full_regression_extra.py tests/test_tm_wednesday_cutover.py tests/test_test_manage.py tests/test_test_manage_edge.py tests/test_test_manage_audit.py tests/test_wecom_push.py tests/test_week_period.py -q
# 后端已启动时：对开发库 TPT v2.1 现场 API 回归（【回归】前缀数据）
python scripts/tm_live_regression_tpt.py
# 清理自动化残留（【E2E】/【回归】/【测试】项目与 e2e*、tm_live_* 账号；保留 TPT 等正式数据）
python scripts/cleanup_tm_test_data.py

cd ..\frontend
npm test   # boardUi：空卡标红 / Toast 文案 / A1 / 看板过滤

# Playwright UI E2E（现网开发库；全程页面点击创建数据，不用 API 灌数）
# 前置：后端 48010 + 前端 vite（默认 3003，见 playwright.config）
$env:PW_DISABLE_TS_ESM='1'   # Windows/Node 必设，否则可能无输出卡住
$env:E2E_RUN_ID=("e2e" + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
npm run test:e2e -- e2e/tm-ui-full.spec.ts
```

覆盖点含：A1 owner 候选人、B1 日更权限矩阵、Tester 交叉、字数上限、草稿锁定与更正、发布后负责人锁定、19:50 日更锁定、**周三切周日更写刚结束周**、风险已解决语义、空周看板过滤、历史周、clone 不带风险、状态机、企微 dry_run 口径（草稿风险不计、空 Task 不计 KPI）、**周报发送时刻规则 / Task 周进度未填回退** 等。  
**UI E2E**：登录/Admin 建用户 → Manager 建项目/领域/Task/Action → 日更与风险 → 更正 → scope/大屏 → Task 完成 → 历史周只读（前缀 `【E2E】`）。  
详细矩阵见 [dev/tm_regression_report_2026-07-31.md](./dev/tm_regression_report_2026-07-31.md)。
