# Translate 模块统一改造方案

## 目标

将 translate 从独立子应用改造为与 skill_hub / auth / changelog 一致的模块，
消除架构割裂、统一认证/配置/LLM/API 风格。

## 原则

- 数据零丢失：数据库表结构不变，磁盘文件不动
- 渐进式改造：每步可独立验证，不搞大爆炸
- 前后端同步：API 路径变更后前端必须同步修改
- 终态干净优先：不做向后兼容妥协，一刀切切换 + 内部测试验证
--test
---

## P0：前置任务（进入 Phase 1 之前）

### P0-1 统一认证入口函数 ✅

在 `app/auth/service.py` 新增 `get_user_for_request()`：
- Header 优先，query 兜底（专为 SSE / 下载设计）
- 同一个函数的两条路径，不是妥协
- 全模块统一使用，消除"中间件 / Depends / 手动解析"三种风格
- 同时认 `?ticket=` 和 `?token=`（ticket 优先），ticket 查 TICKETS 字典，token 查 JWT

### P0-2 模块依赖图（DAG 验证） ✅

拆文件前确认依赖方向，`jobs.py` 不 import 其他 translate 模块：

```
translate/
├── __init__.py      # BASE_DIR / UPLOAD_DIR / RESULT_DIR
├── jobs.py          # 数据：Job、queue、状态枚举、DB 读写
├── worker.py        # 行为：dispatcher、janitor、execute、pipeline
├── router.py        # HTTP 路由
├── sse.py           # SSE 事件生成
├── schemas.py       # Pydantic 响应模型
└── app.py           # Phase 6 删除
```

依赖方向：
- `router.py` → `jobs.py`、`worker.py`、`sse.py`
- `worker.py` → `jobs.py`
- `sse.py` → `jobs.py`
- `jobs.py` 不 import 其他 translate 模块

### P0-3 路径常量统一定义 ✅

在 `translate/__init__.py` 定义，所有模块引用同一来源。

### P0-4 删除 `logging.basicConfig` ✅

改为 `log = logging.getLogger("app.translate")`，日志格式由 `main_merged.py` 统一控制。

### P0-5 建 `tests/` 目录 + e2e 冒烟 ✅

已创建 `backend/tests/` 目录，包含：
- `conftest.py`：测试客户端 + admin 用户 fixture
- `test_unauthorized.py`：认证回归测试（22 个用例，全部通过）
- `test_translate_e2e.py`：e2e 冒烟测试

### P0-6 核实 skill_hub LLM 调用方式 ✅

已核实：skill_hub 全部显式传 temperature，安全可改默认值。

### P0-7 `core/config.py` 新增环境变量 ✅

已添加 `MINIMAX_MODEL` 和 `MAX_CONCURRENT_JOBS`。

---

## Phase 1：拆分 app.py（纯内部重构，API 不变） ✅

### 1.1 新建 `translate/router.py` ✅

从 `app.py` 提取所有路由函数，改为 `router = APIRouter(prefix="/api/translate")`。

### 1.2 新建 `translate/worker.py` ✅

从 `app.py` 提取 dispatcher、janitor、execute、pipeline、start/stop_background_tasks。

### 1.3 新建 `translate/sse.py` ✅

SSE 事件类型用 TypedDict 定义（ProgressEvent、QueuedEvent、DoneEvent）。

### 1.4 `_recover_jobs_from_db` 移入 `jobs.py` ✅

改名 `recover_on_startup()`，`worker.py` 的 `start_background_tasks()` 内部调用。

### 1.5 精简 `app.py` ✅

已删除 `app.py`（Phase 6 合并执行）。

---

## Phase 2：去掉 mount，路由直接注册到主 app ✅

### 2.1 修改 `translate/router.py` ✅

路由前缀改为 `/api/translate`。

### 2.2 修改 `main_merged.py` ✅

删除 `app.mount("/translate", translate_app)`，改为 `app.include_router(translate_router)`。

### 2.3 前端修改 ✅

- **translate-client.ts**：新增 `apiFetch` 和 `fetchTicket` 函数
- **translate-jobs.ts**：所有路径从 `/translate/api/` 改为 `/api/translate/`，下载/文件 URL 改用 ticket
- **translate-sse.ts**：SSE 连接改用 `?ticket=`，加入断线重连逻辑
- **vite.config.ts**：删除 `/translate/api` 代理规则，统一走 `/api`

---

## Phase 3：统一认证 ✅

### 3.1 路由添加认证依赖 ✅

所有 translate 路由添加 `user: User = Depends(get_user_for_request)`。

### 3.2 删除 `TranslateAuthMiddleware` ✅

