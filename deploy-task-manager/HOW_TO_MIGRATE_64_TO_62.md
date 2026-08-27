# 迁移手册：testai-community 从 64 迁到 62（三天窗口期版）

> 目标：三天内把 64 的生产环境完整迁到 62，纳入 guardian 统一守护，64 保留作回退。
> 原则：每步有检验，检验不过不进下一步；迁移期间 64 全程不停服，随时可回退。
> 日期：2026-08-26

---

## 0. 迁移总览

| 事项 | 64 现状 | 62 目标 |
|------|---------|---------|
| 代码目录 | D:\deploy\testai_community_prod | D:\testai_community_prod（62 已定路径） |
| 后端端口 | 48011 | 48011（不变） |
| Python 环境 | backend\.venv | 不拷贝，62 重建 |
| 守护方式 | 计划任务 TestAI-Backend + keepalive | guardian 网页面板添加服务 |
| AI - Ollama | 待确认跑在哪 | 62 本机安装 + 拉模型 |
| 定时推送 | 62 调 http://10.30.144.64:48011 | 62 调本机 http://127.0.0.1:48011 |
| 数据 | .env / database*.sqlite / data\ / dist | 全部拷贝 |

**不拷**：`.venv`、`node_modules`、`__pycache__`、`backend\tests\.data`（测试垃圾产物，上百 MB）

**必拷**：`.env`（根目录）、`database*.sqlite`（根目录）、`data\`（知识库向量库 chroma 在里面）、`frontend\dist`、`backend\app\tool_artifacts`、`backend\app\uploads`、`backend\app\results`、`tools\`（若 64 带了 LibreOffice）

---

## 阶段 A：62 环境准备（约半天）

### A1. 装 Python 3.11.5（与 64 完全同版本）

下载（在 62 的浏览器直接打开任一链接）：

- 官方直链：https://www.python.org/ftp/python/3.11.5/python-3.11.5-amd64.exe
- 备用（国内更快）：https://mirrors.huaweicloud.com/python/3.11.5/python-3.11.5-amd64.exe

安装（双击 python-3.11.5-amd64.exe）：

1. 第一屏：**务必勾选底部的 "Add python.exe to PATH"**（不勾后面全是坑）
2. 点 "Install Now"
3. 等待进度条走完；若最后出现 "Disable path length limit" 选项，点一下（不点也能用）
4. 关闭安装器

**检验（新开一个 PowerShell 窗口）：**

```powershell
python --version    # 应显示 Python 3.11.5
```

若提示 "python 不是内部或外部命令"：说明 PATH 没勾上，重新双击安装包 → Modify → 勾选 "Add Python to environment variables" → 装完重开窗口再验。

### A2. 装 Ollama

下载（任选其一）：

- 官方：https://ollama.com/download/windows （页面点 Download for Windows，得到 OllamaSetup.exe）
- 备用：https://github.com/ollama/ollama/releases/latest 页面下载 OllamaSetup.exe

安装：双击 OllamaSetup.exe，一路默认（无需选路径），装完自动驻留后台托盘，
默认监听 127.0.0.1:11434。

**检验（新开 PowerShell）：**

```powershell
ollama --version                               # 应显示版本号
curl.exe --max-time 3 http://127.0.0.1:11434   # 应显示 Ollama is running
```

### A3. 模型获取（首选：从 64 直接拷贝文件夹，免下载，约 7G）

**第 1 步：在 64 上确认模型位置**

```powershell
dir $env:USERPROFILE\.ollama\models
```

应看到 `blobs` 和 `manifests` 两个目录（模型本体全在里面）。

**第 2 步：把整个 models 文件夹拷到 62（远程桌面驱动器映射，一次连接搞定）**

64 和 62 都在内网，推荐用远程桌面自带的"本地驱动器"功能，纯图形操作：

1. 在 64 上按 `Win+R` → 输入 `mstsc` 回车 → 输入 62 的地址 `10.30.144.62`
2. 点左下角"显示选项" → "本地资源"选项卡 → 点"详细信息..." → 勾选"驱动器"
   （可以展开后只勾 C、D 盘）
3. 点"连接"，登录 62
4. 在 62 上打开"此电脑"，会多出几个**红色小字的盘**（写着 tsclient 之类）——
   那就是 64 的磁盘，在 62 上可以直接读
5. 从里面找到 64 的 `C:\Users\<64登录用户名>\.ollama\models`，
   整个文件夹拖到 62 的 `C:\Users\<62登录用户名>\.ollama\` 下（约 7G，内网几分钟）

注意：如果远程桌面已经连着 62，需要断开重新连一次，并在第 2 步勾选驱动器后才会出现。

**同一个方法可以传任何文件**：OllamaSetup.exe、Python 安装包、后面阶段的代码目录压缩包，
都是"64 上选中 → Ctrl+C → 切到 62 的窗口 → Ctrl+V"。小文件直接剪贴板复制粘贴就行，
不用断开重连。

**第 3 步：在 62 上放入模型（先退 Ollama 防文件占用）**

1. 62 上先双击一次 Ollama 让它生成默认目录（装完 A2 其实已经有了）
2. 右下角托盘找到 Ollama 图标 → 右键 → Quit Ollama（完全退出）
3. 把拷来的 `models` 文件夹覆盖到 62 的 `C:\Users\<62登录用户名>\.ollama\` 下
   （即最终路径为 `C:\Users\<62登录用户名>\.ollama\models\blobs` 这样）
4. 再启动 Ollama（开始菜单里点开即可）

**检验：**

```powershell
ollama list    # 应显示 bge-m3、qwen2.5vl:7b 两行
```

备选（不想拷贝且网速好）：直接在 62 执行 `ollama pull bge-m3` 与 `ollama pull qwen2.5vl:7b`。

### A4. 端口预检

```powershell
netstat -ano | findstr :48011    # 检验：无输出（空闲）
```

浏览器打开 guardian 面板 `http://127.0.0.1:9000`，确认守护正常。

