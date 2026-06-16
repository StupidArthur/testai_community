# 工具集使用手册

> 文档版本：2026-06-16  
> 面向对象：平台使用者、管理员、运维  
> 技术细节见 [dev/modules/tool_hub.md](./dev/modules/tool_hub.md)

---

## 1. 工具集是什么

**工具集**是 TestAI Community 中统一管理「可下载客户端」与「平台集成工具」的入口。

| 类型 | tool_kind | 你能做什么 |
|------|-----------|------------|
| **客户端工具** | `client` | 下载 zip / exe / msi 到本机运行 |
| **平台集成工具** | `platform` | 跳转到站内功能页（如 AI 翻译） |

登录后：**顶部导航 → 工具集**，或首页 Portal **工具集** 卡片进入。

- 前端路由：`/tool-hub`、`/tool-hub/:toolId`
- API 前缀：`/api/tool-hub`

---

## 2. 预置工具与推荐工作流

平台启动时自动注册两个工具（并列关系，非父子）：

| 工具 | slug | 类型 | 说明 |
|------|------|------|------|
| **功能录制** | `feature_recorder` | client | 下载 Windows 客户端，在 Chromium 中录制 UI 操作 |
| **AI 翻译** | `ai_translate` | platform | 上传录制 zip，生成中文测试用例 |

### 推荐流水线

```text
工具集 → 功能录制（下载客户端）
    → 本地录制 UI 操作
    → 得到 run_*.zip
工具集 → AI 翻译
    → 上传 zip
    → 下载翻译结果
```

> AI 翻译、功能录制**不再单独出现在顶栏**，统一从工具集进入。翻译页内有「返回工具集」按钮。

---

## 3. 功能录制：下载、解压、运行

### 3.1 下载

1. 工具集 → **功能录制** → 详情页
2. 点击 **下载**，得到 `feature-recorder-win64.zip`（约 200MB）

> 需管理员先在服务器执行构建脚本并重启后端，工具集才会出现可下载的 zip。见 [§6 运维：构建客户端](#6-运维构建功能录制包)。

### 3.2 为什么是「带拉链的文件夹」？

Windows 会把 `.zip` 显示为 **「压缩(zipped)文件夹」**（图标带拉链），可以双击进去浏览，**但这不是已解压**。

**不要**在压缩包内直接双击 `feature-recorder.cmd`，会闪退或报找不到 `node.exe`。

### 3.3 正确解压步骤

1. 在「下载」中找到 `feature-recorder-win64.zip`
2. **右键** → **「全部解压缩…」**
3. 解压到**短路径**，例如：`C:\feature-recorder`
4. 若浏览器下载的 zip，先在 **属性 → 解除锁定** 再解压
5. 确认解压目录内**同时存在**：
   - `feature-recorder.cmd`
   - `node\`（含 `node.exe`）
   - `app\`
   - `chrome-win64\`
   - `static\`

### 3.4 启动

1. 进入解压后的文件夹
2. 双击 **`feature-recorder.cmd`**
3. **黑色窗口应保持打开**，浏览器自动打开 http://localhost:3000
4. 若窗口一闪就关：
   - 查看同目录 `startup.log`
   - 确认已完整解压（不是只在 zip 里点 cmd）
   - 任务管理器结束占用 **3000 端口** 的旧 `node.exe` 后重试

### 3.5 录制与 zip 产物

1. Dashboard 填写被测 URL → **开始录制**
2. 在弹出 Chromium 中操作
3. **关闭浏览器窗口**结束录制
4. 产物位置（在解压目录下）：
   - 文件夹：`output\run_时间戳\`
   - **自动生成的 zip**：`output\run_时间戳.zip`
5. Dashboard 右侧「录制历史」可 **生成 ZIP** / **下载 ZIP**

将 `run_*.zip` 上传到 **工具集 → AI 翻译**。

---

## 4. AI 翻译：上传录制包

1. 工具集 → **AI 翻译** → 进入 `/translate`
2. 上传功能录制产生的 `run_*.zip`
3. 在任务列表查看进度，完成后下载结果

平台会解压 zip 并查找 `meta.json`（支持 zip 内带 `run_*` 文件夹或平铺结构）。

---

## 5. 浏览与管理工具

### 5.1 所有人

- 浏览已上架工具列表与详情
- 下载客户端工具最新版本
- 跳转平台集成工具

### 5.2 上传自己的工具

| 步骤 | 说明 |
|------|------|
| 创建工具 | 填写 slug、名称、类型（client/platform）、使用说明（Markdown） |
| 客户端首版 | 必须上传制品（`.zip` / `.exe` / `.msi`） |
| 发新版本 | 提交 changelog（Markdown）；客户端须附新制品 |
| 编辑/下架 | 仅工具**所有者**可改自己的工具元数据或下架 |

### 5.3 管理员

- 可**删除**任意工具（普通用户只能管理自己的）
- 用户管理、翻译任务清理等仍在 **用户管理** / 翻译页

---

## 6. 运维：构建功能录制包

在项目根目录（Windows）：

```powershell
.\scripts\build_feature_recorder.ps1
```

产物：

- `feature_recorder/release/feature-recorder-win64.zip`
- `feature_recorder/release/recorder/feature-recorder.cmd`

构建脚本会自动跑 **ZIP API 冒烟测试**。完成后：

```powershell
.\restart_dev.bat
```

后端 `tool_hub.bootstrap` 会将 zip 同步到 `TOOL_HUB_ARTIFACT_DIR`（默认 `backend/app/tool_artifacts`），工具集「功能录制」即可下载。

常用参数：

| 命令 | 说明 |
|------|------|
| `.\scripts\build_feature_recorder.ps1 -SkipClean` | 保留 Node/Chromium 缓存，加快二次构建 |
| `.\scripts\build_feature_recorder.ps1 -ExeOnly` | 跳过 Chromium，仅验证启动器 |

详见 [dev/modules/feature_recorder.md](./dev/modules/feature_recorder.md)。

---

## 7. 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `TOOL_HUB_ARTIFACT_DIR` | `backend/app/tool_artifacts` | 客户端制品存储目录 |

---

## 8. 常见问题

| 现象 | 处理 |
|------|------|
| 工具集「功能录制」无法下载 | 先执行构建脚本并重启后端 |
| 下载的是带拉链的「文件夹」 | 正常；需 **右键全部解压缩** 后再运行 |
| `feature-recorder.cmd` 闪退 | 看 `startup.log`；完整解压到 `C:\feature-recorder` |
| 3000 页面 Not Found | 用新版客户端；确认 `/api/status` 含 `runZipApi: true` |
| ZIP 生成报「未知 API」 | 关闭旧黑窗口，重新运行 `feature-recorder.cmd` |
| AI 翻译上传失败 | 确认 zip 内含 `meta.json`（用功能录制导出的 zip） |

---

## 9. 相关文档

| 文档 | 内容 |
|------|------|
| [dev/modules/tool_hub.md](./dev/modules/tool_hub.md) | API、数据模型、权限 |
| [backend/tests/tool_hub/README.md](./backend/tests/tool_hub/README.md) | **自动化测试集**（42 项） |
| [dev/modules/feature_recorder.md](./dev/modules/feature_recorder.md) | 录制客户端开发与打包 |
| [dev/modules/translate.md](./dev/modules/translate.md) | AI 翻译流水线 |
| [user_manual.md](./user_manual.md) | 平台整体用户手册 |

---

*designed by @yuzechao*
