# 62 调度 → 64 TestAI 日/周报（按代码核实）

## 代码实际在干什么

```
62 平台（:8020）cron 或点「执行」
  → 跑 tasks/tm_daily_push/run.py（或 tm_weekly_push）
  → testai_push_client.trigger_push()
       1) 读任务目录 .env（只认文件，不认平台环境变量）
       2) POST http://10.30.144.64:48011/api/auth/login
       3) POST /api/test-manage/push/daily|weekly
            body: { "dry_run": true|false, "force": true|false }
64 TestAI
  → dry_run=true：只生成文案，reason=dry_run，不发钉钉业务群
  → dry_run=false：用 64 的 DINGTALK_WEBHOOK_URL（或 OpenAPI）发真实日报/周报
  → DINGTALK_PUSH_ENABLED=false 只关 64「自己闹钟」，不影响上面这个 API
```

两套钉钉，别混：

| 消息 | 谁发 | 配置在哪 |
|------|------|----------|
| 「绿区定时任务管理平台 - 成功」运行报告 | 62 平台 | 62 `deploy/.env` 的 `PLATFORM_WEBHOOK_URL` |
| 测试日报/周报正文+截图 | 64 TestAI | 64 `testai_community_prod/.env` 的 `DINGTALK_*` |

点「执行」后只看到运行报告、没有业务日报 → 看输出里 `dry_run` / `sent`。

---

## 64（已做可跳过）

1. 禁用 `TestAI-WeCom-Daily` / `Weekly`（保留 `TestAI-Backend`）
2. `DINGTALK_PUSH_ENABLED=false`，保留 `DINGTALK_WEBHOOK_URL`
3. 重启 Backend，health ok

---

## 62：文件必须齐

```
D:\deploy-task-manager\deploy\tasks\tm_daily_push\
  run.py
  testai_push_client.py   ← 必须用仓库最新版（.env 覆盖逻辑）
  config.json
  .env

D:\deploy-task-manager\deploy\tasks\tm_weekly_push\
  run.py                  ← 最新版
  config.json
  .env
```

### 日报 `.env`（真发就这样写）

```ini
TESTAI_BASE_URL=http://10.30.144.64:48011
TESTAI_PUSH_USER=admin
TESTAI_PUSH_PASS=你的64网站密码
TESTAI_DRY_RUN=false
TESTAI_FORCE=false
```

周报 `.env` 同样；`TESTAI_DRY_RUN=false` 才真发。

用户须为 64 上 **Admin 或 Manager**（能调 push 接口）。

### cron（平台注册时）

| 任务 | cron | 含义 |
|------|------|------|
| 日报 | `0 20 * * 1-5` | 周一～五 20:00 |
| 周报 | `15 17 * * 3` | 周三 17:15 |
| 超时 | `600` | 最长 10 分钟 |

---

## 怎么执行

### A. 手动试发（先验证真发）

1. 确认已把最新 `testai_push_client.py` / 两个 `run.py` 拷到 62  
2. 两个 `.env` 都是 `TESTAI_DRY_RUN=false`  
3. 打开 http://10.30.144.62:8020/  
4. 点 **TestAI 测试日报（调64）** → **执行**  
5. 看运行报告输出，成功真发应类似：

```text
local_dry_run=False dry_run=False sent=True
```

6. 到 **64 webhook 对应的业务群** 看日报（不是 task-mgr 运行报告群）

若 `sent=False reason=本日已推送过`：临时 `.env` 设 `TESTAI_FORCE=true` 再执行一次，然后改回 `false`。

### B. 定时发送（日常）

任务保持 **启用**，到点平台自动跑（与点「执行」同一套代码）。  
无需再开 64 上的 WeCom 计划任务。

---

## 输出怎么读

| 输出 | 含义 |
|------|------|
| `local_dry_run=True` | 任务 `.env` 仍是 true，或未更新客户端脚本 |
| `dry_run=True reason=dry_run` | 64 按请求做了预览，业务群不会有日报 |
| `sent=True` | 业务群应已收到 |
| `skipped=True` | 幂等跳过 |
| 仅有平台「成功」通知 | 只说明 62 任务跑完，不等于业务已发 |

---

## 故障排查

### TypeError: unexpected keyword argument 'extra_env_paths'

`run.py` 与 `testai_push_client.py` 版本不一致（只更新了一个）。  
用仓库最新版**同时覆盖**下面 3 个文件后再执行：

- `tm_daily_push\testai_push_client.py`
- `tm_daily_push\run.py`
- `tm_weekly_push\run.py`

新版只调用 `trigger_push("daily")` / `trigger_push("weekly")`，不再传额外参数。

### `.env` 已是 false 仍 dry_run=True

旧客户端用 `setdefault` 会被平台环境盖住。覆盖最新 `testai_push_client.py` 后再执行；输出应含 `local_dry_run=`。

### 64 上 DINGTALK_PUSH_ENABLED=false

这是对的，不要改回 true。它只关 64 自己的闹钟；API 真发仍用 `DINGTALK_WEBHOOK_URL`。
