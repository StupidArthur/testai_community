# TestAI Community 需求文档

> 文档版本：2026-06-13  
> 项目路径：`G:/deploy/testai_community/`

---

## 1. 背景与目标

TestAI Community 将原 **Skill Hub（技能管理）** 与 **Recorder Translate（AI 翻译）** 合并为单一 Web 应用，提供统一的测试资产管理和 UI 录制翻译能力。

**核心目标：**

- 单一入口：一个前端 + 一个后端，共享认证与用户体系
- 技能全生命周期：创建、分支、版本、Fork、Merge、Pre-Commit AI 审查
- AI 翻译流水线：上传 UI 录制 ZIP → 自动翻译为中文测试用例 → 进度跟踪与结果下载
- 对内私有化部署，支持 Engineer / Admin 两种角色

---

## 2. 用户角色

| 角色 | 说明 | 典型能力 |
|------|------|----------|
| **Admin** | 系统管理员 | 用户管理、重置密码、删除翻译任务记录、Changelog 发布 |
| **Engineer** | 测试/开发工程师 | Skill 编辑、Fork/Merge、上传翻译任务、查看全部任务队列 |

> 首个注册用户自动成为 Admin；后续注册需 Admin 代为创建用户。

---

## 3. 功能需求

### 3.1 认证与用户

| ID | 需求 | 优先级 |
|----|------|--------|
| AUTH-01 | 用户登录，返回 JWT（60 分钟有效） | P0 |
| AUTH-02 | 首个用户注册为 Admin | P0 |
| AUTH-03 | Admin 创建/删除用户、重置密码 | P0 |
| AUTH-04 | 用户修改自己的密码 | P1 |
| AUTH-05 | 未认证访问受保护 API 返回 401 | P0 |
| AUTH-06 | SSE/下载使用短期 ticket（30s 一次性） | P0 |

### 3.2 技能管理（Skill Hub）

| ID | 需求 | 优先级 |
|----|------|--------|
| SK-01 | 技能列表、创建技能 | P0 |
| SK-02 | 分支管理：master / standard / personal | P0 |
| SK-03 | 九维 Prompt 编辑（结构化 + 纯文本双模式） | P0 |
| SK-04 | 版本时间线、创建新版本 | P0 |
| SK-05 | Pre-Commit AI 审查（评估草稿后提交） | P0 |
| SK-06 | Fork 分支、Merge 到 master | P1 |
| SK-07 | LLM 工具：run / lint / diff | P1 |
| SK-08 | Integration API：外部系统通过 API Key 调用 Skill | P1 |

### 3.3 AI 翻译（Translate）

| ID | 需求 | 优先级 |
|----|------|--------|
| TR-01 | 上传 UI 录制 ZIP（含 meta.json） | P0 |
| TR-02 | 任务队列：queued → running → completed/failed/cancelled | P0 |
| TR-03 | SSE 实时进度、任务详情页 | P0 |
| TR-04 | 完成后下载结果 ZIP、在线预览 Markdown/JSON | P0 |
| TR-05 | 取消 queued/running 任务 | P1 |
| TR-06 | Admin 删除已完成/失败任务记录 | P1 |
| TR-07 | 下载内置 Prompt 模板包 | P2 |

### 3.4 更新日志（Changelog）

| ID | 需求 | 优先级 |
|----|------|--------|
| CL-01 | 所有登录用户可查看 Changelog | P1 |
| CL-02 | Admin 创建/编辑/删除 Changelog 条目 | P1 |

### 3.5 日报管理（Daily Report）

| ID | 需求 | 优先级 |
|----|------|--------|
| DR-01 | 顶栏「日报管理」入口，纯文本上传日报 | P1 |
| DR-02 | Skill `Daily_Report_Structurer` 结构化并校验 | P1 |
| DR-03 | 结构化结果存 SQLite；工程师看自己、Admin 看全部 | P1 |

### 3.6 工具集（Tool Hub）

| ID | 需求 | 优先级 |
|----|------|--------|
| TH-01 | 工具列表：客户端下载 + 平台集成跳转 | P0 |
| TH-02 | 用户可上传/维护自己的 client 工具 | P1 |
| TH-03 | Admin 可删除任意工具 | P1 |
| TH-04 | 预置「功能录制」「AI 翻译」及推荐工作流 | P0 |

