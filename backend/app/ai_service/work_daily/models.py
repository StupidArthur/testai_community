"""
工作日报审核结果（内存模型，非 ORM）。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class WorkItem(BaseModel):
    """单项工作：种类 + 描述 + 工时 + 占比。"""

    category: str = ""
    description: str = ""
    hours: float = 0.0
    ratio: float = 0.0


class WorkDailyAuditResult(BaseModel):
    """Skill 审核输出（解析后）。"""

    valid: bool = True
    validation_issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    work_items: list[WorkItem] = Field(default_factory=list)
    total_hours: float = 0.0
    dimension_coverage: list[str] = Field(default_factory=list)
    missing_dimensions: list[str] = Field(default_factory=list)
    feedback: str = ""
    summary: str = ""
