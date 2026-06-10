# todo.md 风险评审（自洽版）

> 评审对象：`todo.md`（Translate 模块统一改造方案 6 阶段）
> 评审时间：2026-06-10
> 评审立场：**没有外部用户，系统只需自洽**。不为向后兼容做任何妥协 —— 终态干净优先于过渡期平稳。
> 评审范围：6 个 Phase 的方案风险 + 实施风险

---

## 一、立场声明（重要）

本评审**不**讨论"如何保留旧路径 / 旧配置 / 旧 API 让老客户端继续工作"。

- ❌ 不做 `/translate/api/*` 双路由兼容
- ❌ 不为 `ai.local.json` 保留 deprecated fallback
- ❌ 不为 `python -m app.translate` 独立运行留后门
- ❌ 不为短期 ticket 之外保留 JWT-in-URL 兜底

任何"为了兼容"而加的代码层都是**对终态完整性的污染**，应该用一刀切切换 + 内部测试验证代替。

---

## 二、风险总览

| # | 风险 | 等级 | 影响 Phase | 类别 |
|---|------|------|-----------|------|
| 1 | SSE/下载认证与 `get_current_user` 依赖不兼容 | 🔴 Critical | 3 | 架构一致性 |
| 2 | 拆文件可能引发循环导入 | 🔴 Critical | 1 | 模块结构 |
| 3 | `BASE_DIR` 路径拆完重算可能错 | 🔴 Critical | 1 | 模块结构 |
| 4 | 删中间件后路由级认证不闭合 | 🔴 Critical | 3 | 架构一致性 |
| 5 | JWT 出现在 URL query 里（结构上脏） | 🟠 High | 3 | 架构一致性 |
| 6 | LLM `temperature` / `model` 默认值漂移 | 🟠 High | 4 | 行为一致性 |
| 7 | todo.md 全程未提测试 | 🟠 High | 全部 | 质量保证 |
| 8 | `ai.yaml` 与 `app.core.config` 配置来源分裂 | 🟠 High | 4 | 配置一致性 |
| 9 | `logging.basicConfig` 在 import 时改全局配置 | 🟡 Medium | 1 | 模块洁净 |
| 10 | `_recover_jobs_from_db` 归属不清 | 🟡 Medium | 1 | 模块结构 |
| 11 | SSE 事件不应套 Pydantic schema | 🟡 Medium | 5 | 架构一致性 |
| 12 | `_dispatcher_loop` 双重启动保护依赖模块全局变量 | 🟡 Medium | 1 | 生命周期 |
| 13 | `MAX_CONCURRENT_JOBS=1` + 多 worker 部署隐患 | 🟡 Medium | 部署 | 并发一致性 |

---

## 三、Critical 级风险详解

### 风险 1：SSE/下载认证与 `get_current_user` 依赖不兼容

**事实**：
- `app/auth/service.py:40-50` 的 `get_current_user` 用 `HTTPBearer()` 依赖，**只接受 `Authorization: Bearer` header**
- 浏览器 `EventSource` API 物理上**无法**设置自定义 header
- `translate-sse.ts:24` 当前是 `?token=` 形式，下载同理（`<a href>` 不能带 header）

**问题**：
- todo.md Phase 3 说"SSE 和下载的路由保留手动解析 token 的逻辑，但不再用中间件"
- 没说"如何保持全模块认证风格一致"
- 路由内 token 解析逻辑会变成 N 处复制粘贴

**自洽要求**：
- 全模块认证走**同一个**依赖函数
- 不要再有"中间件 / 路由 Depends / 路由手动解析"三种风格混用

**建议终态**：
```python
# app/auth/service.py 新增唯一入口
def get_user_for_request(
    request: Request,
    token: str | None = None,
    db: Session = Depends(get_db),
) -> User:
    """全模块统一认证入口。Header 优先，query 兜底。
    
    不再有 TranslateAuthMiddleware，不再有每路由重复解析。
    """
    # 1. header 优先
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    # 2. query 兜底（专为 SSE / 下载设计）
    if not token:
        token = request.query_params.get("token")
    if not token:
        raise HTTPException(401, "未认证")
    # 3. 解码 + 查用户
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(401, "无效的认证令牌")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(401, "无效的认证令牌")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(401, "用户不存在")
    return user
```

