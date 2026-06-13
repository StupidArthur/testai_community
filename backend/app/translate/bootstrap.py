"""translate 模块启动/关闭与 schema 补丁（由 platform.factory lifespan 调用）。"""

from __future__ import annotations

import sqlite3

from .worker import start_background_tasks, stop_background_tasks


def migrate_schema(db_engine) -> None:
    """translate_jobs 表结构增量补丁（待 Alembic 替代）。"""
    db_path = str(db_engine.url).replace("sqlite:///", "")
    if not db_path:
        return
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(translate_jobs)")
    existing = {row[1] for row in cursor.fetchall()}
    for col in ("name", "username"):
        if col not in existing:
            cursor.execute(
                f"ALTER TABLE translate_jobs ADD COLUMN {col} VARCHAR DEFAULT ''"
            )
    conn.commit()
    conn.close()


async def on_startup() -> None:
    await start_background_tasks()


async def on_shutdown() -> None:
    await stop_background_tasks()
