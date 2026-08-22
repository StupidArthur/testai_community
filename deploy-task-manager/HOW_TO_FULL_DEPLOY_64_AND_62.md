# 端到端操作手册：开发机 → 64 生产代码 + OpenAPI → 62 定时

> 目标：64 用**应用机器人**把生产数据发到开发机同款钉钉群（带清晰截图）；62 定时触发并反馈成功/失败。  
> 原则：每做完一步就做「检验」，不通过不要进入下一步。  
> 日期：2026-08-22

---

# 阶段 0：开始前（两边都看一眼）

## 0.1 角色分工（先记住）

| 机器 | 做什么 |
|------|--------|
| 开发机 | 写代码、自测 OpenAPI 发图、`git push`、`npm run build` |
| 64 | `git pull`、覆盖 `frontend/dist`、配 OpenAPI、跑网站；**禁用**本机日/周报计划任务 |
| 62 | 定时调 64 推送 API；平台 webhook 反馈成败 |

## 0.2 不要做的事

- 不要用开发机 `.env` **整文件覆盖** 64 `.env`
- 不要覆盖 64 的 `database_prod.sqlite` / `.venv`
- 不要在 64 再跑 `install_wecom_scheduled_tasks.ps1`（改由 62 调度）
- 不要把 `DINGTALK_APP_SECRET` 发到钉钉群/聊天

## 0.3 开发机确认 OpenAPI 本地已通

本地 `.env` 应有（值非空）：

```ini
DINGTALK_APP_KEY=...
DINGTALK_APP_SECRET=...
DINGTALK_ROBOT_CODE=...
DINGTALK_OPEN_CONVERSATION_ID=...
```

本地能发带截图日报后再开始下面步骤。

---

# 阶段 1：开发机 — 提交并推送代码

在 **开发机** PowerShell：

## 1.1 进入仓库

```powershell
cd D:\代码\testai_community
git status
git branch
```

**检验：** 当前分支正确（常见 `main` / `master` / 你们发布分支）。

## 1.2 查看改动（确认推送内容包含钉钉 OpenAPI 相关）

```powershell
git status
git diff --stat
```

至少应包含后端推送相关（若你本地已有）：

- `backend/app/test_manage/dingtalk_client.py`
- `backend/app/test_manage/push_service.py`
- `backend/app/platform/config.py`
- 以及本次其它要上生产的改动

**不要**把这些加入提交：

- `.env`、`database*.sqlite`、`node_modules`、本机密钥

## 1.3 提交（按你们规范；示例）

```powershell
git add backend/app/test_manage/dingtalk_client.py
git add backend/app/test_manage/push_service.py
git add backend/app/platform/config.py
# 按需继续 add 其它本次要上线的文件
# 不要：git add .env

git status
git commit -m "prod: 钉钉应用机器人 OpenAPI 推送与相关修复"
```

**检验：**

```powershell
git log -1 --oneline
```

应看到刚提交的说明。

## 1.4 推送到远程

```powershell
git push
```

若提示要设 upstream：

```powershell
git push -u origin HEAD
```

**检验：**

```powershell
git status
```

应显示 `Your branch is up to date with 'origin/...'`（或至少已 push 成功无报错）。

## 1.5 前端打包（有前端改动时必做；纯后端也可做一次保险）

```powershell
cd D:\代码\testai_community\frontend
npm run build
```

**检验：**

```powershell
Test-Path D:\代码\testai_community\frontend\dist\index.html
```

必须为 `True`。  
把整个 `frontend\dist` 目录准备拷到 64（远程桌面 / 共享盘均可）。

---

# 阶段 2：64 — 停服 → pull → 覆盖 dist → 启服

在 **64** 管理员 PowerShell：

## 2.1 停站

```powershell
cd D:\deploy\testai_community_prod\backend\scripts
.\stop_prod_backend.cmd
```

**检验：**

```powershell
curl.exe --max-time 3 http://127.0.0.1:48011/api/health
```

应失败/超时/连不上（说明已停）。

## 2.2 拉代码

```powershell
cd D:\deploy\testai_community_prod
git status
git pull
```

**检验：**

```powershell
git log -1 --oneline
```

应与开发机刚 push 的 commit 一致（或至少包含本次 OpenAPI 相关提交）。

若 `git pull` 失败：改用拷贝覆盖代码目录，仍**禁止覆盖** `.env`、库、`.venv`。

## 2.3 覆盖前端 dist

从开发机拷贝整个目录到：

```text
D:\deploy\testai_community_prod\frontend\dist\
```

**检验：**

```powershell
Test-Path D:\deploy\testai_community_prod\frontend\dist\index.html
```

必须为 `True`。

## 2.4 依赖（仅当 requirements.txt 有变）

```powershell
cd D:\deploy\testai_community_prod\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

无依赖变更可跳过。

## 2.5 启站

```powershell
cd D:\deploy\testai_community_prod\backend\scripts
.\install_prod_backend.cmd
```

**检验：** 屏幕出现 **`[6/6] PASS`**，且：

```powershell
curl.exe --max-time 5 http://127.0.0.1:48011/api/health
```

返回：

```json
{"status":"ok","service":"testai-community"}
```

浏览器：

- `http://127.0.0.1:48011`
- `http://10.30.144.64:48011`（Ctrl+F5）

