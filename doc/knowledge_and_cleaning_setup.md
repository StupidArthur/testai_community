# 知识库 + 数据清洗：你需要准备什么

> 版本：2026-06-17  
> 面向：平台管理员 / 测试负责人  
> 说明：**不需要**额外接入第三方知识库 SaaS；能力均在 TestAI Community 后端内实现。

---

## 一、一句话结论

| 类别 | 是否需要你提供 |
|------|----------------|
| 外部知识库 API（如 Dify、FastGPT、企业 KB） | **不需要**，本系统自建 Chroma + SQLite |
| LLM API（MiniMax） | **需要**，`.env` 中配置 `MINIMAX_API_KEY` |
| 向量 / 视觉（Ollama 本机） | **需要**，同机安装并 pull 模型 |
| 旧版 `.doc` | **一般不用配**，项目自带 LibreOffice；首次可跑 `scripts/ensure_libreoffice.ps1` |
| 业务锚点词典 | **建议 Admin 维护**（产品功能树 + 同义词） |
| 目标知识库 | **不需要手动创建**；全站自动使用唯一默认知识库 |

---

## 二、环境与服务（必做）

### 2.1 MiniMax（云端 LLM）

用于：

| 场景 | 用途 |
|------|------|
| 知识库 RAG 对话 | 根据检索片段生成回答 |
| 数据清洗 | 段落提炼精华、库内冲突精判 |

`.env` 配置：

```env
MINIMAX_API_KEY=你的密钥
MINIMAX_MODEL=MiniMax-M2.7          # 或 Coding Plan 对应模型名
# MINIMAX_API_URL=https://api.minimaxi.com/v1
```

生产环境（`ENV=production`）未配置会直接启动失败。

### 2.2 Ollama（本机，免费）

用于：

| 场景 | 模型（默认） |
|------|----------------|
| 文档向量化（入库、检索） | `bge-m3` |
| PDF/Office 内嵌图、流程图描述 | `qwen2.5vl:7b` |
| 锚点向量匹配 | `bge-m3` |

```powershell
ollama pull bge-m3
ollama pull qwen2.5vl:7b
```

**一键检查（推荐）**：项目根目录或 `scripts` 下执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\ensure_ollama.ps1
```

或双击 `scripts\ensure_ollama.bat`。脚本会：检测 Ollama 是否安装 → 未运行则自动 `ollama serve` → 缺少模型则自动 `pull`（仅首次较慢）。

开发环境：`restart_dev.bat` / `restart_dev.ps1` 已集成上述检查（步骤 `[0/4]`）。

**生产环境**：不需要每次手动敲命令。推荐做法：

| 步骤 | 频率 | 说明 |
|------|------|------|
| 安装 Ollama | 一次 | [ollama.com](https://ollama.com/download)，安装程序默认开机自启 |
| `ensure_ollama.ps1` | 首次部署 / 升级模型 | 拉取 `bge-m3`、`qwen2.5vl:7b` |
| 日常重启后端 | 自动 | Ollama 常驻后台；后端只连 `OLLAMA_BASE_URL` |
| 可选 | 开机任务 | 将 `ensure_ollama.ps1 -SkipPull` 注册为 Windows 计划任务，仅保活 API |

若 Ollama 与后端不在同一台机，在 `.env` 把 `OLLAMA_BASE_URL` 指向内网 Ollama 服务器即可。

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBED_MODEL=bge-m3
OLLAMA_VL_MODEL=qwen2.5vl:7b
```

**要求**：Ollama 与后端在同一台机器（或 `OLLAMA_BASE_URL` 指向可达地址）。

### 2.3 LibreOffice（仅 `.doc` 旧格式）

| 情况 | 操作 |
|------|------|
| 只上传 docx / pdf / md | 无需关心 |
| 上传 `.doc` | 项目自带 `tools/LibreOffice/`，一般自动可用 |
| 转换失败 | 运行 `scripts/ensure_libreoffice.ps1`（安装 VC++，整机一次） |

### 2.4 A/B 双环境（开发 + 生产）

两套目录 **各自** 维护 `.env`，**不要共用**数据库与数据目录：

| 配置项 | 开发 (A) | 生产 (B) |
|--------|----------|----------|
| `ENV` | `dev` | `production` |
| `DATABASE_URL` | `database_dev.sqlite` | `database_prod.sqlite` |
| `BACKEND_PORT` | `48010` | `48011` |
| `SECRET_KEY` | 可选 | **必须** |
| `MINIMAX_API_KEY` | 可共用同一密钥 | 可共用 |
| `KNOWLEDGE_BASE_DATA_DIR` | 默认即可 | 建议显式指向 B 目录下 `data/` |

详见 [deploy_ab_same_pc.md](./deploy_ab_same_pc.md)。

---

## 三、业务侧建议准备的内容

这些**不是 API**，但直接影响清洗与检索质量。

### 3.1 知识库（全站唯一）

1. 顶栏 **知识库** 进入统一入口
2. **清洗入库** Tab：上传长文档 → 审核 → 批准入库
3. **知识问答** Tab：对已入库内容 RAG 对话

> 平台仅维护一个知识库（启动时自动创建；若已有库则复用最早创建的）。无需新建、切换多个库。

### 3.2 锚点词典（Admin）

路径：**知识库 → 清洗入库 → 锚点词典**（Admin）

| 你应提供 | 示例 |
|----------|------|
| 产品功能树 | 登录 → 短信验证码、密码登录 |
| 同义词 | 「短信 OTP」「验证码登录」→ `login_sms` |
| 模块 id | 英文 snake_case：`order_refund` |

