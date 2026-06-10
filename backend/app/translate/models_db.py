from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class TranslateJob(Base):
    __tablename__ = "translate_jobs"

    id = Column(String, primary_key=True)
    status = Column(String, nullable=False, default="queued", index=True)
    upload_path = Column(String, nullable=False)
    result_zip_path = Column(String, nullable=True)
    current_phase = Column(String, default="")
    current_step = Column(Integer, default=0)
    total_steps = Column(Integer, default=0)
    message = Column(Text, default="")
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
