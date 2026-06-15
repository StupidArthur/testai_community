"""
工作日报业务：校验、持久化、导出（审核调用 ai_service.work_daily）。
"""
from __future__ import annotations

import json
import io
import zipfile
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.ai_service.work_daily import (
    REPORT_ROLES,
    MAX_DAYS_BACK,
    MAX_RAW_TEXT_LENGTH,
    audit_work_daily,
)
from app.ai_service.work_daily.audit import get_work_daily_standard_version_id
from app.ai_service.work_daily.models import WorkDailyAuditResult
from app.auth.models import User, UserRole
from app.daily_report.models import DailyReport
from app.daily_report.schemas import (
    WorkDailyAuditResponse,
    WorkDailyListOut,
    WorkDailyOut,
    WorkDailySubmitRequest,
)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def assert_report_date_allowed(report_date: date) -> None:
    """允许今天及过去 MAX_DAYS_BACK 天内（含）。"""
    if report_date > _today():
        raise HTTPException(status_code=400, detail="不能选择未来日期")
    if report_date < _today() - timedelta(days=MAX_DAYS_BACK):
        raise HTTPException(status_code=400, detail=f"仅可补交最近 {MAX_DAYS_BACK} 天内的日报")


def assert_report_role(role: str) -> str:
    role = (role or "").strip()
    if role not in REPORT_ROLES:
        raise HTTPException(status_code=400, detail=f"日报角色须为：{' / '.join(REPORT_ROLES)}")
    return role


def _audit_from_json(raw: str | None) -> WorkDailyAuditResult:
    if not raw:
        return WorkDailyAuditResult()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return WorkDailyAuditResult()
    if not isinstance(data, dict):
        return WorkDailyAuditResult()
    return WorkDailyAuditResult.model_validate(data)


def _row_to_out(db: Session, row: DailyReport) -> WorkDailyOut:
    user = db.query(User).filter(User.id == row.user_id).first()
    return WorkDailyOut(
        id=row.id,
        user_id=row.user_id,
        username=user.username if user else str(row.user_id),
        report_date=row.report_date,
        report_role=row.report_role,
        raw_text=row.raw_text,
        audit=_audit_from_json(row.audit_json),
        skill_version_id=row.skill_version_id,
        created_at=row.created_at,
    )


def _row_to_list(db: Session, row: DailyReport) -> WorkDailyListOut:
    user = db.query(User).filter(User.id == row.user_id).first()
    audit = _audit_from_json(row.audit_json)
    text = row.raw_text.strip().replace("\n", " ")
    preview = text[:80] + ("…" if len(text) > 80 else "")
    return WorkDailyListOut(
        id=row.id,
        user_id=row.user_id,
        username=user.username if user else str(row.user_id),
        report_date=row.report_date,
        report_role=row.report_role,
        summary_preview=preview,
        total_hours=audit.total_hours,
        created_at=row.created_at,
    )


def assert_can_read(row: DailyReport, user: User) -> None:
    if user.role == UserRole.Admin:
        return
    if row.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看他人的日报")


async def audit_draft(
    db: Session,
    report_date: date,
    report_role: str,
    raw_text: str,
) -> WorkDailyAuditResponse:
    assert_report_date_allowed(report_date)
    role = assert_report_role(report_role)
    text = raw_text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="日报内容不能为空")
    if len(text) > MAX_RAW_TEXT_LENGTH:
        raise HTTPException(status_code=400, detail=f"内容过长，最多 {MAX_RAW_TEXT_LENGTH} 字符")

    audit, skill_version_id = await audit_work_daily(db, text, report_date, role)
    return WorkDailyAuditResponse(audit=audit, skill_version_id=skill_version_id)


