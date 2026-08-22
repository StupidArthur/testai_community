import asyncio, json, time
from app.platform.database import SessionLocal
from app.test_manage import push_report as r
from app.test_manage.period import get_daily_context_period
from app.test_manage.config import now_tm
from app.ai_service.client import chat

async def main():
    db = SessionLocal()
    day = now_tm().date()
    ctx = get_daily_context_period(db)
    lines = r.collect_today_action_lines(db, today=day, week_start=ctx.week_start, week_key_s=ctx.week_key)[:5]
    payload = [{"i":i,"title":x.action_title[:40],"note":(x.note or "")[:80],"risk":(x.risk or "")[:80]} for i,x in enumerate(lines)]
    prompt = "为每条总结 note_summary/risk_summary 各<=28字。只输出JSON数组。\n" + json.dumps(payload, ensure_ascii=False)
    for think, mt in ((False, 8192), (False, 2048), (True, 2048)):
        t0 = time.time()
        try:
            out = await asyncio.wait_for(
                chat([{"role":"user","content":prompt}], temperature=0.1, max_tokens=mt, think=think, max_retries=1, base_delay_ms=200),
                timeout=35,
            )
            print("think", think, "mt", mt, "ok", round(time.time()-t0,1), "len", len(out or ""), "head", repr((out or "")[:100]))
        except Exception as e:
            print("think", think, "mt", mt, "fail", round(time.time()-t0,1), type(e).__name__, e)
    db.close()
asyncio.run(main())
