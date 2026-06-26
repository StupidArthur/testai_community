# 知识库用户手册

> 文档版本：2026-06-16  
> 面向对象：平台使用者（测试工程师、管理员）

---

## 1. 功能概述

知识库是 TestAI Community 的 **RAG（检索增强生成）** 模块：上传文档后自动解析、向量化，即可基于文档内容进行智能问答。

**核心特点：**

- **全站共享**：所有登录用户可查看任意知识库、上传文档、进行对话
- **多格式支持**：md、txt、doc、docx、pdf、pptx、xlsx
- **图文混合**：PDF/Office 内嵌图片与流程图由本地视觉模型识别
- **引用溯源**：回答附带参考文档名、页码与片段摘要

| 操作 | 权限 |
|------|------|
| 查看知识库 / 上传文档 / 对话 | 所有登录用户 |
| 删除自己上传的文档 | 文档上传者 |
| 删除任意文档 | Admin |
| 修改 / 删除知识库 | 知识库创建者 或 Admin |

---

## 2. 界面与使用步骤

### 2.1 入口

登录后，顶栏点击 **知识库** 进入列表页（`/knowledge-base`）。

### 2.2 创建知识库

1. 点击 **新建知识库**
2. 填写名称与描述（描述可选）
3. 创建成功后自动进入详情页；创建者拥有该库的修改/删除权限

### 2.3 上传文档

1. 进入知识库详情页（`/knowledge-base/{id}`）
2. 点击 **上传文档**，选择本地文件（任意登录用户均可上传）
3. 文档进入异步处理队列，状态变化如下：

| 状态 | 含义 |
|------|------|
| 排队中 | 等待 Worker 处理 |
| 处理中 | 正在解析、分块、向量化 |
| 可用 | 已入库，可参与 RAG 检索 |
| 失败 | 处理出错，可查看错误信息 |

页面在有文档处于「排队中 / 处理中」时会每 3 秒自动刷新状态。

### 2.4 知识库对话

1. 确保至少有一份文档状态为 **可用**
2. 在详情页右侧 **知识库对话** 面板输入问题并发送
3. 系统检索相关片段，由 MiniMax 生成中文回答
4. 回答下方展示 **参考来源**（文档名、页码、片段摘要）
5. 对话历史按用户隔离：每人只能看到自己与该库的问答记录

### 2.5 管理操作

| 操作 | 条件 |
|------|------|
| 删除文档 | 上传者本人，或 Admin |
| 修改知识库名称/描述 | 创建者，或 Admin |
| 删除知识库 | 创建者，或 Admin（同时删除原始文件与向量数据） |

---

## 3. 支持的文档格式

| 格式 | 处理方式 |
|------|----------|
| `.md` / `.markdown` / `.txt` | 直接读取文本 |
| `.docx` / `.pptx` / `.xlsx` | python-docx / python-pptx / openpyxl 解析 |
| `.pdf` | PyMuPDF 提取文字与内嵌图片 |
| `.doc` | 需 LibreOffice 转为 docx 后解析（见下文环境准备） |

文档中的 **图片与流程图** 会调用本地 Ollama 视觉模型（默认 Qwen2.5-VL）生成文字描述，再一并参与分块与检索。

---

## 4. 环境准备与部署

### 4.1 Ollama（与后端同机部署）

Embedding 与视觉识别使用本地 Ollama，**免费、无需外网 API**：

```powershell
ollama pull qwen2.5vl:7b
ollama pull bge-m3
```

大模型体积较大（`qwen2.5vl:7b` 约 6GB），下载完成后执行 `restart_dev.bat` 重启开发环境。

确认 Ollama 服务运行中（默认 `http://127.0.0.1:11434`）。

### 4.2 `.env` 配置

在项目根目录 `.env` 中配置：

```env
# 问答生成（必需）
MINIMAX_API_KEY=你的密钥

# Ollama（Embedding + 视觉）
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_API_KEY=
OLLAMA_VL_MODEL=qwen2.5vl:7b
OLLAMA_EMBED_MODEL=bge-m3
```

