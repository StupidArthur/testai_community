"""
手动触发测试任务企微日报/周报（调试用）。

入口不用命令行参数，直接改 __main__ 里的函数调用。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


async def trigger_push(
    *,
    kind: str = "daily",
    dry_run: bool = True,
    force: bool = True,
) -> None:
    """
    kind: daily | weekly
    dry_run: True 只预览文案；False 真正发到群
    force: True 忽略本日/本周已推送幂等
    """
    from app.platform.database import SessionLocal, engine, Base
    from app.test_manage import models as _models  # noqa: F401
    from app.test_manage import push_service as push_svc
    from app.test_manage.config import PUSH_TRIGGER_MANUAL

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if kind == "daily":
            result = await push_svc.push_daily(
                db, trigger=PUSH_TRIGGER_MANUAL, dry_run=dry_run, force=force
            )
        elif kind == "weekly":
            result = await push_svc.push_weekly(
                db, trigger=PUSH_TRIGGER_MANUAL, dry_run=dry_run, force=force
            )
        else:
            raise ValueError("kind 须为 daily 或 weekly")
        print(
            f"kind={result.kind} period={result.period_key} "
            f"sent={result.sent} skipped={result.skipped} "
            f"reason={result.reason!r} bytes={result.message_bytes} "
            f"added={result.added_count} unresolved={result.unresolved_count}"
        )
        if result.message:
            print("--- message ---")
            print(result.message)
    finally:
        db.close()


if __name__ == "__main__":
    # 调试：先 dry_run 看文案；确认后再改 dry_run=False 真发
    asyncio.run(trigger_push(kind="daily", dry_run=True, force=True))
    # asyncio.run(trigger_push(kind="weekly", dry_run=True, force=True))
