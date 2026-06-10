from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from passlib.context import CryptContext
import hashlib

from app.core.database import Base, get_db, SessionLocal
from app.skill_hub.integration_models import LLMTask, TaskStatus
from app.skill_hub.service import get_skill_by_name, version_to_langgpt_payload
from app.skill_hub.minimax_client import call_minimax, LLMError

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _api_key_fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class ServiceAccount(Base):
    __tablename__ = "service_accounts"

    id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String, nullable=False)
    token_fingerprint = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


def verify_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> ServiceAccount:
    fingerprint = _api_key_fingerprint(x_api_key)
    account = db.query(ServiceAccount).filter(ServiceAccount.token_fingerprint == fingerprint).first()
    if account and pwd_context.verify(x_api_key, account.token_hash):
        return account
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的API密钥",
    )


async def process_llm_task_bg(task_id: str, skill_name: str, user_input: str):
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

        latest_version = skill.versions[0] if skill.versions else None
        system_prompt = version_to_langgpt_payload(latest_version) if latest_version else ""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        result = await call_minimax(messages, temperature=0.7)

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