---

## 阶段 B：代码与数据搬迁（约半天，64 不停服）

### B1. 64 上打出干净副本再拷贝

在 **64** 管理员 PowerShell（排除不需要的目录，生成干净副本）：

```powershell
robocopy D:\deploy\testai_community_prod D:\testai_migration /E /XD .venv node_modules __pycache__ .data
```

然后用 **A3 第 2 步的远程桌面驱动器映射**，把 64 的 `D:\testai_migration`
整个文件夹拖到 62 的 `D:\` 下，改名为：

```text
D:\testai_community_prod
```

（62 与 64 部署路径不同没有影响：项目里数据库、数据目录全部按代码位置
相对推导，不依赖目录名。）

**检验（在 62）：**

```powershell
Test-Path D:\testai_community_prod\backend\run_prod.py          # True
Test-Path D:\testai_community_prod\.env                         # True
Test-Path D:\testai_community_prod\database*.sqlite             # True（数据完整）
Test-Path D:\testai_community_prod\data\knowledge_base\chroma   # True（向量库完整）
```

### B2. 62 重建虚拟环境

```powershell
cd D:\testai_community_prod\backend
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**检验（核心依赖）：**

```powershell
.\.venv\Scripts\python.exe -c "import uvicorn, chromadb; print('core deps ok')"
```

pymupdf（fitz，只影响 PDF 解析功能，不影响服务启动）单独验：

```powershell
.\.venv\Scripts\python.exe -c "import fitz; print('pymupdf ok')"
```

若报 `ImportError: DLL load failed while importing _extra`：新装系统缺 VC++ 运行时，
下载 https://aka.ms/vs/17/release/vc_redist.x64.exe 双击安装，重开窗口再验；
仍不行则执行
`.\.venv\Scripts\pip.exe install --force-reinstall --no-cache-dir pymupdf -i https://pypi.tuna.tsinghua.edu.cn/simple`
还不行就锁旧版 `pip install pymupdf==1.24.9`。

### B3. 核对 .env（只核对，不整文件替换）

```powershell
Select-String -Path D:\testai_community_prod\.env -Pattern "^ENV=|^BACKEND_PORT=|^OLLAMA_BASE_URL=|^SECRET_KEY=|^MINIMAX_API_KEY=|^DINGTALK_APP_KEY="
```

**检验标准：**

| 变量 | 期望 |
|------|------|
| ENV | production |
| BACKEND_PORT | 48011 |
| OLLAMA_BASE_URL | http://127.0.0.1:11434（ollama 就在 62 本机，保持默认即可） |
| SECRET_KEY / MINIMAX_API_KEY / 钉钉四项 | 非空 |

### B4. 手动试跑一次

```powershell
cd D:\testai_community_prod\backend
.\.venv\Scripts\python.exe run_prod.py
```

另开窗口：

```powershell
curl.exe --max-time 5 http://127.0.0.1:48011/api/health
```

**检验：** 返回 `{"status":"ok",...}`。通过后 Ctrl+C 停掉，进入阶段 C。

---

## 阶段 C：接入 guardian 统一守护（约 1 小时）

### C1. 网页面板添加服务

浏览器打开 `http://127.0.0.1:9000`，右上角「+ 添加服务」，填：

| 字段 | 值 |
|------|-----|
| 服务名称 | testai-backend（或 testai_community_prod，好认即可） |
| 进程名 | python.exe |
| 命令行匹配 | run_prod.py（用于区分其他 python 进程，重要，别漏填） |
| 可执行文件路径 | D:\testai_community_prod\backend\.venv\Scripts\python.exe |
| 启动参数 | run_prod.py |
| 工作目录 | D:\testai_community_prod\backend |
| 监听端口 | 48011 |
| 自动重启 | 是 |

