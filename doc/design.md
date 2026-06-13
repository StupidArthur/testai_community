# TestAI Community 设计文档

> 文档版本：2026-06-13  
> 项目路径：`G:/deploy/testai_community/`

---

## 1. 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser (React SPA)                      │
│  Portal │ Skill Hub │ Translate │ Changelog │ Admin         │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / SSE
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI  platform/factory.py  (:48010)               │
│  ┌─────────┐ ┌───────────┐ ┌───────────┐ ┌──────────────────────────┐  │
│  │  auth   │ │ skill_hub │ │ translate │ │ platform (config/changelog)│  │
│  └────┬────┘ └─────┬─────┘ └─────┬─────┘ └────────────┬─────────────┘  │
│       └────────────┴─────────────┴────────────────────┘                 │
│              ai_service (LLM) + external_api                               │
└──────────────────────────┬──────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
      database.sqlite              磁盘 (uploads / results)
```

**开发模式**：前端 Vite `:3003`，`/api` 代理到后端 `:48010`。  
**生产模式**：`frontend/dist` 由后端静态托管 + SPA fallback。

---

## 2. 技术栈

| 层级 | 选型 |
|------|------|
| 前端 | React 19、Vite 8、TypeScript、Ant Design 5、TanStack Query 5、Zustand |
| 后端 | FastAPI、SQLAlchemy 2、Pydantic 2、PyJWT、passlib |
| 数据库 | SQLite（默认 `database.sqlite`） |
| LLM | MiniMax API（`ai_service/client.py` 统一封装） |

---

## 3. 目录结构

```
testai_community/
├── doc/                          # 项目文档（本目录）
├── backend/
│   ├── app/
│   │   ├── platform/             # config、database、factory、changelog
│   │   ├── ai_service/           # LLM 客户端
│   │   ├── auth/                 # JWT、用户、ticket
│   │   ├── skill_hub/            # Skill / Branch / Version
│   │   ├── translate/            # 上传、队列、worker、workflow
│   │   ├── external_api/         # X-API-Key 外部调用
│   ├── config/prompts/           # Translate 用 Prompt 模板
│   ├── scripts/seed_db.py        # 演示数据种子
│   ├── tests/                    # pytest
│   ├── requirements.txt
│   └── run.py                    # 生产启动脚本
└── frontend/
    └── src/
        ├── auth/                 # 登录
        ├── skill_hub/pages/      # Skill 业务页
        ├── translate/            # 翻译页与组件
        ├── changelog/            # Changelog 页
        └── shared/               # API、布局、类型、hooks
```

---

## 4. 模块设计

### 4.1 认证（auth）

- **JWT Bearer**：常规 API，`Authorization: Bearer <token>`
- **get_current_user_by_ticket**：Translate 统一入口，支持 Header + query `ticket`/`token`
- **ticket 机制**：`POST /api/translate/ticket` 颁发 30s 一次性 ticket，供 SSE/下载使用
- **RequireRole**：基于 `get_current_user` 的角色装饰依赖（Admin 专用路由）

```python
# 凭证解析顺序（get_current_user_by_ticket）
# 1. Authorization: Bearer
# 2. query ticket（一次性，TTLCache）
# 3. query token（JWT，兼容旧链接）
```

### 4.2 技能管理（skill_hub）

**数据模型：**

```
Skill (技能)
  └── Branch (分支: master / standard / personal)
        └── SkillVersion (版本，九维 Text 字段)
