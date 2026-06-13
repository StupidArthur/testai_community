# 如何接入新业务模块（How to Add New App）

> 文档版本：2026-06-13  
> 适用场景：在 TestAI Community **单 APP** 内增加一个新的业务模块（前后端一体接入）

本文是一份**操作手册**：按步骤做完即可跑通。架构背景见 [architecture_guide.md](./architecture_guide.md)；**跨 App 允许 import 哪些函数**见 [dev/module_internal_api.md](./dev/module_internal_api.md)。

---

## 0. 开始之前

### 0.1 命名

选定模块短名 `<app>`，全小写、无空格，例如 `report`、`metrics`。

| 用途 | 命名 |
|------|------|
| 后端 Python 包 | `backend/app/<app>/` |
| 前端目录 | `frontend/src/<app>/` |
| API 前缀 | `/api/<app>/...` |
| 前端路由 | `/<app>`、`/<app>/...` |

### 0.2 你需要动哪些「公共文件」

每个新模块**必须**改动的注册点（仅此几处，其余代码都在模块目录内）：

| 文件 | 改动 |
|------|------|
| `backend/app/platform/registry.py` | 追加 `AppModule`（router、models、可选 lifespan 钩子） |
| `frontend/src/router.tsx` | 增加路由 |
| `frontend/src/shared/components/AppLayout.tsx` | 顶栏导航（面向用户时） |
| `frontend/src/shared/pages/Portal.tsx` | 首页卡片（可选） |

**不要**新建第二个 FastAPI app、不要新开端口、不要复制 auth/platform。

### 0.3 参照现有模块

| 你要做的 | 照着抄 |
|----------|--------|
| 平台能力 CRUD | `platform/changelog`（非独立业务 App） |
| 复杂业务 + 多页面 | `skill_hub` |
| 上传 / SSE / 后台任务 | `translate` |

---

## 1. 后端：最小可运行模块（5 步）

以下示例模块名：**`report`**（测试报告中心）。

### Step 1 — 创建目录

```
backend/app/report/
├── __init__.py
├── router.py
├── schemas.py      # 有请求/响应体时
├── models.py       # 需要建表时
└── service.py      # 业务逻辑（推荐）
```

### Step 2 — `__init__.py`（模块常量）

```python
"""report 模块：测试报告中心。"""

from pathlib import Path

# 若模块需要磁盘目录，在此单点定义
REPORT_DIR = Path(__file__).resolve().parent.parent / "report_data"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
```

### Step 3 — `schemas.py`

```python
from pydantic import BaseModel


class ReportSummary(BaseModel):
    id: str
    title: str
    created_by: str
```

### Step 4 — `router.py`

```python
"""report HTTP 路由。"""

from fastapi import APIRouter, Depends

from app.auth.models import User
from app.auth.service import get_current_user

from .schemas import ReportSummary

router = APIRouter(prefix="/api/report", tags=["report"])


@router.get("/list", response_model=list[ReportSummary])
def list_reports(user: User = Depends(get_current_user)) -> list[ReportSummary]:
    # 业务逻辑放 service.py，这里只做 HTTP 适配
    return [
        ReportSummary(id="demo-1", title="示例报告", created_by=user.username),
    ]
```

> **鉴权规则**：每个路由必须加 `Depends(get_current_user)`、`Depends(get_current_user_by_ticket)` 或 `Depends(RequireRole([...]))` 之一，不可留空。

### Step 5 — 注册到 `platform/registry.py`

在 `APPS` 元组末尾追加一条 `AppModule`；`factory` 会自动建表、route_guard、`include_router`：

```python
from app.report.models import Report
from app.report.router import router as report_router
from app.platform.app_module import AppModule

# APPS 内追加：
AppModule(
    name="report",
    router=report_router,
    models=(Report,),  # 无表则 models=()
),
```

若有后台 worker，参照 translate 挂 `startup_async` / `shutdown_async`；同步迁移参照 `startup_sync=...`。

### Step 6 — 登记内部 Python API（若其它 App 需调用本模块）

