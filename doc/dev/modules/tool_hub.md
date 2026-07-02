# 工具集（tool_hub）

> 文档版本：2026-06-15  
> API 前缀：`/api/tool-hub` · 前端路由：`/tool-hub`

---

## 1. 功能概述

管理两类工具：

| tool_kind | 说明 | 主操作 |
|-----------|------|--------|
| `client` | 客户端可下载工具（exe / zip / msi） | 下载最新版本制品 |
| `platform` | 平台集成工具模块（如 AI 翻译） | 跳转站内路径或外链 |

预留字段 `tool_type`，当前默认 `default`。

### 权限

| 操作 | 普通用户 | 管理员 |
|------|----------|--------|
| 浏览已上架工具 | ✓ | ✓ |
| 上传新工具 | ✓ | ✓ |
| 为自己工具发新版本 | ✓ | ✓ |
| 编辑 / 下架自己的工具 | ✓ | ✓ |
| 删除工具 | ✗ | ✓ |

上传首版必须提供 Markdown 使用说明；发布新版本须提交 Markdown changelog。客户端工具新版本须上传制品文件。

---

## 2. HTTP 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tool-hub/tools` | 列表（`?tool_kind=`、`?tool_type=`） |
| GET | `/api/tool-hub/tools/{id}` | 详情（含合并 Markdown） |
| POST | `/api/tool-hub/tools` | 创建（multipart） |
| POST | `/api/tool-hub/tools/{id}/versions` | 新版本（multipart） |
| PUT | `/api/tool-hub/tools/{id}` | 编辑元数据（含最新版本 `manual_md`）/ 上下架 |
| DELETE | `/api/tool-hub/tools/{id}` | 删除（仅 Admin） |
| GET | `/api/tool-hub/tools/{id}/download` | 下载客户端工具最新制品 |

### 详情页 Markdown 结构

1. **使用说明** — 取最新非空 `manual_md`
2. **版本更新记录** — 各版本 `changelog_md`（新版在前）

---

## 3. 数据模型

- `tools`：slug、display_name、tool_kind、tool_type、link_url、owner、enabled
- `tool_versions`：version_label、manual_md、changelog_md、artifact 文件名与存储路径

制品目录：`TOOL_HUB_ARTIFACT_DIR`（默认 `backend/app/tool_artifacts`）

---

## 4. 启动预置

`bootstrap.ensure_tool_hub_startup` 自动注册：

| slug | 名称 | 类型 | 说明 |
|------|------|------|------|
| `ai_translate` | AI 翻译 | platform | `link_url=/translate` |
| `feature_recorder` | 功能录制 | client | 下载 `feature-recorder-win64.zip`（需先执行构建脚本） |

二者为**并列工具**：先录制 zip，再上传 AI 翻译。详见 [feature_recorder.md](./feature_recorder.md)。

---

## 5. 前端

| 路径 | 页面 |
|------|------|
| `/tool-hub` | 工具集首页（卡片） |
| `/tool-hub/:toolId` | 工具详情（统一样式：标题 + 下载/跳转 + Markdown 滚动区；所有者「编辑」可改标题、链接、类型及使用说明 Markdown） |

平台集成工具页（如 `/translate`）**不在顶栏与首页单独展示**，仅从工具集进入；页内提供 **返回工具集** 按钮（`ReturnToToolHubButton`）。

---

*designed by @yuzechao*
