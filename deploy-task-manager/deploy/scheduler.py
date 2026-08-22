"""调度服务：APScheduler 封装 + 数据库热更新同步。

对外接口：
- start_scheduler(db_path=None) -> BackgroundScheduler
  初始化 DB、启动调度器、同步当前任务并返回句柄。
- run_poll_loop(scheduler)
  轮询 DB 变更热更新，阻塞运行直到退出。
"""

import logging
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import db
from actions import execute_task

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("task_manager")

POLL_INTERVAL = 5
MAX_INSTANCES = 1
COALESCE = True


def build_trigger(task):
    """根据任务 trigger_params.expr 构造 APScheduler CronTrigger。

    支持 5 段（标准）或 6 段（含秒）cron 表达式。
    """
    expr = task["trigger_params"]["expr"]
    parts = expr.split()
    if len(parts) == 5:
        return CronTrigger.from_crontab(expr)
    if len(parts) == 6:
        second, minute, hour, day, month, dow = parts
        return CronTrigger(
            second=second, minute=minute, hour=hour, day=day, month=month, day_of_week=dow,
        )
    raise ValueError(f"cron 表达式段数必须为 5 或 6: {expr}")


def _job_exec(task):
    """任务触发后的执行入口：运行 run.py 并记录历史。"""
    try:
        run_id, status = execute_task(task)
        logger.info("任务 #%s %s 执行结束: %s", task["id"], task["name"], status)
    except Exception as exc:
        logger.error("任务 #%s %s 执行异常: %s", task["id"], task["name"], exc)


def _apply_task(scheduler, task):
    """将单个任务同步到调度器：禁用则移除，启用则按最新参数重建。"""
    job_id = str(task["id"])
    existing = scheduler.get_job(job_id)
    if not task["enabled"]:
        if existing:
            scheduler.remove_job(job_id)
        return
    trigger = build_trigger(task)
    if existing:
        if existing.trigger != trigger:
            existing.reschedule(trigger=trigger)
    else:
        scheduler.add_job(
            _job_exec,
            trigger=trigger,
            id=job_id,
            args=[task],
            replace_existing=True,
            max_instances=MAX_INSTANCES,
            coalesce=COALESCE,
        )


def sync_tasks(scheduler):
    """全量重建式同步：对比 DB 当前任务与调度器已注册任务，做增删改。"""
    tasks = {t["id"]: t for t in db.list_tasks()}
    registered = {j.id for j in scheduler.get_jobs()}

    for task_id in registered - set(tasks.keys()):
        scheduler.remove_job(str(task_id))
    for task in tasks.values():
        _apply_task(scheduler, task)


def start_scheduler(db_path=None):
    """初始化 DB、启动调度器并同步当前任务，返回调度器句柄。"""
    db.init_db(db_path)
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.start()
    sync_tasks(scheduler)
    logger.info("调度器已启动，任务数量: %s", len(scheduler.get_jobs()))
    return scheduler


def run_poll_loop(scheduler):
    """阻塞轮询 DB 变更并热更新，Ctrl+C 退出。"""
    last_sync = db.get_max_updated_at()
    try:
        while True:
            max_updated = db.get_max_updated_at()
            if max_updated > last_sync:
                logger.info("检测到任务变更，重新同步...")
                sync_tasks(scheduler)
                last_sync = max_updated
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        logger.info("收到退出信号，调度器关闭")
    finally:
        scheduler.shutdown(wait=False)
