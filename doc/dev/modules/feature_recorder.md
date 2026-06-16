# 功能录制（feature_recorder）

> 代码路径：`feature_recorder/`（自 [ai_ui_recorder/recorder](https://github.com/StupidArthur/ai_ui_recorder) 迁入）  
> 工具集登记：`slug=feature_recorder`，`tool_kind=client`

---

## 1. 定位

| 模块 | 职责 |
|------|------|
| `feature_recorder/` | 本地 Playwright 录制客户端（便携 Node 分发包） |
| `backend/app/translate/` | 平台侧 AI 翻译（录制 ZIP 的后半段流水线） |
| `backend/app/tool_hub/` | 工具集：功能录制（下载）+ AI 翻译（平台集成）并列 |

**推荐工作流：** 功能录制 → 自动生成 `run_*.zip` → AI 翻译上传。

---

## 2. 开发与打包

```powershell
cd feature_recorder
npm install
npx playwright install chromium
npm run dashboard
```

根目录一键打包：

```powershell
.\scripts\build_feature_recorder.ps1
```

镜像源：

| 资源 | 地址 |
|------|------|
| Node.js | `https://npmmirror.com/mirrors/node` |
| npm | `https://registry.npmmirror.com` |
| Chromium（打包） | `https://registry.npmmirror.com/-/binary/chrome-for-testing`（版本 `131.0.6778.85`，与 playwright-core 1.49.1 匹配） |

产物：

- `feature_recorder/release/recorder/feature-recorder.cmd`
- `feature_recorder/release/feature-recorder-win64.zip`

后端 `tool_hub.bootstrap` 启动时若 zip 存在，自动同步到 `TOOL_HUB_ARTIFACT_DIR` 并绑定「功能录制」下载。

---

## 3. 与上游差异

- 分发方式为 **便携 Node（npmmirror）+ `feature-recorder.cmd`**，不再使用 pkg 单 EXE
- Chromium：优先 `LOCAL_CHROME_ZIP`（默认 `D:\chrome_download\chrome-win64.zip`），否则从 npmmirror **chrome-for-testing** 下载并解压到 `chrome-win64/`（不再使用 `playwright install`，避免镜像未同步最新 Chromium 导致 404）
- 翻译引导用户使用平台 `/translate`

---

*designed by @yuzechao*
