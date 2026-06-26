"""全站默认唯一知识库：启动时确保存在，业务 API 统一指向该库。"""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.platform.config import KNOWLEDGE_BASE_DATA_DIR

from .config import DEFAULT_KB_DESCRIPTION, DEFAULT_KB_NAME, RAW_SUBDIR
from .models import KnowledgeBase


def _kb_raw_dir(kb_id: str) -> Path:
    return KNOWLEDGE_BASE_DATA_DIR / kb_id / RAW_SUBDIR


def _pick_owner_user_id(db: Session) -> int:
    """选取知识库归属用户：优先 Admin，否则任意首个用户。"""
    admin = db.query(User).filter(User.role == UserRole.Admin).order_by(User.id.asc()).first()
    if admin:
        return admin.id
    any_user = db.query(User).order_by(User.id.asc()).first()
    if any_user is None:
        raise RuntimeError("无法创建默认知识库：系统中尚无用户，请先完成 auth 初始化")
    return any_user.id


def get_or_create_default_kb(db: Session) -> KnowledgeBase:
    """
    返回全站唯一知识库。
    若已有知识库则复用最早创建的；否则自动创建 DEFAULT_KB_NAME。
    """
    existing = db.query(KnowledgeBase).order_by(KnowledgeBase.created_at.asc()).first()
    if existing:
        return existing

    kb_id = uuid.uuid4().hex
    kb = KnowledgeBase(
        id=kb_id,
        name=DEFAULT_KB_NAME,
        description=DEFAULT_KB_DESCRIPTION,
        user_id=_pick_owner_user_id(db),
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    _kb_raw_dir(kb_id).mkdir(parents=True, exist_ok=True)
    return kb


def ensure_default_knowledge_base(engine: Engine) -> None:
    """启动时确保默认知识库存在。"""
    with Session(engine) as db:
        get_or_create_default_kb(db)