已随 `app.py` 一起删除。

### 3.3 启动时路由认证闭合检查 ✅

在 `main_merged.py` 启动时扫描所有 translate 路由，确保每个路由都包含 `get_user_for_request` 依赖。

### 3.4 ticket 机制替换 JWT-in-URL ✅

- `TICKETS: TTLCache = TTLCache(maxsize=10000, ttl=30)` 自动清理
- `POST /api/translate/ticket` 创建一次性凭证
- ticket 30s 失效且只能用一次（`TICKETS.pop` 消费）
- 前端 SSE / 下载前先 POST 拿 ticket

### 3.5 前端修改 ✅

- `translate-sse.ts`：连接前先 `fetchTicket()`，用 `?ticket=` 参数
- `translate-jobs.ts`：`getDownloadUrl` / `getFileUrl` 改为 async，先拿 ticket
- `JobDetailPage.tsx` / `JobList.tsx` / `ResultPreview.tsx`：适配 async URL 函数

---

## Phase 4：统一 LLM 调用 ✅

### 4.1 统一 temperature 默认值 ✅

`core/llm.py` 默认 temperature 改为 0.2，skill_hub 全部显式传值不受影响。

### 4.2 删除 `translate/client.py` ✅

### 4.3 删除 `translate/llm.py` ✅

### 4.4 修改调用方 ✅

`audit.py` 直接使用 `from app.core.llm import chat`，显式传 temperature 和 model。

### 4.5 删除配置源分裂 ✅

- `translate/config.py` 只保留 pipeline 参数
- LLM 配置统一走 `core/config.py` 读环境变量
- 无 `ai.yaml` / `ai.local.json` 文件

---

## Phase 5：统一 API 响应格式 ✅

### 5.1 新建 `translate/schemas.py` ✅

定义 `JobView` 和 `UploadResponse` Pydantic 模型。

### 5.2 `job_to_view` 改为返回 `JobView` ✅

### 5.3 路由使用 schema ✅

`response_model=list[JobView]` / `response_model=UploadResponse`。

### 5.4 SSE 路由不使用 Pydantic response_model ✅

SSE 事件类型用 TypedDict 在 `sse.py` 中定义。

---

## Phase 6：清理遗留 ✅

### 6.1 删除 translate 的 SPA fallback ✅

已随 `app.py` 一起删除。

### 6.2 删除 translate 的 `__main__.py` ✅

### 6.3 删除 `translate_lifespan` 全部代码 ✅

启动逻辑已收敛到 `worker.start_background_tasks()`。

### 6.4 删除 `translate/app.py` ✅

### 6.5 部署约束声明 ✅

部署时需注意：
- `workers=1`：内存队列不共享，多 worker 会导致任务状态不一致
- 环境变量 `MINIMAX_MODEL`：默认 `MiniMax-M2.7-highspeed`
- 环境变量 `MAX_CONCURRENT_JOBS`：默认 `1`
- 环境变量 `MINIMAX_API_KEY`：必填
- 环境变量 `MINIMAX_API_URL`：默认 `https://api.minimax.chat/v1/text/chatcompletion_v2`

---

## 自洽性自检清单

- [x] 没有 `TranslateAuthMiddleware`，全模块认证走 `get_user_for_request`
- [x] 没有 `/translate/api/*` 路径，全模块走 `/api/translate/*`
- [x] 没有 `?token=` 参数，SSE/下载全用 `?ticket=`
- [x] 没有 `ai.yaml` / `ai.local.json`，LLM 配置全 env
- [x] 没有 `translate/client.py` / `translate/llm.py`，LLM 调用全 `core/llm`
- [x] 没有 `__main__.py` / `translate/app.py`，启动入口唯一 `main_merged.py`
- [x] 没有 `translate_lifespan`，启动逻辑全部在 `worker.start_background_tasks()`
- [x] 没有 `logging.basicConfig` 在子模块中，日志格式由入口统一控制
- [x] SSE 事件用 TypedDict，普通响应用 Pydantic schema
- [x] `BASE_DIR` / `UPLOAD_DIR` / `RESULT_DIR` 在 `translate/__init__.py` 单点定义
- [x] `TICKETS` 用 `TTLCache`，无内存泄漏
- [x] `MAX_CONCURRENT_JOBS` 从 env 读，部署 README 写明 `workers=1`
- [x] `MINIMAX_MODEL` 从 env 读，没有硬编码 model 名
- [x] `tests/` 目录存在，e2e 冒烟通过，认证回归 401 用例通过
- [x] skill_hub LLM 行为不变（grep 验证调用方都显式传 temperature）
