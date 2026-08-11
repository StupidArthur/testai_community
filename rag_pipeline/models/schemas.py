"""
Chunk 与 Pipeline 相关数据结构定义。

入库全流程禁止 LLM；chunk 正文必须与原文逐字一致（仅允许删除噪音字符）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    """返回 UTC ISO8601 时间戳（带 Z）。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Chunk(BaseModel):
    """写入向量库的语义单元。"""

    chunk_id: str
    doc_id: str
    doc_title: str
    raw_text: str
    chunk_text: str
    chapter_path: str
    heading_level: int = 0
    chunk_index: int
    prev_chunk_id: str | None = None
    next_chunk_id: str | None = None
    is_table: bool = False
    is_list_block: bool = False
    key_entities: list[str] = Field(default_factory=list)
    doc_summary: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)


class QualityReport(BaseModel):
    """阶段五质检报告。"""

    fabrication_passed: bool = False
    fabrication_failures: list[str] = Field(default_factory=list)
    coverage_ratio: float = 0.0
    coverage_passed: bool = False
    exact_duplicates_removed: int = 0
    fuzzy_duplicates_removed: int = 0
    semantic_duplicates_removed: int = 0
    chunk_count_before: int = 0
    chunk_count_after: int = 0
    details: dict[str, Any] = Field(default_factory=dict)


class DocumentStatus(BaseModel):
    """文档处理状态。"""

    doc_id: str
    status: str  # pending | processing | completed | failed
    message: str = ""
    quality_report: QualityReport | None = None
    chunk_count: int = 0
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class PipelineResult(BaseModel):
    """Pipeline 完整输出。"""

    doc_id: str
    doc_title: str
    raw_text: str
    cleaned_text: str = ""
    chunks: list[Chunk] = Field(default_factory=list)
    quality_report: QualityReport | None = None
    doc_summary: str = ""
