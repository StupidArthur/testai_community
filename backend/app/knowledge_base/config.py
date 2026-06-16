"""
knowledge_base 模块常量。
"""

from __future__ import annotations

from app.platform.config import (
    KB_MAX_CONCURRENT_JOBS,
    KB_MAX_DOCS_PER_KB,
    KB_MAX_TOTAL_MB,
    KB_MAX_UPLOAD_MB,
    KNOWLEDGE_BASE_DATA_DIR,
)

# 支持的原始文档后缀（小写，含点）
ALLOWED_DOC_EXTENSIONS = {
    ".md",
    ".markdown",
    ".txt",
    ".doc",
    ".docx",
    ".pdf",
    ".pptx",
    ".xlsx",
}

# 文档处理队列轮询间隔（秒）
QUEUE_TICK_SEC = 2

# 单文档处理超时（秒）
DOCUMENT_PROCESS_TIMEOUT_SEC = 600

MAX_UPLOAD_BYTES = KB_MAX_UPLOAD_MB * 1024 * 1024
MAX_TOTAL_BYTES = KB_MAX_TOTAL_MB * 1024 * 1024
MAX_DOCS_PER_KB = KB_MAX_DOCS_PER_KB
MAX_CONCURRENT_JOBS = KB_MAX_CONCURRENT_JOBS

RAW_SUBDIR = "raw"