详见 [tool_hub.md](./tool_hub.md)。

### 3.7 数据清洗（Data Cleaning）

| ID | 需求 | 优先级 |
|----|------|--------|
| DC-01 | 上传长文档创建清洗任务；选择目标知识库、文档类型、产品/版本/环境 | P1 |
| DC-02 | 自动切分、LLM 提炼精华、锚点匹配、库内冲突检测 | P1 |
| DC-03 | 人工审核段落；批准后才写入知识库（Knowledge Unit + Chroma） | P1 |
| DC-04 | 冲突段落须选择 supersede/coexist/skip；superseded KU 不参与 RAG | P1 |
| DC-05 | Admin 维护锚点词典；启动种子基础功能树 | P2 |

详见 [data_cleaning.md](./data_cleaning.md)。

### 3.8 知识库（Knowledge Base）

| ID | 需求 | 优先级 |
|----|------|--------|
| KB-01 | 创建知识库（名称、描述）；全站列表可见 | P1 |
| KB-02 | 上传文档：md/txt/doc/docx/pdf/pptx/xlsx；异步处理队列 | P1 |
| KB-03 | 文档解析：文字提取 + 内嵌图片 VL 描述 + 分块向量化 | P1 |
| KB-04 | RAG 问答：检索 ChromaDB + MiniMax 生成；返回引用来源 | P1 |
| KB-05 | 对话历史：按用户隔离，持久化到 SQLite | P2 |
| KB-06 | 权限：全员可读/上传/对话；创建者/Admin 改删库；上传者/Admin 删文档 | P1 |
| KB-07 | 容量限制：单文件、单库总容量、单库文档数可配置 | P2 |

详见 [knowledge_base.md](./knowledge_base.md)（用户手册）与 [dev/modules/knowledge_base.md](./dev/modules/knowledge_base.md)（技术架构）。

### 3.9 门户与导航

| ID | 需求 | 优先级 |
|----|------|--------|
| NAV-01 | 首页双卡片导航（Skill 管理 / 工具集） | P0 |
| NAV-02 | 统一顶栏：模块切换、改密、退出、主题切换 | P1 |
| NAV-03 | 顶栏「数据清洗」「知识库」入口（数据清洗在知识库之前） | P1 |

---

## 4. 非功能需求

| 类别 | 要求 |
|------|------|
| **部署** | Windows 开发环境；后端单 worker（`MAX_CONCURRENT_JOBS=1`） |
| **数据库** | 默认 SQLite；A/B 开发/生产各用独立文件（见 `deploy_ab_same_pc.md`） |
| **安全** | API Key、SECRET_KEY 必须通过环境变量配置，禁止硬编码 |
| **日志** | 应用入口统一配置日志格式 |
| **过程文件** | 上传/结果存磁盘；任务元数据持久化到 DB |
| **并发** | 翻译任务默认单并发；多 worker 部署需额外设计 |

---

## 5. 已知限制与待办

| 项 | 状态 | 说明 |
|----|------|------|
| Translate 任务可见性 | 全员共享 | 所有登录用户可见全部任务（含排队/运行中），便于观察队列 |
| Pre-Commit Modal Loading | 已修复 | 评估结束在 `onSettled` 关闭 Spinner |
| Admin 前端路由守卫 | 已加强 | `/admin` 使用 `AdminRoute` + role 校验 |
| API Key 环境变量化 | 已完成 | 根目录 `.env` + `platform/config.py` |
| Markdown XSS 防护 | 待实现 | Changelog 渲染需 sanitize |
| skill_hub 自动化测试 | 缺失 | 后端测试未覆盖 Skill 模块 |

---

## 6. 验收标准（概要）

1. 登录后可访问 Skill Hub、Translate、Changelog、知识库 各模块
2. 上传合法录制 ZIP 后，任务能完成并下载结果
3. Skill 九维编辑、版本提交、Fork/Merge 流程可用
4. 知识库上传文档后可处理为「可用」状态，并能基于文档进行 RAG 问答
5. 无 token 访问 `/api/translate/*` 等受保护路由返回 401
6. 生产环境未设置 `SECRET_KEY` / `MINIMAX_API_KEY` 时拒绝启动

---

*文档维护：功能变更时请同步更新本文档。*
