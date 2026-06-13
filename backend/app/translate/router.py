"""translate HTTP 路由。"""

from __future__ import annotations

import io
import logging
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.auth.service import (
    get_current_user,
    get_current_user_by_ticket,
    create_ticket,
    RequireRole,
)
from app.auth.models import User, UserRole
from app.platform.database import SessionLocal

from . import jobs as J
from . import UPLOAD_DIR
from .worker import dispatch_queued
from .schemas import JobView, CreateJobResponse
from .sse import event_gen
from .zip_utils import MAX_UPLOAD_SIZE_MB, safe_extract
from .prompts.loader import load_prompt_md

log = logging.getLogger("app.translate")


def _ts(iso: str) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat(iso).timestamp()
    except Exception:
        return 0.0

router = APIRouter(prefix="/api/translate", tags=["translate"])


def _load_job_from_db(job_id: str) -> J.Job:
    from app.translate.models_db import TranslateJob as TranslateJobRow
    db = SessionLocal()
    try:
        row = db.query(TranslateJobRow).filter(TranslateJobRow.id == job_id).first()
        if not row:
            raise HTTPException(404, "job 不存在")
        job = J.Job(
            id=row.id,
            status=J.JobStatus(row.status),
            upload_path=Path(row.upload_path),
            created_at=row.created_at,
            updated_at=row.updated_at,
            name=row.name or "",
            username=row.username or "",
            message=row.message or "",
            error=row.error,
            current_phase=row.current_phase or "",
            current_step=row.current_step or 0,
            total_steps=row.total_steps or 0,
            result_zip_path=Path(row.result_zip_path) if row.result_zip_path else None,
        )
        J.jobs[job_id] = job
        return job
    finally:
        db.close()


def _get_job(job_id: str) -> J.Job:
    job = J.jobs.get(job_id)
    if not job:
        job = _load_job_from_db(job_id)
    return job


async def _create_job_from_upload(
    request: Request,
    file: UploadFile,
    name: str,
    user: User,
) -> CreateJobResponse:
    """解压上传 ZIP 并创建翻译任务。"""
    cl = request.headers.get("content-length")
    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if cl and int(cl) > max_bytes:
        raise HTTPException(413, f"上传文件超过 {MAX_UPLOAD_SIZE_MB}MB")

    job_tmp_id = f"upload-{datetime.now().timestamp():.0f}"
    raw_zip = UPLOAD_DIR / f"{job_tmp_id}.zip"
    written = 0
    with raw_zip.open("wb") as fh:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                raw_zip.unlink(missing_ok=True)
                raise HTTPException(413, f"上传文件超过 {MAX_UPLOAD_SIZE_MB}MB")
            fh.write(chunk)

    extract_dir = UPLOAD_DIR / job_tmp_id
    try:
        run_dir = safe_extract(raw_zip, extract_dir)
    except ValueError as e:
        shutil.rmtree(extract_dir, ignore_errors=True)
        raw_zip.unlink(missing_ok=True)
        raise HTTPException(400, str(e))
    finally:
        raw_zip.unlink(missing_ok=True)

    job = J.create_job(upload_path=run_dir, name=name, username=user.username)
    dispatch_queued()
    ahead, total = J.get_queue_position(job.id)
    return CreateJobResponse(
        job_id=job.id,
        status=job.status.value,
        queue_ahead=ahead,
        queue_total=total,
        total_steps=job.total_steps,
        current_step=job.current_step,
    )


@router.post("/ticket")
async def issue_ticket(user: User = Depends(get_current_user)) -> dict:
    return create_ticket(user)


PROMPT_FILES = [
    ("snapshots-2-steps-skill.md", "snapshots-2-steps-skill.md"),
    ("steps-2-cases-skill.md", "steps-2-cases-skill.md"),
    ("case-4-agents-skill.md", "case-4-agents-skill.md"),
]


@router.get("/prompts")
async def download_prompts(user: User = Depends(get_current_user_by_ticket)):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path, arc_name in PROMPT_FILES:
            content = load_prompt_md(rel_path)
            zf.writestr(arc_name, content)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=prompts.zip"},
    )


@router.post("/jobs", response_model=CreateJobResponse)
async def create_job(
    request: Request,
    file: UploadFile,
    name: str = Form(""),
    user: User = Depends(get_current_user),
) -> CreateJobResponse:
    """multipart 上传 ZIP 并创建翻译任务。"""
    return await _create_job_from_upload(request, file, name, user)


@router.get("/jobs", response_model=list[JobView])
async def list_jobs(user: User = Depends(get_current_user)) -> list[JobView]:
    all_from_db = J.load_all_jobs_from_db()
    for jid, job in all_from_db.items():
        if jid not in J.jobs:
            J.jobs[jid] = job
    out = [J.job_to_view(j) for j in J.jobs.values()]
    STATUS_ORDER = {"running": 0, "queued": 1, "completed": 2, "failed": 3, "cancelled": 4}
    def _sort_key(d):
        p = STATUS_ORDER.get(d.status, 9)
        ts = _ts(d.created_at)
        return (p, ts) if d.status == 'queued' else (p, -ts)
    out.sort(key=_sort_key)
    return out


@router.get("/jobs/{job_id}", response_model=JobView)
async def get_job(
    job_id: str,
    user: User = Depends(get_current_user),
) -> JobView:
    job = _get_job(job_id)
    return J.job_to_view(job)


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    job = _get_job(job_id)
    is_admin = user.role == UserRole.Admin
    if not is_admin and job.username != user.username:
        raise HTTPException(403, "无权取消他人任务")
    if job.status not in (J.JobStatus.QUEUED, J.JobStatus.RUNNING):
        raise HTTPException(400, "任务不在可取消状态")
    J.cancel(job)
    job.status = J.JobStatus.CANCELLED
    job.updated_at = datetime.now()
    J.persist_job(job)
    J._push_event(
        job, {"type": "done", "status": job.status.value, "error": job.error}
    )
    return {"status": "cancelled"}


@router.delete("/jobs/{job_id}/record")
async def delete_job_record(
    job_id: str,
    user: User = Depends(RequireRole(["Admin"])),
) -> dict:
    from app.translate.models_db import TranslateJob as TranslateJobRow
    db = SessionLocal()
    try:
        row = db.query(TranslateJobRow).filter(TranslateJobRow.id == job_id).first()
        if not row:
            raise HTTPException(404, "任务不存在")
        if row.status in (J.JobStatus.QUEUED.value, J.JobStatus.RUNNING.value):
            raise HTTPException(400, "运行中的任务不能删除")
        db.delete(row)
        db.commit()
        J.jobs.pop(job_id, None)
        J.running_jobs.pop(job_id, None)
        return {"message": "已删除"}
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(500, "删除失败")
    finally:
        db.close()


@router.get("/jobs/{job_id}/stream")
async def stream(
    job_id: str,
    request: Request,
    user: User = Depends(get_current_user_by_ticket),
) -> StreamingResponse:
    job = _get_job(job_id)
    return StreamingResponse(
        event_gen(job, request), media_type="text/event-stream"
    )


@router.get("/jobs/{job_id}/download")
async def download(
    job_id: str,
    user: User = Depends(get_current_user_by_ticket),
) -> FileResponse:
    job = _get_job(job_id)
    if job.status == J.JobStatus.CANCELLED:
        raise HTTPException(410, "任务已取消")
    if job.status != J.JobStatus.COMPLETED or not job.result_zip_path:
        raise HTTPException(409, "任务尚未完成")
    return FileResponse(
        job.result_zip_path,
        filename=f"translate-result-{job_id}.zip",
        media_type="application/zip",
    )
