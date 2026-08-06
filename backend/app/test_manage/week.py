"""
周窗口计算：默认周三 17:00 为一周起点。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.test_manage.config import (
    TM_TZ,
    WEEK_BOUNDARY_HOUR,
    WEEK_BOUNDARY_MINUTE,
    WEEK_BOUNDARY_WEEKDAY,
)


def _as_local(dt: datetime | None = None) -> datetime:
    """将时刻规范化到业务时区（无 tz 视为本地naive→注入 TM_TZ）。"""
    if dt is None:
        return datetime.now(TM_TZ)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TM_TZ)
    return dt.astimezone(TM_TZ)


def current_week_start(now: datetime | None = None) -> datetime:
    """
    返回「当前所处周」的起始时刻（周三 17:00）。

    例：周四任意时刻 → 本周三 17:00；
    周三 16:59 → 上一周三 17:00；周三 17:00 → 本周三 17:00。
    """
    local = _as_local(now)
    # 回溯到本周一 0 点再对齐到周三 18:00 候选
    days_since_monday = local.weekday()  # Mon=0
    monday = (local - timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    # 本自然周的周三 18:00
    this_wed = monday + timedelta(days=WEEK_BOUNDARY_WEEKDAY)
    candidate = this_wed.replace(
        hour=WEEK_BOUNDARY_HOUR,
        minute=WEEK_BOUNDARY_MINUTE,
        second=0,
        microsecond=0,
    )
    if local >= candidate:
        return candidate
    return candidate - timedelta(days=7)


def week_end(week_start: datetime) -> datetime:
    """周结束时刻（下一周三 17:00，半开区间右端）。"""
    ws = _as_local(week_start)
    return ws + timedelta(days=7)


def previous_week_start(week_start: datetime | None = None) -> datetime:
    """上一周的 week_start。"""
    ws = week_start if week_start is not None else current_week_start()
    return _as_local(ws) - timedelta(days=7)


def week_key(week_start: datetime) -> str:
    """可读周标识，如 2026-07-15T18。"""
    ws = _as_local(week_start)
    return ws.strftime("%Y-%m-%dT%H")


def _this_wednesday_boundary(local: datetime) -> datetime:
    """本自然周（周一～周日）内的周三 17:00 切周点。"""
    days_since_monday = local.weekday()
    monday = (local - timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    this_wed = monday + timedelta(days=WEEK_BOUNDARY_WEEKDAY)
    return this_wed.replace(
        hour=WEEK_BOUNDARY_HOUR,
        minute=WEEK_BOUNDARY_MINUTE,
        second=0,
        microsecond=0,
    )


def daily_context_week_start(now: datetime | None = None) -> datetime:
    """
    日更 / 企微日报所属周。

    切周日（周三）全天：日报与日更仍归属「以今天 17:00 为终点」的那一周
    （即刚结束或即将结束的一周的最后一天），不写「新一周」的日报。
    其它日子：与 current_week_start 一致。
    """
    local = _as_local(now)
    if local.weekday() == WEEK_BOUNDARY_WEEKDAY:
        return _this_wednesday_boundary(local) - timedelta(days=7)
    return current_week_start(local)