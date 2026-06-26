"""
data_cleaning 模块常量。
"""

from __future__ import annotations

from app.knowledge_base.config import ALLOWED_DOC_EXTENSIONS

# 清洗任务队列
QUEUE_TICK_SEC = 2
JOB_PROCESS_TIMEOUT_SEC = 1800
MAX_CONCURRENT_CLEAN_JOBS = 1
# 超过该秒数无心跳的 processing 任务视为僵死（如后端重启），自动重新入队
STALE_PROCESSING_SEC = 180
# 单任务内并行处理段落数（MiniMax 调用并发，显著缩短长文档耗时）
PARAGRAPH_CONCURRENCY = 4

# 单任务最多段落数（控制 Token）
MAX_PARAGRAPHS_PER_JOB = 120
# 低于此字符数的段落跳过 LLM 提炼
MIN_PARAGRAPH_CHARS = 120
# 段落原文入库最大长度
MAX_PARAGRAPH_RAW_CHARS = 12000

# 锚点向量匹配阈值（0~1，cosine 相似度近似）
ANCHOR_VECTOR_MATCH_THRESHOLD = 0.78
ANCHOR_VECTOR_REVIEW_THRESHOLD = 0.65

# 库内召回后再精判的最低相似度（distance 越小越相似，chroma cosine distance）
ALIGN_RECALL_MAX_DISTANCE = 0.55
ALIGN_MIN_CONFIDENCE = 0.7

DOC_TYPES = ("prd", "performance_report", "mixed", "general")

RAW_SUBDIR = "raw"

__all__ = [
    "ALLOWED_DOC_EXTENSIONS",
    "QUEUE_TICK_SEC",
    "MAX_PARAGRAPHS_PER_JOB",
    "MIN_PARAGRAPH_CHARS",
    "DOC_TYPES",
]
