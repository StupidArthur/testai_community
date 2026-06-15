"""
工作日报 HTTP 路由。前缀：/api/work-daily
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.auth.service import get_current_user, RequireRole
from app.daily_report import DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT
from app.daily_report.schemas import (
    WorkDailyAuditRequest,
    WorkDailyAuditResponse,
    WorkDailyListOut,
    WorkDailyOut,
    WorkDailySubmitRequest,
)
from app.daily_report.service import (
    audit_draft,
    build_download_zip,
    export_json_by_date,
    get_report,
    list_reports,
    submit_report,
)
from app.platform.database import get_db

router = APIRouter(prefix="/api/work-daily", tags=["work_daily"])


@router.post("/audit", response_model=WorkDailyAuditResponse)
async def audit_work_daily_api(
    data: WorkDailyAuditRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """审核日报（不落库）；左侧编辑后可反复调用。"""
    return await audit_draft(db, data.report_date, data.report_role, data.raw_text)


@router.post("", response_model=WorkDailyOut, status_code=201)
async def submit_work_daily(
    data: WorkDailySubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交日报（每次新建记录，同天可多次）。"""
    return await submit_report(db, current_user, data)


@router.get("", response_model=list[WorkDailyListOut])
def list_work_daily(
    report_date: date | None = None,
    user_id: int | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list_reports(db, current_user, report_date=report_date, user_id=user_id, limit=limit)


@router.get("/export")
def export_by_date(
    report_date: date = Query(..., description="按日期批量导出"),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRole(UserRole.Admin)),
):
    """Admin：导出指定日期全员日报 JSON。"""
    data = export_json_by_date(db, current_user, report_date)
    return JSONResponse(content=data)


@router.get("/download")
def download_raw_zip(
    start_date: date = Query(...),
    end_date: date = Query(...),
    user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """下载原始日报 txt 压缩包（每人每天一个文件）。"""
    return build_download_zip(
        db, current_user, start_date=start_date, end_date=end_date, user_id=user_id,
    )


@router.get("/{report_id}", response_model=WorkDailyOut)
def get_work_daily(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_report(db, current_user, report_id)
