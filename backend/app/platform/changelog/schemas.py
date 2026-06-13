"""changelog HTTP 请求/响应模型。"""

from typing import Optional

from pydantic import BaseModel, Field


class ChangelogCreate(BaseModel):
    version: str = Field(..., max_length=32, pattern=r"^\d+\.\d+\.\d+$")
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(default="", max_length=10000)


class ChangelogUpdate(BaseModel):
    version: Optional[str] = Field(None, max_length=32, pattern=r"^\d+\.\d+\.\d+$")
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, max_length=10000)


class ChangelogView(BaseModel):
    id: int
    version: str
    title: str
    content: str
    published_by: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_with_publisher(cls, entry) -> "ChangelogView":
        return cls(
            id=entry.id,
            version=entry.version,
            title=entry.title,
            content=entry.content or "",
            published_by=entry.publisher.username if entry.publisher else None,
            created_at=entry.created_at.isoformat(timespec="seconds") if entry.created_at else "",
            updated_at=entry.updated_at.isoformat(timespec="seconds") if entry.updated_at else "",
        )
