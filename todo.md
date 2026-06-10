# Translate 模块统一改造方案

## 目标

将 translate 从独立子应用改造为与 skill_hub / auth / changelog 一致的模块，
消除架构割裂、统一认证/配置/LLM/API 风格。

## 原则

- 数据零丢失：数据库表结构不变，磁盘文件不动
- 渐进式改造：每步可独立验证，不搞大爆炸
- 前后端同步：API 路径变更后前端必须同步修改
- 终态干净优先：不做向后兼容妥协，一刀切切换 + 内部测试验证

---

## P0：前置任务（进入 Phase 1 之前）

### P0-1 统一认证入口函数

在 `app/auth/service.py` 新增 `get_user_for_request()`：
- Header 优先，query 兜底（专为 SSE / 下载设计）
- 同一个函数的两条路径，不是妥协
- 全模块统一使用，消除"中间件 / Depends / 手动解析"三种风格
- 同时认 `?ticket=` 和 `?token=`（ticket 优先），ticket 查 TICKETS 字典，token 查 JWT

```python
def get_user_for_request(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    auth_header = request.headers.get("authorization", "")
    token: str | None = None
    parts = auth_header.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1].strip()

    if not token:
        token = (
            request.query_params.get("ticket")
            or request.query_params.get("token")
        )

    if not token:
        raise HTTPException(401, "未认证")

    # ticket 路径查 TICKETS 字典，token 路径查 JWT
    user = _resolve_user_via_token_or_ticket(token, db)
    if not user:
        raise HTTPException(401, "无效凭证")
    return user
```

### P0-2 模块依赖图（DAG 验证）

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

### P0-3 路径常量统一定义

在 `translate/__init__.py` 定义，所有模块引用同一来源：

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
UPLOAD_DIR = BASE_DIR / "app" / "uploads"
RESULT_DIR = BASE_DIR / "app" / "results"
```

### P0-4 删除 `logging.basicConfig`

`translate/app.py` 的 `logging.basicConfig(...)` 在 import 时改全局配置，
改为 `log = logging.getLogger("app.translate")`，日志格式由 `main_merged.py` 统一控制。

### P0-5 建 `tests/` 目录 + e2e 冒烟

```python
# tests/test_translate_e2e.py
# 1. 登录拿 token
# 2. 上传 fixture zip
# 3. 轮询 /api/translate/jobs/{id} 直到 completed
# 4. 下载结果 zip
# 5. 断言 zip 包含 case 文件
```

```python
# tests/test_unauthorized.py
# 无 token 访问 /api/translate/jobs → 401
# 带过期 token → 401
# 带 query token 访问 SSE → 200
```

### P0-6 核实 skill_hub LLM 调用方式

Phase 4.1 改 `core/llm.py` temperature 默认值前，先确认 skill_hub 是否走默认：

```bash
grep -rn "from app.core.llm" backend/app/skill_hub/
grep -rn "chat(" backend/app/skill_hub/ | grep -v "temperature="
```

- 如果 skill_hub 全部显式传 temperature → 安全可改默认值
- 如果有走默认的 → 不动默认值，translate 调用方显式传 0.2

### P0-7 `core/config.py` 新增环境变量

```python
MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7-highspeed")
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "1"))
```

`core/llm.py` 的 `DEFAULT_MODEL` 改为从 config 读取：
```python
from app.core.config import MINIMAX_MODEL
DEFAULT_MODEL = MINIMAX_MODEL
```

---

## Phase 1：拆分 app.py（纯内部重构，API 不变）

当前 `app.py` 493 行，路由/worker/SSE/中间件/SPA 全塞一起。
拆为独立文件，降低单文件复杂度。

### 1.1 新建 `translate/router.py`

从 `app.py` 提取所有 `@app.get/post/delete` 路由函数：
- `upload`
- `list_jobs`
- `get_job`
- `cancel_job`
- `stream`
- `download`
- `get_result_file`

改为 `router = APIRouter(prefix="/api")`，路由函数不变。

### 1.2 新建 `translate/worker.py`

从 `app.py` 提取：
- `_dispatcher_loop()`
- `_janitor_loop()`
- `_execute_job()`
- `_run_pipeline()`
- `start_background_tasks()` — 统一入口，内部调用 `jobs.recover_on_startup()`
- `stop_background_tasks()` — 取消后台任务

`main_merged.py` 只需调用 `start_background_tasks()` / `stop_background_tasks()`，
不需要知道 recover / dispatcher 的存在。

### 1.3 新建 `translate/sse.py`

从 `app.py` 提取：
- `_event_gen()`
- SSE 事件类型用 TypedDict 定义（不用 Pydantic schema，流式响应无法做编译期验证）

```python
from typing import Literal, TypedDict

