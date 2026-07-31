import enum

from sqlalchemy import Column, Integer, String, Enum, DateTime
from sqlalchemy.sql import func

from app.platform.database import Base


class UserRole(str, enum.Enum):
    Engineer = "Engineer"
    Admin = "Admin"
    Manager = "Manager"  # 测试管理员（项目管理最高权限）


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    # 真实姓名（企微推送 / 看板展示优先用此字段）
    real_name = Column(String, nullable=False, default="", server_default="")
    password_hash = Column(String, nullable=False)
    # native_enum=False：SQLite 以 VARCHAR 存储，便于扩展 Manager
    role = Column(
        Enum(
            UserRole,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=UserRole.Engineer,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
