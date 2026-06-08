# Todo — 未修复问题清单

> 生成日期：2026-06-08
> 来源：review_by_dsv4.md + review_by_mimo.md

---

## P0 — 必须修复

| # | 问题 | 文件 | 说明 |
|---|------|------|------|
| 1 | API Key 硬编码 | [config.py](file:///g:/github/testai_community/backend/app/core/config.py#L15) | MiniMax API Key 明文写在源码中，需改为纯环境变量 `os.environ["MINIMAX_API_KEY"]`，并轮换已泄露的密钥 |
| 2 | translate 模块依赖外部包 | [app.py](file:///g:/github/testai_community/backend/app/translate/app.py#L22-L28) + [llm.py](file:///g:/github/testai_community/backend/app/translate/llm.py#L10-L11) | 引入了 `recorder_translate_server.backend.*`，该包不在项目中且 `requirements.txt` 未声明。LLM调用层可用 [minimax_client.py](file:///g:/github/testai_community/backend/app/skill_hub/minimax_client.py) 内部替代，但 `audit/preprocess/validate/workflow/xml_parse` 5个翻译业务核心模块需外部包提供或搬运到本仓库 |

---

## P1 — 高优先级

| # | 问题 | 文件 | 说明 |
|---|------|------|------|
| 3 | 前后端分支类型命名不一致 | 后端: [skills_router.py](file:///g:/github/testai_community/backend/app/skill_hub/skills_router.py) L121 `"template"` ；前端: [client.ts](file:///g:/github/testai_community/frontend/src/skill_hub/api/client.ts) L33 `"standard"` | 后端用 `"template"`，前端判断 `"standard"`，导致 template 分支在前端显示为普通分支 |
| 4 | SkillVersion.id 前后端类型不匹配 | 后端: [models.py](file:///g:/github/testai_community/backend/app/skill_hub/models.py) L73 `String(UUID)` ；前端: `client.ts` L36 `number` | 前端把 id 当 number 处理，但后端是 UUID 字符串；merge 接口的 `source_version_id` 同理 |
| 5 | translate 任务状态仅存内存 | [jobs.py](file:///g:/github/testai_community/backend/app/translate/jobs.py#L61-L63) | 服务重启后所有翻译任务丢失，生产环境需改为数据库存储 |

---

## P2 — 中优先级

| # | 问题 | 文件 | 说明 |
|---|------|------|------|
| 6 | FilePreview 未携带认证信息 | [ResultPreview.tsx](file:///g:/github/testai_community/frontend/src/translate/components/ResultPreview.tsx) L50 | 使用原生 `fetch` 而非 `apiFetch`，若 translate 路由需要认证则请求会 401 |
| 7 | Dashboard creating 状态管理有误 | [Dashboard.tsx](file:///g:/github/testai_community/frontend/src/skill_hub/pages/Dashboard.tsx) L51-L54 | `setCreating(false)` 在 mutation 发起后立即执行，loading 闪烁无效，应使用 `isPending` |
| 8 | main_combined.py 是否应删除 | [main_combined.py](file:///g:/github/testai_community/backend/app/main_combined.py) | 与 main_merged.py 功能重叠，评审建议仅保留 main_merged.py 作为唯一入口 |
| 9 | 两套 CSS 全局样式 | [global.css](file:///g:/github/testai_community/frontend/src/shared/styles/global.css) vs [globals.css](file:///g:/github/testai_community/frontend/src/shared/styles/globals.css) | `globals.css` 未被导入但存在于项目中，与 `global.css` 颜色变量冲突（蓝色 vs 绿色） |
| 10 | vite.config.ts 含 Python 风格注释 | [vite.config.ts](file:///g:/github/testai_community/frontend/vite.config.ts) L16 | 使用了 `#` 注释（Python 风格），应改为 `//` |
| 11 | 重复的 vite.config.js | [vite.config.js](file:///g:/github/testai_community/frontend/vite.config.js) | 与 vite.config.ts 共存且配置不同，应删除 |
| 12 | translate `on_event` 已废弃 | [app.py](file:///g:/github/testai_community/backend/app/translate/app.py#L72) | FastAPI 推荐使用 `lifespan` 替代 `@app.on_event("startup")` |

---

## P3 — 低优先级 / 可选优化

| # | 问题 | 文件 | 说明 |
|---|------|------|------|
| 13 | 缺少 .gitignore | 项目根目录 | venv/、node_modules/、database.sqlite、__pycache__ 等不应提交 |
| 14 | 前端重复定义类型 | [client.ts](file:///g:/github/testai_community/frontend/src/skill_hub/api/client.ts) + [types/models.ts](file:///g:/github/testai_community/frontend/src/skill_hub/types/models.ts) | User、Skill、Branch 等接口在两处重复定义，应统一到 models.ts |
| 15 | AppLayout 每次渲染解析 localStorage | [AppLayout.tsx](file:///g:/github/testai_community/frontend/src/shared/components/AppLayout.tsx) L22 | 应使用 `useMemo` 或 Zustand store |
| 16 | 错误响应格式不统一 | 多个路由文件 | auth 用中文、skill_hub 混用中英文、translate 用英文 |
| 17 | 数据库迁移策略缺失 | 全局 | 仅用 `Base.metadata.create_all` 自动建表，生产环境应接入 Alembic |

---

## 架构建议（非阻塞）

- translate 模块与主应用耦合度高，建议重构为与 skill_hub 同级的共享 core 模块，而非保留独立 app 形态
- 统一错误处理中间件，统一响应格式和语言