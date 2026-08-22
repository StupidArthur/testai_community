"""
RAG Pipeline 模块级配置（物理意义常量集中定义，避免魔法数字扩散）。
"""

from __future__ import annotations

import os
from pathlib import Path

# 切分软上限（字符）
CHUNK_SOFT_LIMIT = 500

# 质检阈值
COVERAGE_MIN_RATIO = 0.95
SIMHASH_SIMILARITY_MIN = 0.85
COSINE_SIMILARITY_MIN = 0.92

# 向量库
CHROMA_DIR = Path(
    os.environ.get("RAG_PIPELINE_CHROMA_DIR", str(Path(__file__).resolve().parent / ".data" / "chroma"))
)
CHROMA_COLLECTION = os.environ.get("RAG_PIPELINE_COLLECTION", "rag_pipeline_chunks")

# Embedding / Chat（复用现有 Ollama；入库只用 embed，不调用 LLM 生成正文）
OLLAMA_BASE_URL = (os.environ.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL") or "bge-m3:latest"
OLLAMA_CHAT_MODEL = os.environ.get("OLLAMA_CHAT_MODEL") or "qwen2.5:7b"

# 检索
RETRIEVE_TOP_K = 15
DOC_SUMMARY_PREFILTER_LIMIT = 20
