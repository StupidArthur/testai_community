"""Task Manager 入口：启动 FastAPI Web Server + 常驻调度服务。"""

import argparse
import threading
import time
from pathlib import Path

import uvicorn

import db


def load_env():
    """启动时把 .env 文件里的 K=V 灌入 os.environ（不覆盖已有值）。"""
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


import os

load_env()


def main():
    parser = argparse.ArgumentParser(prog="task_manager")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=None)
    parser.add_argument("--no-scheduler", action="store_true", help="仅启动 Web，不启动调度器（调试用）")
    parsed = parser.parse_args()

    db.init_db(parsed.db)

    from app import create_app, scheduler_control
    from scheduler import start_scheduler

    scheduler = None
    if not parsed.no_scheduler:
        scheduler = start_scheduler(parsed.db)
        threading.Thread(target=_poll_loop, args=(scheduler,), daemon=True).start()

    scheduler_control.scheduler = scheduler
    app = create_app()

    platform = os.environ.get("PLATFORM_NAME", "定时任务管理平台")
    print(f"{platform} 已启动: http://{parsed.host}:{parsed.port}")
    uvicorn.run(app, host=parsed.host, port=parsed.port, log_level="warning")


def _poll_loop(scheduler):
    from scheduler import run_poll_loop
    time.sleep(1)
    run_poll_loop(scheduler)


if __name__ == "__main__":
    main()