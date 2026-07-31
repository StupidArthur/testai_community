"""
企微日报/周报定时调度：进程内 asyncio 轮询（默认每 60s）。

未配置 WECOM_WEBHOOK_URL 或 WECOM_PUSH_ENABLED=false 时不实际发送。
"""
from __future__ import annotations

import asyncio
import logging

from app.platform.config import (
    WECOM_DAILY_PUSH_HOUR,
    WECOM_DAILY_PUSH_MINUTE,
    WECOM_PUSH_ENABLED,
    WECOM_WEBHOOK_URL,
    WECOM_WEEKLY_PUSH_HOUR,
    WECOM_WEEKLY_PUSH_MINUTE,
    WECOM_WEEKLY_PUSH_WEEKDAY,
)
from app.platform.database import SessionLocal
from app.test_manage.config import (
    PUSH_TRIGGER_SCHEDULE,
    WECOM_SCHEDULER_POLL_SECONDS,
    now_tm,
)
from app.test_manage import push_service as push_svc

log = logging.getLogger("app.test_manage.push.scheduler")

_task: asyncio.Task | None = None
_stop = asyncio.Event()
# 进程内「本 period 已尝试发送」：幂等关闭时防止每 60s 狂发
_fired_periods: set[str] = set()


def _mark_and_should_fire(kind: str, period_key: str) -> bool:
    key = f"{kind}:{period_key}"
    if key in _fired_periods:
        return False
    _fired_periods.add(key)
    return True


async def _tick_once() -> None:
    if not WECOM_PUSH_ENABLED:
        return
    if not WECOM_WEBHOOK_URL:
        return

    now = now_tm()
    db = SessionLocal()
    try:
        # 日报：到点后本自然日首次
        if (
            now.hour > WECOM_DAILY_PUSH_HOUR
            or (
                now.hour == WECOM_DAILY_PUSH_HOUR
                and now.minute >= WECOM_DAILY_PUSH_MINUTE
            )
        ):
            # 先探测 period，避免无脑 force 刷屏
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
                    # 跳过（无内容等）允许同 period 稍后再试
                    _fired_periods.discard(f"daily:{period}")

        # 周报：指定星期几到点后本周首次
        if now.weekday() == WECOM_WEEKLY_PUSH_WEEKDAY and (
            now.hour > WECOM_WEEKLY_PUSH_HOUR
            or (
                now.hour == WECOM_WEEKLY_PUSH_HOUR
                and now.minute >= WECOM_WEEKLY_PUSH_MINUTE
            )
        ):
            from app.test_manage import push_report as report
            from app.test_manage.week import daily_context_week_start

            period = report.weekly_period_key(daily_context_week_start())
            if _mark_and_should_fire("weekly", period):
                result = await push_svc.push_weekly(
                    db, trigger=PUSH_TRIGGER_SCHEDULE, dry_run=False, force=True
                )
                if result.sent:
                    log.info("scheduled weekly push sent period=%s", result.period_key)
                elif result.skipped:
                    log.info(
                        "scheduled weekly skipped: %s period=%s",
                        result.reason,
                        result.period_key,
                    )
                    _fired_periods.discard(f"weekly:{period}")
    except Exception as exc:  # noqa: BLE001
        log.exception("scheduled push failed: %s", exc)
    finally:
        db.close()


async def _loop() -> None:
    log.info(
        "wecom push scheduler started (daily %02d:%02d, weekly weekday=%s %02d:%02d, poll=%ss)",
        WECOM_DAILY_PUSH_HOUR,
        WECOM_DAILY_PUSH_MINUTE,
        WECOM_WEEKLY_PUSH_WEEKDAY,
        WECOM_WEEKLY_PUSH_HOUR,
        WECOM_WEEKLY_PUSH_MINUTE,
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
