"""
RAG Embedding：封装 Ollama 向量化。
"""

from __future__ import annotations

from app.ai_service.providers.ollama import get_ollama_provider


async def embed_text(text: str) -> list[float]:
    """单条文本向量化。"""
    return await get_ollama_provider().embed_text(text)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量文本向量化。"""
    return await get_ollama_provider().embed_texts(texts)
