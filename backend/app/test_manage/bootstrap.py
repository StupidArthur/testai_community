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


def _ensure_daily_is_blocking_column(engine: Engine) -> None:
    """增量加 is_blocking；并修复「曾勾选阻塞、被表单旧值写丢」的最新日更。"""
    insp = inspect(engine)
    if "tm_daily_updates" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("tm_daily_updates")}
    with engine.begin() as conn:
        if "is_blocking" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE tm_daily_updates "
                    "ADD COLUMN is_blocking BOOLEAN NOT NULL DEFAULT 0"
                )
            )
            # 存量：原先有风险文案的视为阻塞，避免日报突然清空
            conn.execute(
                text(
                    "UPDATE tm_daily_updates SET is_blocking = 1 "
                    "WHERE risk_blocker IS NOT NULL AND TRIM(risk_blocker) != ''"
                )
            )
            log.info("added column tm_daily_updates.is_blocking")

        # 修复：同一 Action 历史上勾选过阻塞，但最新一条有风险文案却 is_blocking=0
        # （日更 Form 未同步勾选状态时会写丢）
        conn.execute(
            text(
                """
                UPDATE tm_daily_updates
                SET is_blocking = 1
                WHERE id IN (
                  SELECT d.id
                  FROM tm_daily_updates d
                  WHERE d.risk_blocker IS NOT NULL
                    AND TRIM(d.risk_blocker) != ''
                    AND (d.is_blocking = 0 OR d.is_blocking IS NULL)
                    AND EXISTS (
                      SELECT 1 FROM tm_daily_updates h
                      WHERE h.action_id = d.action_id
                        AND h.is_blocking = 1
                        AND (
                          h.report_date < d.report_date
                          OR (
                            h.report_date = d.report_date
                            AND h.id != d.id
                          )
                        )
                    )
                    AND NOT EXISTS (
                      SELECT 1 FROM tm_daily_updates n
                      WHERE n.action_id = d.action_id
                        AND (
                          n.report_date > d.report_date
                          OR (
                            n.report_date = d.report_date
                            AND n.updated_at > d.updated_at
                          )
                        )
                    )
                )
                """
            )
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


def _ensure_task_req_stage_columns(engine: Engine) -> None:
    """增量：tm_tasks 需求进展字段；缺省回填存量数据。"""
    insp = inspect(engine)
    if "tm_tasks" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("tm_tasks")}
    alters: list[tuple[str, str]] = [
        ("req_stage", "VARCHAR NOT NULL DEFAULT 'pending_dev'"),
        ("expected_handover_at", "DATE"),
        ("actual_handover_at", "DATE"),
        ("test_started_at", "DATE"),
        ("expected_test_end_at", "DATE"),
        ("test_ended_at", "DATE"),
    ]
    with engine.begin() as conn:
        for name, decl in alters:
            if name in cols:
                continue
            conn.execute(text(f"ALTER TABLE tm_tasks ADD COLUMN {name} {decl}"))
            log.info("added column tm_tasks.%s", name)
        # 存量：进行中 → 测试中；已完成 → 测试完成
        if "req_stage" not in cols:
            conn.execute(
                text(
                    "UPDATE tm_tasks SET req_stage = 'testing' "
                    "WHERE status = 'published' AND (req_stage IS NULL OR req_stage = '' OR req_stage = 'pending_dev')"
                )
            )
            conn.execute(
                text(
                    "UPDATE tm_tasks SET req_stage = 'test_done' "
                    "WHERE status = 'done'"
                )
            )


def _backfill_missing_req_stage_dates(engine: Engine) -> None:
    """演示/存量：测试中/测试完成缺必填日期时补合理日期，避免大屏满屏「未填」。"""
    from datetime import date, timedelta

    from app.test_manage.config import REQ_STAGE_TEST_DONE, REQ_STAGE_TESTING
    from app.test_manage.models import TmTask

    insp = inspect(engine)
    if "tm_tasks" not in set(insp.get_table_names()):
        return
    today = date.today()
    with Session(engine) as db:
        testing_rows = (
            db.query(TmTask)
            .filter(TmTask.req_stage == REQ_STAGE_TESTING)
            .filter((TmTask.test_started_at.is_(None)) | (TmTask.expected_test_end_at.is_(None)))
            .all()
        )
        for t in testing_rows:
            if t.test_started_at is None:
                t.test_started_at = today - timedelta(days=3)
            if t.expected_test_end_at is None:
                t.expected_test_end_at = today + timedelta(days=4)
        done_rows = (
            db.query(TmTask)
            .filter(TmTask.req_stage == REQ_STAGE_TEST_DONE)
            .filter(TmTask.test_ended_at.is_(None))
            .all()
        )
        for t in done_rows:
            if t.test_started_at is None:
                t.test_started_at = today - timedelta(days=7)
            if t.expected_test_end_at is None:
                t.expected_test_end_at = today - timedelta(days=1)
            t.test_ended_at = today - timedelta(days=1)
        if testing_rows or done_rows:
            db.commit()
            log.info(
                "backfilled req-stage dates: testing=%s test_done=%s",
                len(testing_rows),
                len(done_rows),
            )


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
    # 推送表 + 周周期/Task 周进度：增量创建，不随 TM_SCHEMA_VERSION 重建清空
    Base.metadata.create_all(
        bind=engine,
        tables=[
            _models.TmPushSnapshot.__table__,
            _models.TmPushRun.__table__,
            _models.TmWeekPeriod.__table__,
            _models.TmTaskWeekProgress.__table__,
            _models.TmTaskStageSnapshot.__table__,
        ],
    )
    _ensure_daily_is_blocking_column(engine)
    _ensure_task_req_stage_columns(engine)
    _backfill_missing_req_stage_dates(engine)
    ensure_manager_user()
    # 预热当前周窗口（无则按经典周三规则创建）
    db = SessionLocal()
    try:
        from app.test_manage.period import get_or_create_active_period

        get_or_create_active_period(db)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("ensure week period failed")
    finally:
        db.close()
    log.info("test_manage ready (schema=%s)", TM_SCHEMA_VERSION)
