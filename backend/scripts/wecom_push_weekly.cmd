@echo off
REM WeCom weekly push wrapper for Task Scheduler
set TM_PUSH_KIND=weekly
cd /d "D:\代码\testai_community\backend"
"C:\Users\huangjing4\AppData\Local\Python\pythoncore-3.14-64\python.exe" "D:\代码\testai_community\backend\scripts\wecom_scheduled_push.py"
