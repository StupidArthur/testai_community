"""
tool_hub ORM：工具元数据与版本（说明书 + changelog + 客户端制品）。
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.platform.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Tool(Base):
    """工具登记：客户端 exe 或平台集成跳转。"""

    __tablename__ = "tools"

    id = Column(String, primary_key=True, default=_new_uuid)
    slug = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=False)
    tool_kind = Column(String, nullable=False, index=True)  # client | platform
    tool_type = Column(String, nullable=False, default="default", index=True)
    link_url = Column(String, nullable=True)  # platform 工具跳转地址（可外链）
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner = relationship("User")
    versions = relationship(
        "ToolVersion",
        back_populates="tool",
        cascade="all, delete-orphan",
    )


class ToolVersion(Base):
    """工具版本：首版含说明书；后续版本含 changelog。"""

    __tablename__ = "tool_versions"

    id = Column(String, primary_key=True, default=_new_uuid)
    tool_id = Column(String, ForeignKey("tools.id"), nullable=False, index=True)
    version_label = Column(String, nullable=False)
    manual_md = Column(Text, nullable=False, default="")
    changelog_md = Column(Text, nullable=False, default="")
    artifact_filename = Column(String, nullable=True)
    artifact_stored_name = Column(String, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tool = relationship("Tool", back_populates="versions")
    creator = relationship("User")
