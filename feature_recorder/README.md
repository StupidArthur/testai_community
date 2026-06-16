# 功能录制（Feature Recorder）

从 [ai_ui_recorder](https://github.com/StupidArthur/ai_ui_recorder) 迁入的 **UI 操作录制** 客户端。

- 在真实 Chromium 中录制用户操作，生成 `output/run_*/` 证据目录（含 `meta.json`、快照、actions）
- 录制结束后在 `output/` 下生成 `run_*` 目录，并**自动生成** `run_*.zip`（可上传到 AI 翻译）

> 本目录仅包含录制与本地 Dashboard；翻译能力由平台 `backend/app/translate/` 提供。

## 开发运行

```powershell
cd feature_recorder
npm install
npx playwright install chromium
npm run dashboard
```

浏览器访问 `http://localhost:3000` 开始录制。

## 打包 Windows 分发包（便携 Node + 离线 Chromium）

在项目根目录执行：

```powershell
.\scripts\build_feature_recorder.ps1
```

**第 3 步** 从 [npmmirror](https://npmmirror.com) 下载便携 Node.js（**不走 GitHub/pkg**），通常 1~3 分钟；Node zip 缓存在 `feature_recorder/.cache/`。

**第 4 步** 从 npmmirror **chrome-for-testing** 下载 Chromium（版本 `131.0.6778.85`），解压到 `chrome-win64/`；不再走 `playwright install`（Playwright 镜像常缺最新 Chromium 包）。

| 命令 | 用途 |
|------|------|
| `.\scripts\build_feature_recorder.ps1 -ExeOnly` | 跳过 Chromium |
| `.\scripts\build_feature_recorder.ps1 -SkipClean` | 保留缓存 |
| `$env:LOCAL_CHROME_ZIP="D:\path\chrome-win64.zip"` | 本地 Chromium |

**解压注意：** 必须将 zip **完整解压**到同一目录后再双击 `feature-recorder.cmd`；不要只复制 cmd 文件。建议解压到短路径（如 `C:\feature-recorder`），并在 zip 属性中「解除锁定」。

在 `feature_recorder` 子目录也可：`.\build.ps1`

产物：

- `feature_recorder/release/recorder/feature-recorder.cmd`（双击启动）
- `feature_recorder/release/recorder/chrome-win64/`（离线 Chromium）
- `feature_recorder/release/feature-recorder-win64.zip`（供工具集下载）

后端启动时会自动将 zip 同步到工具集「功能录制」的下载制品（若文件存在）。

## 与 AI 翻译协作

1. 工具集下载并运行「功能录制」
2. 录制完成后，在解压目录的 `output/` 下获取 `run_*.zip`（Dashboard 也可直接「下载 ZIP」）
3. 工具集 → AI 翻译 → 上传该 zip
