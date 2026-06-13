"""external_api 服务：API Key 校验与异步 LLM 任务。"""

from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session

from app.platform.database import get_db, SessionLocal
from app.external_api.models import (
    LLMTask,
    TaskStatus,
    ServiceAccount,
    api_key_fingerprint,
    verify_api_key_plain,
)
from app.skill_hub.service import get_skill_by_name, get_master_latest_version, version_to_langgpt_payload
from app.ai_service.client import chat


def verify_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> ServiceAccount:
    """校验请求头 X-API-Key，返回对应服务账户。"""
    fingerprint = api_key_fingerprint(x_api_key)
    account = db.query(ServiceAccount).filter(ServiceAccount.token_fingerprint == fingerprint).first()
    if account and verify_api_key_plain(x_api_key, account.token_hash):
        return account
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的API密钥",
    )


async def process_llm_task_bg(task_id: str, skill_name: str, user_input: str) -> None:
    """后台执行：读取 master Skill → 调 MiniMax → 更新 llm_tasks。"""
    db = SessionLocal()
    try:
        task = db.query(LLMTask).filter(LLMTask.id == task_id).first()
        if not task:
            return

        task.status = TaskStatus.Processing
        db.commit()

        skill = get_skill_by_name(db, skill_name)
        if not skill:
            task.status = TaskStatus.Failed
            task.error_message = f"Skill '{skill_name}' 不存在或未发布"
            db.commit()
            return

        latest_version = get_master_latest_version(db, skill)
        system_prompt = version_to_langgpt_payload(latest_version) if latest_version else ""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        result = await chat(messages, temperature=0.7)

        task.status = TaskStatus.Completed
        task.result = result
        db.commit()
    except Exception as e:
        db.rollback()
        task = db.query(LLMTask).filter(LLMTask.id == task_id).first()
        if task:
            task.status = TaskStatus.Failed
            task.error_message = str(e)
            db.commit()
    finally:
        db.close()
