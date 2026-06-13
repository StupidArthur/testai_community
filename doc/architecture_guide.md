# 单 APP 架构指南

> 文档版本：2026-06-13  
> 面向对象：需要扩展平台、接入新业务模块的开发者

---

## 1. 架构原则：一个 APP，多个业务模块

TestAI Community 采用 **单应用（Monolith SPA + Monolith API）** 模式：

| 层级 | 形态 | 说明 |
|------|------|------|
| **前端** | 一个 React SPA | 统一登录、统一顶栏、统一主题；各业务以「模块目录 + 路由」接入 |
| **后端** | 一个 FastAPI 进程 | 统一端口（48010）；各业务以「Python 包 + APIRouter」接入 |
| **认证** | 一套用户体系 | 所有模块共享 `users` 表与 JWT |
| **部署** | 一次构建、一次启动 | 生产环境后端托管 `frontend/dist`，无独立微服务 |

**不做的事（当前约定）：**

- 不为每个业务模块单独起端口或单独部署前端
- 不在模块内再搞一套用户/登录体系
- 不使用命令行参数传业务配置（用函数参数 + 模块顶部常量 + 环境变量）

```
                    ┌─────────────────────────────────┐
                    │         单 SPA（frontend）        │
                    │  shared/  auth/  skill_hub/  …   │
                    └───────────────┬─────────────────┘
                                    │ /api/*
                    ┌───────────────▼─────────────────┐
                    │    platform/factory.py（单进程）       │
                    │  platform/ auth/ skill_hub/ …    │
                    └───────────────┬─────────────────┘
                                    │
                         database.sqlite + 磁盘文件
```

---

## 2. 后端：单 APP 对各部分的要求

### 2.1 目录与职责

每个业务模块是 `backend/app/<模块名>/` 下的**独立 Python 包**，至少包含：

| 文件 | 职责 | 是否必须 |
|------|------|----------|
| `router.py` | 定义 `APIRouter`，挂载 HTTP 路由 | 必须 |
| `schemas.py` | Pydantic 请求/响应模型 | 推荐 |
| `models.py` / `models_db.py` | SQLAlchemy 模型（若有持久化） | 按需 |
| `service.py` | 业务逻辑，与路由解耦 | 推荐 |
| `__init__.py` | 模块级常量（如路径、配置） | 推荐 |

**公共层**（不可复制、直接依赖）：

```
backend/app/
├── platform/factory.py      # create_app()：循环 APPS、lifespan、SPA 回落
├── platform/registry.py     # AppModule 注册表（新增 App 主要改这里）
├── platform/app_module.py   # AppModule dataclass
├── platform/           # config / database / route_guard / changelog
├── ai_service/         # LLM 客户端；后续 RAG / Memory
└── auth/               # 用户、JWT、ticket、RequireRole
```

### 2.2 API 路由约定

| 规则 | 说明 | 示例 |
|------|------|------|
| **统一前缀** | 业务 API 以 `/api/<模块名>` 开头 | `/api/translate/jobs` |
| **独立 Router** | 每个模块导出一个 `router = APIRouter(prefix=...)` | `translate/router.py:40` |
| **在入口注册** | 只在 `platform/registry.py` 追加 `AppModule` | factory 循环 APPS |
| **健康检查** | 全局仅 `/api/health`，业务模块不自建 health | — |
| **响应格式** | JSON + Pydantic `response_model`；错误用 `HTTPException(detail=中文)` | — |

当前已注册 App（`platform/registry.py` → `APPS`）：

| App | 前缀 |
|-----|------|
| auth | `/api/auth` |
| skills | `/api/skills` |
| external_api | `/api/v1/external` |
| platform.changelog | `/api/changelog` |
| translate | `/api/translate` |

`factory.create_app()` 循环 `APPS` 执行 `include_router`；无需在 factory 内手写各 router。

### 2.3 认证要求

模块路由**默认必须鉴权**，按场景选择依赖：

| 依赖 | 适用场景 | 能力 |
|------|----------|------|
| `get_current_user` | 普通 REST，客户端带 Bearer Header | 标准 JWT |
| `get_current_user_by_ticket` | 需要 SSE / 下载 / query ticket 的场景 | Bearer + ticket/token query |
| `RequireRole(["Admin"])` | 仅管理员 | 基于 JWT 的角色校验 |

```python
from app.auth.service import get_current_user, get_current_user_by_ticket, RequireRole
from app.auth.models import User

@router.get("/items")
def list_items(user: User = Depends(get_current_user)):
    ...

@router.get("/stream")
def stream(user: User = Depends(get_current_user_by_ticket)):
    ...  # 支持 ?ticket= 供 EventSource 使用
```

**特殊认证（不走路由 Depends）：**

- Integration 模块用 `verify_api_key`（`X-API-Key`），面向外部系统，与 Web 登录分离

**启动时安全检查（translate 已做，新模块建议对齐）：**

- 在 `lifespan` 中对模块 router 调用 `assert_all_routes_protected`，确保无漏网路由

### 2.4 数据库与配置

