"""
文档分块：将纯文本/块列表切分为适合向量检索的 chunk。
"""

from __future__ import annotations

import re
import uuid

from app.platform.config import KB_CHUNK_OVERLAP, KB_CHUNK_SIZE

from .schemas import DocumentBlock, DocumentBlockType


def _split_long_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """按字符长度切分长文本，保留重叠区。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _split_by_headings(text: str) -> list[str]:
    """按 Markdown 标题行粗分节。"""
    lines = text.splitlines()
    sections: list[str] = []
    current: list[str] = []
    for line in lines:
        if re.match(r"^#{1,6}\s+", line) and current:
            sections.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current).strip())
    return [s for s in sections if s]


def blocks_to_chunks(
    blocks: list[DocumentBlock],
    *,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[dict]:
    """
    将 DocumentBlock 列表转为带元数据的 chunk 列表。

    每个 chunk 包含：id, text, metadata（page, block_type, source）
    """
    size = chunk_size if chunk_size is not None else KB_CHUNK_SIZE
    ov = overlap if overlap is not None else KB_CHUNK_OVERLAP
    chunks: list[dict] = []

    for block in blocks:
        text = block.text.strip()
        if not text:
            continue

        if block.block_type == DocumentBlockType.IMAGE_CAPTION:
            piece_texts = [text]
        else:
            sections = _split_by_headings(text)
            piece_texts: list[str] = []
            for section in sections:
                piece_texts.extend(_split_long_text(section, size, ov))

        for piece in piece_texts:
            chunks.append(
                {
                    "id": f"chunk_{uuid.uuid4().hex[:12]}",
                    "text": piece,
                    "metadata": {
                        "page": block.page if block.page is not None else -1,
                        "block_type": block.block_type.value,
                        "source": block.source or "",
                        "image_path": block.image_path or "",
                    },
                }
            )
    return chunks
