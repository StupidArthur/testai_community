"""
工作日报 HTTP 模型。
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.ai_service.work_daily.models import WorkDailyAuditResult
from app.ai_service.work_daily.constants import REPORT_ROLES


class WorkDailyAuditRequest(BaseModel):
    report_date: date
    report_role: str = Field(..., description="测试工程师 | 测试负责人")
    raw_text: str = Field(..., min_length=1)

    @field_validator("report_role")
    @classmethod
    def check_role(cls, v: str) -> str:
        if v not in REPORT_ROLES:
            raise ValueError(f"report_role 须为 {REPORT_ROLES}")
        return v


class WorkDailySubmitRequest(BaseModel):
    report_date: date
    report_role: str
    raw_text: str = Field(..., min_length=1)
    audit: WorkDailyAuditResult | None = None

    @field_validator("report_role")
    @classmethod
    def check_role(cls, v: str) -> str:
        if v not in REPORT_ROLES:
            raise ValueError(f"report_role 须为 {REPORT_ROLES}")
        return v


class WorkDailyAuditResponse(BaseModel):
    audit: WorkDailyAuditResult
    skill_version_id: str | None = None


class WorkDailyOut(BaseModel):
    id: str
    user_id: int
    username: str
    report_date: date
    report_role: str
    raw_text: str
    audit: WorkDailyAuditResult
    skill_version_id: str | None = None
    created_at: datetime


class WorkDailyListOut(BaseModel):
    id: str
    user_id: int
    username: str
    report_date: date
    report_role: str
    summary_preview: str
    total_hours: float
    created_at: datetime


class WorkDailyListPage(BaseModel):
    items: list[WorkDailyListOut]
    total: int
    page: int
    page_size: int
