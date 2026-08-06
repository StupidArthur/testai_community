"""
企微日报/周报定时调度：进程内 asyncio 轮询（默认每 60s）。

周报发送时刻 = 当前/结束周的 week_end + 15 分钟（见 period.compute_weekly_push_at）。
"""
from __future__ import annotations

import asyncio
import logging

from app.platform.config import (
    WECOM_DAILY_PUSH_HOUR,
    WECOM_DAILY_PUSH_MINUTE,
    WECOM_PUSH_ENABLED,
    WECOM_WEBHOOK_URL,
)
from app.platform.database import SessionLocal
from app.test_manage.config import (
    PUSH_TRIGGER_SCHEDULE,
    WECOM_SCHEDULER_POLL_SECONDS,
    now_tm,
)
from app.test_manage import push_service as push_svc
from app.test_manage.period import (
    compute_weekly_push_at,
    get_daily_context_period,
    get_or_create_active_period,
)
from app.test_manage.week import _as_local

log = logging.getLogger("app.test_manage.push.scheduler")

_task: asyncio.Task | None = None
_stop = asyncio.Event()
_fired_periods: set[str] = set()


def _mark_and_should_fire(kind: str, period_key: str) -> bool:
    key = f"{kind}:{period_key}"
    if key in _fired_periods:
        return False
    _fired_periods.add(key)
    return True


def _should_send_weekly(now, push_at) -> bool:
    """到点后本分钟起可发（由幂等保证不重复）。"""
    n = _as_local(now)
    p = _as_local(push_at)
    return n >= p


async def _tick_once() -> None:
    if not WECOM_PUSH_ENABLED:
        return
    if not WECOM_WEBHOOK_URL:
        return

    now = now_tm()
    db = SessionLocal()
    try:
        if (
            now.hour > WECOM_DAILY_PUSH_HOUR
            or (
                now.hour == WECOM_DAILY_PUSH_HOUR
                and now.minute >= WECOM_DAILY_PUSH_MINUTE
            )
        ):
            from app.test_manage import push_report as report

            period = report.daily_period_key(now.date())
            if _mark_and_should_fire("daily", period):
                result = await push_svc.push_daily(
                    db, trigger=PUSH_TRIGGER_SCHEDULE, dry_run=False, force=True
                )
                if result.sent:
                    log.info("scheduled daily push sent period=%s", result.period_key)
                elif result.skipped:
                    log.info(
                        "scheduled daily skipped: %s period=%s",
                        result.reason,
                        result.period_key,
                    )
                    _fired_periods.discard(f"daily:{period}")

        # 周报：对「日更上下文周」（切日仍属结束周）按推导时刻发送
        ctx = get_daily_context_period(db)
        push_at = compute_weekly_push_at(ctx.week_end)
        if _should_send_weekly(now, push_at):
            from app.test_manage import push_report as report

            period = report.weekly_period_key(ctx.week_start)
            if _mark_and_should_fire("weekly", period):
                result = await push_svc.push_weekly(
                    db, trigger=PUSH_TRIGGER_SCHEDULE, dry_run=False, force=True
                )
                if result.sent:
                    log.info(
                        "scheduled weekly push sent period=%s push_at=%s",
                        result.period_key,
                        push_at.isoformat(),
                    )
                elif result.skipped:
                    log.info(
                        "scheduled weekly skipped: %s period=%s",
                        result.reason,
                        result.period_key,
                    )
                    _fired_periods.discard(f"weekly:{period}")

        # 预热活动周（跨过 week_end 后自动开新窗）
        get_or_create_active_period(db)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        log.exception("scheduled push failed: %s", exc)
    finally:
        db.close()


async def _loop() -> None:
    log.info(
        "wecom push scheduler started (daily %02d:%02d, weekly=from week_end rule, poll=%ss)",
        WECOM_DAILY_PUSH_HOUR,
        WECOM_DAILY_PUSH_MINUTE,
        WECOM_SCHEDULER_POLL_SECONDS,
    )
    while not _stop.is_set():
        await _tick_once()
        try:
            await asyncio.wait_for(_stop.wait(), timeout=WECOM_SCHEDULER_POLL_SECONDS)
        except asyncio.TimeoutError:
            continue


async def start_scheduler() -> None:
    global _task
    _stop.clear()
    if _task and not _task.done():
        return
    if not WECOM_PUSH_ENABLED:
        log.info("wecom push scheduler disabled (WECOM_PUSH_ENABLED=false)")
        return
    _task = asyncio.create_task(_loop(), name="tm-wecom-push-scheduler")


async def stop_scheduler() -> None:
    global _task
    _stop.set()
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
    log.info("wecom push scheduler stopped")
