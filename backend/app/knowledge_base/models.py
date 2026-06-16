"""
knowledge_base ORM 模型。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.platform.database import Base


class KnowledgeBase(Base):
    """用户知识库。"""

    __tablename__ = "knowledge_bases"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    documents = relationship("KnowledgeDocument", back_populates="knowledge_base", cascade="all, delete-orphan")
    messages = relationship("KnowledgeChatMessage", back_populates="knowledge_base", cascade="all, delete-orphan")


class KnowledgeDocument(Base):
    """知识库中的原始文档及处理状态。"""

    __tablename__ = "knowledge_documents"

    id = Column(String, primary_key=True)
    kb_id = Column(String, ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    original_path = Column(String, nullable=False)
    file_size = Column(Integer, default=0)
    status = Column(String, default="queued", nullable=False, index=True)
    error = Column(Text, nullable=True)
    chunk_count = Column(Integer, default=0)
    asset_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    knowledge_base = relationship("KnowledgeBase", back_populates="documents")


class KnowledgeChatMessage(Base):
    """知识库对话历史。"""

    __tablename__ = "knowledge_chat_messages"

    id = Column(String, primary_key=True)
    kb_id = Column(String, ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    citations_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    knowledge_base = relationship("KnowledgeBase", back_populates="messages")
