"""业务周结束 → 周报发送时刻规则。"""
from datetime import datetime

from app.test_manage.config import TM_TZ
from app.test_manage.period import compute_weekly_push_at


def _dt(y: int, m: int, d: int, hh: int, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=TM_TZ)


def test_weekly_push_always_fifteen_after_afternoon_end():
    """周结束 15:00 → 15:15。"""
    assert compute_weekly_push_at(_dt(2026, 7, 29, 15, 0)) == _dt(2026, 7, 29, 15, 15)


def test_weekly_push_always_fifteen_after_seventeen():
    """周结束 17:00 → 17:15。"""
    assert compute_weekly_push_at(_dt(2026, 7, 29, 17, 0)) == _dt(2026, 7, 29, 17, 15)


def test_weekly_push_always_fifteen_after_default_end():
    """周结束 18:00 → 18:15。"""
    assert compute_weekly_push_at(_dt(2026, 7, 29, 18, 0)) == _dt(2026, 7, 29, 18, 15)
