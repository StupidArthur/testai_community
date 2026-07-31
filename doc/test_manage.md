# 测试任务管理（Test Manage / 项目管理）

> 文档版本：2026-07-29  
> 状态：**一期已实现（Domain → Task → Action）**  
> 模块：`backend/app/test_manage/` · `frontend/src/test_manage/`  
> 入口：顶栏/门户「项目管理」→ `/projects` · API `/api/test-manage`  
> **产品使用说明（谁填什么、日更/周报、界面操作）**：[test_manage_product_guide.md](./test_manage_product_guide.md)

---

## 1. 层级

```
Project（组织容器，如 TPT V2.1；创建维度 + 看板可选筛选）
  └── Domain（平台 / Agent / 交付 / 定制…）
        └── Task（需求内容 + 测试负责人 + 测试人员；可更新并记日志）
              └── Action（周实例：测试内容 / 环境；草稿可改，发布后锁定）
```

- **Project**：创建与组织用；看板上可按项目筛选，主汇总仍是 **周 × Task**。  
- **Task**：主题线；负责人写其下 Action。需求内容上限 **5000** 字。  
- **Action**：周轮回（周三 18:00 → 下周三 18:00）；本周负责人只能从 Task **测试负责人 + 测试人员** 中选；测试内容上限 **1000** 字，环境上限 **300** 字。卡片上的「负责人」若未写明「本周」，请以 Action 的 **本周负责人** 为准（与 Task 测试负责人可以不是同一人）。

---

## 2. 权限（A1 / B1）

| 操作 | Admin / Manager | Task 测试负责人 | Action 本周负责人（非 lead） | Task 测试人员（非该 Action owner） |
|------|-----------------|-----------------|------------------------------|-------------------------------------|
| 编辑 Task / 变更 Task 状态 | 是 | 是 | 否 | 否 |
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
| 日更 | 仅 **进行中**；owner/管理员；**说明去空白后非空（无最少字数）**；**进度不倒退**；**仅当天**；默认 **19:50** 后锁定（企微日报 **20:00**）；**切周日（周三）日更仍写上一汇报周**；已完成不可日更；进度/风险取最新一条 |
| 更正 | 发布后仅**追加**更正说明；时间线正序（最新在底）；提交成功 toast「追加成功」并自动滚到时间线底部 |
| 看板 KPI | 「已发布」仅计 `published`，「完成」另计 `done`（与周报口径一致） |
| 看板风险 | **不**再在 Task 卡片上放大块「风险 N 项」；仅 Action 卡片内最多 **3 行**省略展示 |
| 周三截止 | `due_at` = 本周窗口结束；不自动生成下周 Action |

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

| 表 | 用途 |
|----|------|
| tm_projects / tm_domains | 项目、领域 |
| tm_tasks | Task |
| tm_task_testers | 测试人员 |
| tm_task_update_logs | Task 更新历史 |
| tm_actions | 周 Action（`test_content` / `environment`） |
| tm_action_corrections | 更正说明追加 |
| tm_daily_updates | 日更 |
| tm_push_snapshots | 企微推送风险快照（日报/周报各一份） |
| tm_push_runs | 推送幂等记录（仅成功发送占坑；空跑不写） |

---

## 6. 看板（项目管理首页）

- 默认 Tab「**本周大屏**」：领导汇报视图——KPI、周×Task 明细、风险聚焦侧栏、全屏汇报；支持 **本周 / 历史**（历史下拉最多 10 周，只读）。
- 「工作台」：同一周切换；历史周隐藏新建入口。  
  - 筛选条在双栏上方；左右面板标题与内容区顶对齐、等高；明细默认「需关注」，多 Action 折叠，表体定高滚动。  
  - **KPI 分两行**：Task / Action 维度各自统计；Action「均进度」= 算术平均（旁侧文案只反映进度，不绑风险）；「有风险」仅计 **进行中** Action。明细「负责人」：**Task 测试负责人在前**，多人「甲 等N人」。  
- Tab「工作台」：创建 Project/Domain/Task/Action、卡片操作与日更入口。  
- Tab「我的 Action」：仅 **当前周** 且 **负责人是当前登录用户** 的 Action。  
- 大屏「**已完成**」Tab：**仅 Task.status = done / cancelled**；不因 Action 全做完而归入。

---

## 6b. 企微群推送（日报 / 周报）

基于日更「开放风险」快照对比（R1），推送到企业微信群机器人。

