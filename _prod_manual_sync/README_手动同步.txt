# 生产手动同步包（GitHub 不可用时）

生成时间: 2026-08-10 10:03:26
来源: 开发机本地 commit（未 push）+ 新打的 frontend/dist

## 生产机操作

1. 停服
   cd D:\deploy\testai_community_prod\backend\scripts
   .\stop_prod_backend.cmd

2. 把本包内文件按相对路径覆盖到
   D:\deploy\testai_community_prod\
   （可用资源管理器复制，或下方 robocopy）

3. 前端必须覆盖整个 frontend\dist

4. 启服
   .\install_prod_backend.cmd
   成功标准: [6/6] PASS

5. 验收
   curl.exe --max-time 5 http://127.0.0.1:48011/api/health
   浏览器 Ctrl+F5: http://10.30.144.64:48011

## 禁止覆盖（生产机上千万别动）

- .env
- backend\database_prod.sqlite（或实际库文件）
- backend\.venv\
- backend\scripts\logs\

## robocopy 示例（在生产机，包解压到 C:\temp\prod_sync 后）

robocopy C:\temp\prod_sync\backend D:\deploy\testai_community_prod\backend /E /XD .venv __pycache__ scripts\logs
robocopy C:\temp\prod_sync\frontend\dist D:\deploy\testai_community_prod\frontend\dist /E
robocopy C:\temp\prod_sync\doc D:\deploy\testai_community_prod\doc /E
robocopy C:\temp\prod_sync\frontend\src D:\deploy\testai_community_prod\frontend\src /E
