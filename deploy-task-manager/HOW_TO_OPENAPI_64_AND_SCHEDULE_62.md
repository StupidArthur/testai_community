# 目标架构：开发机同款应用机器人 → 64 发业务群；62 定时 + 反馈结果

```
开发机调试成功的「应用机器人」配置
        │ 拷贝四项密钥
        ▼
64 TestAI（数据 + 截图 + 发群）
  .env: DINGTALK_APP_* + OPEN_CONVERSATION_ID
  DINGTALK_PUSH_ENABLED=false   ← 自己不闹钟
        ▲
        │ HTTP POST /api/test-manage/push/daily|weekly
62 定时任务平台 :8020
  tm_daily_push / tm_weekly_push
  .env: TESTAI_*（登录 64）
  PLATFORM_WEBHOOK_URL → 运维「成功/失败」反馈（可另群或同群）
```

**不要**把 `DINGTALK_APP_KEY` 配到 62 任务里——业务发群只发生在 64。

---

## A. 开发机：确认并导出配置（不要发到聊天）

1. 打开开发机项目根目录 `.env`（你本地能成功发带截图日报的那份）。
2. 确认有这四项（值非空）：

```ini
DINGTALK_APP_KEY=...
DINGTALK_APP_SECRET=...
DINGTALK_ROBOT_CODE=...
DINGTALK_OPEN_CONVERSATION_ID=...
```

说明：

| 项 | 作用 |
|----|------|
| APP_KEY / SECRET | 企业内部应用凭证 |
| ROBOT_CODE | 机器人 code，很多环境与 APP_KEY 相同 |
| OPEN_CONVERSATION_ID | **目标群**会话 ID（发到哪个群由它决定） |

3. 用 U 盘/远程桌面把这四行 **安全拷到 64**（不要贴到群里、不要提交 Git）。

可选自检（开发机已跑着后端时）：

- 登录后调推送状态，或看 dry_run 输出里 `channel=openapi`。

---

## B. 64：写入应用机器人并重启

### B1. 编辑生产 `.env`

```powershell
notepad D:\deploy\testai_community_prod\.env
```

写入/改成（与开发机一致）：

```ini
DINGTALK_APP_KEY=（开发机同款）
DINGTALK_APP_SECRET=（开发机同款）
DINGTALK_ROBOT_CODE=（开发机同款）
DINGTALK_OPEN_CONVERSATION_ID=（开发机同款）

DINGTALK_PUSH_ENABLED=false
```

建议：

- **保留**原来的 `DINGTALK_WEBHOOK_URL` 作兜底也可以；OpenAPI 齐全时**优先走应用机器人**，带清晰截图。
- 不要把 `DINGTALK_PUSH_ENABLED` 改回 `true`（否则 64 自己也会定时推，和 62 双发）。

保存。

### B2. 确认计划任务仍禁用

```powershell
Get-ScheduledTask -TaskName "TestAI-WeCom-Daily","TestAI-WeCom-Weekly" | Format-Table TaskName, State
```

应为 **Disabled**。`TestAI-Backend` 保持启用。

### B3. 重启后端让配置生效

```powershell
cd D:\deploy\testai_community_prod\backend\scripts
.\stop_prod_backend.cmd
.\install_prod_backend.cmd
```

看到 **PASS**，且：

```powershell
curl.exe --max-time 5 http://127.0.0.1:48011/api/health
```

返回 ok。

### B4.（推荐）在 64 本机先确认 OpenAPI 通道

浏览器打开 `http://127.0.0.1:48011`，用 Admin/Manager 登录 → 测试管理里若有「推送状态 / 手动推送」：

- 先 **dry_run**，看通道是否为 openapi  
- 再真发一条，看 **开发机配置的那个群** 是否收到带截图日报  

（也可用 API；核心是确认 64 单独就能发到目标群。）

---

## C. 62：定时调用 64 + 反馈执行结果

### C1. 覆盖最新任务脚本（三文件一起）

从本机仓库拷到 62：

```text
D:\deploy-task-manager\deploy\tasks\tm_daily_push\testai_push_client.py
D:\deploy-task-manager\deploy\tasks\tm_daily_push\run.py
D:\deploy-task-manager\deploy\tasks\tm_weekly_push\run.py
```

验证：

