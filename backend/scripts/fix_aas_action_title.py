# -*- coding: utf-8 -*-
r"""
一次性数据修复（62 环境）：把已发布 Action「AAS未开始联调」改名为「AAS和NYX数据对接」。

背景：Action 发布后标题字段被业务规则锁定（API 403），只能直接改库。
安全措施：自动找库 → 先备份 → 校验旧标题必须完全匹配 → 单行 UPDATE → 回读验证。
幂等：已是新标题则直接提示成功退出。

用法（62 机器上，任意位置均可）：
    python fix_aas_action_title.py
    指定解释器亦可：D:\testai_community_prod\backend\.venv\Scripts\python.exe fix_aas_action_title.py
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

ACTION_ID = "fe22e974-bb09-4df2-b470-db8362a58d4d"
OLD_TITLE = "AAS未开始联调"
NEW_TITLE = "AAS和NYX数据对接"

CANDIDATES = [
    r"D:\testai_community_prod\backend\database_prod.sqlite",
    r"D:\testai_community_prod\backend\database.sqlite",
    r"D:\deploy\testai_community_prod\backend\database_prod.sqlite",
    r"D:\deploy\testai_community_prod\backend\database.sqlite",
]


def find_db() -> Path:
    env = os.environ.get("DATABASE_URL", "")
    if env.startswith("sqlite:///"):
        p = Path(env.replace("sqlite:///", "").lstrip("/"))
        if p.exists():
            return p
    for c in CANDIDATES:
        p = Path(c)
        if p.exists():
            return p
    for name in ("database_prod.sqlite", "database.sqlite"):
        p = Path(name)
        if p.exists():
            return p
    sys.exit("!! 找不到数据库（database_prod.sqlite / database.sqlite），请把本脚本放到 backend 目录运行")


def backup_db(db: Path) -> None:
    bak = db.with_name(db.name + ".bak_fix_aas_title")
    if bak.exists():
        print(f"  ~ 备份已存在，跳过：{bak.name}")
        return
    shutil.copy2(db, bak)
    print(f"  + 备份 → {bak}")


def fetch_action(conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute(
        "SELECT id, title, status, week_key, owner_id FROM tm_actions WHERE id=?",
        (ACTION_ID,),
    ).fetchone()
    if row is None:
        sys.exit(f"!! 未找到 Action id={ACTION_ID}")
    return row


def update_title(conn: sqlite3.Connection) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for attempt in range(1, 6):  # 后端在跑，偶发写锁时重试
        try:
            conn.execute(
                "UPDATE tm_actions SET title=?, updated_at=? WHERE id=?",
                (NEW_TITLE, now, ACTION_ID),
            )
            conn.commit()
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < 5:
                print(f"  ~ 数据库被占用（第{attempt}次），1 秒后重试…")
                time.sleep(1)
            else:
                raise


def main() -> None:
    try:  # 防 GBK 控制台打印中文报错
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    db = find_db()
    print(f"== 修复 Action 标题 ==")
    print(f"  数据库: {db}")
    backup_db(db)

    conn = sqlite3.connect(db, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        row = fetch_action(conn)
        print(f"  当前: title={row['title']!r} status={row['status']} week={row['week_key']}")
        if row["title"] == NEW_TITLE:
            print("  ✓ 已是新标题，无需修改")
            return
        if row["title"] != OLD_TITLE:
            sys.exit(f"!! 标题不匹配（期望 {OLD_TITLE!r}），为安全起见不修改；如确认要改请手动处理")
        update_title(conn)
        row2 = fetch_action(conn)
        if row2["title"] != NEW_TITLE:
            sys.exit("!! 修改后回读校验失败，请从备份恢复并人工检查")
        print(f"  ✓ 修改完成：{OLD_TITLE!r} → {NEW_TITLE!r}")
        print("  无需重启后端，刷新页面即可生效")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
