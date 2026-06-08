# TestAI Community 代码评审报告（第二轮）

> 评审人：MiMo
> 评审日期：2026-06-08（复审）
> 项目：TestAI Community（统一测试资产管理与 AI 翻译平台）
> 代码范围：backend/app + frontend/src 全量源码

---

## 一、修复情况总览

上一轮提出的 **3 个 P0 问题**中，已修复 2 个；**5 个 P1 问题**中，已修复 3 个。translate 模块完成了重大重构——将外部包 `recorder_translate_server` 的全部源码内化到 `app/translate/` 目录下，消除了外部依赖。整体质量有明显提升。

| 原编号 | 问题 | 状态 |
|--------|------|------|
| 2.1 | API Key 硬编码 | ❌ **未修复** — MINIMAX_API_KEY 仍在 config.py:16 |
| 2.2 | translate 依赖外部包 | ✅ 已修复 — 全部内化为相对导入 |
| 2.3 | integration 引用废弃字段 | ✅ 已修复 — 改用 9 维模型 + version_to_langgpt_payload |
| 3.1 | template vs standard 命名 | ❌ **未修复** — 前端仍用 `standard`，后端仍用 `template` |
| 3.2 | SkillVersion.id 类型不匹配 | ❌ **未修复** — 前端仍定义为 `number` |
| 3.3 | main.py 损坏的死代码 | ✅ 已删除 |
| 3.4 | SECRET_KEY 硬编码默认值 | ✅ 已修复 — 环境变量 + 警告 |
| 3.5 | utils.py 过时的 5 维代码 | ✅ 已修复 — 已更新为 9 维 |

---

## 二、遗留严重问题（P0）

### 2.1 🔴 MINIMAX_API_KEY 仍然硬编码

**文件：** `backend/app/core/config.py:16`

```python
MINIMAX_API_KEY = "sk-cp-aXV4X8TlWZeR3E1hpIaPtjEFnafrpbEi_IMlm6NhSY_0-CQHOV5WupxDkg4LV2JXfB3sO_AoGodPCkQ6irIC7PuIoxC29MVKqG70AYz_hQ1VIjNDgSpCvOo"
```

上一轮已指出，此问题未修复。API Key 泄露到版本控制是最高优先级安全风险。

**建议：**
```python
MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
```

---

### 2.2 🔴 translate 模块新增依赖未加入 requirements.txt

translate 模块内化后引入了新的 Python 包依赖，但 `requirements.txt` 未更新：

| 包 | 导入位置 | requirements.txt |
|---|---|---|
| `openai` | `translate/client.py:11` | ❌ 缺失 |
| `pyyaml` (`yaml`) | `translate/config.py:9` | ❌ 缺失 |

应用启动时，`from openai import AsyncOpenAI` 将直接 `ModuleNotFoundError`。

**建议：** 更新 `requirements.txt`：
```
openai>=1.0.0
pyyaml>=6.0
```

---

## 三、遗留高优先级问题（P1）

### 3.1 🟠 前后端 `template` vs `standard` 命名不一致

此问题仍未修复：

- **后端** `skills_router.py:120`：`branch_type="template"`
- **前端** `client.ts:33`：`branch_type: 'master' | 'standard' | 'personal'`
- **前端** `SkillBranches.tsx:99`：`b.branch_type === 'standard'`

**后果：** 后端创建的 `template` 分支在前端不会被识别为标准模板分支，UI 样式和标签显示异常。

**建议：** 后端改为 `"standard"`（改动最小，仅 `skills_router.py:120` 和 `199`）。

---

### 3.2 🟠 `SkillVersion.id` 类型不匹配

此问题仍未修复：

- **后端模型** `models.py:73`：`id = Column(String, primary_key=True, default=generate_uuid)` → UUID 字符串
- **前端类型** `client.ts:35` 和 `models.ts:43`：`id: number`
- **前端 merge 调用** `client.ts:86`：`source_version_id: number`

**建议：** 前端两处类型定义中 `id` 改为 `string`，`source_version_id` 改为 `string`。

---

### 3.3 🟠 `translate/workflow.py` 与 `translate/app.py` 存在双重 LLM 调用

**文件：** `translate/app.py:164-182` 和 `translate/workflow.py:52`

