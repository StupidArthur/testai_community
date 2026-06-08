# TestAI Community 设计文档

> 文档版本：2026-06-08
> 项目路径：`G:/github/testai_community/`

---

## 一、项目概述

TestAI Community 是一个统一测试资产管理与 AI 翻译平台，将原有的 `skill_hub`（技能管理）和 `recorder_translate_server`（AI 翻译）两个服务合并为单一应用。

**核心功能：**
- **技能管理**：管理 AI Agent 的 Skill 资产（分支、版本、评估、Merge/Fork）
- **AI 翻译**：上传 UI 录制 ZIP → 自动翻译为中文测试用例
- **统一入口**：单一前端 + 单一后端，多模块共享认证

---

## 二、技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | React 19 + Vite 8 + TypeScript |
| UI 库 | Ant Design 6 + Pro Components |
| 状态/数据 | TanStack Query v5 + Zustand |
| 后端框架 | FastAPI (Python) |
| 数据库 | SQLite (`database.sqlite`) |
| LLM 调用 | MiniMax API (`MiniMax-M2.7-highspeed`) |
| 开发端口 | 后端 48010 / 前端 3003 |

---

## 三、目录结构

```
G:/github/testai_community/
├── backend/
│   ├── app/
│   │   ├── auth/                      # 认证模块
│   │   │   ├── models.py             # User 模型
│   │   │   ├── router.py             # /api/auth/*, /api/users/*
│   │   │   ├── schemas.py            # Pydantic schemas
│   │   │   └── service.py            # hash_password, verify_password, create_access_token
│   │   │
│   │   ├── skill_hub/                # 技能管理模块
│   │   │   ├── skills_router.py      # /api/skills/*
│   │   │   ├── llm_router.py        # /api/llm/* (run/lint/diff)
│   │   │   ├── integration_router.py # /api/v1/integration/*
│   │   │   ├── models.py             # Skill, Branch, SkillVersion 模型
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   ├── utils.py
│   │   │   ├── integration_models.py # LLMTask, TaskStatus
│   │   │   ├── integration_service.py
│   │   │   ├── minimimax_client.py  # MiniMax LLM 调用封装
│   │   │   └── migrate_to_5fields.py
│   │   │
│   │   ├── translate/                 # AI 翻译模块
│   │   │   ├── app.py               # FastAPI 实例（/api/* 路由）
│   │   │   ├── jobs.py              # 任务队列管理
│   │   │   ├── llm.py
│   │   │   ├── web_progress.py
│   │   │   ├── result_zip.py
│   │   │   ├── zip_utils.py
│   │   │   └── __main__.py
│   │   │
│   │   ├── core/                     # 公共基础设施
│   │   │   ├── config.py            # DATABASE_URL 等配置
│   │   │   ├── database.py          # SQLAlchemy engine, SessionLocal
│   │   │   └── security.py          # JWT Bearer 认证依赖
│   │   │
│   │   ├── main_merged.py           # ⚠️ 启动入口
│   │   └── main_combined.py         # (废弃，网关模式)
│   │
│   ├── database.sqlite
│   └── requirements.txt
│
└── frontend/
    ├── src/
    │   ├── App.tsx                  # 根组件，ConfigProvider + RouterProvider
    │   ├── main.tsx                 # React 入口，QueryClientProvider
    │   ├── router.tsx               # React Router v7 配置
    │   │
    │   ├── auth/                    # 登录模块
    │   │   └── Login.tsx
    │   │
    │   ├── skill_hub/pages/         # 技能管理页面
    │   │   ├── Dashboard.tsx        # 技能列表页
    │   │   ├── SkillBranches.tsx    # 分支列表页
    │   │   ├── BranchSandbox.tsx    # 沙盒编辑页
    │   │   └── AdminPage.tsx        # 用户管理页
    │   │
    │   ├── translate/pages/          # AI 翻译页面
    │   │   ├── HomePage.tsx         # 上传 + 任务列表
    │   │   └── JobDetailPage.tsx    # 任务详情/进度/下载
    │   │
    │   ├── translate/components/      # AI 翻译组件
    │   │   ├── UploadZone.tsx
    │   │   ├── JobList.tsx
    │   │   ├── JobProgress.tsx
    │   │   ├── ResultPreview.tsx
    │   │   └── StatusBadge.tsx
    │   │
    │   └── shared/                  # 公共模块
    │       ├── api/
    │       │   ├── client.ts        # 认证 API
    │       │   ├── translate-client.ts
    │       │   ├── translate-jobs.ts
    │       │   └── translate-sse.ts
    │       ├── components/
    │       │   └── AppLayout.tsx     # 导航栏 + Content 布局
    │       ├── hooks/
    │       │   ├── useTheme.ts      # 主题切换
    │       │   └── useTranslateStream.ts
    │       ├── pages/
    │       │   └── Portal.tsx       # 首页（双卡片导航）
    │       ├── styles/
    │       │   ├── global.css
    │       │   ├── globals.css
    │       │   └── tokens.ts        # Ant Design 主题 token
    │       └── types/
    │           └── models.ts
    │
    ├── index.html
    ├── package.json
    └── vite.config.ts
```

---

## 四、API 设计

### 4.1 认证模块（auth）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册用户 |
| POST | `/api/auth/login` | 登录，返回 JWT token |
| GET | `/api/users/me` | 获取当前用户信息 |
| GET | `/api/users` | 获取用户列表（Admin） |
| POST | `/api/users/{user_id}/reset-password` | 重置密码（Admin） |
| POST | `/api/users/me/password` | 修改自己密码 |

