"""
文档处理数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DocumentBlockType(str, Enum):
    """文档块类型。"""

    TEXT = "text"
    IMAGE_CAPTION = "image_caption"
    TABLE = "table"


@dataclass
class DocumentBlock:
    """文档中的一个语义块（文字或图片描述）。"""

    block_type: DocumentBlockType
    text: str
    page: int | None = None
    source: str = ""
    image_path: str | None = None


@dataclass
class DocumentProcessResult:
    """文档处理完整结果。"""

    filename: str
    plain_text: str
    blocks: list[DocumentBlock] = field(default_factory=list)
    asset_count: int = 0
    warnings: list[str] = field(default_factory=list)
