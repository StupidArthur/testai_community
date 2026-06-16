"""
文档视觉理解：调用 Ollama Qwen2.5-VL 描述图片/流程图。
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.ai_service.providers.ollama import get_ollama_provider

from .schemas import DocumentBlock, DocumentBlockType

log = logging.getLogger(__name__)


async def describe_images(
    image_paths: list[Path],
    *,
    source: str,
    page: int | None = None,
) -> list[DocumentBlock]:
    """
    对图片列表逐张调用 VL 模型，生成 IMAGE_CAPTION 块。

    单张失败时记录日志并跳过，不中断整批处理。
    """
    provider = get_ollama_provider()
    blocks: list[DocumentBlock] = []
    for idx, image_path in enumerate(image_paths, start=1):
        try:
            caption = await provider.describe_image(image_path)
            blocks.append(
                DocumentBlock(
                    block_type=DocumentBlockType.IMAGE_CAPTION,
                    text=f"[图片{idx}描述] {caption}",
                    page=page,
                    source=source,
                    image_path=str(image_path),
                )
            )
        except Exception as exc:
            log.warning("图片描述失败 %s: %s", image_path, exc)
    return blocks
