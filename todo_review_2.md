# todo.md 第二轮评审（同事修订版）

> 评审对象：`todo.md`（同事修订后版本）
> 评审时间：2026-06-10
> 立场：与第一轮一致 —— **没有外部用户，系统只需自洽**
> 评审范围：相对第一轮的吸收情况 + 新引入问题 + 残留遗漏

---

## 一、整体评价

**吸收得不错**：
- ✅ P0 前置任务 4 项都进去了（认证函数 / DAG / 路径 / logging）
- ✅ Phase 1 拆文件的 DAG 列得很清楚
- ✅ Phase 1.3 SSE 用 TypedDict（不套 Pydantic）
- ✅ Phase 2 明确"一刀切，不保留旧路径"
- ✅ Phase 3 用 `get_user_for_request` 统一认证入口
- ✅ Phase 4 删 `ai.yaml` / `ai.local.json`，对齐 temperature
- ✅ Phase 4.3 改 `translate/llm.py` 为简单委托
- ✅ Phase 5 SSE 明确不套 schema
- ✅ Phase 6 删 `__main__.py` / `app.py` / `lifespan`
- ✅ 自洽性自检清单（7 条）

**但有 3 个关键遗漏、5 个新引入隐患、6 个次要问题**，下面分类列出。

---

## 二、🔴 关键遗漏（必须修）

### 遗漏 1：没有 `tests/` 目录 ← 第一轮 review 第 7 项明确要求过

**事实**：P0 任务只列了 4 项（P0-1 认证函数、P0-2 DAG、P0-3 路径、P0-4 logging），**没有 P0-5 建 `tests/` 目录**。

**问题**：
- 每个 Phase 的"验证"都是手动冒烟
- Phase 1 拆完 router 没办法自动确认路由还能跑
- Phase 3 改认证没办法批量回归 401 行为
- Phase 4 LLM 改完没有 fixture 对比脚本
- 6 Phase 累积 bug 无感知

**建议**：补 P0-5：
```python
# tests/test_translate_e2e.py
# 1. 登录拿 token
# 2. 上传 fixture zip
# 3. 轮询 /api/translate/jobs/{id} 直到 completed
# 4. 下载结果 zip
# 5. 断言 zip 包含 case 文件
```

加 `tests/test_unauthorized.py`：
```python
# 无 token 访问 /api/translate/jobs → 401
# 带过期 token → 401
# 带 query token 访问 SSE → 200
```

---

### 遗漏 2：自洽清单漏了 7 项关键结构

清单 7 条覆盖了 `client.py`、`__main__.py`、`app.py`、`logging.basicConfig`，**但**：

| # | 漏列项 | Phase 来源 | 严重度 |
|---|--------|-----------|--------|
| 1 | `translate/llm.py`（re-export 没必要存在，应整体删） | Phase 4.3 | 🟠 |
| 2 | `translate_lifespan` 函数本身 | Phase 6.3 | 🟠 |
| 3 | `BASE_DIR` 单点定义在 `__init__.py` | P0-3 | 🟡 |
| 4 | `TICKETS` 内存存储结构 | Phase 3.4 | 🟠 |
| 5 | `MAX_CONCURRENT_JOBS` 从 env 读 | Phase 6.5 | 🟠 |
| 6 | `MINIMAX_MODEL` 从 env 读 | Phase 4.5 | 🟠 |
| 7 | `tests/` 目录存在 | 遗漏 1 | 🔴 |

**建议自洽清单扩展到 14 条**（见第七节）。

---

### 遗漏 3：`assert_all_routes_protected` 实现有 bug

3.3 的代码：
```python
deps = [d.call.__name__ for d in route.dependant.dependencies]
if "get_user_for_request" not in deps:
    raise RuntimeError(...)
```

**问题**：
- `route.dependant.dependencies` 是**直接依赖**（不含嵌套）
- `get_user_for_request` 内部又 `Depends(get_db)` —— `get_db` 会在直接依赖里
- `get_user_for_request` **自己**不算直接依赖（它是路由的 dependency 函数的 dependant 树里的某个节点）

**正确写法需要递归收集**：
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

**风险**：原版可能**漏检**或**误检**（取决于 FastAPI 内部表示），安全断言不可信。

---

## 三、🟠 新引入的隐患

### 隐患 1：Phase 4.1 改 `temperature` 默认值会污染 skill_hub

`core/llm.py:42` 当前 `temperature: float = 0.3`，Phase 4.1 改 0.2 对齐 translate。