保存即生效。等价 services.json 片段（备查）：

```json
{
  "name": "testai-backend",
  "process": "python.exe",
  "path": "D:\\testai_community_prod\\backend\\.venv\\Scripts\\python.exe",
  "args": "run_prod.py",
  "workdir": "D:\\testai_community_prod\\backend",
  "port": 48011,
  "auto_restart": true
}
```

### C2. 验证守护

面板上 testai-backend 卡片 30 秒内变 running，端口显示 48011 listening。
再从自己电脑访问：`http://10.30.144.62:48011/api/health` 返回 ok（防火墙由 guardian 自动放行）。

**注意：** python.exe 与任务平台跑任务的 python 进程同名，务必填写
"命令行匹配 = run_prod.py"加以区分（guardian 面板自带该字段），避免误判/误杀。

### C3. Ollama 先不动

Ollama 安装后默认托盘自启，第一周先用默认自启保持简单。
若要纳入 guardian 统一管理（服务名 ollama、参数 serve、端口 11434），
必须先关闭 Ollama 自身自启，避免双开打架。稳定运行一周后再考虑。

### C4. 不要在 62 跑 64 的计划任务脚本

`install_prod_backend_task.ps1` 是 64 的旧守护方案，62 上由 guardian 替代，不要执行。

---

## 阶段 D：调度切换 + 全链路验收（约半天）

### D1. 62 任务指向改本机

```powershell
notepad D:\deploy-task-manager\deploy\tasks\tm_daily_push\.env    # TESTAI_BASE_URL=http://127.0.0.1:48011
notepad D:\deploy-task-manager\deploy\tasks\tm_weekly_push\.env   # 同上
```

**检验：**

```powershell
type D:\deploy-task-manager\deploy\tasks\tm_daily_push\.env
type D:\deploy-task-manager\deploy\tasks\tm_weekly_push\.env
```

### D2. 推送链路验收

任务平台网页手动执行 tm_daily_push：

1. 先 dry_run 一次，返回正常
2. 再真发一次（临时 TESTAI_FORCE=true），业务群收到带截图日报后改回 false

### D3. 功能验收清单（http://10.30.144.62:48011）

- [ ] 登录 admin 正常
- [ ] 知识库：上传一篇文档，检索出结果（验证 ollama embedding 链路）
- [ ] AI 对话（验证 MiniMax）
- [ ] AI 早报（验证 Tavily）
- [ ] 翻译/文档解析跑一单（验证 LibreOffice / playwright）

### D4. 重启演练

62 重启一次，验证开机自愈：guardian 自动拉起 deploy-task-manager 和 testai-backend，
Ollama 托盘自启，面板全绿，网站可访问。

### D5. 64 下线（保留回退）

```powershell
cd D:\deploy\testai_community_prod\backend\scripts
.\stop_prod_backend_task.ps1
Disable-ScheduledTask -TaskName "TestAI-Backend"
```

64 代码和 .env 原样保留至少 2 周，作回退环境。

### D6. 开放使用

通知大家新地址：`http://10.30.144.62:48011`（老地址 64 不再服务）。

---

## 三天节奏建议

| 天 | 内容 |
|----|------|
| 第 1 天 | 阶段 A + B：装环境、搬代码数据、手动试跑通 |
| 第 2 天 | 阶段 C + D1~D3：接入守护、切调度、功能验收，拉师兄/同事试用 |
| 第 3 天 | 阶段 D4~D6：重启演练、64 下线、开放使用，留缓冲处理意外 |

---

## 回退预案（随时可用）

任何一步卡死，5 分钟恢复原状：

1. guardian 面板停掉 testai-backend 服务卡片
2. 62 两个任务 .env 改回 `TESTAI_BASE_URL=http://10.30.144.64:48011`
3. 64 从未停服，一切照旧

---

## 风险与注意

- **模型约 7G**：优先走 64 压缩拷贝方案，比外网下载稳；拷完务必 ollama list 验收
- **chromadb/protobuf 版本敏感**：venv 一律按 requirements.txt 锁定版本安装，不要手动升级
- **python.exe 进程名识别**：guardian 守护 python 服务时留意与任务平台 python 进程的区分，靠端口判断
- **长期优化**：以后有空可把后端打成 exe（同 deploy-task-manager），根治进程识别问题；chromadb+playwright 打包难度大，窗口期内不做

---

## 口诀

```
62 装环境：python + ollama + 两个模型
搬三样：  代码目录（除venv）+ .env + 数据（库/向量/制品）
守护接入：面板加服务，路径指 venv python，端口 48011
切调度：  两个任务 .env 改 127.0.0.1
验收四链路：知识库(ollama) 对话(minimax) 早报(tavily) 推送(钉钉)
最后：    重启演练 → 64 停服保留 → 开放
```
