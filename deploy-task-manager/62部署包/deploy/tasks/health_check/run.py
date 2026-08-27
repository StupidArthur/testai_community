import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from task_hooks import main, Callback

import db


STALE_THRESHOLD_SEC = 600


def diagnose():
    """检查调度服务的运行健康度。"""
    now = time.time()
    tasks = db.list_tasks()

    total = len(tasks)
    enabled = sum(1 for t in tasks if t["enabled"])
    disabled = total - enabled

    enabled_tasks = [t for t in tasks if t["enabled"]]

    recent_runs = db.list_runs(limit=50)
    recent_total = len(recent_runs)
    recent_success = sum(1 for r in recent_runs if r["status"] == "success")
    recent_failed = sum(1 for r in recent_runs if r["status"] == "failed")
    recent_running = sum(1 for r in recent_runs if r["status"] == "running")
    failure_rate = round(recent_failed / recent_total * 100, 1) if recent_total else 0.0

    last_run = recent_runs[0] if recent_runs else None
    last_run_age = round(now - last_run["started_at"], 1) if last_run else None

    stuck = [r for r in recent_runs if r["status"] == "running"]

    stale = []
    for t in enabled_tasks:
        task_runs = [r for r in recent_runs if r["task_id"] == t["id"]]
        if not task_runs:
            stale.append({"name": t["name"], "reason": "启用但从未运行"})
        else:
            last = task_runs[0]
            age = now - last["started_at"]
            if last["status"] == "running" and age > STALE_THRESHOLD_SEC:
                stale.append({"name": t["name"], "reason": f"卡住 {int(age)}s"})
            elif age > STALE_THRESHOLD_SEC and last["status"] != "running":
                stale.append({"name": t["name"], "reason": f"已 {int(age)}s 未触发"})

    proc = None
    try:
        import psutil
        p = psutil.Process(os.getpid())
        proc = {
            "rss_mb": round(p.memory_info().rss / 1024 ** 2, 1),
            "threads": p.num_threads(),
        }
    except ImportError:
        proc = None

    return {
        "ts": now,
        "tasks": {
            "total": total,
            "enabled": enabled,
            "disabled": disabled,
        },
        "runs_recent_50": {
            "total": recent_total,
            "success": recent_success,
            "failed": recent_failed,
            "running": recent_running,
            "failure_rate_pct": failure_rate,
        },
        "last_run": {
            "id": last_run["id"] if last_run else None,
            "task_id": last_run["task_id"] if last_run else None,
            "status": last_run["status"] if last_run else None,
            "age_sec": last_run_age,
        },
        "stuck_runs": [{"id": r["id"], "task_id": r["task_id"], "age_sec": round(now - r["started_at"], 1)} for r in stuck],
        "stale_tasks": stale,
        "process": proc,
        "verdict": _verdict(failure_rate, len(stuck), len(stale)),
    }


def _verdict(failure_rate, stuck_count, stale_count):
    if stuck_count > 0:
        return "异常"
    if failure_rate >= 50:
        return "异常"
    if stale_count > 0 or failure_rate >= 20:
        return "警告"
    return "正常"


def run(cb: Callback):
    d = diagnose()
    v = d["verdict"]
    summary = (
        f"[{v}] 任务 {d['tasks']['enabled']}/{d['tasks']['total']} 启用 "
        f"| 近 50 次失败 {d['runs_recent_50']['failed']} ({d['runs_recent_50']['failure_rate_pct']}%) "
        f"| 卡住 {len(d['stuck_runs'])} | 异常任务 {len(d['stale_tasks'])}"
    )
    cb.status(summary)

    if v == "异常":
        cb.error(f"调度服务异常：{summary}")
    elif v == "警告":
        cb.log("warn", f"调度服务需关注：{summary}")
    else:
        cb.log("info", f"调度服务正常：{summary}")

    cb.log(
        "info",
        f"任务统计：启用 {d['tasks']['enabled']} / 停用 {d['tasks']['disabled']} / 总 {d['tasks']['total']}",
    )
    cb.log(
        "info",
        f"近 50 次：成功 {d['runs_recent_50']['success']} 失败 {d['runs_recent_50']['failed']} "
        f"运行中 {d['runs_recent_50']['running']} 失败率 {d['runs_recent_50']['failure_rate_pct']}%",
    )

    if d["last_run"]["id"] is not None:
        cb.log(
            "info",
            f"最近一次：run#{d['last_run']['id']} task#{d['last_run']['task_id']} "
            f"{d['last_run']['status']} {d['last_run']['age_sec']}s 前",
        )
    else:
        cb.log("warn", "尚无任何运行记录")

    for s in d["stuck_runs"]:
        cb.log("error", f"卡住：run#{s['id']} task#{s['task_id']} 已 {s['age_sec']}s")
    for s in d["stale_tasks"]:
        cb.log("warn", f"异常任务：{s['name']} - {s['reason']}")

    if d["process"]:
        cb.log(
            "info",
            f"进程 pid={os.getpid()} RSS={d['process']['rss_mb']}MB 线程={d['process']['threads']}",
        )

    return json.dumps(d, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main(run)