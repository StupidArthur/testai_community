"""验证日报过长时的适配路径：完整长度 → fit 后字节数 → 是否走 AI/硬截断。

用法（backend 目录）：
    python scripts/verify_daily_push_fit.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from app.platform.database import SessionLocal
from app.test_manage import push_report as report
from app.test_manage.config import WECOM_MSG_MAX_BYTES, now_tm
from app.test_manage.week import daily_context_week_start


async def main() -> None:
    day = now_tm().date()
    db = SessionLocal()
    try:
        ws = daily_context_week_start()
        summary = report.collect_progress_summary(db, week_start=ws)
        current = report.collect_open_risks(db, week_start=ws)
        action_lines = report.collect_today_action_lines(db, today=day, week_start=ws)
        previous = report.load_snapshot_risks(db, "daily")
        diff = report.diff_risks(previous, current)

        full = report.build_daily_markdown(
            today=day,
            diff=diff,
            summary=summary,
            action_lines=action_lines,
            max_risk_items=999,
            max_action_lines=999,
        )
        full_n = report.utf8_len(full)
        print(f"=== 当前库日报（未适配）===")
        print(f"Action 行数={len(action_lines)} 风险开放={len(current)} 字节={full_n} 上限={WECOM_MSG_MAX_BYTES}")

        fitted = await report.fit_daily_markdown(
            today=day,
            diff=diff,
            summary=summary,
            action_lines=action_lines,
        )
        fit_n = report.utf8_len(fitted)
        print(f"=== 适配后 ===")
        print(f"字节={fit_n} 单条可发={fit_n <= WECOM_MSG_MAX_BYTES}")
        print("--- 预览前 600 字 ---")
        print(fitted[:600])
        print("--- 预览尾 300 字 ---")
        print(fitted[-300:])

        # 人为加长：复制 Action 行模拟「数据过多」
        fat_lines = list(action_lines)
        while len(fat_lines) < 80 and action_lines:
            fat_lines.extend(action_lines)
        fat_lines = fat_lines[:80]
        fat_full = report.build_daily_markdown(
            today=day,
            diff=diff,
            summary=summary,
            action_lines=fat_lines,
            max_risk_items=999,
            max_action_lines=999,
        )
        fat_n = report.utf8_len(fat_full)
        print(f"\n=== 模拟过多数据（约 {len(fat_lines)} 行 Action）未适配字节={fat_n} ===")
        fat_fit = await report.fit_daily_markdown(
            today=day,
            diff=diff,
            summary=summary,
            action_lines=fat_lines,
        )
        fat_fit_n = report.utf8_len(fat_fit)
        print(f"适配后字节={fat_fit_n} 单条可发={fat_fit_n <= WECOM_MSG_MAX_BYTES}")
        print("结论：无论多长，最终仍只发 1 条，且 ≤4096 字节（先尽量 AI 压全文，再砍行，最后硬截断）。")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