**问题**：
- `core/llm.py` 是 `main_merged.py:25` 引入的 `llm_router` 共享的
- `app/skill_hub/llm_router.py` 也在用 `core/llm.py`
- **如果 skill_hub 的调用方是显式传 temperature → 不影响**
- **如果走默认 → 改 0.2 会让 skill_hub 行为漂移**

**验证**（todo.md 没做）：
```bash
grep -rn "from app.core.llm" backend/app/skill_hub/
grep -rn "chat(" backend/app/skill_hub/ | grep -v "temperature="
```

**建议**：
- 如果 skill_hub **全部显式传** → 安全可改
- 如果有走默认的 → **不动默认值**，改用"translate 调用方显式传 0.2"
- 自洽清单加一条"skill_hub LLM 行为不变（grep 验证）"

---

### 隐患 2：Phase 3.4 ticket 端点没有清理机制

3.4 的代码：
```python
TICKETS[ticket] = {"user_id": user.id, "exp": time.time() + 30}
```

`TICKETS` 是模块级 dict，30s 后 ticket 失效但**字典里永远在**。

**问题**：
- 长跑服务 → TICKETS 单调增长
- 用户量大的话 OOM
- **结构问题**，不是 nice-to-have

**建议**：
- 方案 A：`from cachetools import TTLCache; TICKETS = TTLCache(maxsize=10000, ttl=30)`
- 方案 B：加 janitor 协程，30s 扫一次，删过期项
- 方案 C：每次 `_event_gen` 时 lazy 清理（不适合 hot path）

**选 A 最简**——但要确认 `cachetools` 是已装依赖；B 更轻量但要启后台任务。

---

### 隐患 3：Phase 3.4 ticket 标"可选" ← 自洽性倒退

todo.md 3.4 明确写"**可选，优先级低于核心改造**"。

**问题**：
- JWT-in-URL 是结构脏
- ticket 是修复这个结构问题的方案
- "可选" → 团队 Sprint 时可能被砍 → 终态不完整
- **不是 nice-to-have**——是和"删 `TranslateAuthMiddleware`"同一级别的结构性修复

**建议**：
- 把"可选"去掉
- ticket 和认证函数是同一个 Phase 3 的事
- 自洽清单加一条"没有 `?token=` 参数，所有 SSE/下载用 `?ticket=`"

---

### 隐患 4：Phase 3.1 `get_user_for_request` 没考虑 `?ticket=`

P0-1 的实现只查 `query_params.get("token")`：
```python
token = request.query_params.get("token")
```

ticket 来了之后：
- 端点 `/ticket` 颁发 ticket
- SSE URL `/jobs/.../stream?ticket=xxx`
- `get_user_for_request` **查不到** ticket 字段

**问题**：
- 要么 `get_user_for_request` 同时认 `?token=` 和 `?ticket=`
- 要么新加 `get_user_for_ticket` 依赖（**和"一个入口"违背**）

