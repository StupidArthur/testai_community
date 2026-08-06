# 服务器部署与排障（Windows · 10.30.144.64）

> 文档版本：2026-08-04  
> 适用：生产目录 `D:\deploy\testai_community_prod`，端口 **48011**  
> 目标：本机 / 局域网通过 `http://服务器IP:48011` 稳定打开网站

---

## 0. 问题现象与结论

| 现象 | 含义 |
|------|------|
| 窗口显示 `Uvicorn running`，但 `curl` / 浏览器一直转圈超时 | **进程在听端口，但 HTTP 不回包**（Windows 上常见） |
| `netstat` 只有 `TIME_WAIT`、没有 `LISTENING` | **服务根本没在跑** |
| 本机 `127.0.0.1` 通、别人 IP 不通 | 多半是**防火墙**未放行 |

**生产请用 `python run_prod.py`（强制 `asyncio` + `h11`），不要用带 reload 的 `python run.py`。**

---

## 1. 目录与文件清单（先核对）

服务器上应有：

```
D:\deploy\testai_community_prod\
  .env                          ← 生产配置（勿用开发库）
  frontend\dist\index.html      ← 前端构建产物（从开发机拷）
  backend\
    .venv\                      ← Python 3.12 虚拟环境
    run_prod.py                 ← 生产启动（必须有）
    diag_listen.py              ← 最小诊断（必须有）
    scripts\start_prod_server.ps1
    app\
    requirements.txt
```

生产 `.env` 最少包含：

```ini
ENV=production
SECRET_KEY=一长串随机字符
BACKEND_PORT=48011
DATABASE_URL=sqlite:///./database_prod.sqlite
WECOM_PUSH_ENABLED=false
MINIMAX_API_KEY=你的key
WECOM_WEBHOOK_URL=你的webhook
```

---

## 2. 从头启动（按顺序，一条一条执行）

### 2.1 管理员 PowerShell：放行防火墙（做一次即可）

```powershell
New-NetFirewallRule -DisplayName "TestAI-48011" -Direction Inbound -Protocol TCP -LocalPort 48011 -Action Allow -ErrorAction SilentlyContinue
```

### 2.2 确认前端 dist 在

```powershell
Test-Path D:\deploy\testai_community_prod\frontend\dist\index.html
```

必须为 `True`。否则从开发机拷整个 `frontend\dist` 过来。

### 2.3 最小诊断（判断是「系统/uvicorn」还是「业务 App」）

**窗口 A：**

```powershell
cd D:\deploy\testai_community_prod\backend
.\.venv\Scripts\Activate.ps1
python diag_listen.py
```

应看到 listening `48012`。

**窗口 B：**

```powershell
curl.exe --max-time 5 http://127.0.0.1:48012/ping
```

| 结果 | 下一步 |
|------|--------|
| 返回 `{"ok":true...}` | uvicorn 正常 → 窗口 A 里 `Ctrl+C`，做 2.4 |
| 仍然超时 | 本机 Python/安全软件拦截网络；换网、关第三方防火墙后再试，或重装 Python 3.12 到 `.venv` |

### 2.4 启动正式服务

**窗口 A（保持不关）：**

```powershell
cd D:\deploy\testai_community_prod\backend
.\.venv\Scripts\Activate.ps1
# 先清端口
netstat -ano | findstr :48011
# 若有 LISTENING，记下 PID：
# taskkill /PID <数字> /F

python run_prod.py
```

或一键：

```powershell
powershell -ExecutionPolicy Bypass -File D:\deploy\testai_community_prod\backend\scripts\start_prod_server.ps1
```

看到：

```
Application startup complete
Uvicorn running on http://0.0.0.0:48011
```

**窗口 B：**

```powershell
curl.exe --max-time 5 http://127.0.0.1:48011/api/health
```

必须看到：

```json
{"status":"ok","service":"testai-community"}
```

此时看窗口 A：应出现一行访问日志（GET /api/health）。  
**若仍超时且窗口 A 完全没有 GET 日志** → 连接没进这个进程，把 `netstat -ano | findstr 48011` 发出来。

### 2.5 本机浏览器 / 同事访问

- 服务器本机：`http://127.0.0.1:48011`
- 你的电脑 / 同事：`http://10.30.144.64:48011`（以 `ipconfig` 为准）
- 地址必须带 **`http://`**

---

## 3. 日常更新代码

**完整标准流程（推荐照此执行）：** 见 [deploy_sop_production.md](./deploy_sop_production.md)

摘要：开发机 `push` + `npm run build` → 生产 `stop_prod_backend` → `git pull` → 覆盖 `frontend/dist` →（可选）pip → `install_prod_backend` 到 PASS → 验收。  
`.env` 与业务库不要覆盖；`frontend/dist` 不在 Git 中，必须单独拷贝。

---

## 4. 长期运行（唯一推荐做法）

**不要**用开着的 PowerShell 跑 `python run_prod.py` 当生产——关窗口网站必挂。

### 唯一推荐：CMD 一键安装（隐藏后台，关窗口不杀站）

拷到生产 `backend\scripts\`：

- `install_prod_backend.cmd`
- `run_prod_keepalive.cmd`
- `run_prod_keepalive_hidden.vbs`（**必须有**，避免弹出黑窗口）
- `stop_prod_backend.cmd`

```bat
cd /d D:\deploy\testai_community_prod\backend\scripts
.\install_prod_backend.cmd
```

看到 **PASS** 后关掉所有窗口；**不应再出现**一直开着的黑色 CMD。  
若关某个黑窗口网站就挂，说明还在用旧任务，请重新跑上面的安装命令。

### 企微推送

```powershell
powershell -ExecutionPolicy Bypass -File .\install_wecom_scheduled_tasks.ps1
```

生产 `.env`：`WECOM_PUSH_ENABLED=false`。开发机企微任务保持禁用。
---

## 5. 禁止事项

1. 生产不要用 `python run.py`（`ENV=dev` 会开 reload，Windows 上极易「显示 running 但不回包」）  
2. 激活虚拟环境路径是 `.\.venv\...`（前面有个点）  
3. 不要在卡在 `>>` 续行时瞎粘贴；先 `Ctrl+C` 回到 `PS>`  
4. 不要把带密钥的 `.env` 发到聊天/提交 Git  

---

## 6. 一次成功的验收清单

- [ ] `curl http://127.0.0.1:48011/api/health` → ok  
- [ ] 服务器 Edge/Chrome 打开首页有样式  
- [ ] 另一台电脑 `http://10.30.144.64:48011` 能打开  
- [ ] 防火墙规则 `TestAI-48011` 存在  
- [ ] 启动方式是计划任务 `TestAI-Backend`（`run_prod.py`），**不依赖**开着的 PowerShell  
- [ ] 企微计划任务只在生产机：`TestAI-WeCom-Daily` / `Weekly` / `KeepAwake`  
- [ ] 生产 `.env`：`WECOM_PUSH_ENABLED=false`  
