import enum

from sqlalchemy import Column, Integer, String, Enum, DateTime
from sqlalchemy.sql import func

from app.platform.database import Base


class UserRole(str, enum.Enum):
    Engineer = "Engineer"
    Admin = "Admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.Engineer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())