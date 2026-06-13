"""external_api HTTP 路由：/api/v1/external/*，认证 X-API-Key。"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.platform.database import get_db
from app.external_api.service import verify_api_key, process_llm_task_bg
from app.external_api.models import LLMTask, TaskStatus, ServiceAccount
from app.skill_hub.service import get_skill_by_name, get_master_latest_version, version_to_langgpt_payload

router = APIRouter(prefix="/api/v1/external", tags=["external_api"])


class ExecuteRequest(BaseModel):
    user_input: str


@router.get("/skills/{skill_name}")
def get_external_skill(
    skill_name: str,
    db: Session = Depends(get_db),
    _sa: ServiceAccount = Depends(verify_api_key),
):
    skill = get_skill_by_name(db, skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill不存在或未发布")

    latest_version = get_master_latest_version(db, skill)
    payload = ""
    icio = {}
    if latest_version:
        payload = version_to_langgpt_payload(latest_version)
        icio = _to_icio(payload)

    return {
        "name": skill.name,
        "version": latest_version.version_num if latest_version else 0,
        "payload": payload,
        "icio_format": icio,
        "fields": {
            "role": latest_version.role if latest_version else "",
            "profile": latest_version.profile if latest_version else "",
            "background": latest_version.background if latest_version else "",
            "goals": latest_version.goals if latest_version else "",
            "constraints": latest_version.constraints if latest_version else "",
            "core_skills": latest_version.core_skills if latest_version else "",
            "workflows": latest_version.workflows if latest_version else "",
            "output_format": latest_version.output_format if latest_version else "",
            "initialization": latest_version.initialization if latest_version else "",
        },
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

    task = LLMTask(
        skill_name=skill_name,
        status=TaskStatus.Pending,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    background_tasks.add_task(process_llm_task_bg, task.id, skill_name, data.user_input)

    return {"task_id": task.id, "status": task.status.value}


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
