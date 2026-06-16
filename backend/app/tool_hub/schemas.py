"""
tool_hub Pydantic 模型。
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ToolKind = Literal["client", "platform"]


class ToolVersionOut(BaseModel):
    id: str
    version_label: str
    manual_md: str
    changelog_md: str
    artifact_filename: str | None
    created_by_user_id: int
    creator_username: str
    created_at: datetime


class ToolCardOut(BaseModel):
    """工具集首页卡片。"""

    id: str
    slug: str
    display_name: str
    tool_kind: ToolKind
    tool_type: str
    link_url: str | None
    owner_user_id: int
    owner_username: str
    enabled: bool
    latest_version: str | None
    has_artifact: bool
    created_at: datetime
    updated_at: datetime


class ToolDetailOut(BaseModel):
    """工具详情页：含合并后的 Markdown 文档。"""

    id: str
    slug: str
    display_name: str
    tool_kind: ToolKind
    tool_type: str
    link_url: str | None
    owner_user_id: int
    owner_username: str
    enabled: bool
    latest_version: str | None
    has_artifact: bool
    combined_markdown: str
    versions: list[ToolVersionOut]
    created_at: datetime
    updated_at: datetime
    can_edit: bool
    can_delete: bool


class ToolUpdateRequest(BaseModel):
    display_name: str | None = None
    link_url: str | None = None
    tool_type: str | None = None
    enabled: bool | None = None


class ToolCreateFormMeta(BaseModel):
    """用于校验 multipart 表单字段（router 内手动解析后校验）。"""

    slug: str = Field(min_length=2, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    tool_kind: ToolKind
    tool_type: str = "default"
    link_url: str | None = None
    version_label: str = Field(default="1.0.0", max_length=32)
    manual_md: str = Field(min_length=1)


class ToolVersionCreateMeta(BaseModel):
    version_label: str = Field(min_length=1, max_length=32)
    changelog_md: str = Field(min_length=1)
    manual_md: str | None = None