**重要**：query 兜底不是为了"兼容浏览器限制"——而是因为**SSE 这种协议层无法带 header**的客观事实，需要**架构层面承认**这一点。query 兜底和 header 认证是**同一个函数的两条路径**，不是"妥协"。

---

### 风险 2：拆文件可能引发循环导入

**事实**：
- `translate/jobs.py:3` 注释明确写：
  > dispatcher 和 janitor 协程在 app.py 中实现（避免循环导入）
- `translate/app.py:74-87` 的 `translate_lifespan` 内部直接定义 `_dispatcher_loop`、`_janitor_loop`
- `app.py:150-181` 的 `_dispatcher_loop` / `_janitor_loop` / `_execute_job` / `_run_pipeline` 都在同一文件

**问题**：
- 拆到 `worker.py` 后，`worker.py` 要 `import jobs`
- `jobs.py:163` 的 `cancel()` 操作 `job.task`，Task 在 `worker.py` 中创建
- 如果未来加 feature 让 `jobs.py` 回调 worker → 立刻循环导入

**自洽要求**：
- 模块依赖是**单向 DAG**，不允许环
- 数据层（jobs）不知道 worker 的存在

**建议**：拆前画依赖图（写到 Phase 1 任务里）：

```
translate/
├── jobs.py          # 数据：Job、queue、状态枚举、DB 读写
├── worker.py        # 行为：dispatcher、janitor、execute、pipeline
├── router.py        # HTTP 路由
├── sse.py           # SSE 事件生成
└── app.py           # FastAPI 工厂（可选，Phase 6 决定）
```

依赖方向：  
- `router.py` → `jobs.py`、`worker.py`、`sse.py`  
- `worker.py` → `jobs.py`  
- `sse.py` → `jobs.py`  
- `jobs.py` 不 import 其他 translate 模块

---

### 风险 3：`BASE_DIR` 路径拆完重算可能错

**事实**：
- `translate/app.py:42-45`：
  ```python
  BASE_DIR = Path(__file__).resolve().parent.parent  # = backend/app
  UPLOAD_DIR = BASE_DIR / "uploads"
  RESULT_DIR = BASE_DIR / "results"
  ```

**问题**：
- 拆到子目录后，`.parent.parent` 表达式失效
- 未来再加子目录（如 `translate/worker/dispatcher.py`）路径立刻错

**自洽要求**：
- 路径定义在**模块树的根**（`translate/__init__.py`），所有模块引用同一个 `BASE_DIR`
- 不会出现"我以为我指向 backend/app，结果是 translate/"这种错位

**建议**：
```python
# app/translate/__init__.py
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
UPLOAD_DIR = BASE_DIR / "app" / "uploads"
RESULT_DIR = BASE_DIR / "app" / "results"
```

```python
# app/translate/worker.py
from app.translate import UPLOAD_DIR, RESULT_DIR
```

---

### 风险 4：删中间件后路由级认证不闭合

**事实**：
- 当前 `TranslateAuthMiddleware`（`translate/app.py:98-141`）是**黑名单式**——只放行 `/api/health` 和非 `/api/` 路径
- **所有 `/api/*` 都强制认证**

**问题**：
- Phase 3 改成 `Depends(get_current_user)` 后：
  - 路由 A 加了依赖 → 受保护
  - 路由 B 漏了依赖 → **完全公开**
  - 默认行为从"全保护"反转成"全不保护"

**自洽要求**：
- 安全是**默认安全**，不是"记得加"

**建议**：用代码扫描保证全闭合：

```python
# main_merged.py 启动时
from app.auth.service import get_user_for_request

def assert_all_routes_protected(router):
    for route in router.routes:
        if route.path in ("/health", "/api/health"):
            continue
        # 检查依赖图里有 get_user_for_request
        deps = [d.call.__name__ for d in route.dependant.dependencies]
        if "get_user_for_request" not in deps:
            raise RuntimeError(
                f"[安全] 路由 {route.path} 缺少 get_user_for_request 依赖"
            )

assert_all_routes_protected(translate_router)
```

