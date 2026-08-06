"""
Windows 计划任务调用的企微推送入口（不依赖 python run.py 常驻）。

用法（由计划任务传入环境变量 TM_PUSH_KIND）：
  TM_PUSH_KIND=daily|weekly

原则：失败重试，最终必须尽量发出去（force 默认可开）。
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import date as date_cls
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(BACKEND_DIR.parent / ".env")
except Exception:
    pass

_LOG_DIR = Path(__file__).resolve().parent / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

# 整次推送重试（网络/瞬态失败）
PUSH_MAX_ATTEMPTS = 3
PUSH_RETRY_DELAY_SECONDS = 3.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            _LOG_DIR / f"wecom_push_{os.getenv('TM_PUSH_KIND', 'daily')}.log",
            encoding="utf-8",
        ),
    ],
)
log = logging.getLogger("wecom_scheduled_push")


async def run_push(*, kind: str, dry_run: bool = False, force: bool = False) -> None:
    from app.platform.database import Base, SessionLocal, engine
    from app.test_manage import models as _models  # noqa: F401
    from app.test_manage import push_service as push_svc
    from app.test_manage.config import PUSH_TRIGGER_SCHEDULE

    Base.metadata.create_all(bind=engine)
    today_raw = (os.getenv("TM_PUSH_TODAY") or "").strip()
    today = date_cls.fromisoformat(today_raw) if today_raw else None

    last_err: Exception | None = None
    for attempt in range(1, PUSH_MAX_ATTEMPTS + 1):
        db = SessionLocal()
        try:
            if kind == "daily":
                result = await push_svc.push_daily(
                    db,
                    trigger=PUSH_TRIGGER_SCHEDULE,
                    dry_run=dry_run,
                    force=force,
                    today=today,
                )
            elif kind == "weekly":
                from app.test_manage.config import now_tm
                from app.test_manage.week import _as_local, current_week_start, week_end

                # Prefer configurable period (newer deploys); fall back to classic Wed 18:00 window.
                try:
                    from app.test_manage.period import (
                        compute_weekly_push_at,
                        get_daily_context_period,
                        get_or_create_active_period,
                    )

                    get_or_create_active_period(db)
                    ctx = get_daily_context_period(db)
                    push_at = compute_weekly_push_at(ctx.week_end)
                except (ModuleNotFoundError, ImportError) as exc:
                    log.warning(
                        "period/week models incomplete (%s) — use classic week_end+15min; "
                        "sync backend/app/test_manage/ (period.py + models.py) to prod",
                        exc,
                    )
                    from datetime import timedelta

                    we = week_end(current_week_start())
                    push_at = _as_local(we) + timedelta(minutes=15)

                now = now_tm()
                # force=1 用于联调/一次性测试任务，可绕过「未到 week_end+15」门闩
                if (
                    _as_local(now) < _as_local(push_at)
                    and not dry_run
                    and not force
                ):
                    log.info(
                        "weekly not due yet push_at=%s now=%s — skip",
                        push_at.isoformat(),
                        now.isoformat(),
                    )
                    return
                if force and _as_local(now) < _as_local(push_at):
                    log.info(
                        "weekly force=1 bypass time gate push_at=%s now=%s",
                        push_at.isoformat(),
                        now.isoformat(),
                    )
                result = await push_svc.push_weekly(
                    db, trigger=PUSH_TRIGGER_SCHEDULE, dry_run=dry_run, force=force
                )
            else:
                raise ValueError(f"未知 kind={kind!r}，应为 daily 或 weekly")

            log.info(
                "attempt=%s kind=%s period=%s sent=%s skipped=%s reason=%s bytes=%s",
                attempt,
                result.kind,
                result.period_key,
                result.sent,
                result.skipped,
                result.reason,
                result.message_bytes,
            )
            if result.message and dry_run:
                print(result.message)
            if result.sent or dry_run:
                return
            if result.skipped and result.reason in ("本日已推送过", "本周已推送过"):
                # 已成功发过：备份任务命中，算完成
                log.info("already sent ok, stop retry: %s", result.reason)
                return
            # skipped 其它原因（极少）也重试一次
            last_err = RuntimeError(result.reason or "not sent")
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            log.exception("push attempt %s/%s failed", attempt, PUSH_MAX_ATTEMPTS)
        finally:
            db.close()

        if attempt < PUSH_MAX_ATTEMPTS:
            await asyncio.sleep(PUSH_RETRY_DELAY_SECONDS)

    raise RuntimeError(f"push failed after {PUSH_MAX_ATTEMPTS} attempts: {last_err}")


if __name__ == "__main__":
    kind = (os.getenv("TM_PUSH_KIND") or "daily").strip().lower()
    dry = (os.getenv("TM_PUSH_DRY_RUN") or "").strip().lower() in ("1", "true", "yes")
    # 默认不 force：已成功则跳过，由 20:01~20:04 备份任务补漏
    force_env = (os.getenv("TM_PUSH_FORCE") or "0").strip().lower()
    force = force_env in ("1", "true", "yes")
    try:
        asyncio.run(run_push(kind=kind, dry_run=dry, force=force))
    except Exception:
        log.exception("wecom scheduled push FATAL kind=%s", kind)
        sys.exit(1)
    sys.exit(0)
