"""external_api 服务：API Key 校验与异步 LLM 任务。"""

from __future__ import annotations

import json

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
from app.skill_hub.service import (
    get_skill_by_name,
    version_to_langgpt_payload,
    resolve_skill_ref,
    resolve_skill_publish_version,
)
from app.skill_hub.skill_ref import SkillRef, ResolveMode
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


def default_skill_ref(skill_name: str) -> SkillRef:
    """与旧行为一致：master HEAD。"""
    return SkillRef(
        resolve_mode=ResolveMode.branch_head,
        skill_name=skill_name,
        branch_type="master",
    )


def resolve_for_external(db: Session, skill_name: str, skill_ref: SkillRef | None) -> tuple[str, str, str]:
    """
    解析 Skill 引用，返回 (system_prompt, resolved_version_id, skill_ref_json)。

    默认（master HEAD）走 resolve_skill_publish_version；master 无版本时回退 standard。
    """
    ref = skill_ref or default_skill_ref(skill_name)
    if ref.skill_name is None:
        ref = ref.model_copy(update={"skill_name": skill_name})

    if (
        ref.resolve_mode == ResolveMode.branch_head
        and ref.branch_id is None
        and ref.branch_type in (None, "master")
        and ref.owner_user_id is None
        and ref.version_id is None
    ):
        resolved = resolve_skill_publish_version(db, skill_name)
        publish_ref = default_skill_ref(skill_name)
        if resolved.branch_type == "standard":
            publish_ref = SkillRef(
                resolve_mode=ResolveMode.branch_head,
                skill_name=skill_name,
                branch_type="standard",
            )
        return resolved.payload, resolved.version_id, publish_ref.model_dump_json()

    try:
        resolved = resolve_skill_ref(db, ref)
    except HTTPException as exc:
        if (
            exc.status_code == 404
            and ref.resolve_mode == ResolveMode.branch_head
            and (ref.branch_type == "master" or ref.branch_type is None)
            and ref.branch_id is None
        ):
            fallback = SkillRef(
                resolve_mode=ResolveMode.branch_head,
                skill_name=skill_name,
                branch_type="standard",
            )
            resolved = resolve_skill_ref(db, fallback)
            ref = fallback
        else:
            raise
    return resolved.payload, resolved.version_id, ref.model_dump_json()


async def process_llm_task_bg(
    task_id: str,
    skill_name: str,
    user_input: str,
    skill_ref_json: str | None = None,
) -> None:
    """后台执行：解析 SkillRef → 调 LLM → 更新 llm_tasks。"""
    db = SessionLocal()
    try:
        task = db.query(LLMTask).filter(LLMTask.id == task_id).first()
        if not task:
            return

        task.status = TaskStatus.Processing
        db.commit()

        ref: SkillRef | None = None
        if skill_ref_json:
            ref = SkillRef.model_validate_json(skill_ref_json)

        try:
            system_prompt, resolved_vid, ref_json = resolve_for_external(db, skill_name, ref)
        except HTTPException as exc:
            task.status = TaskStatus.Failed
            task.error_message = str(exc.detail)
            db.commit()
            return

        task.resolved_version_id = resolved_vid
        task.skill_ref_json = ref_json
        db.commit()

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