```powershell
findstr /C:"def trigger_push(kind: str)" D:\deploy-task-manager\deploy\tasks\tm_daily_push\testai_push_client.py
findstr /C:"trigger_push(\"daily\")" D:\deploy-task-manager\deploy\tasks\tm_daily_push\run.py
```

两行都要有输出。

### C2. 任务 `.env`（登录 64，真发）

`D:\deploy-task-manager\deploy\tasks\tm_daily_push\.env`：

```ini
TESTAI_BASE_URL=http://10.30.144.64:48011
TESTAI_PUSH_USER=admin
TESTAI_PUSH_PASS=能登录64网站的密码
TESTAI_DRY_RUN=false
TESTAI_FORCE=false
```

`tm_weekly_push\.env` 同样一份。

### C3. 平台「反馈发送结果」（运维通知）

62 的 `D:\deploy-task-manager\deploy\.env` 里已有类似：

```ini
PLATFORM_NAME=绿区定时任务管理平台
PLATFORM_WEBHOOK_URL=...
DINGTALK_KEYWORD=task-mgr
```

这决定 **task-mgr-pub「成功/失败」** 发到哪个群。

| 你想要的反馈方式 | 怎么做 |
|------------------|--------|
| 运维群看成败（推荐） | 保持现在的 `PLATFORM_WEBHOOK_URL`（你已能收到运行报告） |
| 业务群也想看到成败摘要 | 把平台 webhook 改成业务群自定义机器人（会和日报同群，消息会多一条运维卡片） |

业务日报正文+截图 **不会** 走 `PLATFORM_WEBHOOK_URL`，只走 64 的 OpenAPI。

### C4. 平台任务保持启用

http://10.30.144.62:8020/

| 任务 | cron | 超时 |
|------|------|------|
| tm_daily_push | `0 20 * * 1-5` | 600 |
| tm_weekly_push | `15 17 * * 3` | 600 |

状态：**启用**。

### C5. 从 62 测到 64

```powershell
curl.exe --max-time 5 http://10.30.144.64:48011/api/health
```

### C6. 手动试发（验收全链路）

1. 打开 http://10.30.144.62:8020/  
2. **TestAI 测试日报（调64）** → **执行**  
3. 看两类结果：

**① 运维反馈（62 平台 webhook 群）**  
输出须类似：

```text
local_dry_run=False dry_run=False sent=True
```

失败会显示「失败」+ 报错（这就是「反馈发送结果」）。

**② 业务结果（开发机同款群，OpenAPI）**  
应收到 **真实测试日报（说明 + 链接 + 清晰截图）**。

若 `sent=False` 且 `本日已推送过`：临时 `TESTAI_FORCE=true` 再执行一次，然后改回 `false`。

周报同理点周报「执行」验收一次即可。

---

## D. 日常运转（做完验收后）

| 机器 | 保持 |
|------|------|
| 64 | Backend 跑着；WeCom Daily/Weekly **禁用**；OpenAPI 四项在 `.env`；`PUSH_ENABLED=false` |
| 62 | 两个任务 **启用**；`.env` 里 `DRY_RUN=false`；到点自动跑 |

到点后：

1. 运维群：平台成功/失败卡片（含 `sent=`）  
2. 业务群：64 应用机器人发的日/周报  

---

## E. 对照检查清单

- [ ] 开发机四项密钥已拷到 64 `.env`  
- [ ] 64 已重启 Backend，health ok  
- [ ] 64 上 Daily/Weekly 计划任务仍禁用  
- [ ] 62 三个 `.py` 为最新（无 `extra_env_paths` 报错）  
- [ ] 62 两个任务 `.env`：`DRY_RUN=false`  
- [ ] 62→64 health 通  
- [ ] 手动执行：`sent=True` + 业务群收到带截图日报  
- [ ] 任务保持启用，等定时  

---

## F. 常见坑

| 现象 | 原因 |
|------|------|
| 只有运维成功、业务群没有 | 仍 `dry_run=True`，或 64 未配 OpenAPI 且 webhook 失败 |
| 业务群有字没清晰图 | 64 只配了 webhook，没配齐 OpenAPI 四项 |
| TypeError extra_env_paths | 三文件未一起覆盖最新版 |
| 两个群都收到「运行报告」但没有日报 | 看输出 `sent=`，不要只看平台「成功」二字 |
| 64 与 62「双发」 | `DINGTALK_PUSH_ENABLED=true` 或 WeCom 计划任务又启用了 |