能打开、能登录。

---

# 阶段 3：64 — 配置 OpenAPI（应用机器人）

仍在 **64**：

## 3.1 打开生产 `.env`（只改钉钉段，不要整文件替换）

```powershell
notepad D:\deploy\testai_community_prod\.env
```

从**开发机** `.env` 抄入/核对这四行（值与开发机一致）：

```ini
DINGTALK_APP_KEY=（开发机同款）
DINGTALK_APP_SECRET=（开发机同款）
DINGTALK_ROBOT_CODE=（开发机同款，常与 APP_KEY 相同）
DINGTALK_OPEN_CONVERSATION_ID=（开发机同款 = 目标群）
```

并保证：

```ini
DINGTALK_PUSH_ENABLED=false
ENV=production
BACKEND_PORT=48011
```

`DINGTALK_WEBHOOK_URL` 可保留作兜底；OpenAPI 齐全时**优先走应用机器人发图**。

保存关闭。

## 3.2 检验变量名是否存在（不要把值贴到聊天）

```powershell
Select-String -Path D:\deploy\testai_community_prod\.env -Pattern "^DINGTALK_APP_KEY=|^DINGTALK_APP_SECRET=|^DINGTALK_ROBOT_CODE=|^DINGTALK_OPEN_CONVERSATION_ID=|^DINGTALK_PUSH_ENABLED="
```

**检验：** 五行都有；`PUSH_ENABLED` 为 `false`；前四项等号右侧非空。

## 3.3 重启使 `.env` 生效

```powershell
cd D:\deploy\testai_community_prod\backend\scripts
.\stop_prod_backend.cmd
.\install_prod_backend.cmd
```

**检验：** 再次 PASS + health ok。

## 3.4 确认本机推送计划任务仍禁用（改由 62 调度）

```powershell
Get-ScheduledTask -TaskName "TestAI-WeCom-Daily","TestAI-WeCom-Weekly","TestAI-Backend" | Format-Table TaskName, State -AutoSize
```

**检验：**

| 任务 | 期望 |
|------|------|
| TestAI-Backend | Ready / Running |
| TestAI-WeCom-Daily | Disabled |
| TestAI-WeCom-Weekly | Disabled |

若 Daily/Weekly 不是 Disabled：

```powershell
Stop-ScheduledTask -TaskName "TestAI-WeCom-Daily" -ErrorAction SilentlyContinue
Disable-ScheduledTask -TaskName "TestAI-WeCom-Daily"
Stop-ScheduledTask -TaskName "TestAI-WeCom-Weekly" -ErrorAction SilentlyContinue
Disable-ScheduledTask -TaskName "TestAI-WeCom-Weekly"
```

## 3.5 64 本机试发（先确认业务群通，再配 62）

### 方式 A：网站手动推送（若界面有）

1. 打开 `http://127.0.0.1:48011`  
2. Admin/Manager 登录  
3. 测试管理 → 推送相关 → 先 dry_run 再真发  

### 方式 B：API（在 64 上）

把密码换成真实值：

```powershell
# 登录拿 token
curl.exe -s -X POST http://127.0.0.1:48011/api/auth/login -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"password\":\"你的密码\"}"
```

从返回里复制 `access_token`，再：

```powershell
# 先 dry_run（不真发）
curl.exe -s -X POST "http://127.0.0.1:48011/api/test-manage/push/daily" -H "Content-Type: application/json" -H "Authorization: Bearer 这里粘贴token" -d "{\"dry_run\":true,\"force\":false}"
```

**检验 dry_run：** JSON 里大致有 `"dry_run":true`，且能看到预览相关字段；不应在业务群多一条真报。

```powershell
# 真发
curl.exe -s -X POST "http://127.0.0.1:48011/api/test-manage/push/daily" -H "Content-Type: application/json" -H "Authorization: Bearer 这里粘贴token" -d "{\"dry_run\":false,\"force\":true}"
```

**检验真发：**

- 返回里 `"sent":true`（或等价成功）  
- **开发机配置的那个钉钉群** 收到带说明 + 链接 + **清晰截图**的日报  

若只有字没有清晰图：多半 OpenAPI 四项未生效或未重启，或仍走 webhook。

**本步不过 → 不要进入阶段 4。**

---

# 阶段 4：62 — 任务脚本 + 定时 + 反馈

在 **62**（任务平台 `http://10.30.144.62:8020/`）。

## 4.1 从开发机拷贝最新任务脚本（三文件必须一起）

源（开发机仓库）：

```text
D:\代码\testai_community\deploy-task-manager\deploy\tasks\tm_daily_push\testai_push_client.py
D:\代码\testai_community\deploy-task-manager\deploy\tasks\tm_daily_push\run.py
D:\代码\testai_community\deploy-task-manager\deploy\tasks\tm_weekly_push\run.py
```

目标（62）：

```text
D:\deploy-task-manager\deploy\tasks\tm_daily_push\testai_push_client.py
D:\deploy-task-manager\deploy\tasks\tm_daily_push\run.py
D:\deploy-task-manager\deploy\tasks\tm_weekly_push\run.py
```

