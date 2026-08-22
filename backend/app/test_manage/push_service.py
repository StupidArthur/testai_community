"""
测试任务群推送编排：日报 / 周报发送、幂等、dry_run（钉钉机器人）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
import asyncio

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.platform.config import (
    DINGTALK_PUSH_IDEMPOTENCY_ENABLED,
    DINGTALK_WEBHOOK_URL,
    DINGTALK_WEEKLY_IDEMPOTENCY_ENABLED,
    dingtalk_openapi_ready,
    dingtalk_push_channel_ready,
)
from app.test_manage.dingtalk_client import (
    DINGTALK_WEEKLY_SCREENSHOT_FILENAME,
    send_daily_report_messages,
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
from app.test_manage.period import get_daily_context_period
from app.test_manage.screen_capture import (
    capture_today_screen_png,
    capture_week_screen_png,
)

log = logging.getLogger("app.test_manage.push")


def _capture_daily_screenshot() -> bytes | None:
    """
    截今日大屏：先走配置的公开 Origin；失败再试本机前端（开发机常见）。
    必须在线程中调用（Playwright sync API）。
    """
    png = capture_today_screen_png()
    if png:
        return png
    # 生产页可能未部署公开大屏；开发时用本地 Vite
    for url in (
        "http://127.0.0.1:3003/tm-screen?view=today&screenshot=1",
        "http://127.0.0.1:48010/tm-screen?view=today&screenshot=1",
    ):
        png = capture_today_screen_png(url=url)
        if png:
            log.info("daily screenshot fallback url=%s bytes=%s", url, len(png))
            return png
    return None


def _capture_weekly_screenshot() -> bytes | None:
    """
    截本周大屏：优先本机前端（含最新「截图自动展开」），再试配置的公开 Origin。
    必须在线程中调用（Playwright sync API）。
    """
    for url in (
        "http://127.0.0.1:3003/tm-screen?view=current&screenshot=1",
        "http://127.0.0.1:48010/tm-screen?view=current&screenshot=1",
    ):
        png = capture_week_screen_png(url=url)
        if png:
            log.info("weekly screenshot local url=%s bytes=%s", url, len(png))
            return png
    png = capture_week_screen_png()
    if png:
        return png
    return None


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

    DINGTALK_PUSH_IDEMPOTENCY_ENABLED=false 时始终视为未发送（可重复推）。
    """
    if not DINGTALK_PUSH_IDEMPOTENCY_ENABLED:
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