这是**模块洁净的一部分**——开发期错误，不是上线后被渗透。

---

## 四、High 级风险详解

### 风险 5：JWT 出现在 URL query 里（结构上脏）

**事实**：
- `translate-sse.ts:24` SSE URL：`/translate/api/jobs/{id}/stream?token=xxx`
- `translate-jobs.ts:75` 下载 URL：`?token=xxx`
- `translate-jobs.ts:82` 预览 URL：`?token=xxx`
- JWT 60 分钟有效期

**为什么是结构问题而不是兼容问题**：
- 浏览器历史、access log、CDN 日志都记录 URL
- 一个能读 access log 的人 60 分钟内能伪造身份
- **不是"为了兼容 EventSource 限制才这样"**——而是因为**SSE 协议本身决定了 query 是唯一通道**

**自洽要求**：
- token 应该是**短期的、一次性的**
- 不要把"主凭证"（JWT）暴露在 query 里

**建议终态**：
```python
# 新增 ticket 端点（不是兼容，是替换）
@router.post("/ticket")
async def create_ticket(user: User = Depends(get_user_for_request)) -> dict:
    """颁发 30s 有效的一次性 ticket，专门给 SSE/下载用。"""
    ticket = secrets.token_urlsafe(32)
    TICKETS[ticket] = user.id  # 内存即可，不需要持久化
    return {"ticket": ticket, "expires_in": 30}
```

前端：
```typescript
// 每次打开 SSE/下载前先拿 ticket
const { ticket } = await apiFetch<{ticket: string}>('/api/translate/ticket', {method: 'POST'})
const url = `/api/translate/jobs/${id}/stream?ticket=${ticket}`
```

ticket 泄漏 30s 后自动失效，**且 ticket 不能用来调其他 API**（因为 ticket 不带 user context）。

---

### 风险 6：LLM `temperature` / `model` 默认值漂移

**事实**（关键代码差异）：

| 文件 | 默认 temperature | 默认 model |
|------|------------------|-----------|
| `translate/client.py:46` `call_chat` | 0.2 | `translate/config.py:DEFAULT_MODEL` |
| `core/llm.py:42` `chat` | **0.3** | `core/llm.py:15` `"MiniMax-M2.7-highspeed"` |
| `core/llm.py:82` `vision` | — | `"MiniMax-M3"`（**与 chat 不一致**） |

**问题**：
- 直接 `from app.core.llm import chat` 替换 → translate 行为从 temp=0.2 变 0.3
- 0.1 的 temperature 差异在 LLM 输出上**可见**

**自洽要求**：
- 同一类调用（chat）应该有**同一个默认值**
- 调用方必须**显式**传 temperature，不允许走"看似合理"的默认

**建议**：
- `core/llm.py:42` 改成 `temperature: float = 0.2`（对齐 translate 现状）
- 强制所有调用方显式传 `model` 参数（不留默认）
- Phase 4 改造时**逐个 phase** 替换，跑同一批 fixture 对比输出
  - 不是"为了兼容"——是为了**验证行为没漂移**
- vision 用 `MiniMax-M3`、chat 用 `MiniMax-M2.7-highspeed` 是**故意不同**的，要在 `core/llm.py` 加注释说明

---

### 风险 7：todo.md 全程未提测试

**事实**：
- 全仓库没看到 `tests/` 目录
- todo.md 6 个 Phase 都没有验证手段

**自洽要求**：
- 没有测试就没有"自洽"——系统行为只靠人脑保证
- 6 个 Phase 改完可能引入累积 bug

**建议**：
在每个 Phase 末尾加"验证项"，**不是为兼容**——是为了一致性：

