"""
生产环境后端启动入口
用法：python run.py
"""

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "app.main_merged:app",
        host="0.0.0.0",
        port=48010,
        workers=4,                 # 生产环境用多 worker
        log_level="info",
        access_log=True,
    )