class ProgressEvent(TypedDict):
    type: Literal["progress"]
    phase: str
    step: int
    total_steps: int
    message: str

class QueuedEvent(TypedDict):
    type: Literal["queued"]
    ahead: int
    total: int

class DoneEvent(TypedDict):
    type: Literal["done"]
    status: str
    error: str | None
```

### 1.4 `_recover_jobs_from_db` 移入 `jobs.py`

- 改名 `recover_on_startup()`，归属最贴近数据的模块
- `worker.py` 的 `start_background_tasks()` 内部调用

### 1.5 精简 `app.py`

只保留：
- FastAPI 实例创建
- `TranslateAuthMiddleware`（Phase 3 删除）
- `translate_lifespan` — 改为 `worker.start_background_tasks()` 的薄壳（Phase 6 删除）
- SPA fallback 路由（Phase 6 删除）
- `include_router`

`translate_lifespan` 改为：
```python
@asynccontextmanager
async def translate_lifespan(app_instance: FastAPI):
    from .worker import start_background_tasks, stop_background_tasks
    await start_background_tasks()
    yield
    await stop_background_tasks()
```

### 验证

- `python -c "from app.translate.router import router"` 启动无错
- 所有 `/translate/api/*` 接口行为不变
- e2e 冒烟通过

---

## Phase 2：去掉 mount，路由直接注册到主 app

当前：`app.mount("/translate", translate_app)` → 子应用模式
目标：translate 路由像 skill_hub 一样直接 `include_router`

**一刀切，不保留旧路径。**

### 2.1 修改 `translate/router.py`

路由前缀改为 `/api/translate`：
```
router = APIRouter(prefix="/api/translate", tags=["translate"])
```

对应 API 路径变化：
| 旧路径 | 新路径 |
|--------|--------|
| /translate/api/upload | /api/translate/upload |
| /translate/api/jobs | /api/translate/jobs |
| /translate/api/jobs/{id} | /api/translate/jobs/{id} |
| /translate/api/jobs/{id}/stream | /api/translate/jobs/{id}/stream |
| /translate/api/jobs/{id}/download | /api/translate/jobs/{id}/download |
| /translate/api/jobs/{id}/file | /api/translate/jobs/{id}/file |

### 2.2 修改 `main_merged.py`

- 删除 `app.mount("/translate", translate_app)`
- 改为 `app.include_router(translate_router)`

### 2.3 前端修改

**translate-client.ts**：`apiFetch` 路径前缀从 `/translate/api/` 改为 `/api/translate/`

**translate-jobs.ts**：
- `uploadJob` 中 `/translate/api/upload` → `/api/translate/upload`
- `listJobs` 中 `/translate/api/jobs` → `/api/translate/jobs`
- `getJob` / `cancelJob` / `getDownloadUrl` / `getFileUrl` 同理

**translate-sse.ts**：
- `subscribeJob` 中 `/translate/api/jobs/...` → `/api/translate/jobs/...`

**vite.config.ts**：
- proxy 规则从 `/translate/api` → `/api/translate`

### 验证

- `/api/translate/*` 路径都能通
- `/translate/api/*` 全部 404（说明切干净了）
- e2e 冒烟通过

---

## Phase 3：统一认证

当前：translate 用自定义 `TranslateAuthMiddleware` 手动解析 JWT
目标：全模块走 `get_user_for_request()`，一个入口三种凭证（header / ticket / token）

### 3.1 路由添加认证依赖

`translate/router.py` 中所有路由添加：
```python
from app.auth.service import get_user_for_request
from app.auth.models import User

@router.post("/upload")
async def upload(..., user: User = Depends(get_user_for_request)):
```

SSE 和下载路由同样使用 `get_user_for_request`，query 中的 ticket / token 由该函数统一处理，
不再需要路由内手动解析。

### 3.2 删除 `TranslateAuthMiddleware`

从 `app.py` 中移除整个中间件类。

### 3.3 启动时路由认证闭合检查

在 `main_merged.py` 启动时扫描所有 translate 路由，
确保每个路由都包含 `get_user_for_request` 依赖（`/health` 除外），
防止遗漏导致路由完全公开。

**必须递归收集依赖**（FastAPI 的 `dependant.dependencies` 是扁平的，嵌套依赖需递归）：

```python
def assert_all_routes_protected(router):
    def collect_dep_names(dependant) -> set[str]:
        names = set()
        for d in dependant.dependencies:
            names.add(d.call.__name__)
            names.update(collect_dep_names(d))
        return names

    for route in router.routes:
        if route.path in ("/health", "/api/health"):
            continue
        all_deps = collect_dep_names(route.dependant)
        if "get_user_for_request" not in all_deps:
            raise RuntimeError(
                f"[安全] 路由 {route.path} 缺少 get_user_for_request 依赖，"
                f"实际依赖: {all_deps}"
            )
```

### 3.4 ticket 机制替换 JWT-in-URL

当前 JWT 60 分钟有效期暴露在 URL 中（浏览器历史、access log 可见）。
新增短期一次性 ticket 端点替换，**不是可选，是必做**：

```python
from cachetools import TTLCache

TICKETS: TTLCache = TTLCache(maxsize=10000, ttl=30)

@router.post("/ticket")
async def create_ticket(user: User = Depends(get_user_for_request)) -> dict:
    ticket = secrets.token_urlsafe(32)
    TICKETS[ticket] = user.id
    return {"ticket": ticket, "expires_in": 30}
```

前端：SSE / 下载前先 POST 拿 ticket，用 `?ticket=` 替代 `?token=`。
ticket 30s 失效且不能调其他 API。
`TTLCache` 自动清理过期项，无内存泄漏。

### 3.5 前端修改

- `uploadJob` 已通过 header 传 token，无需改动
- SSE 和下载 URL：改用 `?ticket=`，先 POST `/api/translate/ticket` 拿 ticket

### 验证

- 无 token 访问受保护路由 → 401
- 带过期 token → 401
- 带 query ticket 访问 SSE / 下载 → 正常
- ticket 30s 后失效 → 401
- `test_unauthorized.py` 全部通过

---

## Phase 4：统一 LLM 调用

当前：translate 有 `client.py`（LLMClient 类）+ `llm.py`（工厂）+ `config.py`（ai.yaml 查找）
目标：直接用 `core/llm.py`，去掉 translate 的 LLM 封装层

### 4.1 统一 temperature 默认值

根据 P0-6 核实结果决定：
- 如果 skill_hub 全部显式传 temperature → `core/llm.py` 默认改 0.2（对齐 translate）
- 如果 skill_hub 有走默认的 → 不动默认值，translate 调用方显式传 `temperature=0.2`

vision 用 `MiniMax-M3`、chat 用 `MiniMax-M2.7-highspeed` 是故意不同的，加注释说明。

### 4.2 删除 `translate/client.py`

`LLMClient` 类的功能与 `core/llm.py` 完全重复，整个删除。

### 4.3 删除 `translate/llm.py`

re-export 层没必要存在，调用方直接 `from app.core.llm import chat, vision, ping, create_openai_client`。

### 4.4 修改调用方

`worker.py` 中 `build_client()` + `client.call_chat()` 改为直接 `chat()`，
显式传 `temperature` 和 `model` 参数。
`model` 从 `core/config.py` 的 `MINIMAX_MODEL` 读取。

### 4.5 删除配置源分裂

- 删除 `backend/app/translate/config/ai.yaml`
- 删除 `backend/app/translate/config/ai.local.json`
- 删除 `translate/config.py` 中的 `load_ai_config()` 和 `from_config()`
- `translate/config.py` 只保留 pipeline 参数（PHASE1_BATCH_SIZE 等）
- LLM 配置统一走 `core/config.py` 读环境变量

### 验证

- 用同一批 fixture 输入，对比改造前后输出，token 数差异 < 5%
- 逐个 phase 替换验证，不是一次性全换
- skill_hub LLM 行为不变（grep 验证调用方都显式传 temperature）

---

## Phase 5：统一 API 响应格式

当前：translate 路由手动拼 dict 返回
目标：用 Pydantic schema 定义响应模型（SSE 除外）

### 5.1 新建 `translate/schemas.py`

```python
from typing import Literal

class JobView(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    created_at: str
    updated_at: str
    current_phase: str
    current_step: int
    total_steps: int
    message: str
    queue_ahead: int
    queue_total: int
    error: str | None

class UploadResponse(BaseModel):
    job_id: str
    status: str
    queue_ahead: int
    queue_total: int
    total_steps: int
    current_step: int
```

### 5.2 `job_to_view` 改为返回 `JobView`

```python
def job_to_view(job: Job) -> JobView:
    ahead, qtotal = (
        get_queue_position(job.id) if job.status == JobStatus.QUEUED else (0, 0)
    )
    return JobView(
        job_id=job.id,
        status=job.status.value,
        ...
    )
```

### 5.3 路由使用 schema

```python
@router.get("/jobs", response_model=list[JobView])
async def list_jobs(...):
```

### 5.4 SSE 路由不使用 Pydantic response_model

SSE 是流式响应，无法做编译期验证。
事件类型用 TypedDict 在 `sse.py` 中定义（Phase 1.3 已完成）。

### 验证

- SSE 事件流未变
- 普通响应符合 schema
- e2e 冒烟通过

---

## Phase 6：清理遗留

### 6.1 删除 translate 的 SPA fallback

`app.py` 中的 `spa_root` 和 `spa` 路由已由主 app 处理，translate 不需要。

### 6.2 删除 translate 的 `__main__.py`

独立运行模式不再需要，统一通过 `main_merged.py` 启动。
不创建 `create_app()` 工厂，启动入口唯一。

### 6.3 删除 `translate_lifespan` 全部代码

启动逻辑已收敛到 `worker.start_background_tasks()`，
`translate_lifespan` 和双重启动保护变量全部删除。

### 6.4 删除 `translate/app.py`

所有路由通过 `translate/router.py` 注册，`app.py` 不再需要。
删除前 grep 确认无外部引用：
```bash
grep -rn "from app.translate.app" backend/
grep -rn "import app.translate.app" backend/
```
命中行全部改 `from app.translate.worker` / `from app.translate.jobs`。

### 6.5 部署约束声明

单 worker 部署（`workers=1`），`MAX_CONCURRENT_JOBS` 从 `core/config.py` 读取。
多 worker 部署时内存队列不共享，需声明此约束。
`main_merged.py` lifespan 启动时加 sanity check。

### 验证

- `python -m app.translate` 启动失败（已废弃）
- `main_merged.py` 启动正常
- e2e 冒烟通过

---

## 改造顺序 & 依赖关系

```
P0（前置）        ← 无依赖，先做
    ↓
Phase 1（拆文件）  ← 依赖 P0-2（DAG）、P0-3（路径）、P0-4（logging）
    ↓
Phase 2（去 mount） ← 依赖 Phase 1 的 router.py
    ↓
Phase 3（统一认证） ← 依赖 P0-1（统一认证函数）、Phase 2
    ↓
Phase 4（统一 LLM） ← 依赖 P0-6（skill_hub 核实）、P0-7（MINIMAX_MODEL env）
    ↓
Phase 5（统一响应） ← 无依赖，可随时做
    ↓
Phase 6（清理）     ← 依赖 Phase 3
```

Phase 1→2→3 有依赖关系，Phase 4/5 可穿插进行。

---

## 自洽性自检清单

Phase 6 全部完成时，以下条件应全部满足：

- [ ] 没有 `TranslateAuthMiddleware`，全模块认证走 `get_user_for_request`
- [ ] 没有 `/translate/api/*` 路径，全模块走 `/api/translate/*`
- [ ] 没有 `?token=` 参数，SSE/下载全用 `?ticket=`
- [ ] 没有 `ai.yaml` / `ai.local.json`，LLM 配置全 env
- [ ] 没有 `translate/client.py` / `translate/llm.py`，LLM 调用全 `core/llm`
- [ ] 没有 `__main__.py` / `translate/app.py`，启动入口唯一 `main_merged.py`
- [ ] 没有 `translate_lifespan`，启动逻辑全部在 `worker.start_background_tasks()`
- [ ] 没有 `logging.basicConfig` 在子模块中，日志格式由入口统一控制
- [ ] SSE 事件用 TypedDict，普通响应用 Pydantic schema
- [ ] `BASE_DIR` / `UPLOAD_DIR` / `RESULT_DIR` 在 `translate/__init__.py` 单点定义
- [ ] `TICKETS` 用 `TTLCache`，无内存泄漏
- [ ] `MAX_CONCURRENT_JOBS` 从 env 读，部署 README 写明 `workers=1`
- [ ] `MINIMAX_MODEL` 从 env 读，没有硬编码 model 名
- [ ] `tests/` 目录存在，e2e 冒烟通过，认证回归 401 用例通过
- [ ] skill_hub LLM 行为不变（grep 验证调用方都显式传 temperature）