```
Phase 1 验证：python -c "from app.translate.router import router" 启动无错
Phase 2 验证：/api/translate/* 路径都能通，/translate/api/* 全部 404（说明切干净了）
Phase 3 验证：无 token 访问受保护路由 → 401；带过期 token → 401
Phase 4 验证：3 批 fixture 输入，old vs new 输出 token 数差异 < 5%
Phase 5 验证：SSE 事件流未变；普通响应符合 schema
Phase 6 验证：python -m app.translate 启动失败（已废弃）；main_merged.py 启动正常
```

---

### 风险 8：`ai.yaml` 与 `app.core.config` 配置来源分裂

**事实**：
- `core/config.py` 读环境变量（`MINIMAX_API_KEY` 等）
- `translate/config.py:load_ai_config()` 读 `backend/app/translate/config/ai.yaml` / `ai.local.json`
- `translate/client.py:31-40` 有 `from_config()` 类方法，**单独走 yaml 路径**
- `translate/client.py:23-28` 默认构造走 `app.core.config`（env）

**问题**：
- 同一个 `apiKey` 可以从两个地方来
- `load_ai_config()` 读 yaml 后，**覆盖**还是**叠加** env？没明说

**自洽要求**：
- 配置来源**唯一**：`app.core.config` 读 env（12-factor）
- **删除 `ai.yaml` / `ai.local.json`**——不为 yaml 留 deprecated
- `translate/config.py` 只保留 pipeline 参数（`PHASE1_BATCH_SIZE` 等），不保留 LLM 配置

**建议终态**：
```python
# app/core/config.py —— 唯一配置来源
MINIMAX_API_KEY = os.environ["MINIMAX_API_KEY"]
MINIMAX_API_URL = os.environ.get("MINIMAX_API_URL", "https://...")
MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7-highspeed")
```

```python
# app/translate/config.py —— 只剩 pipeline 参数
PHASE1_BATCH_SIZE = 8
PHASE2_WINDOW_SIZE = 20
PHASE4_WINDOW_SIZE = 20
```

```
# 删除文件
backend/app/translate/config/ai.yaml
backend/app/translate/config/ai.local.json
```

---

## 五、Medium 级风险详解

### 风险 9：`logging.basicConfig` 在 import 时改全局配置

**事实**：
- `translate/app.py:36-39` 在模块 import 级别调用 `logging.basicConfig(...)`
- `main_merged.py` 启动时 import `translate.app` → 改全局日志格式

**自洽要求**：
- logger 只声明身份，不配置全局
- 日志格式由应用入口统一控制

**建议**：
```python
# app/translate/app.py（修改后）
log = logging.getLogger("app.translate")  # 没了 basicConfig
```

```python
# main_merged.py 启动时统一配置
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
```

---

### 风险 10：`_recover_jobs_from_db` 归属不清

**事实**：
- `translate/app.py:50-64` 实现 `_recover_jobs_from_db()`
- `main_merged.py:48` 显式 import 调用

**自洽要求**：
- 启动时序**明确**：先 recover → 再启 dispatcher
- 函数归属按**职责**而非"谁先 import"

**建议**：
- 放 `jobs.py`（最贴近数据）
- 改名 `recover_on_startup()`（明确意图）
- `worker.py` 启动时**主动调用** `jobs.recover_on_startup()`，不是 `main_merged.py`

```python
# app/translate/worker.py
async def start_background_tasks():
    jobs.recover_on_startup()
    asyncio.create_task(_dispatcher_loop())
    asyncio.create_task(_janitor_loop())
```

```python
# main_merged.py
from app.translate.worker import start_background_tasks

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    await start_background_tasks()
    yield
```

`main_merged.py` **不知道** recover / dispatcher 存在，只调用 `start_background_tasks`。

---

### 风险 11：SSE 事件不应套 Pydantic schema

**事实**：
- todo.md 5.2 写"路由用 schema"
- SSE `StreamingResponse` 返回的是流式字符串
- 事件类型动态：`progress` / `queued` / `done`，字段不固定

**自洽要求**：
- 不同形态的响应有**不同的契约**：
  - 普通 JSON：Pydantic schema（编译期 + 文档）
  - SSE 事件：TypedDict（仅 IDE 提示）+ 发送方/接收方共知格式
- 不要因为"统一"就把所有响应都套 schema

