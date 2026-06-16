"""
knowledge_base Pydantic 模型。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    """创建知识库请求。"""

    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


class KnowledgeBaseUpdate(BaseModel):
    """更新知识库元数据。"""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class KnowledgeBaseOut(BaseModel):
    """知识库列表项。"""

    id: str
    name: str
    description: str
    user_id: int
    username: str = ""
    document_count: int = 0
    ready_document_count: int = 0
    created_at: datetime
    updated_at: datetime
    can_manage: bool = False


class KnowledgeDocumentOut(BaseModel):
    """文档处理状态。"""

    id: str
    kb_id: str
    user_id: int
    username: str = ""
    filename: str
    file_size: int
    status: str
    error: str | None = None
    chunk_count: int = 0
    asset_count: int = 0
    can_delete: bool = False
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseDetailOut(KnowledgeBaseOut):
    """知识库详情（含文档列表）。"""

    documents: list[KnowledgeDocumentOut] = Field(default_factory=list)


class ChatRequest(BaseModel):
    """RAG 对话请求。"""

    question: str = Field(..., min_length=1, max_length=4000)


class CitationOut(BaseModel):
    """引用片段。"""

    chunk_id: str | None = None
    filename: str = ""
    page: int | None = None
    snippet: str = ""
    distance: float | None = None


class ChatResponse(BaseModel):
    """RAG 对话响应。"""

    answer: str
    citations: list[CitationOut] = Field(default_factory=list)
    message_id: str


class ChatMessageOut(BaseModel):
    """历史消息。"""

    id: str
    role: str
    content: str
    citations: list[CitationOut] = Field(default_factory=list)
    created_at: datetime