1. 在 **`service.py`** 中实现可复用函数；**禁止**让其它 App import `router.py`。
2. 在 **[dev/module_internal_api.md](./dev/module_internal_api.md)** 的暴露清单中增加符号与「允许调用方」。
3. 在 **`doc/dev/modules/<app>.md`** 增加「内部 Python API」节（可复制 changelog / skill_hub 模板）。
4. 若需调用其它 App，仅 import 对方文档中**已暴露**的 `service` 函数，禁止 import 对方 router。

重启后端，验证：

```powershell
# 先登录拿 token，再请求
curl http://127.0.0.1:48010/api/report/list -H "Authorization: Bearer <token>"
```

---

## 2. 前端：最小可运行模块（5 步）

### Step 1 — 创建目录

```
frontend/src/report/
├── pages/
│   └── ReportPage.tsx
└── components/          # 按需
```

### Step 2 — API 封装 `shared/api/report.ts`

```typescript
import { apiClient } from './client'

export interface ReportSummary {
  id: string
  title: string
  created_by: string
}

export const reportApi = {
  list: () => apiClient.get<ReportSummary[]>('/report/list'),
}
```

> 使用 `apiClient` 会自动带 JWT，401 会跳转登录。

### Step 3 — 页面 `report/pages/ReportPage.tsx`

```tsx
import { Typography, List, Card } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { reportApi } from '../../shared/api/report'

const { Title } = Typography

export default function ReportPage() {
  const { data: reports = [], isLoading } = useQuery({
    queryKey: ['report', 'list'],
    queryFn: () => reportApi.list().then((r) => r.data),
  })

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <Title level={3}>测试报告</Title>
      <Card loading={isLoading}>
        <List
          dataSource={reports}
          renderItem={(item) => (
            <List.Item>{item.title} — {item.created_by}</List.Item>
          )}
        />
      </Card>
    </div>
  )
}
```

### Step 4 — 注册路由 `router.tsx`

在 `ProtectedRoute` → `AppLayout` → `children` 数组中增加：

```tsx
import ReportPage from './report/pages/ReportPage'

// children 内：
{
  path: 'report',
  element: <ReportPage />,
},
```

### Step 5 — 添加入口

**顶栏**（`AppLayout.tsx`）：

```tsx
<NavButton
  icon={<FileTextOutlined />}   // 从 @ant-design/icons 引入
  label="测试报告"
  active={isActive('/report')}
  onClick={() => navigate('/report')}
/>
```

**门户首页**（`Portal.tsx`，可选）：复制现有卡片，改标题、描述、`onClick={() => navigate('/report')}`。

开发模式访问：**http://localhost:3003/report**

---

## 3. 需要数据库表时

### 3.1 `models.py`

```python
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.platform.database import Base


class Report(Base):
    __tablename__ = "reports"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    username = Column(String, nullable=False)  # 创建者
    created_at = Column(DateTime, server_default=func.now())
```

### 3.2 在 `platform/registry.py` 登记模型

在对应 `AppModule.models` 中包含 ORM 类即可（`factory` 启动时 `create_all`）：

```python
from app.report.models import Report

AppModule(name="report", router=report_router, models=(Report,)),
```

### 3.3 路由中使用 DB

```python
from sqlalchemy.orm import Session
from app.platform.database import get_db

@router.get("/list")
def list_reports(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.query(Report).filter(Report.username == user.username).all()
    ...
```

> 当前无 Alembic：改表结构需在 lifespan 中手写迁移（参考 `_migrate_translate_jobs`），或开发环境删库重建。

---

## 4. 常见变体

### 4.1 仅 Admin 可访问

**后端：**

```python
from app.auth.service import RequireRole

@router.post("/publish")
def publish(user: User = Depends(RequireRole(["Admin"]))):
    ...
```

**前端：** 路由组件内校验 role，非 Admin 重定向：

```tsx
function AdminReportPage() {
  const user = JSON.parse(localStorage.getItem('user') || '{}')
  if (user.role !== 'Admin') return <Navigate to="/" replace />
  return <ReportPage />
}
```

### 4.2 文件上传

参照 `translate/router.py` 的 `upload`：

- 用 `UploadFile` + `Form`
- 大小限制检查 `Content-Length`
- 文件存模块 `__init__.py` 定义的目录
- 鉴权用 `get_current_user_by_ticket`（若后续要 SSE/下载）

