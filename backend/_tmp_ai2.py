import asyncio, time, importlib
import app.test_manage.config as cfg
importlib.reload(cfg)
import app.test_manage.push_report as r
importlib.reload(r)
from app.platform.database import SessionLocal
from app.test_manage.period import get_daily_context_period
from app.test_manage.config import now_tm
print("timeout", cfg.PUSH_AI_COMPRESS_TIMEOUT_SEC)
print("fn has batch", "batch_size" in open(r.__file__, encoding="utf-8").read())

async def main():
    db = SessionLocal()
    day = now_tm().date()
    ctx = get_daily_context_period(db)
    lines = r.collect_today_action_lines(db, today=day, week_start=ctx.week_start, week_key_s=ctx.week_key)
    # only first 5 for speed
    t0 = time.time()
    out = await r._ai_summarize_daily_fields(lines[:5], max_bytes=4096)
    print("elapsed", round(time.time()-t0,1), "result", None if out is None else len(out))
    if out:
        print("0", out[0].note, "|", out[0].risk)
    db.close()
asyncio.run(main())
