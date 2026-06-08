import enum
import uuid

from sqlalchemy import Column, String, Enum, Text, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class TaskStatus(str, enum.Enum):
    Pending = "pending"
    Processing = "processing"
    Completed = "completed"
    Failed = "failed"


class LLMTask(Base):
    __tablename__ = "llm_tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    skill_name = Column(String, nullable=False)
    status = Column(Enum(TaskStatus), default=TaskStatus.Pending, nullable=False)
    result = Column(Text, nullable=True)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())