def _require_push_channel() -> None:
    if not dingtalk_push_channel_ready():
        raise HTTPException(
            status_code=400,
            detail=(
                "未配置钉钉推送通道：请配置应用机器人 "
                "（DINGTALK_APP_KEY/SECRET/ROBOT_CODE/OPEN_CONVERSATION_ID）"
                "或 DINGTALK_WEBHOOK_URL（可用 dry_run 预览）"
            ),
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
    日报：当前阻塞列表 + Action 进度四档统计；无阻塞也每天发送。

    汇报周取库内日更上下文周 get_daily_context_period（与看板活动周一致，
    避免经典周三 week_key 与自定义 week_end 开窗不一致导致汇总为 0）。
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

    ctx = get_daily_context_period(db)
    ws = ctx.week_start
    wk = ctx.week_key
    current = report.collect_open_risks(db, week_start=ws, week_key_s=wk)
    previous = report.load_snapshot_risks(db, REPORT_KIND_DAILY)
    diff = report.diff_risks(previous, current)

    # 日报只发：少量说明 + 详情链接 + 明细截图（一条消息）
    from app.test_manage.config import resolve_board_detail_url

    detail_url = resolve_board_detail_url()
    title = report.daily_report_heading(day)
    brief_md = report.build_daily_brief_markdown(
        title=title,
        detail_url=detail_url,
    )
    png = await asyncio.to_thread(_capture_daily_screenshot)
    screenshot_ok = bool(png)
    nbytes = report.utf8_len(brief_md)

    if dry_run:
        preview = (
            f"{brief_md}\n\n---\nscreenshot_bytes={len(png or b'')}"
            f" channel={'openapi' if dingtalk_openapi_ready() else 'webhook'}"
            " format=one_message_brief"
        )
        return PushResult(
            kind=REPORT_KIND_DAILY,
            period_key=period,
            sent=False,
            skipped=False,
            dry_run=True,
            message=preview,
            message_bytes=report.utf8_len(preview),
            added_count=len(diff.added),
            unresolved_count=len(diff.unresolved),
            resolved_count=len(diff.resolved_ids),
            reason="dry_run",
        )

    _require_push_channel()
    send_meta = await send_daily_report_messages(
        title=title,
        detail_url=detail_url,
        screenshot_png=png,
        webhook_url=DINGTALK_WEBHOOK_URL,
    )
    if not screenshot_ok:
        log.warning("daily push without screenshot meta=%s", send_meta)
    report.save_snapshot(
        db,
        report_kind=REPORT_KIND_DAILY,
        current=current,
        period_key=period,
        message=brief_md,
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
        message=brief_md,
        message_bytes=nbytes,
        added_count=len(diff.added),
        unresolved_count=len(diff.unresolved),
        resolved_count=len(diff.resolved_ids),
        reason="ok" if screenshot_ok else "ok_no_screenshot",
    )


async def push_weekly(
    db: Session,
    *,
    trigger: str = PUSH_TRIGGER_MANUAL,
    dry_run: bool = False,
    force: bool = False,
) -> PushResult:
    """
    周报：少量说明 + 本周大屏详情链 + 本周大屏截图（一条消息）。

    周归属与日报一致：用库内 get_daily_context_period（与看板同一 week_key）。
    """
    ctx = get_daily_context_period(db)
    ws = ctx.week_start
    wk = ctx.week_key
    period = wk  # 幂等键与业务周键一致
    # 周报幂等由 DINGTALK_WEEKLY_IDEMPOTENCY_ENABLED 单独控制
    if (
        DINGTALK_WEEKLY_IDEMPOTENCY_ENABLED
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

    current = report.collect_open_risks(db, week_start=ws, week_key_s=wk)
    risk_snap = report.collect_week_risk_snapshot(db, week_start=ws, week_key_s=wk)
    prev_key = report.previous_week_key(db, current_week_start=ws)
    progress_delta, matched_n = report.compute_matched_task_progress_delta(
        db, this_week_key=wk, last_week_key=prev_key
    )
    previous = report.load_snapshot_risks(db, REPORT_KIND_WEEKLY)
    diff = report.diff_risks(previous, current)

    from app.test_manage.config import resolve_week_board_detail_url

    detail_url = resolve_week_board_detail_url()
    title = report.weekly_report_heading()
    weekly_brief = report.build_weekly_brief_text(
        risk_snap,
        progress_delta=progress_delta,
        matched_task_count=matched_n,
    )
    brief_md = report.build_daily_brief_markdown(
        title=title,
        detail_url=detail_url,
        brief=weekly_brief,
    )
    png = await asyncio.to_thread(_capture_weekly_screenshot)
    screenshot_ok = bool(png)
    nbytes = report.utf8_len(brief_md)

    if dry_run:
        preview = (
            f"{brief_md}\n\n---\nscreenshot_bytes={len(png or b'')}"
            f" channel={'openapi' if dingtalk_openapi_ready() else 'webhook'}"
            " format=one_message_brief view=current"
        )
        return PushResult(
            kind=REPORT_KIND_WEEKLY,
            period_key=period,
            sent=False,
            skipped=False,
            dry_run=True,
            message=preview,
            message_bytes=report.utf8_len(preview),
            added_count=len(diff.added),
            unresolved_count=len(diff.unresolved),
            resolved_count=len(diff.resolved_ids),
            reason="dry_run",
        )

    _require_push_channel()
    send_meta = await send_daily_report_messages(
        title=title,
        detail_url=detail_url,
        screenshot_png=png,
        webhook_url=DINGTALK_WEBHOOK_URL,
        brief=weekly_brief,
        image_filename=DINGTALK_WEEKLY_SCREENSHOT_FILENAME,
    )
    if not screenshot_ok:
        log.warning("weekly push without screenshot meta=%s", send_meta)
    report.save_snapshot(
        db,
        report_kind=REPORT_KIND_WEEKLY,
        current=current,
        period_key=period,
        message=brief_md,
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
        message=brief_md,
        message_bytes=nbytes,
        added_count=len(diff.added),
        unresolved_count=len(diff.unresolved),
        resolved_count=len(diff.resolved_ids),
        reason="ok" if screenshot_ok else "ok_no_screenshot",
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
        "webhook_configured": bool(DINGTALK_WEBHOOK_URL),
        "openapi_configured": dingtalk_openapi_ready(),
        "channel_ready": dingtalk_push_channel_ready(),
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