async def submit_report(
    db: Session,
    user: User,
    data: WorkDailySubmitRequest,
) -> WorkDailyOut:
    assert_report_date_allowed(data.report_date)
    role = assert_report_role(data.report_role)
    text = data.raw_text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="日报内容不能为空")
    if len(text) > MAX_RAW_TEXT_LENGTH:
        raise HTTPException(status_code=400, detail=f"内容过长，最多 {MAX_RAW_TEXT_LENGTH} 字符")

    audit = data.audit
    skill_version_id = None
    if audit is None:
        audit, skill_version_id = await audit_work_daily(db, text, data.report_date, role)
    else:
        skill_version_id = get_work_daily_standard_version_id(db)

    row = DailyReport(
        user_id=user.id,
        report_date=data.report_date,
        report_role=role,
        raw_text=text,
        audit_json=json.dumps(audit.model_dump(), ensure_ascii=False),
        skill_version_id=skill_version_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_out(db, row)


def list_reports(
    db: Session,
    user: User,
    *,
    report_date: date | None = None,
    user_id: int | None = None,
    limit: int = 50,
) -> list[WorkDailyListOut]:
    q = db.query(DailyReport)
    if user.role == UserRole.Admin:
        if user_id is not None:
            q = q.filter(DailyReport.user_id == user_id)
    else:
        q = q.filter(DailyReport.user_id == user.id)

    if report_date is not None:
        q = q.filter(DailyReport.report_date == report_date)

    rows = q.order_by(DailyReport.created_at.desc()).limit(limit).all()
    return [_row_to_list(db, r) for r in rows]


def get_report(db: Session, user: User, report_id: str) -> WorkDailyOut:
    row = db.query(DailyReport).filter(DailyReport.id == report_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="日报不存在")
    assert_can_read(row, user)
    return _row_to_out(db, row)


def export_json_by_date(db: Session, user: User, report_date: date) -> list[dict]:
    if user.role != UserRole.Admin:
        raise HTTPException(status_code=403, detail="仅 Admin 可批量导出")
    rows = (
        db.query(DailyReport)
        .filter(DailyReport.report_date == report_date)
        .order_by(DailyReport.user_id, DailyReport.created_at)
        .all()
    )
    return [_row_to_out(db, r).model_dump(mode="json") for r in rows]


def build_download_zip(
    db: Session,
    user: User,
    *,
    start_date: date,
    end_date: date,
    user_id: int | None = None,
) -> StreamingResponse:
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="结束日期不能早于开始日期")
    if (end_date - start_date).days > MAX_DAYS_BACK:
        raise HTTPException(status_code=400, detail=f"下载区间最多 {MAX_DAYS_BACK} 天")

    q = db.query(DailyReport).filter(
        DailyReport.report_date >= start_date,
        DailyReport.report_date <= end_date,
    )
    if user.role == UserRole.Admin:
        if user_id is not None:
            q = q.filter(DailyReport.user_id == user_id)
    else:
        q = q.filter(DailyReport.user_id == user.id)

    rows = q.order_by(DailyReport.user_id, DailyReport.report_date, DailyReport.created_at).all()
    if not rows:
        raise HTTPException(status_code=404, detail="所选范围无日报")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        grouped: dict[tuple[int, date], list[DailyReport]] = {}
        for row in rows:
            grouped.setdefault((row.user_id, row.report_date), []).append(row)

        for (uid, d), items in grouped.items():
            u = db.query(User).filter(User.id == uid).first()
            uname = u.username if u else str(uid)
            parts = [f"# {uname} · {d.isoformat()} · 工作日报\n"]
            for i, item in enumerate(items, 1):
                ts = item.created_at.strftime("%H:%M") if item.created_at else ""
                parts.append(f"\n--- 第{i}次提交 {ts} [{item.report_role}] ---\n")
                parts.append(item.raw_text.strip())
                parts.append("\n")
            filename = f"{uname}_{d.isoformat()}.txt"
            zf.writestr(filename, "".join(parts))

    buf.seek(0)
    label = f"{start_date}_{end_date}"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="work_daily_{label}.zip"'},
    )