**检验（在 62）：**

```powershell
findstr /C:"def trigger_push(kind: str)" D:\deploy-task-manager\deploy\tasks\tm_daily_push\testai_push_client.py
findstr /C:"trigger_push(\"daily\")" D:\deploy-task-manager\deploy\tasks\tm_daily_push\run.py
findstr /C:"trigger_push(\"weekly\")" D:\deploy-task-manager\deploy\tasks\tm_weekly_push\run.py
```

三行都要有输出。若还有 `extra_env_paths` 在 run.py 里，说明没覆盖新文件。

## 4.2 写任务 `.env`（真发）

```powershell
notepad D:\deploy-task-manager\deploy\tasks\tm_daily_push\.env
```

内容：

```ini
TESTAI_BASE_URL=http://10.30.144.64:48011
TESTAI_PUSH_USER=admin
TESTAI_PUSH_PASS=能登录64的密码
TESTAI_DRY_RUN=false
TESTAI_FORCE=false
```

```powershell
notepad D:\deploy-task-manager\deploy\tasks\tm_weekly_push\.env
```

内容与日报相同。

**检验：**

```powershell
type D:\deploy-task-manager\deploy\tasks\tm_daily_push\.env
type D:\deploy-task-manager\deploy\tasks\tm_weekly_push\.env
```

两边都是 `TESTAI_DRY_RUN=false`。

## 4.3 确认 62 → 64 网络

```powershell
curl.exe --max-time 5 http://10.30.144.64:48011/api/health
```

**检验：** 返回 `ok`。

## 4.4 确认运维反馈 webhook（平台）

```powershell
Select-String -Path D:\deploy-task-manager\deploy\.env -Pattern "^PLATFORM_WEBHOOK_URL=|^PLATFORM_NAME=|^DINGTALK_KEYWORD="
```

**检验：** `PLATFORM_WEBHOOK_URL` 非空（你已能收到 task-mgr 运行报告则 OK）。  
这是「执行成功/失败」反馈群，可以和业务群不同。

## 4.5 注册/核对定时任务（网页）

打开：http://10.30.144.62:8020/

| 任务 | cron | 超时 | 状态 |
|------|------|------|------|
| tm_daily_push | `0 20 * * 1-5` | 600 | 启用 |
| tm_weekly_push | `15 17 * * 3` | 600 | 启用 |

未注册则点「+ 注册新任务」。

**检验：**

```powershell
curl.exe http://10.30.144.62:8020/api/available
```

列表含 `tm_daily_push`、`tm_weekly_push`。

```powershell
curl.exe http://10.30.144.62:8020/api/tasks
```

已注册且 enabled。

## 4.6 手动执行验收（全链路）

1. 网页点 **TestAI 测试日报（调64）** → **执行**  
2. 看运维群「运行报告」输出  

**检验 — 必须同时满足：**

```text
local_dry_run=False
dry_run=False
sent=True
```

3. 看 **业务群**（OpenAPI 目标群）是否收到带清晰截图的真实日报  

| 现象 | 处理 |
|------|------|
| TypeError extra_env_paths | 回到 4.1 重拷三文件 |
| 仍 dry_run=True | 检查 4.2 `.env` |
| sent=False 本日已推送过 | 临时 `TESTAI_FORCE=true` 再执行，然后改回 false |
| 运维成功但业务群无图 | 回阶段 3，查 64 OpenAPI |

周报可同样点一次「执行」验收（可用 `FORCE=true` 测一次）。

---

# 阶段 5：日常保持

| 检查项 | 命令/动作 |
|--------|-----------|
| 64 网站活着 | `curl.exe http://127.0.0.1:48011/api/health` |
| 64 不自己推 | Daily/Weekly = Disabled；`PUSH_ENABLED=false` |
| 62 任务启用 | 8020 页面两个任务绿色「启用」 |
| 到点 | 工作日 20:00 日报；周三 17:15 周报 |
| 反馈 | 运维群看成功/失败；业务群看正文+图 |

---

# 总检验清单（全部打勾才算完成）

- [ ] 开发机 `git push` 成功，`git log -1` 与 64 `git log -1` 一致（或含本次提交）  
- [ ] 64 `frontend\dist\index.html` 存在，health ok，能登录  
- [ ] 64 `.env` 有 OpenAPI 四项 + `PUSH_ENABLED=false`，已重启  
- [ ] 64 本机真发：业务群有带清晰截图日报  
- [ ] 64 WeCom Daily/Weekly 禁用  
- [ ] 62 三脚本已更新且 findstr 通过  
- [ ] 62 两任务 `.env` 为 `DRY_RUN=false`  
- [ ] 62 手动执行：`sent=True` + 业务群再收一条  
- [ ] 62 两任务保持启用  

---

# 口诀

```
开发：commit → push → npm run build
64：  stop → pull → 覆盖 dist → 写 OpenAPI 四项 → 重启 → 本机真发验群
62：  拷三脚本 → DRY_RUN=false → 执行看 sent=True → 保持启用等定时
```