| 规则 | 说明 |
|------|------|
| 共用 engine | 通过 `app.platform.database.get_db` 获取 Session |
| 模型注册 | 新表在 `platform/registry.py` 的 `AppModule.models` 中登记；factory lifespan 统一 `create_all` |
| 配置来源 | 环境变量 → `app.platform.config`；模块级 pipeline 参数放模块 `config.py` |
| 路径常量 | 磁盘路径在模块 `__init__.py` 单点定义，如 translate 的 `UPLOAD_DIR` |

### 2.5 后台任务（若有）

长运行任务应：

1. 在模块内聚（如 `translate/bootstrap.py`），通过 `AppModule.startup_async` 挂到 registry
2. 通过 `start_background_tasks()` / `stop_background_tasks()` 由 lifespan 统一启停
3. 状态持久化到 DB，支持重启恢复
4. 日志用 `logging.getLogger("app.<模块名>")`，不在 import 时 `basicConfig`

### 2.6 LLM 调用

需要调大模型时，**必须**走公共层：

```python
from app.ai_service.client import chat
```

不要在业务模块内再封装一套 HTTP 客户端或读独立 yaml 配置。

---

## 3. 前端：单 APP 对各部分的要求

### 3.1 目录与职责

每个业务模块是 `frontend/src/<模块名>/` 下的目录：

```
frontend/src/
├── shared/              # 公共（所有模块依赖）
├── auth/                # 登录（全 APP 共用）
├── skill_hub/           # 业务模块示例
│   └── pages/
├── translate/           # 业务模块示例
│   ├── pages/
│   └── components/
├── changelog/
├── router.tsx           # 全 APP 路由表
└── App.tsx              # ConfigProvider + RouterProvider
```