| 项 | 说明 |
|----|------|
| 配置 | `.env`：`WECOM_WEBHOOK_URL`、`WECOM_PUSH_ENABLED`；可选 `WECOM_DAILY_PUSH_*` / `WECOM_WEEKLY_PUSH_*` |
| 定时（推荐） | Windows 计划任务 + keep-awake；单条 ≤4096，超长先 AI 再砍行；用计划任务时 `WECOM_PUSH_ENABLED=false` |
| 幂等开关 | `WECOM_PUSH_IDEMPOTENCY_ENABLED`（false=已发仍可再发）；计划任务脚本亦可 `TM_PUSH_FORCE=1` |
| 日报 | Action 视角；每天 1 条 |
| 周报 | Task 视角；风险挂在 Task 下并标注 Action+负责人；Task 仅进行中可加 Action；**本周 0 Action 的 Task 不计入周报/日报 KPI 的 task_count**（看板仍标红空卡片） |
| 需关注 | 开放风险或进行中 Action；**不含纯草稿** |
| 切周 | 工作台标红无 Action 的 Task；负责人「复制上周 / 新建」 |
| 已解决 / 不计开放风险 | 最新日更 `risk_blocker` 为空；或 Action 已 **完成/草稿**（及历史取消；完成态遗留风险文案不再进日报与大屏） |
| 过长 | ≤4096：先确定性缩短条数，再硬截断（**不调 AI**，保证定时必发） |
| 备份定时 | 日报 20:00 + **20:15**；周报周三 17:30 + **17:45**（已成功则幂等跳过） |
| 定时 | 进程内轮询（`run.py`）：日报默认每天 **20:00**；周报默认周三 17:30（UTC+8）。日更当日 **19:50** 后锁定。**生产推荐 Windows 计划任务，见上** |
| 手动 | `POST /api/test-manage/push/daily|weekly`（Admin/Manager）；`dry_run` / `force`；未配置 webhook 且非 dry_run → 400 |
| 调试脚本 | `backend/scripts/trigger_wecom_push.py`（改 `__main__` 参数，勿用 CLI） |

---

## 7. 使用提示

1. 用 **manager / 123456**（或 Admin）登录 → 项目管理。  
2. 新建项目 → 领域 → Task（指定负责人与测试人员）。  
3. 负责人在 Task 下新建本周 Action（负责人下拉仅含参与者）→ 草稿点开可改 → 发布后由 **该 Action 负责人** 写日更。  
4. 字段写错：追加「更正说明」，不要改已发布字段（含本周负责人）。  
5. 开发环境 `python run.py` 默认开启 reload；改路由后若仍 404，请重启后端。  
6. **真实测试计划灌数（本地）**：在 `backend` 目录执行  
   `python scripts/seed_real_test_plan.py`  
   （清空「TPT v2.1」旧 Task/Action **并清空推送快照**；约 **8 个大 Task**，原表小项作为 Action；原表划掉/无人回落到 Task 负责人；占位账号「无」禁止登录；密码 `123456`。）  
7. **企微推送调试**：先 `dry_run=true` 预览，再 `force=true` 真发；**推荐** Windows 计划任务（见 §6b），勿依赖 `run.py` 常驻。  
8. **schema 重建**：`tm_schema_meta.version` 变更会 DROP 重建 `tm_*` 表并**清空测试任务数据**；重建后执行 `seed_real_test_plan.py`。  
9. 用户真实姓名：Admin 在「用户管理」维护；启动回填**仅补空值**，不覆盖手工修改。见 [user_manual.md](./user_manual.md) §7。

---

## 8. 自测

```powershell
cd backend
# 单元/边界 + 全场景 + 周三切周（推荐）
python -m pytest tests/test_tm_full_regression.py tests/test_tm_full_regression_extra.py tests/test_tm_wednesday_cutover.py tests/test_test_manage.py tests/test_test_manage_edge.py tests/test_test_manage_audit.py tests/test_wecom_push.py -q
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

覆盖点含：A1 owner 候选人、B1 日更权限矩阵、Tester 交叉、字数上限、草稿锁定与更正、发布后负责人锁定、19:50 日更锁定、**周三切周日更写刚结束周**、风险已解决语义、空周看板过滤、历史周、clone 不带风险、状态机、企微 dry_run 口径（草稿风险不计、空 Task 不计 KPI）等。  
**UI E2E**：登录/Admin 建用户 → Manager 建项目/领域/Task/Action → 日更与风险 → 更正 → scope/大屏 → Task 完成 → 历史周只读（前缀 `【E2E】`）。  
详细矩阵见 [dev/tm_regression_report_2026-07-31.md](./dev/tm_regression_report_2026-07-31.md)。