启动时仅有少量种子（登录、订单、接口等）。**你们产品的真实功能树需要 Admin 补充**，否则锚点匹配会偏弱（仍可在审核页手工改）。

### 3.3 上传清洗任务时的元数据

| 字段 | 何时填 | 作用 |
|------|--------|------|
| 文档类型 | 必填 | PRD / 性能报告 / 混合 / 通用，影响提炼策略 |
| 产品 | 建议填 | 冲突判断 scope |
| 版本 | 有版本差异时填 | 区分 update / coexist |
| 环境 | 多环境时填 | 如 test / prod |

### 3.4 人工审核

自动处理完成后，需要人工：

- 检查 **精华正文** 是否准确  
- 确认 **锚点**、**操作**（新增 / 替换 / 并存 / 跳过）  
- 有 **逻辑冲突** 的段落必须选操作后才能批准入库  

---

## 四、不需要提供的内容

| 项目 | 说明 |
|------|------|
| 外部向量数据库账号 | 使用本地 Chroma（`data/knowledge_base/chroma/`） |
| 外部 RAG 平台 API | 检索 + 生成均在项目内 |
| Tavily / MIMO | 知识库与数据清洗 **不用**；其他模块（如 AI 早报）才用 |
| 单独部署清洗微服务 | 与主后端同进程，Worker 自动调度 |

---

## 五、内置 HTTP API 一览（对接 / 调试）

均需登录态：`Authorization: Bearer <token>`

### 5.1 知识库 `/api/knowledge-base`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/bases/default` | 全站默认唯一知识库 |
| GET | `/bases` | 知识库列表（单库模式下通常仅一条） |
| POST | `/bases` | 创建知识库（单库模式下已存在则 400） |
| GET | `/bases/{kb_id}` | 详情（含文档列表） |
| PATCH | `/bases/{kb_id}` | 修改名称/描述 |
| DELETE | `/bases/{kb_id}` | 删除库及向量 |
| POST | `/bases/{kb_id}/documents` | 直接上传文档（multipart） |
| DELETE | `/bases/{kb_id}/documents/{doc_id}` | 删除文档 |
| POST | `/bases/{kb_id}/chat` | RAG 问答 `{ "question": "..." }` |
| GET | `/bases/{kb_id}/messages` | 当前用户对话历史 |

### 5.2 数据清洗 `/api/data-cleaning`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/jobs` | 清洗任务列表（可选 `?kb_id=`） |
| POST | `/jobs` | 上传创建任务（multipart：`file` + 表单字段） |
| GET | `/jobs/{id}` | 任务详情含段落 |
| POST | `/jobs/{id}/reprocess` | 重新处理（段落为空或规则更新后） |
| PATCH | `/jobs/{id}/paragraphs/{pid}` | 更新段落精华/锚点/操作 |
| POST | `/jobs/{id}/approve` | 批准入库（可选 `paragraph_ids`） |
| GET | `/anchors` | 锚点列表 |
| POST | `/anchors` | 新建锚点（Admin） |
| PATCH | `/anchors/{id}` | 修改锚点（Admin） |

---

## 六、能力调用链（便于排错）

```
上传文档
  → 解析（python-docx / PyMuPDF / LibreOffice）
  → [有图] Ollama VL 描述
  → Ollama bge-m3 向量化
  → Chroma 存储

数据清洗（额外）
  → 切分 + 合并短段
  → MiniMax 提炼精华
  → Ollama 锚点匹配 + Chroma 召回
  → MiniMax 冲突精判
  → 人工审核
  → 批准 → KU + Chroma（ku_status=active）

RAG 问答
  → Ollama 问题向量化
  → Chroma 检索（过滤 superseded）
  → MiniMax 生成回答
```

---

## 七、成本与耗时参考

| 环节 | 依赖 | 说明 |
|------|------|------|
| 直接上传 1 份 docx | Ollama | 主要耗时在 embedding；有图则加 VL |
| 数据清洗 1 份长文档 | MiniMax + Ollama | **每段落 1~2 次 MiniMax**；段数多（如 60+）可能数分钟且消耗 Token |
| 单次 RAG 问答 | Ollama + MiniMax | 1 次 embedding + 1 次生成 |

控制成本建议：长文档走清洗、审核时大量 **跳过** 重复段；性能报告选正确 `doc_type`。

---

## 八、上线前检查清单

**环境**

- [ ] `MINIMAX_API_KEY` 有效（开发 / 生产 `.env` 各自配置）
- [ ] `ollama list` 含 `bge-m3`、`qwen2.5vl:7b`
- [ ] 后端 `/api/health` 正常
- [ ] 若需 `.doc`：已跑通 `scripts/ensure_libreoffice.ps1`
- [ ] 生产已设 `SECRET_KEY`、`ENV=production`

**业务**

- [ ] 后端已启动（自动确保默认知识库存在）
- [ ] Admin 已维护核心锚点词典（至少覆盖主要产品模块）
- [ ] 试跑 1 份 docx：清洗 → 审核 → 批准 → 知识库问答能引用

**双环境**

- [ ] A/B 使用不同 `DATABASE_URL`
- [ ] B 部署后单独 `npm run build` + 重启后端
- [ ] 不在 A/B 之间复制 `database_*.sqlite` 或 `data/knowledge_base/chroma/`

---

## 相关文档

- [data_cleaning.md](./data_cleaning.md) — 数据清洗功能说明  
- [knowledge_base.md](./knowledge_base.md) — 知识库用户手册  
- [deploy_ab_same_pc.md](./deploy_ab_same_pc.md) — 同机 A/B 部署  

---
