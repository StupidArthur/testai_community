"""
清洗任务异步 Worker。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path

from app.ai_service.document.loaders import load_document_text_and_images
from app.data_cleaning.align import align_essence_with_kb, default_review_action
from app.data_cleaning.anchor import match_anchors_for_text, pick_anchor_ids
from app.data_cleaning.config import (
    JOB_PROCESS_TIMEOUT_SEC,
    MAX_CONCURRENT_CLEAN_JOBS,
    PARAGRAPH_CONCURRENCY,
    QUEUE_TICK_SEC,
    STALE_PROCESSING_SEC,
)
from app.data_cleaning.extract import extract_paragraph_essence
from app.data_cleaning.ingest import register_clean_source_document
from app.data_cleaning.models import CleanJob, ParagraphUnit
from app.data_cleaning.splitter import SectionSlice, split_plain_text_to_sections
from app.data_cleaning.utils import dumps_json
from app.platform.database import SessionLocal

log = logging.getLogger("app.data_cleaning.worker")

_dispatcher_task: asyncio.Task | None = None
_running = 0
_tick_count = 0


def recover_stale_processing_jobs() -> int:
    """
    将僵死的 processing 任务重置为 uploaded。

    后端重启时内存 Worker 丢失，但库中仍为 processing，会阻塞整队。
    """
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow().timestamp() - STALE_PROCESSING_SEC
        rows = db.query(CleanJob).filter(CleanJob.status == "processing").all()
        recovered = 0
        for job in rows:
            updated_ts = (job.updated_at or job.created_at).timestamp()
            if updated_ts >= cutoff:
                continue
            db.query(ParagraphUnit).filter(ParagraphUnit.job_id == job.id).delete()
            job.status = "uploaded"
            job.error = None
            job.paragraph_count = 0
            job.updated_at = datetime.utcnow()
            recovered += 1
            log.warning("recovered stale clean job %s (%s)", job.id, job.filename)
        if recovered:
            db.commit()
        return recovered
    finally:
        db.close()


async def start_background_tasks() -> None:
    global _dispatcher_task
    n = recover_stale_processing_jobs()
    if n:
        log.info("recovered %s stale clean job(s) on startup", n)
    _dispatcher_task = asyncio.create_task(_dispatcher_loop())
    log.info("data_cleaning worker started")


async def stop_background_tasks() -> None:
    global _dispatcher_task
    if _dispatcher_task:
        _dispatcher_task.cancel()
        try:
            await _dispatcher_task
        except asyncio.CancelledError:
            pass
        _dispatcher_task = None


def dispatch_queued() -> None:
    """触发调度（上传后可调用）。"""
    pass


async def _dispatcher_loop() -> None:
    global _tick_count
    while True:
        try:
            _tick_count += 1
            if _tick_count % 15 == 0:
                recover_stale_processing_jobs()
            if _running < MAX_CONCURRENT_CLEAN_JOBS:
                job_id = _pick_next_job()
                if job_id:
                    asyncio.create_task(_run_job(job_id))
        except Exception as exc:
            log.exception("clean dispatcher error: %s", exc)
        await asyncio.sleep(QUEUE_TICK_SEC)


def _pick_next_job() -> str | None:
    db = SessionLocal()
    try:
        row = (
            db.query(CleanJob)
            .filter(CleanJob.status == "uploaded")
            .order_by(CleanJob.created_at.asc())
            .first()
        )
        if not row:
            return None
        row.status = "processing"
        row.updated_at = datetime.utcnow()
        db.commit()
        return row.id
    finally:
        db.close()


async def _run_job(job_id: str) -> None:
    global _running
    _running += 1
    try:
        await asyncio.wait_for(_process_job(job_id), timeout=JOB_PROCESS_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        _fail_job(job_id, "处理超时")
    except Exception as exc:
        log.exception("clean job failed %s", job_id)
        _fail_job(job_id, str(exc))
    finally:
        _running -= 1


def _fail_job(job_id: str, error: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(CleanJob).filter(CleanJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.error = error[:2000]
            job.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


async def _process_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(CleanJob).filter(CleanJob.id == job_id).first()
        if not job or job.status != "processing":
            return

        path = Path(job.original_path)
        text, _images, load_warnings = load_document_text_and_images(path)
        if load_warnings:
            log.warning("clean job %s load warnings: %s", job.id, load_warnings)
        plain = text or ""
        slices = split_plain_text_to_sections(plain)
        if not slices and plain.strip():
            log.warning("clean job %s: parsed %s chars but no sections after split", job.id, len(plain))

        register_clean_source_document(
            db,
            kb_id=job.kb_id,
            user_id=job.user_id,
            job_id=job.id,
            filename=job.filename,
            original_path=job.original_path,
            file_size=job.file_size or 0,
        )

        job.paragraph_count = len(slices)
        job.updated_at = datetime.utcnow()
        db.commit()

        sem = asyncio.Semaphore(PARAGRAPH_CONCURRENCY)

        async def _process_slice(sl: SectionSlice) -> None:
            async with sem:
                extracted = await extract_paragraph_essence(
                    sl.raw_text,
                    doc_type=job.doc_type,
                    product=job.product or "",
                    version=job.version or "",
                    environment=job.environment or "",
                )
                essence = extracted["essence"]
                db_local = SessionLocal()
                try:
                    candidates = await match_anchors_for_text(
                        db_local, sl.raw_text + "\n" + essence
                    )
                    anchor_ids = pick_anchor_ids(candidates)
                    scope = extracted.get("scope") or {}
                    if job.product:
                        scope.setdefault("product", job.product)
                    if job.version:
                        scope.setdefault("version", job.version)
                    if job.environment:
                        scope.setdefault("environment", job.environment)

                    alignments: list[dict] = []
                    if essence:
                        alignments = await align_essence_with_kb(
                            job.kb_id,
                            essence,
                            anchor_id=anchor_ids[0] if anchor_ids else "",
                            scope=scope,
                        )
                    action = default_review_action(alignments)
                    review_status = "pending"

                    pu = ParagraphUnit(
                        id=uuid.uuid4().hex,
                        job_id=job.id,
                        seq=sl.seq,
                        section_path=sl.section_path,
                        raw_text=sl.raw_text[:12000],
                        essence_markdown=essence,
                        anchor_ids_json=dumps_json(anchor_ids),
                        suggested_anchors_json=dumps_json(candidates),
                        scope_json=dumps_json(scope),
                        alignment_json=dumps_json(alignments),
                        review_status=review_status,
                        review_action=action if action != "pending" else "add",
                    )
                    db_local.add(pu)
                    row = db_local.query(CleanJob).filter(CleanJob.id == job_id).first()
                    if row:
                        row.updated_at = datetime.utcnow()
                    db_local.commit()
                    log.info("clean job %s progress %s/%s", job_id, sl.seq + 1, len(slices))
                finally:
                    db_local.close()

        await asyncio.gather(*[_process_slice(sl) for sl in slices])

        job = db.query(CleanJob).filter(CleanJob.id == job_id).first()
        if not job:
            return
        job.paragraph_count = len(slices)
        job.status = "pending_review"
        job.error = None
        job.updated_at = datetime.utcnow()
        db.commit()
        log.info("clean job ready job=%s paragraphs=%s", job.id, len(slices))
    finally:
        db.close()
