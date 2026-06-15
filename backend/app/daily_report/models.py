"""
工作日报 ORM：原始文本 + 审核快照；同一天可多次提交。
"""
from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.platform.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id = Column(String, primary_key=True, default=_new_uuid)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    report_date = Column(Date, nullable=False, index=True)
    report_role = Column(String, nullable=False, default="测试工程师")

    raw_text = Column(Text, nullable=False)
    audit_json = Column(Text, nullable=False, default="{}")
    skill_version_id = Column(String, ForeignKey("skill_versions.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
    skill_version = relationship("SkillVersion")
