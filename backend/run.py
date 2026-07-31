"""
后端启动入口
用法：python run.py
入口模块：app.platform.factory:app

开发环境（ENV=dev，默认）开启 reload，改路由后无需手动杀进程。
"""

import os

import uvicorn

from app.platform.config import BACKEND_PORT

# 与 .env 中 ENV 对齐；未设置时按开发处理
_ENV = (os.getenv("ENV") or "dev").strip().lower()
_RELOAD = _ENV in {"dev", "development", "local"}

if __name__ == "__main__":
    uvicorn.run(
        "app.platform.factory:app",
        host="0.0.0.0",
        port=BACKEND_PORT,
        log_level="info",
        access_log=True,
        reload=_RELOAD,
    )
