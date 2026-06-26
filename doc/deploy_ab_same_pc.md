# 同机 A/B 部署指南（开发 → 生产）

> 文档版本：2026-06-13  
> A = 开发目录，B = 生产目录，均在**同一台电脑**上。

---

## 1. 模型说明

```
G:\deploy\
├── testai_community\           ← A 开发（日常改代码、跑测试）
└── testai_community_prod\      ← B 生产（稳定对外使用）
```

| 项目 | A 开发 | B 生产 | 代码更新时 |
|------|--------|--------|------------|
| Python / TS 源码 | ✅ | ✅ 被 A 覆盖 | **覆盖** |
| `frontend/dist` | 可选 | ✅ 在 B 上 build | **在 B 重建** |
| `.env` | 开发配置 | 生产配置 | **不覆盖** |
| 数据库 | `database_dev.sqlite` | `database_prod.sqlite` | **不覆盖** |
| Translate 文件 | `app/uploads`、`app/results` | 各自目录 | **不覆盖** |

原则：**只同步代码，不动 B 的数据和 `.env`。**

---

## 2. 首次搭建

### 2.1 A 开发目录（当前仓库）

```powershell
cd G:\deploy\testai_community
copy .env.example .env
# 编辑 .env：ENV=dev，DATABASE_URL=sqlite:///./database_dev.sqlite，端口 48010/3003
```

### 2.2 B 生产目录

```powershell
# 初次：整份复制（之后改用 robocopy 增量同步代码）
xcopy G:\deploy\testai_community G:\deploy\testai_community_prod /E /I /EXCLUDE:exclude_deploy.txt
```

`exclude_deploy.txt` 示例（放在任意路径，内容）：

```text
\.env
database_dev.sqlite
database_prod.sqlite
database_test.sqlite
\app\uploads\
\app\results\
\node_modules\
\.git\
\tests\.data\
```

在 B 目录单独创建 `.env`：

```ini
ENV=production
SECRET_KEY=请填一串足够长的随机字符串
MINIMAX_API_KEY=你的密钥
BACKEND_PORT=48011
DATABASE_URL=sqlite:///./database_prod.sqlite
```

构建并启动 B：

```powershell
cd G:\deploy\testai_community_prod\frontend
npm install
npm run build

cd ..\backend
python run.py
```

浏览器访问：**http://localhost:48011**

**旧版 `.doc` 上传**：B 目录同步代码后，若本机尚未校验过 LibreOffice，在 B 项目根执行一次 `scripts/ensure_libreoffice.ps1`（VC++ 为整机共享，通常 A 已执行过则 B 无需重复）。

---

## 3. 日常发布：A 代码覆盖 B

在 A 开发自测通过后：

```powershell
robocopy G:\deploy\testai_community G:\deploy\testai_community_prod /MIR ^
  /XD node_modules backend\app\uploads backend\app\results .git backend\tests\.data ^
  /XF .env database_dev.sqlite database_prod.sqlite database_test.sqlite

cd G:\deploy\testai_community_prod\frontend
npm install
npm run build

cd ..\backend
# 若 backend 已在运行，先停掉再：
python run.py
```

### 3.1 发布检查清单

- [ ] A 上 `python -m pytest tests/` 通过
- [ ] robocopy **未覆盖** B 的 `.env`、数据库、uploads/results
- [ ] B 上 `npm run build` 成功
- [ ] B 后端重启后 `/api/health` 返回 ok
- [ ] B 浏览器登录、Translate 上传 smoke 测试

### 3.2 不要覆盖 B 的文件

| 路径 | 原因 |
|------|------|
| `.env` | 生产密钥、端口、`SECRET_KEY` 与 A 不同 |
| `backend/database_prod.sqlite` | 生产用户、Skill、任务历史 |
| `backend/app/uploads/` | 生产翻译任务工作目录 |
| `backend/app/results/` | 生产翻译结果 ZIP |

---

## 4. 数据文件位置速查

| 数据 | 默认路径（相对 `backend/`） | 配置项 |
|------|------------------------------|--------|
| 数据库 | `./database_dev.sqlite` / `./database_prod.sqlite` | `DATABASE_URL` |
| 上传/中间产物 | `app/uploads/` | `TRANSLATE_UPLOAD_DIR`（可选） |
| 结果 ZIP | `app/results/` | `TRANSLATE_RESULT_DIR`（可选） |
| Prompt 模板 | `config/prompts/` | 随代码部署 |
| 测试库（仅 pytest） | `database_test.sqlite` | conftest 自动设置 |
| 测试上传目录 | `tests/.data/uploads` | conftest 自动设置 |

Skill / 用户 / Changelog 等**结构化数据**都在数据库里；Translate 另有磁盘文件，且 DB 中 `upload_path` 指向本机路径，**库与盘必须同属一套 B 目录**。

---

## 5. 业务数据从 A 到 B

代码发布**不会**自动迁移 Skill 或用户。可选做法：

1. **在 B 上手工配置**（推荐生产 Skill、用户单独维护）
2. **运行 seed**（仅演示/初始化）：`python scripts/seed_db.py`（在 B 的 backend 目录）
3. **备份恢复**：复制 `database_prod.sqlite` 做 B 的灾备（不是 A→B 常规流程）

Translate 历史任务一般**不**从 A 迁到 B。

---

## 6. 开发与生产同时运行

| 环境 | 后端端口 | 前端 dev 端口 | 访问方式 |
|------|----------|---------------|----------|
| A 开发 | 48010 | 3003 | `npm run dev` → localhost:3003 |
| B 生产 | 48011 | — | `npm run build` + `python run.py` → localhost:48011 |

两套 `.env` 中 `DATABASE_URL`、`SECRET_KEY`、Translate 目录均独立，可同时开着互不影响。

---

## 7. 运行测试（只在 A）

```powershell
cd G:\deploy\testai_community\backend
python -m pytest tests/ -q
```

pytest 自动使用：

- `backend/database_test.sqlite`
- `backend/tests/.data/uploads` 与 `results`

**不会**写入 `database_dev.sqlite` 或 `app/uploads/`（除非你手动改 conftest 或未通过 pytest 跑接口）。

---

## 8. 相关文档

- [用户手册 - 环境配置](./user_manual.md#101-环境配置项目根目录-env)
- [设计文档 - 数据与路径](./design.md)
- [.env.example](../.env.example)

---

*designed by @yuzechao*
