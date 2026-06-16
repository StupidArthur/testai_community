"""knowledge_base 启动/关闭与 schema 补丁。"""

from __future__ import annotations

import sqlite3

from sqlalchemy.engine import Engine

from app.platform.database import Base

from .models import KnowledgeBase, KnowledgeChatMessage, KnowledgeDocument
from .worker import start_background_tasks, stop_background_tasks


def ensure_knowledge_base_startup(engine: Engine) -> None:
    """确保知识库相关表存在，并执行增量 schema 补丁。"""
    Base.metadata.create_all(
        bind=engine,
        tables=[
            KnowledgeBase.__table__,
            KnowledgeDocument.__table__,
            KnowledgeChatMessage.__table__,
        ],
    )
    migrate_schema(engine)


def migrate_schema(db_engine: Engine) -> None:
    """knowledge_documents 表增量补丁（添加 user_id）。"""
    db_path = str(db_engine.url).replace("sqlite:///", "")
    if not db_path:
        return
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(knowledge_documents)")
    existing = {row[1] for row in cursor.fetchall()}
    if "user_id" not in existing:
        cursor.execute(
            "ALTER TABLE knowledge_documents ADD COLUMN user_id INTEGER DEFAULT 0"
        )
        # 历史文档归属到知识库创建者
        cursor.execute(
            """
            UPDATE knowledge_documents
            SET user_id = (
                SELECT user_id FROM knowledge_bases
                WHERE knowledge_bases.id = knowledge_documents.kb_id
            )
            WHERE user_id = 0 OR user_id IS NULL
            """
        )
    conn.commit()
    conn.close()


async def on_startup() -> None:
    await start_background_tasks()


async def on_shutdown() -> None:
    await stop_background_tasks()
