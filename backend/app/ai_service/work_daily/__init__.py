"""
工作日报 AI 能力：Skill 审核、维度与工时占比解析。

对外入口：audit_work_daily
"""

from app.ai_service.work_daily.audit import audit_work_daily
from app.ai_service.work_daily.constants import (
    MAX_DAYS_BACK,
    MAX_RAW_TEXT_LENGTH,
    REPORT_ROLES,
    WORK_DAILY_SKILL_NAME,
)

__all__ = [
    "audit_work_daily",
    "WORK_DAILY_SKILL_NAME",
    "REPORT_ROLES",
    "MAX_DAYS_BACK",
    "MAX_RAW_TEXT_LENGTH",
]
