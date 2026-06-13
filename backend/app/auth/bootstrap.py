"""auth 模块启动初始化：保证默认 Admin 存在。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.platform.database import SessionLocal
from app.auth.models import User, UserRole
from app.auth.service import hash_password

# 首次部署 / 空库时自动创建的默认管理员（可通过 seed 覆盖同名校验逻辑）
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin"


def ensure_default_admin() -> None:
    """若 users 表为空则创建 admin/admin；已有用户则跳过。"""
    db: Session = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return
        admin = User(
            username=DEFAULT_ADMIN_USERNAME,
            password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
            role=UserRole.Admin,
        )
        db.add(admin)
        db.commit()
    finally:
        db.close()
