"""HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.service import RequireRole, get_current_user
from app.platform.database import get_db

from .schemas import (
    AnchorNodeCreate,
    AnchorNodeOut,
    AnchorNodeUpdate,
    ApproveJobRequest,
    ApproveJobResult,
    BatchReviewActionRequest,
    BatchReviewActionResult,
    CleanJobDetailOut,
    CleanJobOut,
    ParagraphUnitOut,
    ParagraphUpdate,
)
from .service import (
    approve_clean_job,
    batch_set_review_action,
    create_anchor_node,
    create_clean_job,
    get_clean_job_detail,
    list_anchor_nodes,
    list_clean_jobs,
    reprocess_clean_job,
    update_anchor_node,
    update_paragraph,
)

router = APIRouter(prefix="/api/data-cleaning", tags=["data-cleaning"])


@router.get("/jobs", response_model=list[CleanJobOut])
def api_list_jobs(
    kb_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CleanJobOut]:
    return list_clean_jobs(db, current_user, kb_id=kb_id)


@router.post("/jobs", response_model=CleanJobOut, status_code=201)
async def api_create_job(
    kb_id: str | None = Form(None),
    doc_type: str = Form("general"),
    product: str = Form(""),
    version: str = Form(""),
    environment: str = Form(""),
    note: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CleanJobOut:
    return await create_clean_job(
        db,
        current_user,
        file,
        kb_id=kb_id,
        doc_type=doc_type,
        product=product,
        version=version,
        environment=environment,
        note=note,
    )


@router.get("/jobs/{job_id}", response_model=CleanJobDetailOut)
def api_get_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CleanJobDetailOut:
    return get_clean_job_detail(db, current_user, job_id)


@router.post("/jobs/{job_id}/reprocess", response_model=CleanJobOut)
def api_reprocess_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CleanJobOut:
    return reprocess_clean_job(db, current_user, job_id)


@router.patch("/jobs/{job_id}/paragraphs/{paragraph_id}", response_model=ParagraphUnitOut)
def api_update_paragraph(
    job_id: str,
    paragraph_id: str,
    data: ParagraphUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ParagraphUnitOut:
    return update_paragraph(db, current_user, job_id, paragraph_id, data)


@router.post("/jobs/{job_id}/batch-review-action", response_model=BatchReviewActionResult)
def api_batch_review_action(
    job_id: str,
    data: BatchReviewActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BatchReviewActionResult:
    """批量设置本任务全部段落的入库操作（新增/替换/并存/跳过）。"""
    result = batch_set_review_action(db, current_user, job_id, data.review_action)
    return BatchReviewActionResult(**result)


@router.post("/jobs/{job_id}/approve", response_model=ApproveJobResult)
async def api_approve_job(
    job_id: str,
    data: ApproveJobRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApproveJobResult:
    ids = data.paragraph_ids if data else None
    return await approve_clean_job(db, current_user, job_id, paragraph_ids=ids)


@router.get("/anchors", response_model=list[AnchorNodeOut])
def api_list_anchors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AnchorNodeOut]:
    return list_anchor_nodes(db, current_user)


@router.post("/anchors", response_model=AnchorNodeOut, status_code=201)
def api_create_anchor(
    data: AnchorNodeCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(RequireRole(["Admin"])),
) -> AnchorNodeOut:
    return create_anchor_node(db, admin, data)


@router.patch("/anchors/{anchor_id}", response_model=AnchorNodeOut)
def api_update_anchor(
    anchor_id: str,
    data: AnchorNodeUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(RequireRole(["Admin"])),
) -> AnchorNodeOut:
    return update_anchor_node(db, admin, anchor_id, data)
