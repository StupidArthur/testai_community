"""
生产环境后端启动入口
用法：python run.py
入口模块：app.platform.factory:app
"""

import uvicorn

from app.platform.config import BACKEND_PORT

if __name__ == "__main__":
    uvicorn.run(
        "app.platform.factory:app",
        host="0.0.0.0",
        port=BACKEND_PORT,
        log_level="info",
        access_log=True,
    )