### 4.3 SSE 实时推送

参照 `translate`：

1. 路由用 `Depends(get_current_user_by_ticket)`
2. 提供 `POST /api/<app>/ticket` 或在模块内复用 translate 的 ticket 端点
3. 前端 `EventSource` URL 带 `?ticket=...`（不能用 Bearer Header）
4. 参照 `translate-sse.ts`、`useTranslateStream.ts`

### 4.4 后台长任务

参照 `translate/worker.py` + `jobs.py`：

```
<app>/
├── jobs.py       # 状态枚举、队列、DB 读写
├── worker.py     # dispatcher、执行 pipeline
└── router.py     # 触发任务、查状态
```

在 `<app>/bootstrap.py` 实现 `on_startup` / `on_shutdown`，并在 `registry.py` 的 `AppModule` 上挂 `startup_async` / `shutdown_async`（参照 translate）。

### 4.5 调用 LLM

```python
from app.ai_service.client import chat

result = chat(
    messages=[{"role": "user", "content": prompt}],
    temperature=0.2,
    model=...,  # 从 app.platform.config 读 MINIMAX_MODEL
)
```

### 4.6 外部系统调用（不走 Web 登录）

参照 `external_api/router.py`：独立 `APIRouter(prefix="/api/v1/external")` + `verify_api_key`，**不要**与 Web JWT 混用。

---

## 5. 测试（最少要补）

在 `backend/tests/` 下新增 `test_report.py`：

```python
def test_list_without_token(client):
    r = client.get("/api/report/list")
    assert r.status_code == 401


def test_list_with_token(auth_client):
    r = auth_client.get("/api/report/list")
    assert r.status_code == 200
```

运行：

```powershell
cd backend
python -m pytest tests/test_report.py -v
```

---

## 6. 文档更新

| 文档 | 更新内容 |
|------|----------|
| `doc/requirements.md` | 新模块功能条目 |
| `doc/design.md` | API 路由表、数据模型 |
| `doc/user_manual.md` | 用户操作说明（若面向终端用户） |
| `doc/architecture_guide.md` | 业务模块列表（若新增典型模式） |

---

## 7. 上线前 Checklist

```
后端
□ backend/app/<app>/ 目录完整，router prefix = /api/<app>
□ platform/registry.py 已追加 AppModule（router + models + 可选 lifespan）
□ 所有路由已鉴权（factory 启动时自动 assert_router_protected）
□ 未复制 auth/platform/ai_service 实现
□ pytest 401 + 核心路径通过

前端
□ frontend/src/<app>/pages/ 页面可访问
□ shared/api/<app>.ts 使用 apiClient
□ router.tsx 路由在 ProtectedRoute 下
□ AppLayout 顶栏有入口（若需要）
□ Portal 卡片已加（若需要）
□ 未 import 其他业务模块的 pages/components

文档
□ requirements / design / user_manual 已更新
```

---

## 8. 完整改动文件一览（示例 report）

```
新增
  backend/app/report/__init__.py
  backend/app/report/router.py
  backend/app/report/schemas.py
  backend/app/report/service.py          # 可选
  backend/app/report/models.py           # 可选
  backend/tests/test_report.py
  frontend/src/report/pages/ReportPage.tsx
  frontend/src/shared/api/report.ts

修改
  backend/app/platform/registry.py            # 追加 AppModule
  frontend/src/router.tsx                # 路由
  frontend/src/shared/components/AppLayout.tsx
  frontend/src/shared/pages/Portal.tsx   # 可选
  doc/requirements.md
  doc/design.md
  doc/user_manual.md                     # 可选
```

---

## 9. 相关文档

- [architecture_guide.md](./architecture_guide.md) — 单 APP 原则、公共模块清单、依赖规则
- [design.md](./design.md) — 现有模块设计细节
- [requirements.md](./requirements.md) — 功能需求
- [user_manual.md](./user_manual.md) — 终端用户手册
- [new_app.skill.md](./new_app.skill.md) — 本手册的 LangGPT 九维 Skill 版（可导入 Skill Hub）

---

*designed by @yuzechao*