| 部分 | 要求 |
|------|------|
| **pages/** | 路由级页面，负责数据获取与布局 |
| **components/** | 模块内可复用 UI，不跨模块引用其他业务的 components |
| **API** | 调用封装在 `shared/api/` 或模块专属 api 文件，页面不直接拼 URL |

### 3.2 路由约定

| 规则 | 说明 | 示例 |
|------|------|------|
| **登录外均受保护** | 业务路由挂在 `ProtectedRoute` + `AppLayout` 下 | `router.tsx` |
| **路径语义化** | 用模块名做一级路径 | `/translate`、`/skills` |
| **嵌套路由** | 详情页作为子路径 | `/translate/jobs/:jobId` |
| **Admin 路由** | 需 Admin 的页面应加 role 守卫（当前 admin 待加强） | `/admin` |

### 3.3 导航与门户

新模块接入时需要改两处「入口」：

1. **`AppLayout.tsx`** — 顶栏增加 NavButton
2. **`Portal.tsx`**（可选）— 首页增加入口卡片

### 3.4 API 调用约定

| 类型 | 客户端 | 适用 |
|------|--------|------|
| 常规 JSON REST | `shared/api/client.ts` 的 `apiClient`（Axios） | skill_hub、auth、changelog |
| 上传 / SSE / ticket | `shared/api/translate-client.ts` + 模块 api | translate |

**共同要求：**

- 请求自动带 `Authorization: Bearer`（Axios interceptor 或手动）
- 401 统一走 `triggerUnauthorized()` 跳转登录
- 类型定义放 `shared/types/models.ts` 或模块专属 types

### 3.5 UI 与状态

| 规则 | 说明 |
|------|------|
| UI 库 | Ant Design + 现有 CSS 变量（`shared/styles/tokens.ts`、`global.css`） |
| 服务端状态 | TanStack Query（`queryKey` 按模块+资源划分） |
| 客户端状态 | 仅 truly local 的用 useState；跨页面主题用 Zustand |
| 主题 | 使用 `var(--color-*)` 变量，不硬编码颜色 |
| 网站署名 | 首页底部加 `designed by @yuzechao`（用户规范） |

---

## 4. 公共模块清单

### 4.1 后端公共模块

| 模块 | 路径 | 职责 | 业务模块是否依赖 |
|------|------|------|------------------|
| **platform** | `app/platform/` | config、database、route_guard、`factory` 装配 | ✅ 必须 |
| **ai_service** | `app/ai_service/` | LLM 客户端 `chat`（无 HTTP） | ✅ 按需 |
| **auth** | `app/auth/` | 用户模型、JWT、ticket、角色 | ✅ 必须（Web 模块） |

**platform 子模块：**

| 文件 | 提供能力 |
|------|----------|
| `config.py` | `SECRET_KEY`、`DATABASE_URL`、`MINIMAX_*`、`CORS_ORIGINS`、`MAX_CONCURRENT_JOBS` |
| `database.py` | `engine`、`SessionLocal`、`get_db`、`Base` |
| `route_guard.py` | 启动时路由鉴权静态检查 |
| `registry.py` | `APPS` 注册表；新增 App 主要改此文件 |
| `app_module.py` | `AppModule` dataclass |
| `factory.py` | `create_app()`、循环 APPS、lifespan、SPA、`/api/health` |

**ai_service 子模块：**

| 文件 | 提供能力 |
|------|----------|
| `client.py` | `chat()`，带重试 |

**auth 子模块：**

| 文件/符号 | 提供能力 |
|-----------|----------|
| `get_current_user` | 标准 Bearer JWT 鉴权 |
| `get_current_user_by_ticket` | Header + ticket/token query |
| `RequireRole` | Admin 等角色守卫 |
| `create_ticket` | SSE/下载短期凭证 |

### 4.2 前端公共模块

| 模块 | 路径 | 职责 |
|------|------|------|
| **shared/api** | `shared/api/client.ts` | Axios 实例、auth/users/skills API、401 处理 |
| **shared/api** | `shared/api/changelog.ts` | Changelog API |
| **shared/api** | `shared/api/translate-client.ts` | fetch 封装、ticket 获取 |
| **shared/components** | `AppLayout.tsx` | 顶栏、Outlet、改密、主题切换 |
| **shared/pages** | `Portal.tsx` | 门户首页 |
| **shared/hooks** | `useTheme.ts` | 深色/浅色主题 |
| **shared/styles** | `global.css`、`tokens.ts` | 全局样式与 Ant Design token |
| **shared/types** | `models.ts` | 跨模块 TypeScript 类型 |
| **auth** | `Login.tsx` | 登录页（全 APP 共用，非 shared 但属公共） |

### 4.3 业务模块（非公共，可参照接入）

| 模块 | 后端包 | 前端目录 | API 前缀 | 特点 |
|------|--------|----------|----------|------|
| skill_hub | `app/skill_hub/` | `src/skill_hub/` | `/api/skills` | 资产域 |
| ai_service | `app/ai_service/` | — | 无 HTTP | LLM 基础服务 |
| external_api | `app/external_api/` | — | `/api/v1/external` | 工具链 / CI（X-API-Key） |
| translate | `app/translate/` | `src/translate/` | `/api/translate` | 文件上传、SSE、后台 worker |
| changelog | `app/platform/changelog/` | `src/changelog/` | `/api/changelog` | platform 子模块，Admin 写 |

---

## 5. 如何接入一个新业务模块

完整 step-by-step 操作手册见独立文档：

→ **[how_to_add_new_app.md](./how_to_add_new_app.md)**

本节仅保留要点摘要。

### 5.3 模块间依赖规则

App 之间**不走 HTTP**，通过 **Python import** 协作；允许 import 的符号以 **[dev/module_internal_api.md](./dev/module_internal_api.md)** 为准。

```
✅ 允许：
  业务模块 → platform（config / database）
  业务模块 → ai_service（LLM）
  业务模块 → auth.service（鉴权 Depends）
  业务模块 → 其它 App 的 service.py 中「对外暴露」函数（如 external_api → skill_hub.service）
  同模块内：router → service → models

❌ 禁止：
  业务模块 A → 业务模块 B 的 router / phases / jobs 等实现细节
  业务模块 → 自己搞一套 auth / db engine / llm client
  未写入暴露清单的跨 App import
  前端模块 A → 直接 import 模块 B 的 pages/components
```

若模块间需要协作：

- 后端：在被调用方 **`service.py` 增加函数**并更新 `module_internal_api.md`；共用逻辑优先**下沉 platform 或 ai_service**
- 前端：共用 UI/API 放到 **`shared/`**

### 5.4 特殊能力接入参考

| 能力 | 参照模块 | 要点 |
|------|----------|------|
| 文件上传 | translate | `UploadFile`、大小限制、磁盘路径常量 |
| SSE 实时推送 | translate | `get_current_user_by_ticket` + ticket + `StreamingResponse` |
| 后台长任务 | translate | worker + jobs 状态机 + DB 持久化 |
| 外部 API | `external_api/` | 独立 API Key 认证，不走 JWT |
| Admin 专属功能 | changelog、auth | `RequireRole` 或 `_require_admin` |

---

## 6. 开发/生产两种运行方式

| 模式 | 前端 | 后端 | 访问 |
|------|------|------|------|
| 开发 | `npm run dev` :3003 | `python run.py` :48010 | localhost:3003（proxy `/api`） |
| 生产 | `npm run build` → dist | `python run.py` 托管 dist | localhost:48010 |

新模块**无需**改 vite proxy（已代理全部 `/api`），也**无需**单独配置端口。

---

## 7. 自洽性检查（新模块上线前）

- [ ] API 前缀为 `/api/<模块名>/*`，已在 `platform/registry.py` 追加 `AppModule`
- [ ] 所有路由已鉴权（或明确标注公开并写入文档）
- [ ] 未复制 platform/auth 逻辑
- [ ] 前端路由在 `ProtectedRoute` 下，API 走 shared 客户端
- [ ] 顶栏/门户已添加入口（若面向用户）
- [ ] 至少补充 unauthorized 测试
- [ ] 文档已更新：`design.md` 路由表、`requirements.md` 功能项

---

## 8. 相关文档

- [设计文档](./design.md) — 现有模块细节与数据模型
- [需求文档](./requirements.md) — 功能范围
- [用户手册](./user_manual.md) — 使用者操作说明
- [如何接入新模块](./how_to_add_new_app.md) — step-by-step 操作手册

---

*designed by @yuzechao*
