"""后台任务管理：dispatcher、janitor、job 执行。"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from . import jobs as J
from .config import PHASE1_BATCH_SIZE, PHASE2_WINDOW_SIZE, PHASE4_WINDOW_SIZE
from .preprocess import preprocess
from .validate import validate_recording
from .workflow import run_workflow
from .result_zip import create_result_zip
from .web_progress import make_callback
from . import UPLOAD_DIR, RESULT_DIR

log = logging.getLogger("app.translate")

executor = ThreadPoolExecutor(max_workers=4)

_dispatcher_task: asyncio.Task | None = None
_janitor_task: asyncio.Task | None = None


async def start_background_tasks() -> None:
    global _dispatcher_task, _janitor_task
    J.recover_on_startup()
    _dispatcher_task = asyncio.create_task(_dispatcher_loop())
    _janitor_task = asyncio.create_task(_janitor_loop())


async def stop_background_tasks() -> None:
    global _dispatcher_task, _janitor_task
    if _dispatcher_task:
        _dispatcher_task.cancel()
        _dispatcher_task = None
    if _janitor_task:
        _janitor_task.cancel()
        _janitor_task = None


async def _dispatcher_loop() -> None:
    while True:
        await asyncio.sleep(J.QUEUE_TICK_SEC)
        dispatch_queued()


def dispatch_queued() -> None:
    while len(J.running_jobs) < J.MAX_CONCURRENT_JOBS and J.job_queue:
        jid = J.job_queue.popleft()
        job = J.jobs.get(jid)
        if not job or job.cancelled:
            continue
        job.status = J.JobStatus.RUNNING
        job.updated_at = datetime.now()
        J.persist_job(job)
        J._push_event(
            job,
            {
                "type": "progress",
                "phase": "preprocess",
                "step": 0,
                "total_steps": 0,
                "message": "任务开始执行...",
            },
        )
        job.task = asyncio.create_task(_execute_job(job))
        J.running_jobs[jid] = job


async def _janitor_loop() -> None:
    while True:
        await asyncio.sleep(J.CLEANUP_INTERVAL_SEC)
        now = datetime.now()
        for jid in list(J.jobs.keys()):
            job = J.jobs.get(jid)
            if not job:
                continue
            if job.status in (
                J.JobStatus.COMPLETED,
                J.JobStatus.FAILED,
                J.JobStatus.CANCELLED,
            ) and (now - job.updated_at).total_seconds() > J.MEMORY_TTL_HOURS * 3600:
                J.jobs.pop(jid, None)
                log.info(f"[janitor] removed job {jid} from memory (files on disk retained)")


async def _execute_job(job: J.Job) -> None:
    try:
        await asyncio.wait_for(_run_pipeline(job), timeout=J.JOB_TIMEOUT_SEC)
        if not job.cancelled:
            job.status = J.JobStatus.COMPLETED
    except asyncio.CancelledError:
        job.status = J.JobStatus.CANCELLED
    except Exception as e:
        log.exception(f"[job {job.id}] failed")
        if not job.cancelled:
            job.status = J.JobStatus.FAILED
            job.error = str(e)
    finally:
        J.running_jobs.pop(job.id, None)
        job.updated_at = datetime.now()
        J.persist_job(job)
        J._push_event(
            job,
            {
                "type": "done",
                "status": job.status.value,
                "step": job.current_step,
                "total_steps": job.total_steps,
                "message": job.message,
                "error": job.error,
            },
        )


async def _run_pipeline(job: J.Job) -> None:
    loop = asyncio.get_running_loop()

    J._push_event(
        job,
        {
            "type": "progress",
            "phase": "preprocess",
            "step": 0,
            "total_steps": 0,
            "message": "校验与预处理中...",
        },
    )
    meta, raw_actions, _fmt = await loop.run_in_executor(
        executor, validate_recording, job.upload_path
    )
    enriched = await loop.run_in_executor(
        executor, lambda: preprocess(job.upload_path, meta, raw_actions, log)
    )

    cb = make_callback(job)
    await run_workflow(
        job.upload_path,
        enriched,
        phase1_batch_size=PHASE1_BATCH_SIZE,
        phase2_window_size=PHASE2_WINDOW_SIZE,
        phase4_window_size=PHASE4_WINDOW_SIZE,
        client=None,
        log_instance=log,
        progress_callback=cb,
    )

    J._push_event(
        job,
        {
            "type": "progress",
            "phase": "finalize",
            "step": job.current_step,
            "total_steps": job.total_steps,
            "message": "打包结果中...",
        },
    )
    out = RESULT_DIR / f"{job.id}.zip"
    create_result_zip(job.upload_path, out)
    job.result_zip_path = out
