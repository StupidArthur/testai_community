"""
业务周周期：固定周三 17:00 切周（不再支持自定义周结束时刻）。

周报发送时刻由 62 平台 cron 控制，与本模块无关。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.test_manage.config import (
    WEEK_EDIT_LOCK_BEFORE_END_MINUTES,
    now_tm,
)
from app.test_manage.models import TmWeekPeriod
from app.test_manage.week import (
    _as_local,
    current_week_start as classic_week_start,
    week_end as classic_week_end,
    week_key,
)

# 周报相对周结束的固定延迟（分钟）
WEEKLY_PUSH_DELAY_AFTER_END = timedelta(minutes=15)


def compute_weekly_push_at(week_end: datetime) -> datetime:
    """由周结束时刻推导周报发送时刻：一律 week_end + 15 分钟。"""
    return _as_local(week_end) + WEEKLY_PUSH_DELAY_AFTER_END


def _find_containing(db: Session, when: datetime) -> TmWeekPeriod | None:
    local = _as_local(when)
    return (
        db.query(TmWeekPeriod)
        .filter(TmWeekPeriod.week_start <= local, TmWeekPeriod.week_end > local)
        .order_by(TmWeekPeriod.week_start.desc())
        .first()
    )


def _find_ending_on_date(db: Session, day: datetime) -> TmWeekPeriod | None:
    """切日当天：找 week_end 落在该自然日的周期（用于日更仍归属刚结束周）。"""
    local = _as_local(day)
    day0 = local.replace(hour=0, minute=0, second=0, microsecond=0)
    day1 = day0 + timedelta(days=1)
    return (
        db.query(TmWeekPeriod)
        .filter(TmWeekPeriod.week_end > day0, TmWeekPeriod.week_end <= day1)
        .order_by(TmWeekPeriod.week_end.desc())
        .first()
    )


def _create_period(
    db: Session,
    *,
    week_start: datetime,
    week_end: datetime,
    user_id: int | None = None,
) -> TmWeekPeriod:
    ws = _as_local(week_start)
    we = _as_local(week_end)
    if we <= ws:
        raise ValueError("week_end must be after week_start")
    row = TmWeekPeriod(
        week_key=week_key(ws),
        week_start=ws,
        week_end=we,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(row)
    db.flush()
    return row


def get_or_create_active_period(
    db: Session,
    now: datetime | None = None,
    *,
    user_id: int | None = None,
) -> TmWeekPeriod:
    """
    返回当前时刻所属周窗口；若不存在则按经典周三规则（或接上一窗 +7 天）开窗。
    """
    local = _as_local(now)
    found = _find_containing(db, local)
    if found:
        return found

    # 接上一窗：上一结束点作为新起点
    last = (
        db.query(TmWeekPeriod)
        .filter(TmWeekPeriod.week_end <= local)
        .order_by(TmWeekPeriod.week_end.desc())
        .first()
    )
    if last:
        # 切周：先固化上一周需求进展快照，再开新窗
        try:
            from app.test_manage.service import snapshot_task_stages_for_week

            snapshot_task_stages_for_week(db, last.week_key)
        except Exception:  # noqa: BLE001
            # 快照失败不阻断开周
            pass
        # 新窗对齐标准周三 17:00（消除历史自定义窗口带来的时刻漂移）
        we_last = _as_local(last.week_end)
        ws = classic_week_start(we_last)
        if ws < we_last:
            ws = ws + timedelta(days=7)
        we = ws + timedelta(days=7)
        # 周期表存在空洞（如停机跨多周）时逐周推进，确保窗口覆盖当前时刻
        while we <= local:
            ws = we
            we = ws + timedelta(days=7)
    else:
        ws = classic_week_start(local)
        we = classic_week_end(ws)

    existing_key = (
        db.query(TmWeekPeriod).filter(TmWeekPeriod.week_key == week_key(ws)).first()
    )
    if existing_key:
        # 键冲突（历史数据）：扩到能覆盖 now
        if _as_local(existing_key.week_end) <= local:
            existing_key.week_end = local + timedelta(days=1)
            db.flush()
        return existing_key

    return _create_period(db, week_start=ws, week_end=we, user_id=user_id)


def get_daily_context_period(
    db: Session, now: datetime | None = None
) -> TmWeekPeriod:
    """
    日更 / 日报所属周：切日（week_end 所在自然日）全天仍归属该结束周。
    """
    local = _as_local(now)
    ending = _find_ending_on_date(db, local)
    if ending:
        return ending
    return get_or_create_active_period(db, local)


def is_week_edit_locked(db: Session, now: datetime | None = None) -> bool:
    """
    周截止前编辑锁：当前时刻落在「本周 week_end 前 N 分钟 ～ week_end」内时锁定，
    提醒大家在周截止（默认周三 17:00）前 5 分钟结束 Action / Task 内容更新。
    切周后（新一周窗口）自动解锁。
    """
    local = _as_local(now) if now is not None else now_tm()
    period = get_or_create_active_period(db, local)
    we = _as_local(period.week_end)
    lock_since = we - timedelta(minutes=WEEK_EDIT_LOCK_BEFORE_END_MINUTES)
    return lock_since <= local < we
