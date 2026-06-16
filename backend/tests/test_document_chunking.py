"""文档分块单元测试。"""

from app.ai_service.document.chunking import blocks_to_chunks
from app.ai_service.document.schemas import DocumentBlock, DocumentBlockType


def test_blocks_to_chunks_basic():
    blocks = [
        DocumentBlock(
            block_type=DocumentBlockType.TEXT,
            text="第一段内容。" * 50,
            source="a.md",
        ),
        DocumentBlock(
            block_type=DocumentBlockType.IMAGE_CAPTION,
            text="[图片1描述] 流程图：开始 -> 处理 -> 结束",
            source="a.md",
        ),
    ]
    chunks = blocks_to_chunks(blocks, chunk_size=100, overlap=20)
    assert len(chunks) >= 2
    assert all("id" in c and "text" in c and "metadata" in c for c in chunks)


def test_empty_blocks():
    assert blocks_to_chunks([]) == []
