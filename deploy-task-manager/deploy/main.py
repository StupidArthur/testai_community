"""Task Manager 入口：启动 FastAPI Web Server + 常驻调度服务。"""

import argparse
import os
import sys
import threading
import time
from pathlib import Path

import uvicorn

# --- 路径解析（支持 PyInstaller exe 和 python 脚本两种模式）---
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

# 采集动态任务依赖（httpx/boto3/dotenv），必须在业务 import 之前执行，
# 否则 PyInstaller 打出来的 exe 里没有这些包，alg_monitor 会瞬间 ModuleNotFoundError。
import packaging_deps  # noqa: F401

import db


def load_env():
    """启动时把 .env 文件里的 K=V 灌入 os.environ（不覆盖已有值）。"""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


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


def _write_crash_log(exc_text):
    """崩溃信息写入 task-manager-error.log，让启动失败永远可见。"""
    try:
        with open(BASE_DIR / "task-manager-error.log", "a", encoding="utf-8") as f:
            f.write(f"\n===== CRASH {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
            f.write(exc_text + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    # PyInstaller --noconsole（或被 guardian 以 CREATE_NO_WINDOW 拉起）时
    # sys.stdout / sys.stderr 是 None，print 和 uvicorn 日志配置都会崩溃。
    # 重定向到 task-manager.log，保证日志系统可用且错误可见。
    try:
        _log = open(BASE_DIR / "task-manager.log", "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = _log
        if sys.stderr is None:
            sys.stderr = _log
    except Exception:
        pass

    try:
        main()
    except BaseException:
        # BaseException：uvicorn 端口被占用时以 SystemExit 退出，
        # except Exception 抓不到，必须用 BaseException。
        import traceback
        _write_crash_log(traceback.format_exc())
        raise