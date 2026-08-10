"""
运维：设置当前活动周的 week_end（并同步本周 Action.due_at）。

周报正式发送时刻 = week_end + 15 分钟（见 period.compute_weekly_push_at）。
正式计划任务用 TM_PUSH_FORCE=0，到点后由 TestAI-WeCom-Weekly（默认每 1 分钟）触发。

用法（在 backend 目录、使用 .venv Python）::

    python scripts/set_week_end.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(BACKEND_DIR.parent / ".env")
except Exception:
    pass

# 默认：本周结束 2026-08-06 17:15（业务时区 TM_TZ）→ 周报正式发送 17:30
DEFAULT_WEEK_END = "2026-08-06T17:15:00"
# 运维验收允许把 week_end 设到「刚过 / 即将到」的时刻
DEFAULT_ALLOW_PAST = True
# 无登录态时写入 updated_by；0 表示系统运维
DEFAULT_USER_ID = 0


def set_week_end(
    *,
    week_end_iso: str = DEFAULT_WEEK_END,
    allow_past: bool = DEFAULT_ALLOW_PAST,
    user_id: int = DEFAULT_USER_ID,
) -> None:
    """把活动周 week_end 设为指定本地时刻，并打印推导出的周报发送点。"""
    from app.auth.models import User  # noqa: F401  — 注册 users 表供 FK 解析
    from app.platform.database import Base, SessionLocal, engine
    from app.test_manage import models as _models  # noqa: F401
    from app.test_manage.config import TM_TZ
    from app.test_manage.period import compute_weekly_push_at, set_active_week_end
    from app.test_manage.week import _as_local

    Base.metadata.create_all(bind=engine)

    # updated_by 可空；无合法用户时写 None，避免 FK 指向不存在的 id=0
    effective_user_id: int | None = user_id if user_id and user_id > 0 else None
    if effective_user_id is None:
        db0 = SessionLocal()
        try:
            row = db0.query(User.id).order_by(User.id.asc()).first()
            effective_user_id = int(row[0]) if row else None
        finally:
            db0.close()

    naive = datetime.fromisoformat(week_end_iso)
    if naive.tzinfo is None:
        week_end = naive.replace(tzinfo=TM_TZ)
    else:
        week_end = naive.astimezone(TM_TZ)

    db = SessionLocal()
    try:
        period = set_active_week_end(
            db,
            week_end=week_end,
            user_id=effective_user_id,
            allow_past=allow_past,
        )
        db.commit()
        push_at = compute_weekly_push_at(period.week_end)
        print(
            "OK week_key={key} week_start={ws} week_end={we} weekly_push_at={pa}".format(
                key=period.week_key,
                ws=_as_local(period.week_start).isoformat(),
                we=_as_local(period.week_end).isoformat(),
                pa=_as_local(push_at).isoformat(),
            )
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    set_week_end(
        week_end_iso=DEFAULT_WEEK_END,
        allow_past=DEFAULT_ALLOW_PAST,
        user_id=DEFAULT_USER_ID,
    )
