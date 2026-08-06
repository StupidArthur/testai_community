"""
生产启动（Windows 专用）：强制 asyncio + h11，关闭 reload。

在 backend 目录、已激活 .venv 后执行：
  python run_prod.py
"""

from __future__ import annotations

import os
import sys

import uvicorn

# 先加载配置（.env）
from app.platform.config import BACKEND_PORT  # noqa: E402


def main() -> None:
    env = (os.getenv("ENV") or "").strip() or "unset"
    port = int(BACKEND_PORT)
    # 绑定本机所有网卡，供局域网 IP 访问
    host = (os.getenv("BIND_HOST") or "0.0.0.0").strip()
    print(f"[run_prod] ENV={env} bind={host}:{port} http=h11 loop=asyncio reload=False", flush=True)
    if env.lower() not in {"production", "prod"}:
        print(
            "[run_prod] 警告: ENV 不是 production，请检查项目根目录 .env",
            file=sys.stderr,
            flush=True,
        )
    uvicorn.run(
        "app.platform.factory:app",
        host=host,
        port=port,
        log_level="info",
        access_log=True,
        reload=False,
        loop="asyncio",
        http="h11",
        timeout_keep_alive=5,
        # Windows 上避免多进程
        workers=1,
    )


if __name__ == "__main__":
    main()