**建议**：`get_user_for_request` 升级：
```python
def get_user_for_request(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    auth_header = request.headers.get("authorization", "")
    token: str | None = None
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    
    if not token:
        # 优先 ticket，再 fallback token（SSE 场景）
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

**结构上**：ticket 和 JWT 都被抽象为"凭证"，`get_user_for_request` 内部路由到不同验证器。

---

### 隐患 5：Phase 6.5 `MAX_CONCURRENT_JOBS` 从 env 读，但 `core/config.py` 没这个变量

`translate/jobs.py:23` 当前是**硬编码**：
```python
MAX_CONCURRENT_JOBS = 1
```

Phase 6.5 说"从 env 读取"，**但**：
- `core/config.py` 当前没有这个变量
- 没说在哪加、叫什么名字

**建议**：
```python
# app/core/config.py 新增
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "1"))
```

```python
# app/translate/jobs.py 改为
from app.core.config import MAX_CONCURRENT_JOBS
```

单 worker 部署的 sanity check 放 `main_merged.py` lifespan 启动时。

---

## 四、🟡 次要问题

### 次要 1：Phase 4.1 没说 `MINIMAX_MODEL` 环境变量

Phase 4.5 说"LLM 配置统一走 `core/config.py` 读环境变量"，但：
- `core/config.py` 当前只有 `MINIMAX_API_KEY`、`MINIMAX_API_URL`
- `MINIMAX_MODEL` 没说加
- 实际 `core/llm.py:15` 硬编码 `DEFAULT_MODEL = "MiniMax-M2.7-highspeed"`

**问题**：Phase 4.4 改 `worker.py` 显式传 `model=settings.MINIMAX_MODEL`，但 `MINIMAX_MODEL` 没定义。

**建议**：
```python
# core/config.py 新增
MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7-highspeed")
```

```python
# core/llm.py 改为
from app.core.config import MINIMAX_MODEL, MINIMAX_API_KEY, MINIMAX_API_URL
DEFAULT_MODEL = MINIMAX_MODEL  # 或删除这个常量，统一从 config 读
```

---

### 次要 2：Phase 1.2 / 1.5 `translate_lifespan` 和 worker 启动未对齐

当前 `app.py:74-87` 的 `translate_lifespan` 直接 `create_task(_dispatcher_loop())`。

Phase 1.2 把 dispatcher 移到 worker.py，但 `translate_lifespan` **没说**改成调用 `worker.start_background_tasks()`。

Phase 1.5 说"保留 `translate_lifespan`（Phase 6 删除）"——但**没说它现在做什么**。

**问题**：Phase 1 拆完，translate_lifespan 还在 app.py 里，**dispatcher 已经不在 app.py 了**——`translate_lifespan` 怎么启动它们？

**建议**：明确写"`translate_lifespan` 改为 `worker.start_background_tasks()` 的薄壳"：
```python
@asynccontextmanager
async def translate_lifespan(app_instance: FastAPI):
    from .worker import start_background_tasks, stop_background_tasks
    await start_background_tasks()
    yield
    await stop_background_tasks()
```

---

### 次要 3：Phase 5 Pydantic schema 的 `status` 字段弱约束

```python
class JobView(BaseModel):
    status: str  # ← 什么字符串都能传
    ...
```

**建议**：用 `Literal` 强约束：
```python
from typing import Literal

class JobView(BaseModel):
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    ...
```

否则 schema 形同虚设。

---

### 次要 4：Phase 5 `job_to_view` 怎么改没说

当前 `jobs.py:179-196` 返回 dict。Phase 5 改 schema 后没说：
- A. `job_to_view` 改为返回 `JobView`（构造 Pydantic 模型）
- B. 路由里 `JobView.model_validate(jobs.job_to_view(j))`

**建议**：方案 A 更直接：
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

---

### 次要 5：P0-1 函数的 `Bearer` 解析不够规范

```python
if auth_header.startswith("Bearer "):
    token = auth_header[7:]
```

边界 case：
- `"Bearer "` (尾随空 token) → `token=""` → 进入 query，OK
- `"Bearerxxx"` (没空格) → False → 走 query，OK
- `"bearer xxx"` (小写) → False → 走 query。**严格按 HTTP 规范来说 Bearer 应该大小写不敏感**

**建议**：用 `split` 更稳：
```python
parts = auth_header.split(" ", 1)
if len(parts) == 2 and parts[0].lower() == "bearer":
    token = parts[1].strip()
else:
    token = None
