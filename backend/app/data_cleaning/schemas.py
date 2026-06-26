"""Pydantic 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.data_cleaning.models import AnchorNode, CleanJob, KnowledgeUnit, ParagraphUnit
from app.data_cleaning.utils import loads_json


class AnchorNodeOut(BaseModel):
    id: str
    label: str
    parent_id: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    description: str = ""
    sort_order: int = 50
    enabled: bool = True

    model_config = {"from_attributes": True}


class AnchorNodeCreate(BaseModel):
    id: str = Field(..., min_length=2, max_length=64)
    label: str = Field(..., min_length=1, max_length=128)
    parent_id: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    description: str = ""
    sort_order: int = 50


class AnchorNodeUpdate(BaseModel):
    label: str | None = None
    parent_id: str | None = None
    synonyms: list[str] | None = None
    description: str | None = None
    sort_order: int | None = None
    enabled: bool | None = None


class CleanJobCreateMeta(BaseModel):
    kb_id: str
    doc_type: Literal["prd", "performance_report", "mixed", "general"] = "general"
    product: str = ""
    version: str = ""
    environment: str = ""
    note: str = ""


class AlignmentOut(BaseModel):
    relation: str = ""
    confidence: float = 0.0
    topic: str = ""
    new_claim: str = ""
    old_claim: str = ""
    recommended_action: str = ""
    reason: str = ""
    chunk_id: str | None = None
    old_ku_id: str | None = None
    old_filename: str = ""
    old_snippet: str = ""
    distance: float | None = None


class ParagraphUnitOut(BaseModel):
    id: str
    job_id: str
    seq: int
    section_path: str
    raw_text: str
    essence_markdown: str
    anchor_ids: list[str] = Field(default_factory=list)
    suggested_anchors: list[dict[str, Any]] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
    alignments: list[AlignmentOut] = Field(default_factory=list)
    review_status: str
    review_action: str
    ku_id: str | None = None
    skip_reason: str = ""

    model_config = {"from_attributes": True}


class ParagraphUpdate(BaseModel):
    essence_markdown: str | None = None
    anchor_ids: list[str] | None = None
    scope: dict[str, Any] | None = None
    review_status: Literal["pending", "approved", "skipped", "rejected"] | None = None
    review_action: Literal["add", "supersede", "coexist", "skip", "pending"] | None = None
    skip_reason: str | None = None


class CleanJobOut(BaseModel):
    id: str
    kb_id: str
    user_id: int
    username: str = ""
    filename: str
    file_size: int
    doc_type: str
    product: str
    version: str
    environment: str
    note: str
    status: str
    error: str | None = None
    paragraph_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CleanJobDetailOut(CleanJobOut):
    paragraphs: list[ParagraphUnitOut] = Field(default_factory=list)


class ApproveJobRequest(BaseModel):
    """批准任务：处理所有 pending 段落（已标记 skipped 的跳过）。"""
    paragraph_ids: list[str] | None = None


class ApproveJobResult(BaseModel):
    approved_count: int
    skipped_count: int
    ku_ids: list[str]


def anchor_to_out(node: AnchorNode) -> AnchorNodeOut:
    return AnchorNodeOut(
        id=node.id,
        label=node.label,
        parent_id=node.parent_id,
        synonyms=loads_json(node.synonyms_json, []),
        description=node.description or "",
        sort_order=node.sort_order,
        enabled=bool(node.enabled),
    )


def paragraph_to_out(p: ParagraphUnit) -> ParagraphUnitOut:
    align_raw = loads_json(p.alignment_json, [])
    alignments = [AlignmentOut(**a) if isinstance(a, dict) else AlignmentOut() for a in align_raw]
    return ParagraphUnitOut(
        id=p.id,
        job_id=p.job_id,
        seq=p.seq,
        section_path=p.section_path or "",
        raw_text=p.raw_text or "",
        essence_markdown=p.essence_markdown or "",
        anchor_ids=loads_json(p.anchor_ids_json, []),
        suggested_anchors=loads_json(p.suggested_anchors_json, []),
        scope=loads_json(p.scope_json, {}),
        alignments=alignments,
        review_status=p.review_status,
        review_action=p.review_action,
        ku_id=p.ku_id,
        skip_reason=p.skip_reason or "",
    )


def job_to_out(job: CleanJob, username: str = "") -> CleanJobOut:
    return CleanJobOut(
        id=job.id,
        kb_id=job.kb_id,
        user_id=job.user_id,
        username=username,
        filename=job.filename,
        file_size=job.file_size or 0,
        doc_type=job.doc_type,
        product=job.product or "",
        version=job.version or "",
        environment=job.environment or "",
        note=job.note or "",
        status=job.status,
        error=job.error,
        paragraph_count=job.paragraph_count or 0,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
