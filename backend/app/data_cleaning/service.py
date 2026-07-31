"""
数据清洗业务服务。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.data_cleaning.anchor import get_anchor, list_anchors
from app.data_cleaning.config import RAW_SUBDIR
from app.data_cleaning.ingest import approve_paragraph_to_ku
from app.data_cleaning.runtime import ollama_available
from app.data_cleaning.models import AnchorNode, CleanJob, ParagraphUnit
from app.data_cleaning.schemas import (
    AnchorNodeCreate,
    AnchorNodeOut,
    AnchorNodeUpdate,
    ApproveJobResult,
    CleanJobDetailOut,
    CleanJobOut,
    ParagraphUnitOut,
    ParagraphUpdate,
    anchor_to_out,
    job_to_out,
    paragraph_to_out,
)
from app.data_cleaning.utils import dumps_json, loads_json
from app.data_cleaning.worker import dispatch_queued
from app.knowledge_base.config import ALLOWED_DOC_EXTENSIONS, MAX_UPLOAD_BYTES
from app.knowledge_base.default_kb import get_or_create_default_kb
from app.knowledge_base.models import KnowledgeBase
from app.knowledge_base.service import _get_kb_or_404
from app.platform.config import KNOWLEDGE_BASE_DATA_DIR

log = logging.getLogger(__name__)


def _job_raw_dir(kb_id: str, job_id: str) -> Path:
    return KNOWLEDGE_BASE_DATA_DIR / "clean" / kb_id / job_id / RAW_SUBDIR


def _get_job_or_404(db: Session, job_id: str) -> CleanJob:
    job = db.query(CleanJob).filter(CleanJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="清洗任务不存在")
    return job


def _username_map(db: Session, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    from app.auth.models import User as UserModel

    rows = db.query(UserModel).filter(UserModel.id.in_(user_ids)).all()
    return {u.id: u.username for u in rows}


def list_clean_jobs(db: Session, user: User, *, kb_id: str | None = None) -> list[CleanJobOut]:
    q = db.query(CleanJob).order_by(CleanJob.created_at.desc())
    target_kb = kb_id or get_or_create_default_kb(db).id
    q = q.filter(CleanJob.kb_id == target_kb)
    rows = q.limit(100).all()
    names = _username_map(db, {r.user_id for r in rows})
    return [job_to_out(r, names.get(r.user_id, "")) for r in rows]


def get_clean_job_detail(db: Session, user: User, job_id: str) -> CleanJobDetailOut:
    job = _get_job_or_404(db, job_id)
    _get_kb_or_404(db, job.kb_id)
    from app.auth.models import User as UserModel

    u = db.query(UserModel).filter(UserModel.id == job.user_id).first()
    paragraphs = (
        db.query(ParagraphUnit)
        .filter(ParagraphUnit.job_id == job_id)
        .order_by(ParagraphUnit.seq.asc())
        .all()
    )
    base = job_to_out(job, u.username if u else "")
    return CleanJobDetailOut(**base.model_dump(), paragraphs=[paragraph_to_out(p) for p in paragraphs])


async def create_clean_job(
    db: Session,
    user: User,
    file: UploadFile,
    *,
    kb_id: str | None,
    doc_type: str,
    product: str,
    version: str,
    environment: str,
    note: str,
) -> CleanJobOut:
    target_kb_id = (kb_id or "").strip() or get_or_create_default_kb(db).id
    _get_kb_or_404(db, target_kb_id)
    filename = (file.filename or "document").replace("\\", "/").split("/")[-1]
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_DOC_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式 {suffix}")

    job_id = uuid.uuid4().hex
    raw_dir = _job_raw_dir(target_kb_id, job_id)
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / filename

    written = 0
    oversized = False
    try:
        with dest.open("wb") as fh:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    oversized = True
                    break
                fh.write(chunk)
    finally:
        if oversized:
            # Windows：必须先关闭文件句柄再 unlink，否则会 PermissionError
            dest.unlink(missing_ok=True)

    if oversized:
        limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"文件超过大小限制（上限 {limit_mb}MB，当前约 {written // (1024 * 1024)}MB）",
        )

    job = CleanJob(
        id=job_id,
        kb_id=target_kb_id,
        user_id=user.id,
        filename=filename,
        original_path=str(dest.resolve()),
        file_size=written,
        doc_type=doc_type or "general",
        product=(product or "").strip(),
        version=(version or "").strip(),
        environment=(environment or "").strip(),
        note=(note or "").strip(),
        status="uploaded",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    dispatch_queued()
    return job_to_out(job, user.username)


def reprocess_clean_job(db: Session, user: User, job_id: str) -> CleanJobOut:
    """清空段落并重新入队（切分规则修复后重跑）。"""
    job = _get_job_or_404(db, job_id)
    if job.status not in ("pending_review", "failed", "approved"):
        raise HTTPException(status_code=400, detail="当前状态不可重新处理")
    db.query(ParagraphUnit).filter(ParagraphUnit.job_id == job_id).delete()
    job.status = "uploaded"
    job.error = None
    job.paragraph_count = 0
    job.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    dispatch_queued()
    return job_to_out(job, user.username)


def update_paragraph(
    db: Session,
    user: User,
    job_id: str,
    paragraph_id: str,
    data: ParagraphUpdate,
) -> ParagraphUnitOut:
    job = _get_job_or_404(db, job_id)
    if job.status not in ("pending_review", "processing"):
        raise HTTPException(status_code=400, detail="任务已结束，无法编辑段落")
    p = (
        db.query(ParagraphUnit)
        .filter(ParagraphUnit.job_id == job_id, ParagraphUnit.id == paragraph_id)
        .first()
    )
    if not p:
        raise HTTPException(status_code=404, detail="段落不存在")

    if data.essence_markdown is not None:
        p.essence_markdown = data.essence_markdown
    if data.anchor_ids is not None:
        p.anchor_ids_json = dumps_json(data.anchor_ids)
    if data.scope is not None:
        p.scope_json = dumps_json(data.scope)
    if data.review_status is not None:
        p.review_status = data.review_status
    if data.review_action is not None:
        p.review_action = data.review_action
    if data.skip_reason is not None:
        p.skip_reason = data.skip_reason
    p.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(p)
    return paragraph_to_out(p)


async def approve_clean_job(
    db: Session,
    user: User,
    job_id: str,
    *,
    paragraph_ids: list[str] | None = None,
) -> ApproveJobResult:
    job = _get_job_or_404(db, job_id)
    if job.status != "pending_review":
        raise HTTPException(status_code=400, detail="仅 pending_review 状态可批准入库")

    if not await ollama_available(force=True):
        raise HTTPException(
            status_code=503,
            detail=(
                "Ollama 未启动或不可达，无法写入向量库。"
                "请先在本机运行 ollama serve，并执行 ollama pull bge-m3 后重试。"
            ),
        )

    q = db.query(ParagraphUnit).filter(ParagraphUnit.job_id == job_id)
    if paragraph_ids:
        q = q.filter(ParagraphUnit.id.in_(paragraph_ids))
    paragraphs = q.order_by(ParagraphUnit.seq.asc()).all()

    approved = 0
    skipped = 0
    ku_ids: list[str] = []

    for p in paragraphs:
        if p.review_status == "approved" and p.ku_id:
            approved += 1
            ku_ids.append(p.ku_id)
            continue
        if p.review_status == "skipped" or p.review_action == "skip":
            p.review_status = "skipped"
            skipped += 1
            continue
        if p.review_status == "rejected":
            skipped += 1
            continue
        alignments = loads_json(p.alignment_json, [])
        has_contradiction = any(
            isinstance(a, dict) and a.get("relation") == "contradiction" for a in alignments
        )
        if has_contradiction and p.review_action in ("add", "pending", ""):
            raise HTTPException(
                status_code=400,
                detail=f"段落「{p.section_path}」存在逻辑冲突，请选择 supersede/coexist/skip 后再批准",
            )
        try:
            ku = await approve_paragraph_to_ku(db, p, job, user.id)
            if ku:
                approved += 1
                ku_ids.append(ku.id)
            else:
                skipped += 1
            # 每段提交一次，避免 SQLite 长事务锁表；失败后可断点续批
            db.commit()
        except HTTPException:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            log.exception("批准入库段落失败 pid=%s", p.id)
            raise HTTPException(
                status_code=500,
                detail=(
                    f"向量入库失败（已成功 {approved}/{len(paragraphs)} 段）。"
                    "请确认已执行 ollama pull bge-m3，保持 Ollama 运行后再次点击批准。"
                    f" 错误：{str(exc)[:200]}"
                ),
            ) from exc

    job.status = "approved"
    job.updated_at = datetime.utcnow()
    db.commit()
    return ApproveJobResult(approved_count=approved, skipped_count=skipped, ku_ids=ku_ids)


# ---------- 锚点词典（Admin） ----------


def list_anchor_nodes(db: Session, user: User) -> list[AnchorNodeOut]:
    return [anchor_to_out(n) for n in list_anchors(db, include_disabled=True)]


def create_anchor_node(db: Session, user: User, data: AnchorNodeCreate) -> AnchorNodeOut:
    _require_admin(user)
    if get_anchor(db, data.id):
        raise HTTPException(status_code=400, detail="锚点 id 已存在")
    node = AnchorNode(
        id=data.id.strip(),
        label=data.label.strip(),
        parent_id=data.parent_id,
        synonyms_json=dumps_json(data.synonyms),
        description=data.description or "",
        sort_order=data.sort_order,
        enabled=True,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return anchor_to_out(node)


def update_anchor_node(
    db: Session,
    user: User,
    anchor_id: str,
    data: AnchorNodeUpdate,
) -> AnchorNodeOut:
    _require_admin(user)
    node = get_anchor(db, anchor_id)
    if not node:
        raise HTTPException(status_code=404, detail="锚点不存在")
    if data.label is not None:
        node.label = data.label
    if data.parent_id is not None:
        node.parent_id = data.parent_id or None
    if data.synonyms is not None:
        node.synonyms_json = dumps_json(data.synonyms)
    if data.description is not None:
        node.description = data.description
    if data.sort_order is not None:
        node.sort_order = data.sort_order
    if data.enabled is not None:
        node.enabled = data.enabled
    node.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(node)
    return anchor_to_out(node)


def _require_admin(user: User) -> None:
    if user.role != UserRole.Admin:
        raise HTTPException(status_code=403, detail="仅 Admin 可管理锚点词典")