```

---

### 次要 6：Phase 6.4 删 `translate/app.py` 后子模块 import 链

`app.py` 删除后：
- `phase1.py`、`phase2.py`、`phase4.py` 当前相对 import 还能工作
- **但**如果有 `from app.translate.app import ...` 这种绝对 import → 会断

**建议**：Phase 6 删 app.py 前 grep 一遍：
```bash
grep -rn "from app.translate.app" backend/
grep -rn "import app.translate.app" backend/
```

把命中行全部改 `from app.translate.worker` / `from app.translate.jobs`。

---

## 五、🟢 同事改得对的地方（值得肯定）

1. **P0-2 DAG 图**：明确写了模块依赖方向，写得到位
2. **Phase 1.3 TypedDict**：SSE 事件类型用 TypedDict 而非 Pydantic，正确
3. **Phase 2.1 路径映射表**：清晰列出旧→新路径对照
4. **Phase 4.1 注释说明**：vision vs chat 用不同 model 是"故意不同"，加注释
5. **Phase 5.3 明确 SSE 不用 response_model**：和 Phase 1.3 呼应
6. **Phase 6.5 部署约束**：单 worker 声明写明
7. **自洽清单**整体方向对，列了 7 条
8. **改造顺序图**：P0 → Phase 1→2→3，Phase 4/5 可并行，逻辑正确

---

## 六、给同事的修订清单（按优先级）

| 优先级 | 编号 | 事项 | Phase |
|--------|------|------|-------|
| 🔴 P0 | 1 | 补 P0-5：建 `tests/` 目录 + e2e 冒烟 | P0 |
| 🔴 P0 | 2 | 修 `assert_all_routes_protected` 递归收集依赖 | Phase 3.3 |
| 🔴 P0 | 3 | grep skill_hub 是否走 `chat()` 默认 temperature | Phase 4.1 |
| 🟠 P1 | 4 | ticket 端点加 `TTLCache` 或 janitor 清理 | Phase 3.4 |
| 🟠 P1 | 5 | 去掉 ticket "可选" 标签，升级为必做 | Phase 3.4 |
| 🟠 P1 | 6 | `get_user_for_request` 同时认 `?token=` 和 `?ticket=` | P0-1 / Phase 3.1 |
| 🟠 P1 | 7 | `core/config.py` 加 `MAX_CONCURRENT_JOBS` env | Phase 6.5 |
| 🟠 P1 | 8 | `core/config.py` 加 `MINIMAX_MODEL` env | Phase 4.5 |
| 🟠 P1 | 9 | 明确 `translate_lifespan` 改用 `worker.start_background_tasks()` | Phase 1.2/1.5 |
| 🟡 P2 | 10 | 自洽清单加 7 项（见第七节） | 自洽清单 |
| 🟡 P2 | 11 | Phase 5 schema `status` 字段用 `Literal` | Phase 5.1 |
| 🟡 P2 | 12 | Phase 5 明确 `job_to_view` 改返回 `JobView` | Phase 5 |
| 🟡 P2 | 13 | P0-1 函数 Bearer 解析用 `split` 更稳 | P0-1 |
| 🟡 P2 | 14 | Phase 6 删 `app.py` 前 grep `from app.translate.app` 全部改掉 | Phase 6.4 |

---

## 七、自洽性自检清单（建议扩展到 14 条）

**同事原版（7 条）**：
- [ ] 没有 `TranslateAuthMiddleware`，全模块认证走 `get_user_for_request`
- [ ] 没有 `/translate/api/*` 路径，全模块走 `/api/translate/*`
- [ ] 没有 `ai.yaml` / `ai.local.json`，LLM 配置全 env
- [ ] 没有 `translate/client.py`，LLM 调用全 `core/llm`
- [ ] 没有 `__main__.py` / `translate/app.py`，启动入口唯一 `main_merged.py`
- [ ] 没有 `logging.basicConfig` 在子模块中，日志格式由入口统一控制
- [ ] SSE 事件用 TypedDict，普通响应用 Pydantic schema

**建议补充（7 条）**：
- [ ] 没有 `translate/llm.py`（re-export 层没必要存在）
- [ ] 没有 `translate_lifespan`（启动逻辑全部在 `worker.start_background_tasks()`）
- [ ] `BASE_DIR` / `UPLOAD_DIR` / `RESULT_DIR` 在 `translate/__init__.py` 单点定义
- [ ] `TICKETS` 用 `TTLCache` 或 janitor 清理，无内存泄漏
- [ ] `MAX_CONCURRENT_JOBS` 从 env 读，部署 README 写明 `workers=1`
- [ ] `MINIMAX_MODEL` 从 env 读，没有硬编码 model 名
- [ ] `tests/` 目录存在，e2e 冒烟通过，认证回归 401 用例通过
- [ ] skill_hub LLM 行为不变（grep 验证调用方都显式传 temperature）

**不满足的就不算自洽**。

---

## 八、最终结论

同事做得**比第一版好得多**，整体方向对。

**核心问题**（3 个）：
1. ❌ 没有 `tests/` 目录（第一轮就提了，没采纳）
2. ❌ `assert_all_routes_protected` 的递归收集依赖（实现 bug）
3. ❌ `core/llm.py` 改 temperature 默认值前没核实 skill_hub 影响

**次要问题**（11 个）：ticket 清理、可选降级、get_user_for_request 不认 ticket、`MAX_CONCURRENT_JOBS` env、`MINIMAX_MODEL` env、`translate_lifespan` 转向、Pydantic Literal、`job_to_view` 改返回类型、Bearer 解析、删 app.py 前 grep、自洽清单不全。

**建议**：把第六节"修订清单"和第七节"扩展自洽清单"补入 todo.md，然后按 P0 → Phase 1 → 2 → 3 → 4/5 → 6 顺序执行。开工前 P0 全部完成 + P0-5 建好测试夹具。
