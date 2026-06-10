"""任务管理：Job 数据类、FIFO 队列、辅助函数。

dispatcher 和 janitor 协程在 app.py 中实现（避免循环导入）。
元数据持久化到数据库（translate_jobs 表），数据文件保留在磁盘。
"""

from __future__ import annotations

import asyncio
import collections
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from app.core.database import SessionLocal
from app.translate.models_db import TranslateJob as TranslateJobRow

# ==================== 常量 ====================

MAX_CONCURRENT_JOBS = 1
JOB_TIMEOUT_SEC = 600
EVENT_QUEUE_MAX = 1024
MEMORY_TTL_HOURS = 24
CLEANUP_INTERVAL_SEC = 300
QUEUE_TICK_SEC = 1


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ==================== Job ====================


@dataclass
class Job:
    id: str
    status: JobStatus
    upload_path: Path
    created_at: datetime
    updated_at: datetime
    message: str = ""
    error: Optional[str] = None
    current_phase: str = ""
    current_step: int = 0
    total_steps: int = 0
    cancelled: bool = False
    result_zip_path: Optional[Path] = None
    task: Optional[asyncio.Task] = None
    event_queue: asyncio.Queue = field(
        default_factory=lambda: asyncio.Queue(maxsize=EVENT_QUEUE_MAX)
    )
    last_event: Optional[dict] = None


# ==================== 全局状态 ====================

jobs: dict[str, Job] = {}
job_queue: collections.deque[str] = collections.deque()
running_jobs: dict[str, Job] = {}


# ==================== 数据库持久化 ====================


def persist_job(job: Job) -> None:
    """将 Job 元数据同步写入数据库。"""
    db = SessionLocal()
    try:
        row = db.query(TranslateJobRow).filter(TranslateJobRow.id == job.id).first()
        if row:
            row.status = job.status.value
            row.upload_path = str(job.upload_path)
            row.result_zip_path = str(job.result_zip_path) if job.result_zip_path else None
            row.current_phase = job.current_phase
            row.current_step = job.current_step
            row.total_steps = job.total_steps
            row.message = job.message
            row.error = job.error
            row.updated_at = datetime.now()
        else:
            row = TranslateJobRow(
                id=job.id,
                status=job.status.value,
                upload_path=str(job.upload_path),
                result_zip_path=str(job.result_zip_path) if job.result_zip_path else None,
                current_phase=job.current_phase,
                current_step=job.current_step,
                total_steps=job.total_steps,
                message=job.message,
                error=job.error,
            )
            db.add(row)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def load_all_jobs_from_db() -> dict[str, Job]:
    """从数据库加载所有 Job 元数据到内存。"""
    db = SessionLocal()
    try:
        rows = db.query(TranslateJobRow).order_by(TranslateJobRow.created_at.desc()).all()
        result = {}
        for row in rows:
            job = Job(
                id=row.id,
                status=JobStatus(row.status),
                upload_path=Path(row.upload_path),
                created_at=row.created_at,
                updated_at=row.updated_at,
                message=row.message or "",
                error=row.error,
                current_phase=row.current_phase or "",
                current_step=row.current_step or 0,
                total_steps=row.total_steps or 0,
                result_zip_path=Path(row.result_zip_path) if row.result_zip_path else None,
            )
            result[row.id] = job
        return result
    finally:
        db.close()


# ==================== 辅助函数 ====================


def create_job(upload_path: Path) -> Job:
    """创建新 job，加入 FIFO 队列，并持久化到数据库。"""
    jid = uuid.uuid4().hex
    now = datetime.now()
    job = Job(
        id=jid,
        status=JobStatus.QUEUED,
        upload_path=upload_path,
        created_at=now,
        updated_at=now,
    )
    jobs[jid] = job
    job_queue.append(jid)
    persist_job(job)
    return job


def get_queue_position(job_id: str) -> tuple[int, int]:
    """返回 (前面还有几个任务, 队列总任务数)。"""
    arr = list(job_queue)
    total = len(arr)
    if job_id not in arr:
        return (0, total)
    return (arr.index(job_id), total)


def cancel(job: Job) -> None:
    """设置取消标志并尝试取消 asyncio task。"""
    job.cancelled = True
    if job.task and not job.task.done():
        job.task.cancel()


def _push_event(job: Job, event: dict) -> None:
    """向 job 的 SSE 事件队列推送（非阻塞）；同时更新 last_event。"""
    job.last_event = event
    try:
        job.event_queue.put_nowait(event)
    except asyncio.QueueFull:
        pass


def job_to_view(job: Job) -> dict:
    """序列化 Job 为 API 返回视图。"""
    ahead, qtotal = (
        get_queue_position(job.id) if job.status == JobStatus.QUEUED else (0, 0)
    )
    return {
        "job_id": job.id,
        "status": job.status.value,
        "created_at": job.created_at.isoformat(timespec="seconds"),
        "updated_at": job.updated_at.isoformat(timespec="seconds"),
        "current_phase": job.current_phase,
        "current_step": job.current_step,
        "total_steps": job.total_steps,
        "message": job.message,
        "queue_ahead": ahead,
        "queue_total": qtotal,
        "error": job.error,
    }
