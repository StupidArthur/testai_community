"""
knowledge_base 业务逻辑。

权限约定：
- 知识库：全员可见、可上传、可对话；仅创建者与 Admin 可改删知识库本身
- 文档：上传者本人可删；Admin 可删任意文档
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai_service.rag import answer_with_rag, delete_document_chunks, delete_kb_collection
from app.ai_service.rag.store import kb_vector_chunk_count
from app.auth.models import User, UserRole
from app.platform.config import KNOWLEDGE_BASE_DATA_DIR

from .config import (
    ALLOWED_DOC_EXTENSIONS,
    MAX_DOCS_PER_KB,
    MAX_TOTAL_BYTES,
    MAX_UPLOAD_BYTES,
    RAW_SUBDIR,
)
from .default_kb import get_or_create_default_kb
from .models import KnowledgeBase, KnowledgeChatMessage, KnowledgeDocument
from .schemas import (
    ChatMessageOut,
    ChatResponse,
    CitationOut,
    KnowledgeBaseCreate,
    KnowledgeBaseDetailOut,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
    KnowledgeDocumentOut,
)
from .worker import dispatch_queued


def _kb_raw_dir(kb_id: str) -> Path:
    """知识库原始文件目录。"""
    return KNOWLEDGE_BASE_DATA_DIR / kb_id / RAW_SUBDIR


def _is_admin(user: User) -> bool:
    return user.role == UserRole.Admin


def _can_manage_kb(kb: KnowledgeBase, user: User) -> bool:
    """是否可修改/删除知识库本身。"""
    return _is_admin(user) or kb.user_id == user.id


def _can_delete_document(doc: KnowledgeDocument, user: User) -> bool:
    """是否可删除文档。"""
    return _is_admin(user) or doc.user_id == user.id


def _get_kb_or_404(db: Session, kb_id: str) -> KnowledgeBase:
    """知识库存在性校验（全员可读）。"""
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if kb is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return kb


def _doc_to_out(
    doc: KnowledgeDocument,
    *,
    username: str = "",
    current_user: User | None = None,
) -> KnowledgeDocumentOut:
    return KnowledgeDocumentOut(
        id=doc.id,
        kb_id=doc.kb_id,
        user_id=doc.user_id,
        username=username,
        filename=doc.filename,
        file_size=doc.file_size or 0,
        status=doc.status,
        error=doc.error,
        chunk_count=doc.chunk_count or 0,
        asset_count=doc.asset_count or 0,
        can_delete=_can_delete_document(doc, current_user) if current_user else False,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _kb_to_out(
    kb: KnowledgeBase,
    *,
    username: str = "",
    documents: list[KnowledgeDocument] | None = None,
    current_user: User | None = None,
    count_vectors: bool = False,
) -> KnowledgeBaseOut:
    docs = documents if documents is not None else list(kb.documents or [])
    direct_docs = [d for d in docs if d.status != "archived"]
    archived_count = sum(1 for d in docs if d.status == "archived")
    vec_count = kb_vector_chunk_count(kb.id) if count_vectors else 0
    return KnowledgeBaseOut(
        id=kb.id,
        name=kb.name,
        description=kb.description or "",
        user_id=kb.user_id,
        username=username,
        document_count=len(direct_docs),
        ready_document_count=sum(1 for d in direct_docs if d.status == "ready"),
        archived_document_count=archived_count,
        vector_chunk_count=vec_count,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
        can_manage=_can_manage_kb(kb, current_user) if current_user else False,
    )


def _kb_storage_bytes(db: Session, kb_id: str) -> int:
    total = (
        db.query(func.coalesce(func.sum(KnowledgeDocument.file_size), 0))
        .filter(KnowledgeDocument.kb_id == kb_id)
        .scalar()
    )
    return int(total or 0)


def list_knowledge_bases(db: Session, user: User) -> list[KnowledgeBaseOut]:
    """列出全站知识库（全员可见）。"""
    rows = db.query(KnowledgeBase).order_by(KnowledgeBase.updated_at.desc()).all()
    result: list[KnowledgeBaseOut] = []
    for kb in rows:
        owner = db.query(User).filter(User.id == kb.user_id).first()
        result.append(_kb_to_out(kb, username=owner.username if owner else "", current_user=user))
    return result


def get_default_knowledge_base(db: Session, user: User) -> KnowledgeBaseOut:
    """获取全站唯一默认知识库。"""
    kb = get_or_create_default_kb(db)
    owner = db.query(User).filter(User.id == kb.user_id).first()
    return _kb_to_out(
        kb,
        username=owner.username if owner else "",
        current_user=user,
        count_vectors=True,
    )


def create_knowledge_base(db: Session, user: User, data: KnowledgeBaseCreate) -> KnowledgeBaseOut:
    """创建知识库（单库模式：已存在则拒绝）。"""
    if db.query(KnowledgeBase).count() > 0:
        raise HTTPException(status_code=400, detail="平台仅支持一个知识库，请使用默认知识库")
    kb_id = uuid.uuid4().hex
    kb = KnowledgeBase(
        id=kb_id,
        name=data.name.strip(),
        description=(data.description or "").strip(),
        user_id=user.id,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    _kb_raw_dir(kb_id).mkdir(parents=True, exist_ok=True)
    return _kb_to_out(kb, username=user.username, current_user=user)


def get_knowledge_base_detail(db: Session, user: User, kb_id: str) -> KnowledgeBaseDetailOut:
    """获取知识库详情及文档列表。"""
    kb = _get_kb_or_404(db, kb_id)
    owner = db.query(User).filter(User.id == kb.user_id).first()
    docs = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.kb_id == kb_id)
        .order_by(KnowledgeDocument.created_at.desc())
        .all()
    )
    uploader_ids = {d.user_id for d in docs}
    users = {
        u.id: u.username
        for u in db.query(User).filter(User.id.in_(uploader_ids)).all()
    } if uploader_ids else {}

    base = _kb_to_out(
        kb,
        username=owner.username if owner else "",
        documents=docs,
        current_user=user,
        count_vectors=True,
    )
    return KnowledgeBaseDetailOut(
        **base.model_dump(),
        documents=[
            _doc_to_out(d, username=users.get(d.user_id, ""), current_user=user)
            for d in docs
        ],
    )


def update_knowledge_base(db: Session, user: User, kb_id: str, data: KnowledgeBaseUpdate) -> KnowledgeBaseOut:
    """更新知识库名称与描述（创建者或 Admin）。"""
    kb = _get_kb_or_404(db, kb_id)
    if not _can_manage_kb(kb, user):
        raise HTTPException(status_code=403, detail="仅知识库创建者或 Admin 可修改")
    if data.name is not None:
        kb.name = data.name.strip()
    if data.description is not None:
        kb.description = data.description.strip()
    kb.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(kb)
    owner = db.query(User).filter(User.id == kb.user_id).first()
    return _kb_to_out(kb, username=owner.username if owner else "", current_user=user)


def delete_knowledge_base(db: Session, user: User, kb_id: str) -> None:
    """删除知识库（创建者或 Admin）。"""
    kb = _get_kb_or_404(db, kb_id)
    if not _can_manage_kb(kb, user):
        raise HTTPException(status_code=403, detail="仅知识库创建者或 Admin 可删除知识库")
    delete_kb_collection(kb_id)
    kb_dir = KNOWLEDGE_BASE_DATA_DIR / kb_id
    if kb_dir.exists():
        shutil.rmtree(kb_dir, ignore_errors=True)
    db.delete(kb)
    db.commit()


async def upload_document(
    db: Session,
    user: User,
    kb_id: str,
    file: UploadFile,
) -> KnowledgeDocumentOut:
    """任意登录用户可向知识库上传文档。"""
    kb = _get_kb_or_404(db, kb_id)
    doc_count = db.query(KnowledgeDocument).filter(KnowledgeDocument.kb_id == kb_id).count()
    if doc_count >= MAX_DOCS_PER_KB:
        raise HTTPException(
            status_code=400,
            detail=f"该知识库文档数已达上限（{MAX_DOCS_PER_KB} 个）",
        )

    filename = (file.filename or "document").replace("\\", "/").split("/")[-1]
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_DOC_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式 {suffix}，支持: {', '.join(sorted(ALLOWED_DOC_EXTENSIONS))}",
        )

    doc_id = uuid.uuid4().hex
    raw_dir = _kb_raw_dir(kb.id)
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / f"{doc_id}_{filename}"

    written = 0
    with dest.open("wb") as fh:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"单文件超过 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB 限制",
                )
            fh.write(chunk)

    current_total = _kb_storage_bytes(db, kb_id)
    if current_total + written > MAX_TOTAL_BYTES:
        dest.unlink(missing_ok=True)
        raise HTTPException(
            status_code=413,
            detail=f"知识库总容量超过 {MAX_TOTAL_BYTES // (1024 * 1024)}MB 限制",
        )

    doc = KnowledgeDocument(
        id=doc_id,
        kb_id=kb.id,
        user_id=user.id,
        filename=filename,
        original_path=str(dest),
        file_size=written,
        status="queued",
    )
    db.add(doc)
    kb.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(doc)
    dispatch_queued()
    return _doc_to_out(doc, username=user.username, current_user=user)


def delete_document(db: Session, user: User, kb_id: str, doc_id: str) -> None:
    """删除文档：上传者本人或 Admin。"""
    _get_kb_or_404(db, kb_id)
    doc = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.id == doc_id, KnowledgeDocument.kb_id == kb_id)
        .first()
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not _can_delete_document(doc, user):
        raise HTTPException(status_code=403, detail="仅文档上传者或 Admin 可删除该文档")
    delete_document_chunks(kb_id, doc_id)
    path = Path(doc.original_path)
    if path.is_file():
        path.unlink(missing_ok=True)
    db.delete(doc)
    db.commit()


async def chat_with_knowledge_base(db: Session, user: User, kb_id: str, question: str) -> ChatResponse:
    """RAG 问答（全员可用）。"""
    kb = _get_kb_or_404(db, kb_id)
    ready_count = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.kb_id == kb_id, KnowledgeDocument.status == "ready")
        .count()
    )
    vector_count = kb_vector_chunk_count(kb_id)
    if ready_count == 0 and vector_count == 0:
        raise HTTPException(
            status_code=400,
            detail="知识库尚无可检索内容：请在知识库直接上传文档并等待「可用」，或完成数据清洗后「批准入库」",
        )

    user_msg = KnowledgeChatMessage(
        id=uuid.uuid4().hex,
        kb_id=kb.id,
        user_id=user.id,
        role="user",
        content=question.strip(),
        citations_json="[]",
    )
    db.add(user_msg)

    result = await answer_with_rag(kb.id, question.strip())
    citations = result.get("citations") or []
    assistant_msg = KnowledgeChatMessage(
        id=uuid.uuid4().hex,
        kb_id=kb.id,
        user_id=user.id,
        role="assistant",
        content=result.get("answer") or "",
        citations_json=json.dumps(citations, ensure_ascii=False),
    )
    db.add(assistant_msg)
    kb.updated_at = datetime.utcnow()
    db.commit()

    return ChatResponse(
        answer=assistant_msg.content,
        citations=[CitationOut(**c) for c in citations],
        message_id=assistant_msg.id,
    )


def list_chat_messages(db: Session, user: User, kb_id: str, *, limit: int = 50) -> list[ChatMessageOut]:
    """获取当前用户在该知识库下的对话历史。"""
    _get_kb_or_404(db, kb_id)
    rows = (
        db.query(KnowledgeChatMessage)
        .filter(KnowledgeChatMessage.kb_id == kb_id, KnowledgeChatMessage.user_id == user.id)
        .order_by(KnowledgeChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    out: list[ChatMessageOut] = []
    for row in rows:
        try:
            citations_raw = json.loads(row.citations_json or "[]")
        except json.JSONDecodeError:
            citations_raw = []
        out.append(
            ChatMessageOut(
                id=row.id,
                role=row.role,
                content=row.content,
                citations=[CitationOut(**c) for c in citations_raw],
                created_at=row.created_at,
            )
        )
    return out
