# TestAI Community 代码评审意见（第三轮 — 终审）

> 评审人：MiMo
> 评审日期：2026-06-08
> 说明：MINIMAX_API_KEY 硬编码为已知设计决策，不再列出。

---

## 上轮问题修复情况

**全部 P0 / P1 / P2 问题均已修复。** 具体如下：

| 编号 | 问题 | 状态 |
|------|------|------|
| P0-1 | requirements.txt 缺 openai/pyyaml | ✅ 已修复 |
| P1-2 | template vs standard 命名不一致 | ✅ 已修复 — `skills_router.py:119` 改为 `"standard"` |
| P1-3 | SkillVersion.id 类型不匹配 | ✅ 已修复 — 前端 `id` 改为 `string`，`source_version_id` 改为 `string` |
| P1-4 | workflow 与 app 双重 LlmAudit | ✅ 已修复 — `app.py` 中多余的 LlmAudit 已移除 |
| P2-5 | Dashboard creating 状态无效 | ✅ 已修复 — 改用 `createMutation.isPending` |
| P2-6 | FilePreview 未携带 Token | ✅ 已修复 — 现在注入 Authorization header |
| P2-7 | 废弃文件未清理 | ✅ 已修复 — `main_combined.py`、`security.py`、`vite.config.js`、`globals.css` 均已删除 |
| P2-8 | vite.config.ts # 注释 | ✅ 已修复 — 改为 `//` |
| P2-9 | 缺少 .gitignore | ✅ 已修复 — 已添加 |
| P2-10 | CORS 中间件重复 | ✅ 已修复 — translate/app.py 中的 CORS 已移除 |
| P3-11 | config 搜索路径含 release1 | ✅ 已修复 — 已移除 |

---

## 剩余 P3 优化项（非阻塞，可选处理）

以下为低优先级的代码风格/最佳实践建议，不影响功能和安全：

### 1. `on_event("startup")` 已废弃

`translate/app.py:60` 仍使用 `@app.on_event("startup")`。FastAPI 官方建议改用 `lifespan` 上下文管理器。当前功能正常，未来大版本可能移除。

**修复示例：**
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_dispatcher_loop())
    asyncio.create_task(_janitor_loop())
    yield

app = FastAPI(..., lifespan=lifespan)
```

---

### 2. 前端类型定义重复

`client.ts` 和 `types/models.ts` 都定义了 `User`、`Skill`、`Branch`、`SkillVersion`、`MergeRequest` 等接口。两边目前一致，但维护两份容易不同步。

**建议：** 统一到 `types/models.ts`，`client.ts` 从中 import。

---

### 3. localStorage 重复解析

前端多个组件每次渲染都执行 `JSON.parse(localStorage.getItem('user'))`：
- `AppLayout.tsx:22`
- `Dashboard.tsx:38`
- `SkillBranches.tsx:62`
- `BranchSandbox.tsx:167,170`

**建议：** 提取为自定义 hook 或 Zustand store，统一管理用户状态。

---

## 结论

项目代码质量良好，所有功能性问题已修复。剩余均为代码风格层面的 P3 优化建议，不影响正常使用。**可以进入测试/上线阶段。**