`app.py` 中先创建了 `audit = LlmAudit(...)`，然后调用 `run_workflow()`。但 `run_workflow()` 内部（`workflow.py:52`）又创建了一个新的 `LlmAudit` 实例：

```python
# app.py:167
audit = LlmAudit(job.upload_path, client, log)

# workflow.py:52 (run_workflow 内部)
audit = LlmAudit(run_dir, client, _log)  # 又创建了一个
```

`app.py` 中创建的 `audit` 对象被传入 `run_workflow` 但未被使用（`run_workflow` 没有 `audit` 参数），导致：
1. `app.py` 的 `audit.finalize()` 调用（`app.py:181`）审计的是空数据
2. 真正的审计数据在 `run_workflow` 内部的 `audit` 中
3. `run_workflow` 结束时自己调用了 `audit.finalize()`（`workflow.py:131`），所以审计数据实际上被写了两次

**建议：** 移除 `app.py` 中多余的 `LlmAudit` 实例化和 `audit.finalize()` 调用，或将 `audit` 作为参数传入 `run_workflow`。

---

## 四、中优先级问题（P2）

### 4.1 🟡 前端 `Dashboard.tsx` 中 `creating` 状态管理有误

**文件：** `frontend/src/skill_hub/pages/Dashboard.tsx:51-54`

```typescript
setCreating(true)
createMutation.mutate(form)
setCreating(false)  // ← 立即执行，mutation 是异步的
```

`setCreating(false)` 在 `mutate` 发起后立即执行，loading 状态完全无效。

**建议：** 删除 `creating` state，直接使用 `createMutation.isPending`。

---

### 4.2 🟡 `FilePreview` 未携带认证 Token

**文件：** `frontend/src/translate/components/ResultPreview.tsx:50`

```typescript
const res = await fetch(getFileUrl(jobId, path))
```

使用原生 `fetch` 而非 `apiFetch`，不会注入 Bearer Token。虽然当前 translate 路由无独立认证，但如果主 app 的全局认证中间件生效，此处会 401。

**建议：** 统一使用 `apiFetch` 或手动添加 Authorization header。

---

### 4.2 🟡 未清理的废弃文件

以下文件属于历史遗留，应删除：

| 文件 | 原因 |
|------|------|
| `backend/app/main_combined.py` | 废弃的网关模式入口，SPEC.md 已标注废弃 |
| `backend/app/core/security.py` | 与 `auth/service.py` 功能完全重复 |
| `frontend/vite.config.js` | 与 `vite.config.ts` 重复，配置不完整 |
| `frontend/src/shared/styles/globals.css` | 与 `global.css` 冲突（主题色不同），且未被引用 |

---

### 4.3 🟡 `vite.config.ts` 含 Python 风格注释

**文件：** `frontend/vite.config.ts:16`

```typescript
# 统一入口：combined 后端（:48010）
```

`#` 不是 TypeScript 的合法行注释语法。当前能运行是因为 esbuild 的宽容解析，但不规范。

**建议：** 改为 `//`。

---

### 4.4 🟡 缺少 `.gitignore`

项目根目录没有 `.gitignore`，`backend/venv/`、`frontend/node_modules/`、`backend/database.sqlite`、`__pycache__/` 等会被纳入版本控制。

---

### 4.5 🟡 CORS 中间件重复配置

`main_merged.py` 设置了 `allow_origins=["*"]`，`translate/app.py` 内部也设置了 `allow_origins=["*"]`。当 translate app 被 mount 时，两层 CORS 中间件会重复添加 `Access-Control-Allow-Origin` header，可能导致部分浏览器拒绝响应。

**建议：** 移除 `translate/app.py` 中的 CORS 中间件（第 58-64 行），由主 app 统一管理。

---

## 五、低优先级问题（P3）

### 5.1 🟢 `translate/config.py` 配置文件搜索路径过于宽泛

**文件：** `translate/config.py:107-115`

```python
def _get_config_candidates() -> list[Path]:
    app_dir = get_app_dir()
    pkg_dir = _get_package_dir()
    return [
        app_dir / "config" / "ai.yaml",
        app_dir / "config" / "ai.local.json",
        pkg_dir / "config" / "ai.yaml",
        pkg_dir / "config" / "ai.local.json",
        Path.cwd() / "config" / "ai.yaml",
        Path.cwd() / "config" / "ai.local.json",
        Path.cwd() / "release1" / "config" / "ai.local.json",  # ← 这是什么？
    ]
```