**建议**：
- todo.md 5.2 加一个**例外声明**：
  > "SSE 路由不使用 Pydantic response_model，因为流式响应无法做编译期验证。SSE 事件类型用 TypedDict 在 `sse.py` 中定义。"
- `sse.py` 中：
  ```python
  from typing import TypedDict
  
  class ProgressEvent(TypedDict):
      type: Literal["progress"]
      phase: str
      step: int
      ...
  ```

---

### 风险 12：`_dispatcher_loop` 双重启动保护依赖模块全局变量

**事实**：
- `main_merged.py:40-41` 有一份 `_translate_dispatcher_task = None`
- `translate/app.py:70-71` 又有一份
- `translate/app.py:77` 有保护 `if _translate_dispatcher_task is None:`
- `translate_lifespan` 实际**不会**被 FastAPI 触发（子应用 mount 不跑 lifespan）

**自洽要求**：
- 启动入口**唯一**：`main_merged.py`
- 翻译子模块**不**有自己的 lifespan

**建议**：
- 拆 `worker.py` 时把 `translate_lifespan` 全部删除
- 启动函数收敛到 `worker.start()` / `worker.stop()`
- `translate/app.py` Phase 6 改为 `create_app()` 工厂（如果还需要），但**不**再带 lifespan

---

### 风险 13：`MAX_CONCURRENT_JOBS=1` + 多 worker 部署隐患

**事实**：
- `translate/jobs.py:23` `MAX_CONCURRENT_JOBS = 1`
- `translate/app.py:68` `executor = ThreadPoolExecutor(max_workers=4)`
- `uploads/` / `results/` 是进程级共享目录
- uvicorn workers>1 时，多个 worker 共享同一个 queue（in-memory）

**问题**：
- 多 worker 部署时，**A worker 入队的 job 被 B worker 的 dispatcher 取走**（因为 `jobs.job_queue` 是模块级全局，每个 worker 一份）
- `MAX_CONCURRENT_JOBS=1` 实际变成了"每 worker 1 个并发"，4 worker → 4 并发，配置失效
- `uploads/` 文件名 `upload-{timestamp}.hex` 全局唯一，但仍可能两个 worker 抢同一 job

**自洽要求**：
- 单 worker 部署 + `MAX_CONCURRENT_JOBS=1` 是一致的设计
- 多 worker 部署时，要么保证 `MAX_CONCURRENT_JOBS=N workers`（资源浪费），要么把 queue 移到 DB/Redis

**建议**：
- 在 `core/config.py` 加 `MAX_CONCURRENT_JOBS`，从 env 读
- 启动时如果 `uvicorn workers > 1`，强制 `MAX_CONCURRENT_JOBS >= workers`
- 不为多 worker 优化（保持单 worker 简单）——只要**声明清楚**部署约束即可

---

## 六、删除清单（自洽原则下的清理）

按"自洽 ≠ 兼容"原则，todo.md 中以下事项**不应**做：

| # | 不应做的事 | 理由 |
|---|-----------|------|
| 1 | 保留 `/translate/api/*` 双路由 | 路径分裂，违反 API 一致性 |
| 2 | `ai.local.json` 保留为 deprecated | 配置源分裂 |
| 3 | `__main__.py` + `create_app()` 工厂作为"独立运行"兼容 | 启动入口分裂 |
| 4 | `TranslateAuthMiddleware` 简化为"兜底中间件" | 认证风格分裂（应该全部走 Depends） |
| 5 | 给 SSE 保留 JWT-in-URL 路径 | 凭证出现在日志 |
| 6 | `LLMClient` 类作为 `core/llm` 的"过渡封装" | 两套 LLM 调用方式 |

**一刀切的清理方案**：
- 路径：`/translate/api/*` 全部切到 `/api/translate/*`，**不**保留旧路径
- 配置：删除 `ai.yaml` 和 `ai.local.json`，**不**留 deprecated
- 启动：删除 `__main__.py`，**不**加 `create_app()` 工厂（只 `main_merged.py` 启动）
- 认证：删除 `TranslateAuthMiddleware`，**不**留兜底
- SSE：JWT-in-URL 替换为 ticket 机制
- LLM：`client.py` 整个删除，**不**留 `LLMClient` 类作为"过渡"

