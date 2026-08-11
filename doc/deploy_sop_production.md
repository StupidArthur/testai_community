# 生产环境更新 SOP（Windows）

> 适用：`D:\deploy\testai_community_prod` · 端口 **48011** · 访问 `http://10.30.144.64:48011`  
> 更新日期：2026-08-05  
> 原则：有人在用时选低峰；**停服 → 更新 → 启服验收**；保护 `.env` 与业务库。

---

## 0. 更新前确认

- [ ] 开发机功能已自测通过  
- [ ] 代码已 `git commit` + `git push`（或明确用拷贝同步）  
- [ ] 若有前端改动：开发机已 `npm run build`，`frontend/dist` 已准备好  
- [ ] 已知本次是否改了 `requirements.txt`、企微脚本  
- [ ] 通知同事：将短暂停服约 **1～3 分钟**

**Git 拉不下来时**：用拷贝覆盖代码；仍遵守下文「禁止覆盖」清单。

---

## 1. 开发机操作

```powershell
cd D:\代码\testai_community

# 1.1 提交并推送
git status
git add <本次相关文件>
git commit -m "简要说明本次更新原因"
git push

# 1.2 有前端改动则打包（frontend/dist 不在 Git 中）
cd frontend
npm run build
```

将 `frontend\dist` 准备拷到生产（共享盘 / 远程桌面复制均可）。

---

## 2. 生产机：停止服务

```powershell
cd D:\deploy\testai_community_prod\backend\scripts
.\stop_prod_backend.cmd

# 确认已停（应失败/连不上）
curl.exe --max-time 3 http://127.0.0.1:48011/api/health
```

---

## 3. 生产机：更新代码

```powershell
cd D:\deploy\testai_community_prod
git status
git pull
```

### 禁止覆盖（务必保留）

| 路径 | 说明 |
|------|------|
| `.env` | 生产密钥、端口、webhook |
| `backend\database_prod.sqlite`（或实际库文件） | 业务数据 |
| `backend\.venv\` | 本机虚拟环境（不要用开发机 venv 覆盖） |
| `backend\scripts\logs\` | 可选保留 |

### 覆盖前端产物

把开发机 `frontend\dist\` **整目录**覆盖到：

`D:\deploy\testai_community_prod\frontend\dist\`

### 依赖变更时（仅当 requirements.txt 有变）

```powershell
cd D:\deploy\testai_community_prod\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 检查 `.env` 关键项

```env
ENV=production
BACKEND_PORT=48011
DINGTALK_PUSH_ENABLED=false
DINGTALK_KEYWORD=msg
DINGTALK_WEBHOOK_URL=（钉钉机器人 https://oapi.dingtalk.com/robot/send?access_token=...）
DATABASE_URL=sqlite:///./database_prod.sqlite
```

---

## 4. 生产机：启动服务

```powershell
cd D:\deploy\testai_community_prod\backend\scripts
.\install_prod_backend.cmd
```

**成功标准：** 屏幕出现 **`[6/6] PASS`**，且 health 返回 `ok`。

失败：看 `backend\scripts\logs\backend_keepalive.log`，修好后再跑 `.\install_prod_backend.cmd`。

---

## 5. 验收清单

```powershell
curl.exe --max-time 5 http://127.0.0.1:48011/api/health
```

- [ ] 返回 `{"status":"ok","service":"testai-community"}`  
- [ ] 本机浏览器打开 `http://127.0.0.1:48011`  
- [ ] 局域网打开 `http://10.30.144.64:48011`（Ctrl+F5 强刷）  
- [ ] 能登录；项目管理/关键页点开正常  
- [ ] **关掉所有 PowerShell/CMD 后**网站仍可访问（后台任务在跑）  
- [ ] 不应再出现「关黑窗口网站就挂」（任务应为隐藏启动）

---

## 6. 企微推送（仅当本次改了推送脚本时）

```powershell
cd D:\deploy\testai_community_prod\backend\scripts
.\install_wecom_tasks.cmd
```

- 日报正式：**每天 17:12** 一次 + **20:00～20:04**（幂等只发 1 条）  
- 周报正式：每 **1 分钟**检查，**周结束 + 15 分钟**发 1 条（默认周三 17:00 结束 → 17:15；周报幂等默认关可同周重发）  
- **开发机**上的 `TestAI-WeCom-*` 保持禁用，防双发  

未改企微相关文件可跳过本节。

---

## 7. 回滚（更新后异常）

1. `.\stop_prod_backend.cmd`  
2. `git checkout <上一版本标签或 commit>`（或还原拷贝的上一包代码）  
3. 还原上一份 `frontend\dist`（若有备份）  
4. `.\install_prod_backend.cmd` 到 PASS  
5. 再跑第 5 节验收  

`.env` 与数据库一般不回滚，除非本次误改。

---

## 8. 日常口诀

```
开发：commit + push +（前端）npm run build
生产：stop → pull → 覆盖 dist →（可选）pip → install_prod_backend → 验收
保护：.env + 业务库 + .venv
记住：只 git pull 不够，前端必须单独覆盖 dist
```

---

## 9. 常用命令速查

| 目的 | 命令 |
|------|------|
| 停站 | `.\stop_prod_backend.cmd` |
| 启站/重装任务 | `.\install_prod_backend.cmd` |
| 看健康 | `curl.exe --max-time 5 http://127.0.0.1:48011/api/health` |
| 看任务 | `schtasks /Query /TN TestAI-Backend /FO LIST` |
| 后端日志 | `backend\scripts\logs\backend_keepalive.log` |
| 装企微任务 | `.\install_wecom_tasks.cmd` |
| 强制测周报 | `.\wecom_push_test_weekly.cmd` |
| 强制测日报 | `.\wecom_push_test_daily.cmd` |

---

## 10. 与「开发机」分工

| 机器 | 职责 |
|------|------|
| 开发机 | 写代码、自测、commit/push、build dist；**禁用**企微计划任务 |
| 生产机 | git pull、覆盖 dist、跑计划任务扛网站与钉钉推送；`DINGTALK_PUSH_ENABLED=false` |
