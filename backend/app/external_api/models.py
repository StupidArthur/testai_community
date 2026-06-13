"""external_api ORM 模型。"""

import enum
import hashlib
import uuid

from passlib.context import CryptContext
from sqlalchemy import Column, Integer, String, Enum, Text, DateTime
from sqlalchemy.sql import func

from app.platform.database import Base

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TaskStatus(str, enum.Enum):
    Pending = "pending"
    Processing = "processing"
    Completed = "completed"
    Failed = "failed"


class ServiceAccount(Base):
    """外部 API 服务账户（X-API-Key）。"""

    __tablename__ = "service_accounts"

    id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String, nullable=False)
    token_fingerprint = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LLMTask(Base):
    __tablename__ = "llm_tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    skill_name = Column(String, nullable=False)
    status = Column(Enum(TaskStatus), default=TaskStatus.Pending, nullable=False)
    result = Column(Text, nullable=True)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def api_key_fingerprint(key: str) -> str:
    """API Key SHA256 指纹，用于索引查找。"""
    return hashlib.sha256(key.encode()).hexdigest()


def hash_api_key(key: str) -> str:
    """bcrypt 哈希 API Key 明文。"""
    return _pwd_context.hash(key)


def verify_api_key_plain(key: str, token_hash: str) -> bool:
    return _pwd_context.verify(key, token_hash)
