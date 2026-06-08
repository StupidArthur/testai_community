from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.service import get_current_user
from app.auth.models import User
from app.skill_hub.minimax_client import run_prompt, lint_prompt, semantic_diff

router = APIRouter(prefix="/api/llm", tags=["llm"])


class RunRequest(BaseModel):
    prompt: str
    mock_input: str = ""


class LintRequest(BaseModel):
    langgpt_payload: str


class DiffRequest(BaseModel):
    old_payload: str
    new_payload: str


@router.post("/run")
async def llm_run(data: RunRequest, current_user: User = Depends(get_current_user)):
    result = await run_prompt(data.prompt, data.mock_input)
    return {"result": result}


@router.post("/lint")
async def llm_lint(data: LintRequest, current_user: User = Depends(get_current_user)):
    result = await lint_prompt(data.langgpt_payload)
    return {"result": result}


@router.post("/diff")
async def llm_diff(data: DiffRequest, current_user: User = Depends(get_current_user)):
    result = await semantic_diff(data.old_payload, data.new_payload)
    return {"result": result}