"""
批准后 KnowledgeUnit 入库与向量写入。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.ai_service.rag import embed_texts, upsert_chunks
from app.data_cleaning.models import KnowledgeUnit, ParagraphUnit
from app.data_cleaning.utils import dumps_json, loads_json
from app.knowledge_base.models import KnowledgeDocument

log = logging.getLogger(__name__)


def supersede_ku(db: Session, old_ku_id: str) -> None:
    """将旧知识单元标记为 superseded，并删除其向量。"""
    if not old_ku_id:
        return
    old = db.query(KnowledgeUnit).filter(KnowledgeUnit.id == old_ku_id).first()
    if not old or old.status == "superseded":
        return
    old.status = "superseded"
    old.updated_at = datetime.utcnow()
    delete_ku_chunks(old.kb_id, old.id)


def delete_ku_chunks(kb_id: str, ku_id: str) -> None:
    try:
        from app.ai_service.rag.store import get_kb_collection

        collection = get_kb_collection(kb_id)
        collection.delete(where={"ku_id": ku_id})
    except Exception as exc:
        log.warning("删除 KU 向量失败 ku=%s: %s", ku_id, exc)


async def ingest_knowledge_unit(
    db: Session,
    ku: KnowledgeUnit,
    *,
    filename: str,
) -> int:
    """将单条 KU 写入 Chroma，返回 chunk 数。"""
    text = (ku.content_markdown or "").strip()
    if not text:
        return 0
    scope = loads_json(ku.scope_json, {})
    embeddings = await embed_texts([text])
    chunk_id = f"ku_{ku.id}"
    meta: dict[str, Any] = {
        "ku_id": ku.id,
        "anchor_id": ku.anchor_id or "",
        "ku_status": ku.status,
        "filename": filename or ku.source_filename or "清洗入库",
        "source_section": ku.source_section or "",
        "doc_id": ku.source_job_id or ku.id,
        "product": scope.get("product") or "",
        "version": scope.get("version") or "",
        "environment": scope.get("environment") or "",
    }
    upsert_chunks(
        ku.kb_id,
        chunk_ids=[chunk_id],
        texts=[text],
        embeddings=embeddings,
        metadatas=[meta],
    )
    return 1


async def approve_paragraph_to_ku(
    db: Session,
    paragraph: ParagraphUnit,
    job,
    user_id: int,
) -> KnowledgeUnit | None:
    """将审核通过的段落写入 KnowledgeUnit 并向量入库。"""
    action = paragraph.review_action or "add"
    if action == "skip" or paragraph.review_status == "skipped":
        return None

    essence = (paragraph.essence_markdown or "").strip()
    if not essence:
        return None

    scope = loads_json(paragraph.scope_json, {})
    if job.product and not scope.get("product"):
        scope["product"] = job.product
    if job.version and not scope.get("version"):
        scope["version"] = job.version
    if job.environment and not scope.get("environment"):
        scope["environment"] = job.environment

    anchor_ids = loads_json(paragraph.anchor_ids_json, [])
    anchor_id = anchor_ids[0] if anchor_ids else ""

    alignments = loads_json(paragraph.alignment_json, [])
    supersedes: str | None = None
    if action == "supersede" and alignments:
        supersedes = str(alignments[0].get("old_ku_id") or "") or None

    if action == "supersede" and supersedes:
        supersede_ku(db, supersedes)

    ku = KnowledgeUnit(
        id=uuid.uuid4().hex,
        kb_id=job.kb_id,
        anchor_id=anchor_id,
        content_markdown=essence,
        scope_json=dumps_json(scope),
        status="active",
        supersedes_ku_id=supersedes,
        source_job_id=job.id,
        source_paragraph_id=paragraph.id,
        source_filename=job.filename,
        source_section=paragraph.section_path or "",
        created_by=user_id,
    )
    db.add(ku)
    db.flush()

    await ingest_knowledge_unit(db, ku, filename=job.filename)

    paragraph.ku_id = ku.id
    paragraph.review_status = "approved"
    paragraph.updated_at = datetime.utcnow()
    return ku


def register_clean_source_document(
    db: Session,
    *,
    kb_id: str,
    user_id: int,
    job_id: str,
    filename: str,
    original_path: str,
    file_size: int,
) -> KnowledgeDocument:
    """在知识库文档表登记清洗来源文件（不参与向量，仅溯源）。"""
    doc_id = f"clean_{job_id}"
    existing = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
    if existing:
        return existing
    doc = KnowledgeDocument(
        id=doc_id,
        kb_id=kb_id,
        user_id=user_id,
        filename=filename,
        original_path=original_path,
        file_size=file_size,
        status="archived",
        error=None,
        chunk_count=0,
        asset_count=0,
    )
    db.add(doc)
    return doc