### 4.2 技能管理模块（skill_hub）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/skills` | 技能列表 |
| POST | `/api/skills` | 创建技能 |
| GET | `/api/skills/{skill_id}` | 技能详情 |
| GET | `/api/skills/{skill_id}/branches` | 分支列表 |
| POST | `/api/skills/{skill_id}/branches` | 创建分支 |
| GET | `/api/skills/{skill_id}/branches/{branch_id}/versions` | 版本列表 |
| POST | `/api/skills/{skill_id}/branches/{branch_id}/versions` | 创建版本 |
| POST | `/api/skills/{skill_id}/merge` | 合并分支 |
| POST | `/api/skills/{skill_id}/branches/{branch_id}/fork` | Fork 分支 |
| POST | `/api/skills/{skill_id}/branches/{branch_id}/evaluate-draft` | 评估草稿 |
| POST | `/api/llm/run` | 运行 LLM |
| POST | `/api/llm/lint` | LLM Lint |
| POST | `/api/llm/diff` | LLM Diff |
| GET | `/api/v1/integration/skills/{skill_name}` | 获取集成技能 |
| POST | `/api/v1/integration/skills/{skill_name}/execute-async` | 异步执行 |
| GET | `/api/v1/integration/tasks/{task_id}` | 查询任务状态 |

### 4.3 AI 翻译模块（translate）

translate 模块通过 `app.mount("/translate", translate_app)` 挂载，
translate 后端的 `/api/*` 路由自动变成 `/translate/api/*`：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/translate/api/upload` | 上传录制 ZIP |
| GET | `/translate/api/jobs` | 任务列表 |
| GET | `/translate/api/jobs/{job_id}` | 任务详情 |
| DELETE | `/translate/api/jobs/{job_id}` | 取消任务 |
| GET | `/translate/api/jobs/{job_id}/stream` | SSE 进度流 |
| GET | `/translate/api/jobs/{job_id}/download` | 下载结果 ZIP |
| GET | `/translate/api/jobs/{job_id}/file` | 预览单个结果文件 |

### 4.4 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 后端健康状态 |

---

## 五、数据模型

### 5.1 User（auth）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| username | String | 用户名（唯一） |
| password_hash | String | bcrypt 哈希密码 |
| role | Enum | Engineer / Admin |
| created_at | DateTime | 创建时间 |

### 5.2 Skill / Branch / SkillVersion（skill_hub）

```
Skill (技能)
  └── Branch (分支)
        └── SkillVersion (版本)
```

### 5.3 Job（translate）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String | 任务 ID（UUID） |
| status | Enum | QUEUED / RUNNING / COMPLETED / FAILED / CANCELLED |
| upload_path | Path | 上传文件路径 |
| result_zip_path | Path | 结果 ZIP 路径 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

---

## 六、认证机制

- **方式**：JWT Bearer Token
- **过期时间**：60 分钟（`ACCESS_TOKEN_EXPIRE_MINUTES`）
- **存储**：前端 `localStorage.token`
- **保护**：所有非 `/api/auth/*` 和 `/api/health` 的路由需要 Authorization Header

---

## 七、前端路由

| 路径 | 组件 | 说明 |
|------|------|------|
| `/login` | Login | 登录页（无需认证） |
| `/` | Portal | 首页，双卡片导航 |
| `/skills` | Dashboard | 技能列表 |
| `/skill/:skillId` | SkillBranches | 技能分支 |
| `/skill/:skillId/branch/:branchId` | BranchSandbox | 沙盒编辑 |
| `/admin` | AdminPage | 用户管理（Admin） |
| `/translate` | HomePage | AI 翻译 |
| `/translate/jobs/:jobId` | JobDetailPage | 翻译任务详情 |

---

## 八、启动方式

### 开发模式

```bash
# 后端（端口 48010）
cd G:/github/testai_community/backend
python -c "import uvicorn; from app.main_merged import app; uvicorn.run(app, host='0.0.0.0', port=48010)"

# 前端（端口 3003，proxy 到 48010）
cd G:/github/testai_community/frontend
npm run dev
```

### 账号

- 用户名：`admin`
- 密码：`admin123`
- 角色：Admin

---

## 九、配置文件

| 文件 | 说明 |
|------|------|
| `backend/app/translate/config/ai.local.json` | MiniMax API Key |
| `backend/app/translate/config/ai.yaml` | 同上 YAML 版本 |
| `backend/app/core/config.py` | DATABASE_URL 等 |
| `frontend/vite.config.ts` | Vite 配置，含 proxy |
| `frontend/src/shared/styles/tokens.ts` | Ant Design 主题变量 |

---

## 十、命名对照表

| 模块 | 后端目录 | 前端目录 | API 前缀 |
|------|----------|----------|----------|
| 认证 | `app/auth/` | `src/auth/` | `/api/auth/*`, `/api/users/*` |
| 技能管理 | `app/skill_hub/` | `src/skill_hub/` | `/api/skills/*`, `/api/llm/*`, `/api/v1/integration/*` |
| AI 翻译 | `app/translate/` | `src/translate/` | `/translate/api/*` |

---

## 十一、已知限制

1. **Windows 僵尸进程**：部分端口（如 8000、48010）的旧进程可能无法通过 `taskkill` 杀死，需重启 Windows
2. **translate 独立运行**：translate 模块在 `app/translate/` 下保留了完整的 MiniMax 配置，可独立运行
3. **SQLite**：生产环境建议替换为 PostgreSQL，修改 `core/config.py` 中的 `DATABASE_URL` 即可
