"""平台更新日志 HTTP 路由：/api/changelog。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.platform.database import get_db
from app.auth.service import get_current_user, RequireRole
from app.auth.models import User

from .models import ChangelogEntry
from .schemas import ChangelogCreate, ChangelogUpdate, ChangelogView

router = APIRouter(prefix="/api/changelog", tags=["platform-changelog"])


@router.get("", response_model=list[ChangelogView])
def list_changelog(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    rows = (
        db.query(ChangelogEntry)
        .order_by(ChangelogEntry.created_at.desc())
        .limit(limit)
        .all()
    )
    return [ChangelogView.from_orm_with_publisher(r) for r in rows]


@router.get("/{entry_id}", response_model=ChangelogView)
def get_changelog(
    entry_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    row = db.query(ChangelogEntry).filter(ChangelogEntry.id == entry_id).first()
    if not row:
        raise HTTPException(404, "更新记录不存在")
    return ChangelogView.from_orm_with_publisher(row)


@router.post("", response_model=ChangelogView, status_code=201)
def create_changelog(
    body: ChangelogCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(RequireRole(["Admin"])),
):
    existing = db.query(ChangelogEntry).filter(ChangelogEntry.version == body.version).first()
    if existing:
        raise HTTPException(409, f"版本号 {body.version} 已存在")
    row = ChangelogEntry(
        version=body.version,
        title=body.title,
        content=body.content,
        published_by=admin.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ChangelogView.from_orm_with_publisher(row)


@router.put("/{entry_id}", response_model=ChangelogView)
def update_changelog(
    entry_id: int,
    body: ChangelogUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(RequireRole(["Admin"])),
):
    row = db.query(ChangelogEntry).filter(ChangelogEntry.id == entry_id).first()
    if not row:
        raise HTTPException(404, "更新记录不存在")
    if body.version is not None and body.version != row.version:
        conflict = db.query(ChangelogEntry).filter(ChangelogEntry.version == body.version).first()
        if conflict:
            raise HTTPException(409, f"版本号 {body.version} 已存在")
        row.version = body.version
    if body.title is not None:
        row.title = body.title
    if body.content is not None:
        row.content = body.content
    db.commit()
    db.refresh(row)
    return ChangelogView.from_orm_with_publisher(row)


@router.delete("/{entry_id}", status_code=204)
def delete_changelog(
    entry_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(RequireRole(["Admin"])),
):
    row = db.query(ChangelogEntry).filter(ChangelogEntry.id == entry_id).first()
    if not row:
        raise HTTPException(404, "更新记录不存在")
    db.delete(row)
    db.commit()
