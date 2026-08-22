"""FastAPI 应用：REST API + 静态页托管。

对外接口：
- create_app() -> FastAPI
"""

from pathlib import Path
import os
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from apscheduler.triggers.cron import CronTrigger

import db
import tasks as task_repo
from actions import execute_task

STATIC_DIR = Path(__file__).parent / "frontend" / "dist"


def _validate_expr(expr: str) -> None:
    """校验 cron 表达式（5 或 6 段），抛 ValueError 表示不合法。"""
    parts = expr.split()
    if len(parts) == 5:
        CronTrigger.from_crontab(expr)
    elif len(parts) == 6:
        second, minute, hour, day, month, dow = parts
        CronTrigger(second=second, minute=minute, hour=hour, day=day, month=month, day_of_week=dow)
    else:
        raise ValueError(f"段数 {len(parts)} 不支持（需 5 或 6）")


class RegisterRequest(BaseModel):
    name: str
    expr: str | None = None
    timeout: int | None = None
    display_name: str | None = None


class UpdateRequest(BaseModel):
    enabled: bool | None = None
    expr: str | None = None
    timeout: int | None = None
    display_name: str | None = None


class SchedulerControl:
    """调度器控制句柄，由 main 启动时注入。"""

    def __init__(self):
        self.scheduler = None


scheduler_control = SchedulerControl()


def create_app():
    app = FastAPI(title="Task Manager")

    @app.post("/api/tasks", status_code=201)
    def register_task(req: RegisterRequest):
        """注册任务：校验 tasks/ 目录，登记到 DB，调度器热更新生效。

        expr/timeout 不传时回退到 config.json 默认值。
        """
        try:
            spec = task_repo.validate_task(req.name)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        existing = [t for t in db.list_tasks() if t["name"] == req.name]
        if existing:
            raise HTTPException(409, f"任务 {req.name} 已注册")

        expr = req.expr or spec["expr"]
        try:
            _validate_expr(expr)
        except ValueError as exc:
            raise HTTPException(400, f"cron 表达式不合法: {exc}")

        display_name = req.display_name or spec.get("display_name") or req.name

        task_id = db.add_task(
            name=req.name,
            display_name=display_name,
            trigger_type="cron",
            trigger_params={"expr": expr},
            action_type="run.py",
            action_params={},
            enabled=True,
        )
        return {"id": task_id, "name": req.name, "display_name": display_name}

    @app.get("/api/tasks")
    def list_tasks():
        result = []
        for t in db.list_tasks():
            result.append(_task_view(t))
        return {"tasks": result}

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: int):
        t = db.get_task(task_id)
        if not t:
            raise HTTPException(404, "任务不存在")
        return _task_view(t)

    @app.put("/api/tasks/{task_id}")
    def update_task(task_id: int, req: UpdateRequest):
        t = db.get_task(task_id)
        if not t:
            raise HTTPException(404, "任务不存在")
        fields = {}
        if req.enabled is not None:
            fields["enabled"] = req.enabled
        if req.expr is not None:
            try:
                _validate_expr(req.expr)
            except ValueError as exc:
                raise HTTPException(400, f"cron 表达式不合法: {exc}")
            fields["trigger_type"] = "cron"
            fields["trigger_params"] = {"expr": req.expr}
        if req.display_name is not None:
            fields["display_name"] = req.display_name.strip()
        if req.timeout is not None:
            fields["timeout"] = req.timeout
        db.update_task(task_id, fields)
        return _task_view(db.get_task(task_id))

    @app.delete("/api/tasks/{task_id}", status_code=204)
    def delete_task(task_id: int):
        if not db.delete_task(task_id):
            raise HTTPException(404, "任务不存在")
        return None

    @app.post("/api/tasks/{task_id}/pause")
    def pause_task(task_id: int):
        return _set_enabled(task_id, False)

    @app.post("/api/tasks/{task_id}/resume")
    def resume_task(task_id: int):
        return _set_enabled(task_id, True)

    @app.post("/api/tasks/{task_id}/run")
    def run_once(task_id: int):
        """立即触发一次任务（不依赖周期）。"""
        t = db.get_task(task_id)
        if not t:
            raise HTTPException(404, "任务不存在")
        threading.Thread(target=execute_task, args=(t,), daemon=True).start()
        return {"scheduled": True, "task_id": task_id}

    @app.get("/api/runs")
    def list_runs(task_id: int | None = None, limit: int = 20, offset: int = 0):
        total = db.count_runs(task_id=task_id)
        runs = db.list_runs(task_id=task_id, limit=limit, offset=offset)
        return {"runs": runs, "total": total, "limit": limit, "offset": offset}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: int):
        run = db.get_run(run_id)
        if not run:
            raise HTTPException(404, "运行记录不存在")
        run["events"] = db.list_run_events(run_id)
        return run

    @app.get("/api/available")
    def available_tasks():
        return {"tasks": task_repo.scan_available_tasks()}

    @app.get("/api/platform")
    def platform_info():
        return {
            "name": os.environ.get("PLATFORM_NAME", "定时任务管理平台"),
            "version": "1.0.0",
        }

    @app.get("/api/available/{name}/config")
    def available_task_config(name: str):
        """读取任务目录 config.json 的原始配置，供前端预填。"""
        cfg = task_repo.load_task_config(name)
        if not cfg:
            raise HTTPException(404, "任务配置不存在")
        return {"name": name, "config": cfg}

    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")

    return app


def _set_enabled(task_id, enabled):
    if not db.update_task(task_id, {"enabled": enabled}):
        raise HTTPException(404, "任务不存在")
    return {"id": task_id, "enabled": enabled}


def _task_view(t):
    """组装任务视图：补充 trigger 原始结构和下次运行信息。

    webhook_url 为有效推送地址（config.json webhook.url > env PLATFORM_WEBHOOK_URL），
    仅展示用，编辑请改任务目录 config.json。
    """
    scheduler = scheduler_control.scheduler
    job = scheduler.get_job(str(t["id"])) if scheduler else None
    cfg = task_repo.load_task_config(t["name"])
    wh = cfg.get("webhook") or {}
    webhook_url = str(wh.get("url") or os.environ.get("PLATFORM_WEBHOOK_URL") or "").strip()
    return {
        "id": t["id"],
        "name": t["name"],
        "display_name": t.get("display_name") or t["name"],
        "expr": t["trigger_params"].get("expr", ""),
        "enabled": t["enabled"],
        "webhook_url": webhook_url,
        "next_run": job.next_run_time.isoformat() if (job and job.next_run_time) else None,
    }
