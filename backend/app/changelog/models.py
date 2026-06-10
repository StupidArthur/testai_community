from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.core.database import Base


class ChangelogEntry(Base):
    __tablename__ = "changelog_entries"

    id = Column(Integer, primary_key=True, index=True)
    version = Column(String(32), nullable=False, unique=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, default="")
    published_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    publisher = relationship("User", lazy="selectin")
