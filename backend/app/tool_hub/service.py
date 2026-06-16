"""
tool_hub 业务逻辑：权限、版本、文件存储、Markdown 合并。
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.platform.config import TOOL_HUB_ARTIFACT_DIR

from . import ALLOWED_CLIENT_EXTENSIONS, DEFAULT_TOOL_TYPE, MAX_ARTIFACT_BYTES
from .models import Tool, ToolVersion
from .schemas import (
    ToolCardOut,
    ToolCreateFormMeta,
    ToolDetailOut,
    ToolKind,
    ToolUpdateRequest,
    ToolVersionCreateMeta,
    ToolVersionOut,
)

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def _username(db: Session, user_id: int) -> str:
    u = db.query(User).filter(User.id == user_id).first()
    return u.username if u else str(user_id)


def assert_slug_valid(slug: str) -> str:
    slug = (slug or "").strip().lower()
    if not _SLUG_RE.match(slug):
        raise HTTPException(
            status_code=400,
            detail="工具标识须小写字母开头，仅含 a-z、0-9、_",
        )
    return slug


def can_edit_tool(user: User, tool: Tool) -> bool:
    return user.role == UserRole.Admin or tool.owner_user_id == user.id


def can_delete_tool(user: User, tool: Tool) -> bool:
    return user.role == UserRole.Admin


def _latest_version_row(tool: Tool) -> ToolVersion | None:
    if not tool.versions:
        return None
    return max(tool.versions, key=lambda v: (v.created_at, v.version_label))


def _version_to_out(db: Session, row: ToolVersion) -> ToolVersionOut:
    return ToolVersionOut(
        id=row.id,
        version_label=row.version_label,
        manual_md=row.manual_md,
        changelog_md=row.changelog_md,
        artifact_filename=row.artifact_filename,
        created_by_user_id=row.created_by_user_id,
        creator_username=_username(db, row.created_by_user_id),
        created_at=row.created_at,
    )


def _tool_to_card(db: Session, tool: Tool) -> ToolCardOut:
    latest = _latest_version_row(tool)
    return ToolCardOut(
        id=tool.id,
        slug=tool.slug,
        display_name=tool.display_name,
        tool_kind=tool.tool_kind,  # type: ignore[arg-type]
        tool_type=tool.tool_type,
        link_url=tool.link_url,
        owner_user_id=tool.owner_user_id,
        owner_username=_username(db, tool.owner_user_id),
        enabled=tool.enabled,
        latest_version=latest.version_label if latest else None,
        has_artifact=bool(latest and latest.artifact_stored_name),
        created_at=tool.created_at,
        updated_at=tool.updated_at,
    )


def build_combined_markdown(tool: Tool) -> str:
    """说明书 + 各版本 changelog（新版在前）。"""
    versions = sorted(tool.versions, key=lambda v: v.created_at, reverse=True)
    if not versions:
        return "_暂无文档_"

    latest_manual = ""
    for v in versions:
        if v.manual_md.strip():
            latest_manual = v.manual_md.strip()
            break

    parts: list[str] = []
    if latest_manual:
        parts.append("## 使用说明\n\n" + latest_manual)

    changelog_blocks: list[str] = []
    for v in versions:
        if v.changelog_md.strip():
            changelog_blocks.append(
                f"### {v.version_label} ({v.created_at.strftime('%Y-%m-%d')})\n\n{v.changelog_md.strip()}"
            )
    if changelog_blocks:
        parts.append("## 版本更新记录\n\n" + "\n\n".join(changelog_blocks))

    return "\n\n---\n\n".join(parts) if parts else "_暂无文档_"


def list_tools(
    db: Session,
    user: User,
    *,
    tool_kind: ToolKind | None = None,
    tool_type: str | None = None,
) -> list[ToolCardOut]:
    q = db.query(Tool)
    if tool_kind:
        q = q.filter(Tool.tool_kind == tool_kind)
    if tool_type:
        q = q.filter(Tool.tool_type == tool_type)

    rows = q.order_by(Tool.updated_at.desc()).all()
    visible: list[Tool] = []
    for row in rows:
        if row.enabled or can_edit_tool(user, row):
            visible.append(row)
    return [_tool_to_card(db, t) for t in visible]


def get_tool_detail(db: Session, user: User, tool_id: str) -> ToolDetailOut:
    tool = db.query(Tool).filter(Tool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")
    if not tool.enabled and not can_edit_tool(user, tool):
        raise HTTPException(status_code=404, detail="工具不存在或已下架")

    latest = _latest_version_row(tool)
    return ToolDetailOut(
        id=tool.id,
        slug=tool.slug,
        display_name=tool.display_name,
        tool_kind=tool.tool_kind,  # type: ignore[arg-type]
        tool_type=tool.tool_type,
        link_url=tool.link_url,
        owner_user_id=tool.owner_user_id,
        owner_username=_username(db, tool.owner_user_id),
        enabled=tool.enabled,
        latest_version=latest.version_label if latest else None,
        has_artifact=bool(latest and latest.artifact_stored_name),
        combined_markdown=build_combined_markdown(tool),
        versions=[_version_to_out(db, v) for v in sorted(tool.versions, key=lambda x: x.created_at, reverse=True)],
        created_at=tool.created_at,
        updated_at=tool.updated_at,
        can_edit=can_edit_tool(user, tool),
        can_delete=can_delete_tool(user, tool),
    )


def _save_artifact(file: UploadFile, tool_id: str) -> tuple[str, str]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_CLIENT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型，允许：{', '.join(sorted(ALLOWED_CLIENT_EXTENSIONS))}",
        )

    stored = f"{tool_id}_{uuid.uuid4().hex}{suffix}"
    dest = TOOL_HUB_ARTIFACT_DIR / stored
    dest.parent.mkdir(parents=True, exist_ok=True)

    size = 0
    with dest.open("wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_ARTIFACT_BYTES:
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="工具文件过大")
            out.write(chunk)

    return file.filename, stored


def create_tool(
    db: Session,
    user: User,
    meta: ToolCreateFormMeta,
    artifact: UploadFile | None,
) -> ToolDetailOut:
    slug = assert_slug_valid(meta.slug)
    if db.query(Tool).filter(Tool.slug == slug).first():
        raise HTTPException(status_code=400, detail="工具标识已存在")

    if meta.tool_kind == "platform" and not (meta.link_url or "").strip():
        raise HTTPException(status_code=400, detail="平台集成工具须填写跳转链接")
    if meta.tool_kind == "client" and artifact is None:
        raise HTTPException(status_code=400, detail="客户端工具须上传可执行文件")

    tool = Tool(
        slug=slug,
        display_name=meta.display_name.strip(),
        tool_kind=meta.tool_kind,
        tool_type=(meta.tool_type or DEFAULT_TOOL_TYPE).strip() or DEFAULT_TOOL_TYPE,
        link_url=(meta.link_url or "").strip() or None,
        owner_user_id=user.id,
        enabled=True,
    )
    db.add(tool)
    db.flush()

    artifact_filename = None
    artifact_stored = None
    if artifact is not None:
        artifact_filename, artifact_stored = _save_artifact(artifact, tool.id)

    version = ToolVersion(
        tool_id=tool.id,
        version_label=meta.version_label.strip(),
        manual_md=meta.manual_md.strip(),
        changelog_md="",
        artifact_filename=artifact_filename,
        artifact_stored_name=artifact_stored,
        created_by_user_id=user.id,
    )
    db.add(version)
    db.commit()
    db.refresh(tool)
    return get_tool_detail(db, user, tool.id)


def add_tool_version(
    db: Session,
    user: User,
    tool_id: str,
    meta: ToolVersionCreateMeta,
    artifact: UploadFile | None,
) -> ToolDetailOut:
    tool = db.query(Tool).filter(Tool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")
    if not can_edit_tool(user, tool):
        raise HTTPException(status_code=403, detail="无权更新此工具")

    if tool.tool_kind == "client" and artifact is None:
        raise HTTPException(status_code=400, detail="客户端工具新版本须上传文件")

    artifact_filename = None
    artifact_stored = None
    if artifact is not None:
        artifact_filename, artifact_stored = _save_artifact(artifact, tool.id)

    manual_md = meta.manual_md.strip() if meta.manual_md else ""
    if not manual_md:
        prev = _latest_version_row(tool)
        manual_md = prev.manual_md if prev else ""

    version = ToolVersion(
        tool_id=tool.id,
        version_label=meta.version_label.strip(),
        manual_md=manual_md,
        changelog_md=meta.changelog_md.strip(),
        artifact_filename=artifact_filename,
        artifact_stored_name=artifact_stored,
        created_by_user_id=user.id,
    )
    db.add(version)
    tool.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(tool)
    return get_tool_detail(db, user, tool.id)


def update_tool(
    db: Session,
    user: User,
    tool_id: str,
    data: ToolUpdateRequest,
) -> ToolDetailOut:
    tool = db.query(Tool).filter(Tool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")
    if not can_edit_tool(user, tool):
        raise HTTPException(status_code=403, detail="无权编辑此工具")

    if data.display_name is not None:
        tool.display_name = data.display_name.strip()
    if data.link_url is not None:
        tool.link_url = data.link_url.strip() or None
    if data.tool_type is not None:
        tool.tool_type = data.tool_type.strip() or DEFAULT_TOOL_TYPE
    if data.enabled is not None:
        tool.enabled = data.enabled

    if tool.tool_kind == "platform" and not tool.link_url:
        raise HTTPException(status_code=400, detail="平台集成工具须保留跳转链接")

    tool.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(tool)
    return get_tool_detail(db, user, tool.id)


def delete_tool(db: Session, user: User, tool_id: str) -> None:
    tool = db.query(Tool).filter(Tool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")
    if not can_delete_tool(user, tool):
        raise HTTPException(status_code=403, detail="仅管理员可删除工具")

    for v in tool.versions:
        if v.artifact_stored_name:
            path = TOOL_HUB_ARTIFACT_DIR / v.artifact_stored_name
            path.unlink(missing_ok=True)

    db.delete(tool)
    db.commit()


def resolve_artifact_path(db: Session, user: User, tool_id: str) -> tuple[Path, str]:
    tool = db.query(Tool).filter(Tool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")
    if not tool.enabled and not can_edit_tool(user, tool):
        raise HTTPException(status_code=404, detail="工具不存在或已下架")
    if tool.tool_kind != "client":
        raise HTTPException(status_code=400, detail="仅客户端工具可下载")

    latest = _latest_version_row(tool)
    if not latest or not latest.artifact_stored_name:
        raise HTTPException(status_code=404, detail="暂无可下载文件")

    path = TOOL_HUB_ARTIFACT_DIR / latest.artifact_stored_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    filename = latest.artifact_filename or path.name
    return path, filename
