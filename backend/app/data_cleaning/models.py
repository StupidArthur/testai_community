"""
数据清洗 ORM：锚点词典、清洗任务、段落单元、知识单元。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.platform.database import Base


class AnchorNode(Base):
    """锚点词典（Admin 维护功能树节点）。"""

    __tablename__ = "dc_anchor_nodes"

    id = Column(String, primary_key=True)
    label = Column(String, nullable=False)
    parent_id = Column(String, ForeignKey("dc_anchor_nodes.id"), nullable=True, index=True)
    synonyms_json = Column(Text, default="[]")
    description = Column(Text, default="")
    sort_order = Column(Integer, default=50, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class CleanJob(Base):
    """清洗任务（一次上传 + 处理 + 人工审核）。"""

    __tablename__ = "dc_clean_jobs"

    id = Column(String, primary_key=True)
    kb_id = Column(String, ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    original_path = Column(String, nullable=False)
    file_size = Column(Integer, default=0)
    doc_type = Column(String, default="general", nullable=False)
    product = Column(String, default="")
    version = Column(String, default="")
    environment = Column(String, default="")
    note = Column(Text, default="")
    status = Column(String, default="uploaded", nullable=False, index=True)
    error = Column(Text, nullable=True)
    paragraph_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    paragraphs = relationship(
        "ParagraphUnit",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="ParagraphUnit.seq",
    )


class ParagraphUnit(Base):
    """切分后的段落单元（清洗中间态，必存）。"""

    __tablename__ = "dc_paragraph_units"

    id = Column(String, primary_key=True)
    job_id = Column(String, ForeignKey("dc_clean_jobs.id"), nullable=False, index=True)
    seq = Column(Integer, nullable=False, default=0)
    section_path = Column(String, default="")
    raw_text = Column(Text, default="")
    essence_markdown = Column(Text, default="")
    anchor_ids_json = Column(Text, default="[]")
    suggested_anchors_json = Column(Text, default="[]")
    scope_json = Column(Text, default="{}")
    alignment_json = Column(Text, default="[]")
    review_status = Column(String, default="pending", nullable=False)
    review_action = Column(String, default="add", nullable=False)
    ku_id = Column(String, nullable=True, index=True)
    skip_reason = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    job = relationship("CleanJob", back_populates="paragraphs")


class KnowledgeUnit(Base):
    """可检索精华知识单元（批准后写入向量库）。"""

    __tablename__ = "dc_knowledge_units"

    id = Column(String, primary_key=True)
    kb_id = Column(String, ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    anchor_id = Column(String, default="", index=True)
    content_markdown = Column(Text, nullable=False)
    scope_json = Column(Text, default="{}")
    status = Column(String, default="active", nullable=False, index=True)
    supersedes_ku_id = Column(String, nullable=True, index=True)
    source_job_id = Column(String, nullable=True)
    source_paragraph_id = Column(String, nullable=True)
    source_filename = Column(String, default="")
    source_section = Column(String, default="")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
