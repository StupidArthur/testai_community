"""
tool_hub HTTP 路由。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.service import get_current_user
from app.platform.database import get_db

from .schemas import ToolCardOut, ToolDetailOut, ToolKind, ToolUpdateRequest
from .service import (
    add_tool_version,
    create_tool,
    delete_tool,
    get_tool_detail,
    list_tools,
    resolve_artifact_path,
    update_tool,
)
from .schemas import ToolCreateFormMeta, ToolVersionCreateMeta

router = APIRouter(prefix="/api/tool-hub", tags=["tool-hub"])


@router.get("/tools", response_model=list[ToolCardOut])
def api_list_tools(
    tool_kind: ToolKind | None = None,
    tool_type: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ToolCardOut]:
    return list_tools(db, current_user, tool_kind=tool_kind, tool_type=tool_type)


@router.get("/tools/{tool_id}", response_model=ToolDetailOut)
def api_get_tool(
    tool_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ToolDetailOut:
    return get_tool_detail(db, current_user, tool_id)


@router.post("/tools", response_model=ToolDetailOut, status_code=201)
async def api_create_tool(
    slug: str = Form(...),
    display_name: str = Form(...),
    tool_kind: ToolKind = Form(...),
    tool_type: str = Form("default"),
    link_url: str | None = Form(None),
    version_label: str = Form("1.0.0"),
    manual_md: str = Form(...),
    artifact: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ToolDetailOut:
    meta = ToolCreateFormMeta(
        slug=slug,
        display_name=display_name,
        tool_kind=tool_kind,
        tool_type=tool_type,
        link_url=link_url,
        version_label=version_label,
        manual_md=manual_md,
    )
    return create_tool(db, current_user, meta, artifact)


@router.post("/tools/{tool_id}/versions", response_model=ToolDetailOut)
async def api_add_version(
    tool_id: str,
    version_label: str = Form(...),
    changelog_md: str = Form(...),
    manual_md: str | None = Form(None),
    artifact: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ToolDetailOut:
    meta = ToolVersionCreateMeta(
        version_label=version_label,
        changelog_md=changelog_md,
        manual_md=manual_md,
    )
    return add_tool_version(db, current_user, tool_id, meta, artifact)


@router.put("/tools/{tool_id}", response_model=ToolDetailOut)
def api_update_tool(
    tool_id: str,
    data: ToolUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ToolDetailOut:
    return update_tool(db, current_user, tool_id, data)


@router.delete("/tools/{tool_id}", status_code=204, response_class=Response)
def api_delete_tool(
    tool_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    delete_tool(db, current_user, tool_id)
    return Response(status_code=204)


@router.get("/tools/{tool_id}/download")
def api_download_tool(
    tool_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    path, filename = resolve_artifact_path(db, current_user, tool_id)
    return FileResponse(path, filename=filename, media_type="application/octet-stream")
