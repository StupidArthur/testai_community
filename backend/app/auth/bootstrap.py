"""auth 模块启动初始化：保证默认 Admin 存在；补齐 real_name 列与已知姓名。"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.platform.database import SessionLocal, engine
from app.auth.models import User, UserRole
from app.auth.service import hash_password

log = logging.getLogger("app.auth")

# 首次部署 / 空库时自动创建的默认管理员（可通过 seed 覆盖同名校验逻辑）
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin"

# 登录名 → 真实姓名（与测试计划表一致；启动时回填空姓名）
USERNAME_TO_REAL_NAME: dict[str, str] = {
    "admin": "管理员",
    "manager": "测试管理员",
    "无": "无",
    "hj": "黄婧",
    "xiaojun": "袁小君",
    "zhengzhifang": "郑志方",
    "yexuewu": "叶学武",
    "liuyibin": "刘义斌",
    "dingqiao": "丁乔",
    "zhangxue": "张雪",
    "liuzhen": "刘震",
    "youjiaxin": "尤佳欣",
    "wuding": "吴鼎",
    "liujia": "刘佳",
    "yuanqi": "袁琦",
    "liujie": "刘洁",
    "yexueli": "叶学莉",
    "zhangwen": "张雯",
    "xuwenyao": "徐文耀",
    "youyong": "尤勇",
    "zhangying": "张莹",
    "wuxiao": "吴萧",
    "sunhoukai": "孙厚凯",
    "liliping": "李莉萍",
    "lihehai": "李和海",
    "sunyu": "孙瑜",
    "liuhao": "刘灏",
    "xiajia": "夏嘉",
    "tongshuang": "童霜",
}


def ensure_real_name_column() -> None:
    """SQLite 增量加列：users.real_name。"""
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "real_name" in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE users ADD COLUMN real_name VARCHAR NOT NULL DEFAULT ''")
        )
    log.info("added users.real_name column")


def backfill_real_names() -> None:
    """仅给「真实姓名为空」的已知账号补全；不覆盖 Admin 手工修改。"""
    db: Session = SessionLocal()
    try:
        updated = 0
        for row in db.query(User).all():
            if (row.real_name or "").strip():
                continue
            mapped = USERNAME_TO_REAL_NAME.get(row.username)
            if not mapped:
                continue
            row.real_name = mapped
            updated += 1
        if updated:
            db.commit()
            log.info("backfilled real_name for %s users", updated)
    finally:
        db.close()


def ensure_default_admin() -> None:
    """
    启动钩子：补列 → 默认 admin → 回填真实姓名。
    """
    ensure_real_name_column()
    db: Session = SessionLocal()
    try:
        if db.query(User).count() == 0:
            admin = User(
                username=DEFAULT_ADMIN_USERNAME,
                password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
                role=UserRole.Admin,
                real_name=USERNAME_TO_REAL_NAME.get(DEFAULT_ADMIN_USERNAME, "管理员"),
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()
    backfill_real_names()