---

## 七、前置任务：进入 Phase 1 之前

| # | 任务 | 解决风险 |
|---|------|----------|
| P0-1 | 写 `get_user_for_request()` 公共函数（统一 header / query 入口） | 1, 4 |
| P0-2 | 建 `tests/` 目录 + 至少 1 个 e2e 冒烟 | 7 |
| P0-3 | 画 `translate/` 模块依赖图（DAG 验证） | 2 |
| P0-4 | 在 `translate/__init__.py` 定义 `BASE_DIR` / `UPLOAD_DIR` / `RESULT_DIR` | 3 |
| P0-5 | 删除 `logging.basicConfig`，改 `log = logging.getLogger(...)` | 9 |

---

## 八、Phase 顺序修订建议

| Phase | 修订项 | 解决风险 |
|-------|--------|----------|
| Phase 1 | 同步删除 `logging.basicConfig`、`BASE_DIR` 改从 `__init__.py` import | 2, 3, 9, 10, 12 |
| Phase 2 | **不要双路由兼容**。路径一刀切，前端 dist 重新构建后一次切换 | — |
| Phase 3 | 删 `TranslateAuthMiddleware` 前先实现 `get_user_for_request()` | 1, 4, 5 |
| Phase 3 | 加 ticket 端点（**替换** JWT-in-URL，不留兜底） | 5 |
| Phase 4 | **逐个 phase 替换** + 对比 fixture 输出（验证行为没漂移） | 6 |
| Phase 4 | 删 `ai.yaml` / `ai.local.json` / `translate/client.py` / `translate/llm.py` 工厂 | 8 |
| Phase 4 | `core/llm.py` 的 `temperature` 默认改 0.2（与 translate 对齐） | 6 |
| Phase 5 | **SSE 明确不套 schema**，用 TypedDict | 11 |
| Phase 6 | 删 `__main__.py`、删 `translate/app.py`（不创建 `create_app()`） | 12 |
| Phase 6 | 删 `translate_lifespan` 全部代码 | 12 |
| 部署 | 单 worker 部署约束在 README 写明（`workers=1`） | 13 |

---

## 九、自洽性自检清单

Phase 6 全部完成时，以下条件应该全部满足：

- [ ] 没有 `TranslateAuthMiddleware`，全模块认证走 `get_user_for_request`
- [ ] 没有 `/translate/api/*` 路径，全模块走 `/api/translate/*`
- [ ] 没有 `ai.yaml` / `ai.local.json`，LLM 配置全 env
- [ ] 没有 `translate/client.py` / `translate/llm.py`，LLM 调用全 `core/llm`
- [ ] 没有 `__main__.py`，启动入口唯一 `main_merged.py`
- [ ] 没有 `translate_lifespan`，后台任务在 `worker.py` 内聚
- [ ] 没有 `JWT in URL`，SSE/下载全 ticket
- [ ] 没有 `logging.basicConfig` 在 import 级别调用
- [ ] `BASE_DIR` 只在 `translate/__init__.py` 定义一次
- [ ] `translate/` 模块依赖是严格 DAG（jobs 不 import worker/router）
- [ ] `tests/` 目录存在，e2e 冒烟通过

**不满足的就不算自洽**。

---

## 十、最终结论

todo.md 的 6 阶段方向对，但**"为了兼容"的部分都是对完整性的污染**：

1. ❌ 删掉所有兼容层设想
2. ✅ 用一次性切换 + 内部测试验证代替
3. ✅ 终态干净优先于过渡期平稳

**核心问题**：
1. 没把"SSE/下载认证 + Depends 模式不兼容"作为前置问题解决
2. 没考虑拆文件后的循环导入保护
3. 配置源分裂（env vs yaml）
4. 全程无测试

**建议**：把第七节"前置任务"和第八节"Phase 顺序修订"补入 todo.md 头部，按修订后的顺序执行。第九节"自洽性自检清单"作为 Phase 6 的 DoD。
