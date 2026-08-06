"""
测试任务企微推送编排：日报 / 周报发送、幂等、dry_run。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.platform.config import (
    WECOM_PUSH_IDEMPOTENCY_ENABLED,
    WECOM_WEBHOOK_URL,
    WECOM_WEEKLY_IDEMPOTENCY_ENABLED,
)
from app.test_manage.config import (
    PUSH_TRIGGER_MANUAL,
    PUSH_TRIGGER_SCHEDULE,
    REPORT_KIND_DAILY,
    REPORT_KIND_WEEKLY,
    now_tm,
)
from app.test_manage.models import TmPushRun
from app.test_manage import push_report as report
from app.test_manage.wecom_client import send_markdown
from app.test_manage.week import current_week_start, daily_context_week_start

log = logging.getLogger("app.test_manage.push")


@dataclass
class PushResult:
    """单次推送结果（含跳过）。"""

    kind: str
    period_key: str
    sent: bool
    skipped: bool
    dry_run: bool
    message: str | None
    message_bytes: int
    added_count: int
    unresolved_count: int
    resolved_count: int
    reason: str = ""


def assert_can_push(user: User) -> None:
    if user.role not in (UserRole.Admin, UserRole.Manager):
        raise HTTPException(status_code=403, detail="仅 Admin / Manager 可触发推送")


def _already_sent(db: Session, kind: str, period_key: str) -> bool:
    """仅「真正发送成功」占坑；skipped 空跑不阻断当日后续推送。

    WECOM_PUSH_IDEMPOTENCY_ENABLED=false 时始终视为未发送（可重复推）。
    """
    if not WECOM_PUSH_IDEMPOTENCY_ENABLED:
        return False
    row = (
        db.query(TmPushRun)
        .filter(
            TmPushRun.report_kind == kind,
            TmPushRun.period_key == period_key,
            TmPushRun.skipped == 0,
        )
        .first()
    )
    return row is not None


def _require_webhook() -> None:
    if not (WECOM_WEBHOOK_URL or "").strip():
        raise HTTPException(
            status_code=400,
            detail="未配置 WECOM_WEBHOOK_URL，无法推送（可用 dry_run 预览）",
        )


def _record_run(
    db: Session,
    *,
    kind: str,
    period_key: str,
    trigger: str,
    skipped: bool,
    message_bytes: int,
) -> None:
    existing = (
        db.query(TmPushRun)
        .filter(TmPushRun.report_kind == kind, TmPushRun.period_key == period_key)
        .first()
    )
    if existing:
        existing.trigger = trigger
        existing.skipped = 1 if skipped else 0
        existing.message_bytes = message_bytes
        db.commit()
        return
    db.add(
        TmPushRun(
            report_kind=kind,
            period_key=period_key,
            trigger=trigger,
            skipped=1 if skipped else 0,
            message_bytes=message_bytes,
        )
    )
    db.commit()


async def push_daily(
    db: Session,
    *,
    trigger: str = PUSH_TRIGGER_MANUAL,
    dry_run: bool = False,
    force: bool = False,
    today: date | None = None,
) -> PushResult:
    """
    日报：偏 Action + 当前风险（今日日更进展 + 开放风险）；无风险也每天发送。

    汇报周取 daily_context_week_start（周三全天仍用刚结束周）。
    force=True：忽略「本日已推送」幂等（调试用）。
    """
    day = today or now_tm().date()
    period = report.daily_period_key(day)
    if not force and not dry_run and _already_sent(db, REPORT_KIND_DAILY, period):
        return PushResult(
            kind=REPORT_KIND_DAILY,
            period_key=period,
            sent=False,
            skipped=True,
            dry_run=dry_run,
            message=None,
            message_bytes=0,
            added_count=0,
            unresolved_count=0,
            resolved_count=0,
            reason="本日已推送过",
        )

    ws = daily_context_week_start()
    current = report.collect_open_risks(db, week_start=ws)
    summary = report.collect_progress_summary(db, week_start=ws)
    action_lines = report.collect_today_action_lines(db, today=day, week_start=ws)
    previous = report.load_snapshot_risks(db, REPORT_KIND_DAILY)
    diff = report.diff_risks(previous, current)
    markdown = await report.fit_daily_markdown(
        today=day, diff=diff, summary=summary, action_lines=action_lines
    )
    nbytes = report.utf8_len(markdown)

    if dry_run:
        return PushResult(
            kind=REPORT_KIND_DAILY,
            period_key=period,
            sent=False,
            skipped=False,
            dry_run=True,
            message=markdown,
            message_bytes=nbytes,
            added_count=len(diff.added),
            unresolved_count=len(diff.unresolved),
            resolved_count=len(diff.resolved_ids),
            reason="dry_run",
        )

    _require_webhook()
    await send_markdown(WECOM_WEBHOOK_URL, markdown)
    report.save_snapshot(
        db,
        report_kind=REPORT_KIND_DAILY,
        current=current,
        period_key=period,
        message=markdown,
        trigger=trigger,
    )
    _record_run(
        db,
        kind=REPORT_KIND_DAILY,
        period_key=period,
        trigger=trigger,
        skipped=False,
        message_bytes=nbytes,
    )
    return PushResult(
        kind=REPORT_KIND_DAILY,
        period_key=period,
        sent=True,
        skipped=False,
        dry_run=False,
        message=markdown,
        message_bytes=nbytes,
        added_count=len(diff.added),
        unresolved_count=len(diff.unresolved),
        resolved_count=len(diff.resolved_ids),
        reason="ok",
    )


async def push_weekly(
    db: Session,
    *,
    trigger: str = PUSH_TRIGGER_MANUAL,
    dry_run: bool = False,
    force: bool = False,
) -> PushResult:
    """
    周报：偏 Task + 整体进度 + 风险（Task 列表 / 分领域 / 风险 Task 视角）。

    周归属与日报一致用 daily_context_week_start：周三切周(18:00)后补跑仍汇报
    「刚结束的一周」，避免 StartWhenAvailable 晚启动落到空的新周。
    """
    ws = daily_context_week_start()
    period = report.weekly_period_key(ws)
    # 周报幂等由 WECOM_WEEKLY_IDEMPOTENCY_ENABLED 单独控制（默认关，可同周重发）
    if (
        WECOM_WEEKLY_IDEMPOTENCY_ENABLED
        and not force
        and not dry_run
        and _already_sent(db, REPORT_KIND_WEEKLY, period)
    ):
        return PushResult(
            kind=REPORT_KIND_WEEKLY,
            period_key=period,
            sent=False,
            skipped=True,
            dry_run=dry_run,
            message=None,
            message_bytes=0,
            added_count=0,
            unresolved_count=0,
            resolved_count=0,
            reason="本周已推送过",
        )

    summary = report.collect_progress_summary(db, week_start=ws)
    current = report.collect_open_risks(db, week_start=ws)
    task_rows = report.collect_task_progress_rows(db, week_start=ws)
    previous = report.load_snapshot_risks(db, REPORT_KIND_WEEKLY)
    diff = report.diff_risks(previous, current)
    markdown = await report.fit_weekly_markdown(
        summary=summary, diff=diff, task_rows=task_rows
    )
    nbytes = report.utf8_len(markdown)

    if dry_run:
        return PushResult(
            kind=REPORT_KIND_WEEKLY,
            period_key=period,
            sent=False,
            skipped=False,
            dry_run=True,
            message=markdown,
            message_bytes=nbytes,
            added_count=len(diff.added),
            unresolved_count=len(diff.unresolved),
            resolved_count=len(diff.resolved_ids),
            reason="dry_run",
        )

    _require_webhook()
    await send_markdown(WECOM_WEBHOOK_URL, markdown)
    report.save_snapshot(
        db,
        report_kind=REPORT_KIND_WEEKLY,
        current=current,
        period_key=period,
        message=markdown,
        trigger=trigger,
    )
    _record_run(
        db,
        kind=REPORT_KIND_WEEKLY,
        period_key=period,
        trigger=trigger,
        skipped=False,
        message_bytes=nbytes,
    )
    return PushResult(
        kind=REPORT_KIND_WEEKLY,
        period_key=period,
        sent=True,
        skipped=False,
        dry_run=False,
        message=markdown,
        message_bytes=nbytes,
        added_count=len(diff.added),
        unresolved_count=len(diff.unresolved),
        resolved_count=len(diff.resolved_ids),
    )


def push_status(db: Session) -> dict:
    """供调试查看上次快照与运行记录。"""
    from app.test_manage.models import TmPushSnapshot

    snaps = db.query(TmPushSnapshot).all()
    runs = (
        db.query(TmPushRun)
        .order_by(TmPushRun.created_at.desc())
        .limit(20)
        .all()
    )
    return {
        "webhook_configured": bool(WECOM_WEBHOOK_URL),
        "snapshots": [
            {
                "report_kind": s.report_kind,
                "last_period_key": s.last_period_key,
                "last_trigger": s.last_trigger,
                "open_risk_count": len(report.load_snapshot_risks(db, s.report_kind)),
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in snaps
        ],
        "recent_runs": [
            {
                "report_kind": r.report_kind,
                "period_key": r.period_key,
                "trigger": r.trigger,
                "skipped": bool(r.skipped),
                "message_bytes": r.message_bytes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ],
    }
