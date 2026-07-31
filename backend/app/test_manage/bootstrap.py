"""
test_manage 启动：重建 tm_* 表结构，确保 manager 账号存在。
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.auth.service import hash_password
from app.platform.database import Base, SessionLocal
from app.test_manage.config import (
    DEFAULT_MANAGER_PASSWORD,
    DEFAULT_MANAGER_USERNAME,
    TM_TABLE_NAMES,
)
from app.test_manage import models as _models  # noqa: F401 — 注册 metadata

log = logging.getLogger("app.test_manage")

# 结构版本：变更 schema 时递增，触发 drop + create
TM_SCHEMA_VERSION = "3-daily-one-per-action-day"


def _drop_tm_tables(engine: Engine) -> None:
    insp = inspect(engine)
    existing = set(insp.get_table_names())
    with engine.begin() as conn:
        for name in TM_TABLE_NAMES:
            if name in existing:
                conn.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
                log.warning("dropped table %s for schema rebuild", name)


def _ensure_schema_version_table(engine: Engine) -> str | None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS tm_schema_meta ("
                "key VARCHAR PRIMARY KEY, value VARCHAR NOT NULL)"
            )
        )
        row = conn.execute(
            text("SELECT value FROM tm_schema_meta WHERE key='version'")
        ).fetchone()
        return row[0] if row else None


def _set_schema_version(engine: Engine, version: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM tm_schema_meta WHERE key='version'"))
        conn.execute(
            text("INSERT INTO tm_schema_meta(key, value) VALUES('version', :v)"),
            {"v": version},
        )


def ensure_manager_user() -> None:
    """保证测试管理员 manager / 123456 存在（角色 Manager）。"""
    db: Session = SessionLocal()
    try:
        row = db.query(User).filter(User.username == DEFAULT_MANAGER_USERNAME).first()
        if row:
            if row.role != UserRole.Manager:
                row.role = UserRole.Manager
                db.commit()
                log.info("updated user %s role -> Manager", DEFAULT_MANAGER_USERNAME)
            if not (row.real_name or "").strip():
                row.real_name = "测试管理员"
                db.commit()
            return
        db.add(
            User(
                username=DEFAULT_MANAGER_USERNAME,
                password_hash=hash_password(DEFAULT_MANAGER_PASSWORD),
                role=UserRole.Manager,
                real_name="测试管理员",
            )
        )
        db.commit()
        log.info(
            "created test manager user %s / %s",
            DEFAULT_MANAGER_USERNAME,
            DEFAULT_MANAGER_PASSWORD,
        )
    finally:
        db.close()


def ensure_test_manage_startup(engine: Engine) -> None:
    """
    若 schema 版本不一致则重建全部 tm_* 表（开发期允许丢数据）。
    """
    current = _ensure_schema_version_table(engine)
    if current != TM_SCHEMA_VERSION:
        log.warning(
            "tm schema %s -> %s, rebuilding tables", current, TM_SCHEMA_VERSION
        )
        _drop_tm_tables(engine)
        Base.metadata.create_all(
            bind=engine,
            tables=[
                _models.TmProject.__table__,
                _models.TmDomain.__table__,
                _models.TmTask.__table__,
                _models.TmTaskTester.__table__,
                _models.TmTaskUpdateLog.__table__,
                _models.TmAction.__table__,
                _models.TmActionCorrection.__table__,
                _models.TmDailyUpdate.__table__,
            ],
        )
        _set_schema_version(engine, TM_SCHEMA_VERSION)
    # 推送表增量创建，不随 TM_SCHEMA_VERSION 重建清空
    Base.metadata.create_all(
        bind=engine,
        tables=[
            _models.TmPushSnapshot.__table__,
            _models.TmPushRun.__table__,
        ],
    )
    ensure_manager_user()
    log.info("test_manage ready (schema=%s, week=Wed 18:00)", TM_SCHEMA_VERSION)