可选知识库参数（默认值见 `.env.example`）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `KB_MAX_UPLOAD_MB` | 30 | 单文件大小上限 |
| `KB_MAX_TOTAL_MB` | 500 | 单知识库总容量 |
| `KB_MAX_DOCS_PER_KB` | 100 | 单知识库文档数 |
| `KB_MAX_CONCURRENT_JOBS` | 2 | 并发文档处理数 |
| `KB_CHUNK_SIZE` | 800 | 分块字符数 |
| `KB_CHUNK_OVERLAP` | 120 | 分块重叠字符数 |
| `KB_RAG_TOP_K` | 6 | 检索返回片段数 |
| `KNOWLEDGE_BASE_DATA_DIR` | `data/knowledge_base/` | 原始文件目录 |
| `KNOWLEDGE_BASE_CHROMA_DIR` | `.../chroma/` | ChromaDB 向量库目录 |

### 4.3 旧版 `.doc` 文件

项目已自带 **LibreOffice**（`tools/LibreOffice/`），**一般无需配置**。后端会自动：

1. 使用本目录下的 `tools/LibreOffice/program/soffice.com`
2. 将用户配置写入 `data/libreoffice_profile/`（A/B 环境各自独立）

**首次在本机使用 .doc** 时，若转换失败，在项目根执行一次：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/ensure_libreoffice.ps1
```

该脚本会安装 VC++ 运行库并校验 LibreOffice（整机只需一次）。

若使用系统安装的 LibreOffice，可在 `.env` 中指定（A/B 各自 `.env` 独立）：

```env
LIBREOFFICE_SOFFICE_PATH=C:/Program Files/LibreOffice/program/soffice.com
```

也可将 `.doc` 另存为 `.docx` 后上传。

### 4.4 Python 依赖

```powershell
cd backend
pip install -r requirements.txt
```

主要新增依赖：`chromadb`（向量存储）、文档解析库（PyMuPDF、python-docx 等）。

### 4.5 启动

与平台其他模块相同，使用 `restart_dev.bat` 或分别启动前后端。后端启动时会自动：

- 创建 `knowledge_*` 数据库表
- 启动文档处理 Worker 后台任务

---

## 5. 容量限制（默认）

| 项 | 默认值 | 环境变量 |
|----|--------|----------|
| 单文件 | 30 MB | `KB_MAX_UPLOAD_MB` |
| 单知识库总容量 | 500 MB | `KB_MAX_TOTAL_MB` |
| 单知识库文档数 | 100 个 | `KB_MAX_DOCS_PER_KB` |

超出限制时上传接口返回 413 或 400 错误。

---

## 6. 数据存储

| 路径 | 内容 |
|------|------|
| `data/knowledge_base/{kb_id}/raw/` | 原始上传文件 |
| `data/knowledge_base/chroma/` | ChromaDB 持久化向量库 |
| SQLite `knowledge_bases` / `knowledge_documents` / `knowledge_chat_messages` | 元数据与对话历史 |

删除知识库时会同步清理磁盘文件与 Chroma collection。

---

## 7. 常见问题

**Q：上传后一直「排队中」？**  
检查后端日志；确认 Ollama 已启动且模型已 pull；Worker 默认最多 2 个并发任务。

**Q：文档状态「失败」？**  
详情页可查看 `error` 字段。常见原因：格式损坏、`.doc` 未装 LibreOffice、Ollama 不可用、PDF 无文字且无图片。

**Q：对话提示「尚无可用文档」？**  
需至少一份文档处理为「可用」状态后再提问。

**Q：A/B 开发/生产环境如何隔离？**  
与 translate 相同：`DATABASE_URL` 与 `KNOWLEDGE_BASE_DATA_DIR` 各环境独立配置，禁止共用。详见 [deploy_ab_same_pc.md](./deploy_ab_same_pc.md)。

---

## 8. 相关文档

| 文档 | 说明 |
|------|------|
| [dev/modules/knowledge_base.md](./dev/modules/knowledge_base.md) | 技术架构与 API |
| [dev/modules/ai_service.md](./dev/modules/ai_service.md) | document / RAG 子模块 |
| [requirements.md](./requirements.md) §3.8 | 功能需求 |
| [design.md](./design.md) §4.5 | 系统设计 |

---

designed by @yuzechao
