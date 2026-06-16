"""
知识库文档异步处理 Worker。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from app.ai_service.document import process_document_to_chunks
from app.ai_service.rag import delete_document_chunks, embed_texts, upsert_chunks
from app.platform.database import SessionLocal

from .config import DOCUMENT_PROCESS_TIMEOUT_SEC, MAX_CONCURRENT_JOBS, QUEUE_TICK_SEC
from .models import KnowledgeDocument

log = logging.getLogger("app.knowledge_base.worker")

_dispatcher_task: asyncio.Task | None = None
_running_count = 0


async def start_background_tasks() -> None:
    """启动文档处理调度循环。"""
    global _dispatcher_task
    _dispatcher_task = asyncio.create_task(_dispatcher_loop())
    log.info("knowledge_base worker started")


async def stop_background_tasks() -> None:
    """停止调度循环。"""
    global _dispatcher_task
    if _dispatcher_task:
        _dispatcher_task.cancel()
        _dispatcher_task = None


def dispatch_queued() -> None:
    """尝试从 DB 拉取 queued 文档并处理（由上传接口触发）。"""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_try_dispatch())
    except RuntimeError:
        pass


async def _dispatcher_loop() -> None:
    while True:
        await asyncio.sleep(QUEUE_TICK_SEC)
        await _try_dispatch()


async def _try_dispatch() -> None:
    global _running_count
    while _running_count < MAX_CONCURRENT_JOBS:
        doc_id = _pick_next_queued_document()
        if not doc_id:
            break
        _running_count += 1
        asyncio.create_task(_run_document_job(doc_id))


def _pick_next_queued_document() -> str | None:
    db = SessionLocal()
    try:
        row = (
            db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.status == "queued")
            .order_by(KnowledgeDocument.created_at.asc())
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


async def _run_document_job(doc_id: str) -> None:
    global _running_count
    try:
        await asyncio.wait_for(_process_document(doc_id), timeout=DOCUMENT_PROCESS_TIMEOUT_SEC)
    except Exception:
        log.exception("文档处理失败 doc_id=%s", doc_id)
    finally:
        _running_count -= 1
        await _try_dispatch()


async def _process_document(doc_id: str) -> None:
    """完整处理单文档：解析 → 分块 → 向量化 → 入库。"""
    from pathlib import Path

    db = SessionLocal()
    try:
        doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
        if not doc:
            return

        file_path = Path(doc.original_path)
        try:
            result, chunks = await process_document_to_chunks(file_path)
        except Exception as exc:
            doc.status = "failed"
            doc.error = str(exc)
            doc.updated_at = datetime.utcnow()
            db.commit()
            return

        delete_document_chunks(doc.kb_id, doc.id)
        if not chunks:
            doc.status = "failed"
            doc.error = "未生成可向量化的文本块"
            doc.updated_at = datetime.utcnow()
            db.commit()
            return

        texts = [c["text"] for c in chunks]
        embeddings = await embed_texts(texts)
        chunk_ids: list[str] = []
        metadatas: list[dict] = []
        for chunk in chunks:
            chunk_ids.append(f"{doc.id}_{chunk['id']}")
            meta = dict(chunk.get("metadata") or {})
            meta["doc_id"] = doc.id
            meta["filename"] = doc.filename
            meta["kb_id"] = doc.kb_id
            metadatas.append(meta)

        upsert_chunks(
            doc.kb_id,
            chunk_ids=chunk_ids,
            texts=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        doc.status = "ready"
        doc.error = None
        doc.chunk_count = len(chunks)
        doc.asset_count = result.asset_count
        doc.updated_at = datetime.utcnow()
        db.commit()
        log.info("文档处理完成 doc_id=%s chunks=%s", doc.id, len(chunks))
    finally:
        db.close()