`release1/config/ai.local.json` 看起来是某个特定部署的遗留路径，不应出现在通用代码中。`Path.cwd()` 的搜索路径在 uvicorn 多进程部署时不可预测。

**建议：** 精简为 2-3 个确定性路径。

---

### 5.2 🟢 前端重复定义类型

`client.ts` 和 `types/models.ts` 都定义了 `User`、`Skill`、`Branch`、`SkillVersion` 等接口，存在维护不同步风险（事实上两边目前是一致的，但只维护一处更安全）。

---

### 5.3 🟢 `on_event("startup")` 已废弃

FastAPI 官方建议使用 `lifespan` 上下文管理器替代 `@app.on_event("startup")`。当前功能正常，但未来版本可能移除支持。

---

### 5.4 🟢 translate 模块所有状态存储在内存中

**文件：** `translate/jobs.py:61-63`

```python
jobs: dict[str, Job] = {}
job_queue: collections.deque[str] = collections.deque()
running_jobs: dict[str, Job] = {}
```

服务重启后所有翻译任务丢失。当前开发阶段可接受，但应明确标注此限制。

---

### 5.5 🟢 `AppLayout` 每次渲染都解析 localStorage

**文件：** `frontend/src/shared/components/AppLayout.tsx:22`

```typescript
const user = JSON.parse(localStorage.getItem('user') || '{}')
```

性能影响微小，但建议用 `useMemo` 缓存。

---

## 六、问题汇总

| 级别 | 编号 | 问题 | 文件 | 状态 |
|------|------|------|------|------|
| P0 | 2.1 | MINIMAX_API_KEY 硬编码 | `core/config.py` | ❌ 未修复 |
| P0 | 2.2 | requirements.txt 缺 openai/pyyaml | `requirements.txt` | 🆕 新发现 |
| P1 | 3.1 | template vs standard 命名不一致 | 前后端多处 | ❌ 未修复 |
| P1 | 3.2 | SkillVersion.id 类型不匹配 | 前端 client.ts/models.ts | ❌ 未修复 |
| P1 | 3.3 | workflow 与 app 双重 LlmAudit | `translate/workflow.py` | 🆕 新发现 |
| P2 | 4.1 | Dashboard creating 状态有误 | `Dashboard.tsx` | ❌ 未修复 |
| P2 | 4.2 | FilePreview 未携带 Token | `ResultPreview.tsx` | ❌ 未修复 |
| P2 | 4.2 | 废弃文件未清理 | main_combined/security/vite.config.js/globals.css | ❌ 未修复 |
| P2 | 4.3 | vite.config.ts # 注释 | `vite.config.ts` | ❌ 未修复 |
| P2 | 4.4 | 缺少 .gitignore | 项目根目录 | ❌ 未修复 |
| P2 | 4.5 | CORS 中间件重复 | `translate/app.py` | ❌ 未修复 |
| P3 | 5.1 | config 搜索路径含 release1 | `translate/config.py` | 🆕 新发现 |
| P3 | 5.2 | 前端重复定义类型 | client.ts / models.ts | ❌ 未修复 |
| P3 | 5.3 | on_event 废弃 | `translate/app.py` | ❌ 未修复 |
| P3 | 5.4 | translate 状态仅存内存 | `translate/jobs.py` | 已知限制 |
| P3 | 5.5 | localStorage 重复解析 | `AppLayout.tsx` | ❌ 未修复 |

---

## 七、结论

本轮复审确认了上轮 3 个 P0 中 2 个已修复（translate 外部依赖内化、integration 字段名更新），1 个未修复（API Key 硬编码）。translate 模块的内化重构工作量大、质量不错，但引入了新的依赖声明缺失问题。

**当务之急：**
1. 将 `MINIMAX_API_KEY` 改为环境变量读取
2. 在 `requirements.txt` 中添加 `openai` 和 `pyyaml`
3. 统一前后端 `template`/`standard` 命名

这三个问题修复后，应用即可正常启动运行。
