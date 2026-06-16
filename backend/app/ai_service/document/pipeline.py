"""
文档处理流水线：加载 → 文字提取 → 图片 VL 描述 → 合并为 DocumentProcessResult。
"""

from __future__ import annotations

import logging
from pathlib import Path

from .chunking import blocks_to_chunks
from .loaders import load_document_text_and_images, text_to_blocks
from .schemas import DocumentProcessResult
from .vision import describe_images

log = logging.getLogger(__name__)


async def process_document(file_path: Path) -> DocumentProcessResult:
    """
    处理单个文档文件，返回结构化结果。

    :param file_path: 本地文档绝对路径
    """
    path = Path(file_path)
    filename = path.name
    warnings: list[str] = []

    text, image_paths, load_warnings = load_document_text_and_images(path)
    warnings.extend(load_warnings)

    blocks = text_to_blocks(text, source=filename)
    if image_paths:
        image_blocks = await describe_images(image_paths, source=filename)
        blocks.extend(image_blocks)

    plain_parts = [b.text for b in blocks if b.text.strip()]
    plain_text = "\n\n".join(plain_parts)

    return DocumentProcessResult(
        filename=filename,
        plain_text=plain_text,
        blocks=blocks,
        asset_count=len(image_paths),
        warnings=warnings,
    )


async def process_document_to_chunks(file_path: Path) -> tuple[DocumentProcessResult, list[dict]]:
    """处理文档并直接返回 chunk 列表（供知识库入库）。"""
    result = await process_document(file_path)
    chunks = blocks_to_chunks(result.blocks)
    return result, chunks
