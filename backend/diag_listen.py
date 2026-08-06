"""
最小监听诊断：不加载业务代码，只验证本机 uvicorn 能否 HTTP 回包。

  python diag_listen.py
另开窗口：
  curl.exe --max-time 5 http://127.0.0.1:48012/ping
"""

from __future__ import annotations

from fastapi import FastAPI
import uvicorn

app = FastAPI()


@app.get("/ping")
def ping():
    return {"ok": True, "diag": "minimal"}


if __name__ == "__main__":
    print("[diag] listening http://0.0.0.0:48012/ping", flush=True)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=48012,
        loop="asyncio",
        http="h11",
        log_level="info",
        access_log=True,
    )
