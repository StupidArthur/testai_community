"""external_api HTTP 路由：/api/v1/external/*，认证 X-API-Key。"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.platform.database import get_db
from app.external_api.service import verify_api_key, process_llm_task_bg, resolve_for_external, default_skill_ref
from app.external_api.models import LLMTask, TaskStatus, ServiceAccount
from app.skill_hub.service import get_skill_by_name, resolve_skill_ref
from app.skill_hub.skill_ref import SkillRef, ResolveMode

router = APIRouter(prefix="/api/v1/external", tags=["external_api"])


class ExecuteRequest(BaseModel):
    user_input: str
    skill_ref: SkillRef | None = None


def _build_skill_ref_from_query(
    skill_name: str,
    version_id: str | None,
    branch_id: int | None,
    branch_type: str | None,
    owner_user_id: int | None,
    resolve_mode: str | None,
) -> SkillRef | None:
    """Query 参数构造 SkillRef；全空则返回 None（走默认 master HEAD）。"""
    if version_id:
        return SkillRef(resolve_mode=ResolveMode.pinned, version_id=version_id, skill_name=skill_name)
    if branch_id is not None:
        return SkillRef(
            resolve_mode=ResolveMode.branch_head,
            skill_name=skill_name,
            branch_id=branch_id,
        )
    if branch_type or owner_user_id is not None or resolve_mode == "branch_head":
        return SkillRef(
            resolve_mode=ResolveMode.branch_head,
            skill_name=skill_name,
            branch_type=branch_type or "master",
            owner_user_id=owner_user_id,
        )
    return None


@router.get("/skills/{skill_name}")
def get_external_skill(
    skill_name: str,
    version_id: str | None = Query(default=None),
    branch_id: int | None = Query(default=None),
    branch_type: str | None = Query(default=None),
    owner_user_id: int | None = Query(default=None),
    resolve_mode: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _sa: ServiceAccount = Depends(verify_api_key),
):
    skill = get_skill_by_name(db, skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill不存在或未发布")

    ref = _build_skill_ref_from_query(
        skill_name, version_id, branch_id, branch_type, owner_user_id, resolve_mode
    )
    if ref is None:
        ref = default_skill_ref(skill_name)

    try:
        resolved = resolve_skill_ref(db, ref)
    except HTTPException as exc:
        if (
            exc.status_code == 404
            and ref.resolve_mode == ResolveMode.branch_head
            and (ref.branch_type == "master" or ref.branch_type is None)
            and ref.branch_id is None
        ):
            ref = SkillRef(
                resolve_mode=ResolveMode.branch_head,
                skill_name=skill_name,
                branch_type="standard",
            )
            resolved = resolve_skill_ref(db, ref)
        else:
            raise
    payload = resolved.payload
    icio = _to_icio(payload)
    fields = resolved.fields

    return {
        "name": skill.name,
        "version": resolved.version_num,
        "revision": resolved.revision,
        "version_id": resolved.version_id,
        "version_locator": resolved.version_locator,
        "payload": payload,
        "icio_format": icio,
        "fields": fields,
    }


@router.post("/skills/{skill_name}/execute-async", status_code=202)
def execute_skill_async(
    skill_name: str,
    data: ExecuteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _sa: ServiceAccount = Depends(verify_api_key),
):
    skill = get_skill_by_name(db, skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill不存在或未发布")

    ref = data.skill_ref or default_skill_ref(skill_name)
    if ref.skill_name is None:
        ref = ref.model_copy(update={"skill_name": skill_name})

    try:
        _, resolved_vid, ref_json = resolve_for_external(db, skill_name, ref)
    except HTTPException:
        raise

    task = LLMTask(
        skill_name=skill_name,
        skill_ref_json=ref_json,
        resolved_version_id=resolved_vid,
        status=TaskStatus.Pending,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    background_tasks.add_task(
        process_llm_task_bg,
        task.id,
        skill_name,
        data.user_input,
        ref_json,
    )

    return {
        "task_id": task.id,
        "status": task.status.value,
        "resolved_version_id": task.resolved_version_id,
    }


@router.get("/tasks/{task_id}")
def get_task_result(
    task_id: str,
    db: Session = Depends(get_db),
    _sa: ServiceAccount = Depends(verify_api_key),
):
    task = db.query(LLMTask).filter(LLMTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task不存在")

    return {
        "task_id": task.id,
        "status": task.status.value,
        "result": task.result,
        "error_message": task.error_message,
        "resolved_version_id": task.resolved_version_id,
        "skill_ref_json": task.skill_ref_json,
    }


def _to_icio(langgpt_payload: str) -> dict:
    result = {"instruction": "", "context": "", "input": "", "output": ""}
    current_section = None
    section_map = {
        "# Role": "context",
        "## Profile": "context",
        "## Background": "context",
        "## Goals": "instruction",
        "## Constraints": "instruction",
        "## Core Skills": "instruction",
        "## Workflows": "instruction",
        "## Output Format": "output",
        "## Initialization": "output",
    }
    for line in langgpt_payload.split("\n"):
        stripped = line.strip()
        for marker, key in section_map.items():
            if stripped.startswith(marker):
                current_section = key
                break
        if current_section and stripped and not any(stripped.startswith(m) for m in section_map):
            result[current_section] += stripped + "\n"
    return {k: v.strip() for k, v in result.items()}
