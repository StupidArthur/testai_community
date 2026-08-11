"""
先灌 mock 场景，再发送企微日报 + 周报（真发）。

在 backend 目录：
    python scripts/seed_and_push_demo.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from dotenv import load_dotenv

    load_dotenv(_BACKEND / ".env")
except Exception:
    pass


def main() -> None:
    # 同目录模块导入
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "seed_mock_week_scenarios",
        Path(__file__).resolve().parent / "seed_mock_week_scenarios.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    mod.seed()

    async def _push() -> None:
        from app.platform.config import DINGTALK_WEBHOOK_URL
        from app.platform.database import SessionLocal
        from app.test_manage import push_service as push_svc
        from app.test_manage.config import PUSH_TRIGGER_MANUAL

        print(f"\n== push dingtalk webhook_set={bool(DINGTALK_WEBHOOK_URL)} ==")
        if not DINGTALK_WEBHOOK_URL:
            print("ERROR: DINGTALK_WEBHOOK_URL 未配置，无法真发")
            return
        db = SessionLocal()
        try:
            daily = await push_svc.push_daily(
                db, trigger=PUSH_TRIGGER_MANUAL, dry_run=False, force=True
            )
            print(
                f"[daily] sent={daily.sent} skipped={daily.skipped} "
                f"reason={daily.reason!r} bytes={daily.message_bytes} "
                f"added={daily.added_count} unresolved={daily.unresolved_count}"
            )
            if daily.message:
                print("--- daily message ---")
                print(daily.message)
                print("--- end daily ---\n")

            weekly = await push_svc.push_weekly(
                db, trigger=PUSH_TRIGGER_MANUAL, dry_run=False, force=True
            )
            print(
                f"[weekly] sent={weekly.sent} skipped={weekly.skipped} "
                f"reason={weekly.reason!r} bytes={weekly.message_bytes} "
                f"added={weekly.added_count} unresolved={weekly.unresolved_count}"
            )
            if weekly.message:
                print("--- weekly message ---")
                print(weekly.message)
                print("--- end weekly ---")
        finally:
            db.close()

    asyncio.run(_push())


if __name__ == "__main__":
    main()
