"""
清空开发环境知识库相关业务数据（文档 / 清洗任务 / 向量 / 落盘）。

保留：用户账号、默认知识库壳子会在重启后由 ensure_default 重建。
不清理：test_manage、auth、其它业务表。

用法（在 backend 目录、已加载 .env）：
  python -m app.knowledge_base.wipe_dev_data
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path

from app.platform.config import DATABASE_URL, KNOWLEDGE_BASE_CHROMA_DIR, KNOWLEDGE_BASE_DATA_DIR, PROJECT_ROOT

log = logging.getLogger(__name__)

# 知识库 / 清洗相关表（按外键依赖顺序删除）
_TABLES_TO_CLEAR = (
    "dc_paragraph_units",
    "dc_knowledge_units",
    "dc_clean_jobs",
    "dc_anchor_nodes",
    "knowledge_chat_messages",
    "knowledge_documents",
    "knowledge_bases",
)

# 落盘子目录（整目录清空后重建）
_FS_SUBDIRS = ("clean", "chroma")


def _assert_dev_env() -> None:
    """禁止在生产 ENV 下误清。"""
    import os

    env = (os.getenv("ENV") or "dev").strip().lower()
    if env in {"production", "prod"}:
        raise RuntimeError(f"拒绝清理：当前 ENV={env}，仅允许开发环境执行")


def _resolve_sqlite_path(database_url: str) -> Path:
    """解析 sqlite URL 为绝对路径。"""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise RuntimeError(f"仅支持 sqlite 开发库清理，当前 DATABASE_URL={database_url}")
    raw = database_url[len(prefix) :]
    path = Path(raw)
    if not path.is_absolute():
        # uvicorn/run.py 工作目录一般为 backend/
        path = (Path.cwd() / path).resolve()
        if not path.is_file():
            alt = (PROJECT_ROOT / "backend" / raw).resolve()
            if alt.is_file():
                path = alt
    return path


def wipe_knowledge_base_dev_data(
    *,
    database_url: str | None = None,
    data_dir: Path | None = None,
    chroma_dir: Path | None = None,
    dry_run: bool = False,
) -> dict:
    """
    清空知识库模块开发数据。

    返回：统计信息 dict。
    """
    _assert_dev_env()
    url = database_url or DATABASE_URL
    db_path = _resolve_sqlite_path(url)
    kb_data = Path(data_dir or KNOWLEDGE_BASE_DATA_DIR)
    chroma = Path(chroma_dir or KNOWLEDGE_BASE_CHROMA_DIR)

    stats: dict = {
        "database": str(db_path),
        "tables_cleared": {},
        "dirs_removed": [],
        "dry_run": dry_run,
    }

    if not db_path.is_file():
        raise FileNotFoundError(f"数据库不存在: {db_path}")

    # 1) 清表
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=OFF")
        for table in _TABLES_TO_CLEAR:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            if not cur.fetchone():
                stats["tables_cleared"][table] = "missing"
                continue
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            n = int(cur.fetchone()[0])
            if not dry_run:
                cur.execute(f"DELETE FROM {table}")
            stats["tables_cleared"][table] = n
        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    # 2) 清落盘：kb 目录下 clean / chroma / 各 kb_id 文件夹
    if kb_data.is_dir():
        for child in list(kb_data.iterdir()):
            # 保留目录本身，删除内容
            if dry_run:
                stats["dirs_removed"].append(str(child))
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
                stats["dirs_removed"].append(str(child))
            elif child.is_file():
                child.unlink(missing_ok=True)
                stats["dirs_removed"].append(str(child))

    if not dry_run:
        chroma.mkdir(parents=True, exist_ok=True)
        (kb_data / "clean").mkdir(parents=True, exist_ok=True)

    log.info("wipe_knowledge_base_dev_data done: %s", stats)
    return stats


def main() -> None:
    """直接执行清空（非 dry_run）。"""
    logging.basicConfig(level=logging.INFO)
    result = wipe_knowledge_base_dev_data(dry_run=False)
    print("[wipe] done")
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
