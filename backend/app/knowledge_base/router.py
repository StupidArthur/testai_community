"""
knowledge_base HTTP 路由。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.service import get_current_user
from app.platform.database import get_db

from .schemas import (
    ChatMessageOut,
    ChatRequest,
    ChatResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseDetailOut,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
    KnowledgeDocumentOut,
)
from .service import (
    chat_with_knowledge_base,
    create_knowledge_base,
    delete_document,
    delete_knowledge_base,
    get_knowledge_base_detail,
    list_chat_messages,
    list_knowledge_bases,
    update_knowledge_base,
    upload_document,
)

router = APIRouter(prefix="/api/knowledge-base", tags=["knowledge-base"])


@router.get("/bases", response_model=list[KnowledgeBaseOut])
def api_list_bases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[KnowledgeBaseOut]:
    return list_knowledge_bases(db, current_user)


@router.post("/bases", response_model=KnowledgeBaseOut, status_code=201)
def api_create_base(
    data: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KnowledgeBaseOut:
    return create_knowledge_base(db, current_user, data)


@router.get("/bases/{kb_id}", response_model=KnowledgeBaseDetailOut)
def api_get_base(
    kb_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KnowledgeBaseDetailOut:
    return get_knowledge_base_detail(db, current_user, kb_id)


@router.patch("/bases/{kb_id}", response_model=KnowledgeBaseOut)
def api_update_base(
    kb_id: str,
    data: KnowledgeBaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KnowledgeBaseOut:
    return update_knowledge_base(db, current_user, kb_id, data)


@router.delete("/bases/{kb_id}", status_code=204, response_class=Response)
def api_delete_base(
    kb_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    delete_knowledge_base(db, current_user, kb_id)
    return Response(status_code=204)


@router.post("/bases/{kb_id}/documents", response_model=KnowledgeDocumentOut, status_code=201)
async def api_upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KnowledgeDocumentOut:
    return await upload_document(db, current_user, kb_id, file)


@router.delete("/bases/{kb_id}/documents/{doc_id}", status_code=204, response_class=Response)
def api_delete_document(
    kb_id: str,
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    delete_document(db, current_user, kb_id, doc_id)
    return Response(status_code=204)


@router.post("/bases/{kb_id}/chat", response_model=ChatResponse)
async def api_chat(
    kb_id: str,
    data: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    return await chat_with_knowledge_base(db, current_user, kb_id, data.question)


@router.get("/bases/{kb_id}/messages", response_model=list[ChatMessageOut])
def api_list_messages(
    kb_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChatMessageOut]:
    return list_chat_messages(db, current_user, kb_id)