```

**九维字段：** role, profile, background, goals, constraints, core_skills, workflows, output_format, initialization

**External API：** `/api/v1/external/*`，通过 `X-API-Key` 认证 ServiceAccount。

### 4.3 AI 翻译（translate）

**分层：**

| 模块 | 职责 |
|------|------|
| `router.py` | HTTP 路由、上传、SSE、下载 |
| `jobs.py` | Job 状态、内存队列、DB 持久化 |
| `worker.py` | dispatcher、janitor、pipeline 执行 |
| `workflow.py` | 多阶段编排 |
| `preprocess/` | 录制数据预处理 |
| `phases/` | Phase1–4 LLM 调用 |
| `sse.py` | SSE 事件流（TypedDict，非 Pydantic response_model） |

**Job 状态机：**

```
QUEUED → RUNNING → COMPLETED
                 → FAILED
                 → CANCELLED
```

**路径常量**（`translate/__init__.py`，可由 `.env` 覆盖）：

- `TRANSLATE_UPLOAD_DIR` → 默认 `backend/app/uploads/`
- `TRANSLATE_RESULT_DIR` → 默认 `backend/app/results/`

**同机 A/B（开发 / 生产）**：两套项目目录 + 两份 `.env` + 独立 `DATABASE_URL`；发布时只同步代码，不覆盖生产库与 uploads。详见 [deploy_ab_same_pc.md](./deploy_ab_same_pc.md)。

### 4.4 platform 与 ai_service

**platform**（`app/platform/`）：

- **config.py**：`SECRET_KEY`、`DATABASE_URL`、`TRANSLATE_*`、`MINIMAX_*`、`CORS_ORIGINS`
- **database.py**：SQLAlchemy engine、`get_db`
- **route_guard.py**：启动时路由鉴权静态检查（非登录鉴权，见 [platform.md](./dev/modules/platform.md) §5）
- **factory.py**：`create_app()`、lifespan、SPA、`/api/health`

**ai_service**（`app/ai_service/`）：

- **client.py**：`chat()`，经 ModelRegistry → Provider
- **news/**：Tavily 搜索（`days=1`、链接白名单）+ `chat` 总结 + 校验，生成 AI 早报 Markdown（`python -m app.ai_service.news`）

---

## 5. API 设计

### 5.1 路由前缀

| 前缀 | 模块 |
|------|------|
| `/api/auth` | 认证与用户 |
| `/api/skills` | Skill Hub |
| `/api/v1/external` | 外部 API（工具链 / CI） |
| `/api/translate` | AI 翻译 |
| `/api/changelog` | platform.changelog（更新日志） |
| `/api/health` | 健康检查 |

### 5.2 Translate 主要接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/translate/jobs` | multipart 上传 ZIP，创建任务 |
| GET | `/api/translate/jobs` | 任务列表 |
| GET | `/api/translate/jobs/{id}` | 任务详情 |
| GET | `/api/translate/jobs/{id}/stream` | SSE 进度 |
| GET | `/api/translate/jobs/{id}/download` | 下载结果（ticket） |
| POST | `/api/translate/ticket` | 获取 SSE/下载 ticket |
| POST | `/api/translate/jobs/{id}/cancel` | 取消任务 |

### 5.3 应用工厂（platform/factory.py）

后端唯一装配层，**不包含业务逻辑**：

```python
from app.platform.factory import create_app, app

# 测试 / 自定义装配时可调用工厂
application = create_app()

# uvicorn 默认入口（run.py 使用）
# app.platform.factory:app
```

`create_app()` 负责：FastAPI 实例、中间件、循环 `registry.APPS` 注册路由、lifespan（建表、各 App 钩子）、SPA 静态回落。

新模块接入时在 `platform/registry.py` 追加 `AppModule`；`factory.py` 不再逐个写死 bootstrap。

### 5.4 启动时安全断言

`platform/factory.py` 在 lifespan 中对 `APPS` 内每个 router 执行 `assert_router_protected`：除 `/api/health` 外，所有路由必须依赖 JWT / ticket / `RequireRole`。

---

## 6. 前端设计

### 6.1 路由

| 路径 | 页面 |
|------|------|
| `/login` | 登录 |
| `/` | 门户首页 |
| `/skills` | 技能列表 |
| `/skill/:skillId` | 分支列表 |
| `/skill/:skillId/branch/:branchId` | 沙盒编辑 |
| `/admin` | 用户管理 |
| `/translate` | 翻译任务列表 |
| `/translate/jobs/:jobId` | 任务详情 |
| `/changelog` | 更新日志 |

### 6.2 状态与 API

- **TanStack Query**：服务端状态（skills、jobs、users）
- **Zustand persist**：主题（dark/light）
- **双 API 客户端**：
  - Axios `apiClient` → Skill / Auth / Changelog
  - `apiFetch` + XHR → Translate（上传、SSE ticket）

### 6.3 认证存储

- `localStorage.token`：JWT
- `localStorage.user`：用户信息 JSON
- 路由守卫：`ProtectedRoute` 校验 token 存在且未过期（客户端 exp 检查）

---

## 7. 数据模型（概要）

### users

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | |
| username | String unique | |
| password_hash | String | bcrypt |
| role | Enum | Engineer / Admin |

### translate_jobs

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String PK | UUID |
| status | String | queued/running/completed/failed/cancelled |
| username | String | 创建者（当前无 FK） |
| upload_path | String | 解压目录 |
| result_zip_path | String | 结果 ZIP |

### skills / branches / skill_versions

见 `backend/app/skill_hub/models.py`。

---

## 8. 部署约束

1. **单 worker**：uvicorn `workers=1`，与内存队列、`MAX_CONCURRENT_JOBS=1` 一致
2. **ticket 存储**：进程内 TTLCache，多实例不共享
3. **SQLite**：并发写有限，生产建议 PostgreSQL
4. **环境变量**：生产必须设置 `SECRET_KEY`、`MINIMAX_API_KEY`

---

## 9. 与 SPEC.md 的关系

根目录 `SPEC.md` 为早期设计快照；本文档以当前代码为准。主要差异：

- API 路径已为 `/api/translate/*`（非 `/translate/api/*`）
- 认证已统一 `get_current_user_by_ticket` + ticket
- 启动入口：`app.platform.factory.create_app()` / `run.py`

---

## 10. 扩展与接入

- **[开发文档（dev/）](./dev/README.md)** — 分模块 Mermaid 架构、HTTP 接口、调用关系、数据库表  
- **[模块内部 Python API（dev/module_internal_api.md）](./dev/module_internal_api.md)** — 跨 App 允许 import 的函数与依赖矩阵  
- **[架构指南（architecture_guide.md）](./architecture_guide.md)** — 单 APP 约束、公共模块清单  
- **[如何接入新模块（how_to_add_new_app.md）](./how_to_add_new_app.md)** — step-by-step 操作手册

---

*文档维护：架构或 API 变更时请同步更新本文档。*
